"""Main window class for Keong-MAS application."""

import os
import re
import sys
import webbrowser
import subprocess
from PySide6.QtCore import Qt, QThread, QTimer, QSize, Signal
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QMainWindow, QProgressBar, QMessageBox, QFileDialog, QColorDialog, QInputDialog
)
import qtawesome as qta

from APP.ui import create_main_ui
from APP.widgets import ScalableImageLabel, FileTableWidget, ImagePreviewWidget
from APP.workers import RemBgWorker
from APP.helpers.database import DatabaseManager
from APP.helpers.config_manager import (
    get_auto_crop_enabled, set_auto_crop_enabled,
    get_solid_bg_enabled, set_solid_bg_enabled,
    get_solid_bg_color, set_solid_bg_color,
    get_unified_margin, set_unified_margin,
    get_save_mask_enabled, set_save_mask_enabled,
    get_jpg_export_enabled, set_jpg_export_enabled,
    get_jpg_quality, set_jpg_quality,
    get_output_location, set_output_location,
    get_levels_black_point, set_levels_black_point,
    get_levels_mid_point, set_levels_mid_point,
    get_levels_white_point, set_levels_white_point,
    get_selected_model, set_selected_model
)

from APP.helpers import model_manager
from PySide6.QtCore import QObject, Slot
from PySide6.QtCore import Signal as QtSignal
import threading


class MaskWorker(QObject):
    """Worker to generate mask from a raw original image using rembg in background."""
    finished = QtSignal(str, str)  # mask_path, ori_path
    error = QtSignal(str)
    progress = QtSignal(int, str)

    def __init__(self, image_path, output_dir, model_name=None):
        super().__init__()
        self.image_path = image_path
        self.output_dir = output_dir
        self.model_name = model_name
        self.abort = False

    @Slot()
    def run(self):
        try:
            # Ensure output dir exists
            os.makedirs(self.output_dir, exist_ok=True)

            # Convert input to PNG and save original temp
            from PIL import Image
            input_img = Image.open(self.image_path)
            base = os.path.splitext(os.path.basename(self.image_path))[0]
            ori_temp = os.path.join(self.output_dir, f'{base}_ori_temp.png')
            input_img.save(ori_temp)

            # Prepare model (may download)
            try:
                self.progress.emit(5, "Menyiapkan model...")
                prepared = model_manager.prepare_model(model_name=self.model_name)
            except Exception:
                prepared = None

            if self.abort:
                self.progress.emit(0, "Dibatalkan")
                return

            # Create rembg session and remove mask
            import rembg
            self.progress.emit(20, "Memproses: Menghapus latar belakang (mask)...")

            # Prefer direct session if model prepared
            session = None
            try:
                if self.model_name:
                    session = rembg.new_session(self.model_name)
                elif prepared:
                    session = rembg.new_session(prepared)
            except Exception:
                try:
                    session = rembg.new_session()
                except Exception:
                    session = None

            mask = rembg.remove(input_img, only_mask=True, session=session)
            if self.abort:
                self.progress.emit(0, "Dibatalkan")
                return

            mask_path = os.path.join(self.output_dir, f'{base}_mask_temp.png')
            mask.save(mask_path)

            self.progress.emit(100, "Selesai")
            self.finished.emit(mask_path, ori_temp)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""
    # Signal to receive download progress safely in the GUI thread
    downloadProgress = Signal(str, float)
    
    WINDOW_TITLE = "Keong MAS (Kecilin Ongkos, Masking Auto Selesai)"
    DEFAULT_SIZE = (800, 550)
    WHATSAPP_GROUP_LINK = "https://chat.whatsapp.com/CMQvDxpCfP647kBBA6dRn3"
    
    def __init__(self):
        super().__init__()
        self._init_window()
        self._init_ui()
        self._init_connections()
        self._load_settings()
        
        self.worker = None
        self.thread = None
        self.last_processed_files = []
        
        # Download state for model downloads shown on progress bar
        self._download_in_progress = False
        self._saved_progress_value = None
        self._saved_progress_format = None
        self._last_completed_download_model = None

        # Connect download progress signal to UI slot
        try:
            self.downloadProgress.connect(self._on_download_progress_ui)
        except Exception:
            pass

        # Database for session tracking
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "sessions.db"
        )
        self.db = DatabaseManager(db_path)
        self.current_session_id = None
        self.file_id_map = {}  # row_index -> file_id
        
    def _init_window(self):
        """Initialize window properties."""
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)
        self.setAcceptDrops(True)
        
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "APP", "res", "Keong-MAS.ico"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Run an initial cleanup of old temporary files that may have accumulated
        try:
            # Remove very old temp cache files (older than 1 day)
            self._cleanup_all_old_temp_files(age_seconds=86400)
        except Exception:
            pass
    
    def _init_ui(self):
        """Initialize UI components."""
        central_widget, ui_dict = create_main_ui(self)
        self.setCentralWidget(central_widget)
        
        self.ui = type('UI', (), ui_dict)()
        
        self.drop_area = self.ui.drop_area_frame
        self.split_view = self.ui.split_view
        self.file_table = self.ui.file_table
        self.image_preview = self.ui.image_preview
        
        self.dnd_label_1 = self.ui.dnd_label_1
        self.dnd_label_2 = self.ui.dnd_label_2
        self.dnd_label_3 = self.ui.dnd_label_3
        
        if self.dnd_label_1 and self.dnd_label_2 and self.dnd_label_3:
            self.original_label1_text = self.dnd_label_1.text()
            self.original_label2_text = self.dnd_label_2.text()
            self.original_label3_text = self.dnd_label_3.text()
        
        # Make DND area clickable
        self.drop_area.mousePressEvent = self._on_dnd_area_clicked
        
        # Connect table and preview signals
        self.file_table.file_selected.connect(self._on_file_selected)
        self.file_table.file_double_clicked.connect(self._on_file_double_clicked)
        
        # Connect preview double-click signal
        self.image_preview.file_double_clicked.connect(self._on_file_double_clicked)
        
        # Disable context menu for preview
        self.image_preview.view.setContextMenuPolicy(Qt.NoContextMenu)
        
        self._setup_preview_image()
        self._setup_progress_bar()
        self._setup_button_icons()
    
    def _setup_preview_image(self):
        """Setup the image preview widget."""
        self.preview_image = ScalableImageLabel(self.drop_area)
        margins = 20
        self.preview_image.setGeometry(
            margins,
            margins + 40,
            self.drop_area.width() - (margins * 2),
            self.drop_area.height() - (margins * 2) - 80
        )
        self.preview_image.hide()
    
    def _setup_progress_bar(self):
        """Setup the progress bar."""
        self.progress_bar = QProgressBar(self.centralWidget())
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v / %m")
        # Apply consistent style that matches the dark theme so downloads and processing look the same
        try:
            # Use native (vanilla) progressbar styling: remove custom height and stylesheet
            # Do NOT call setFixedHeight or setStyleSheet here so the system default is used
            pass
        except Exception:
            pass
        self.progress_bar.hide()
        
        parent_layout = self.drop_area.parentWidget().layout()
        drop_area_index = parent_layout.indexOf(self.drop_area)
        if drop_area_index >= 0:
            parent_layout.insertWidget(drop_area_index, self.progress_bar)
        else:
            parent_layout.addWidget(self.progress_bar)
        # Ensure the progress bar is on top when shown
        self.progress_bar.raise_()
    
    def _setup_button_icons(self):
        """Setup icons for all buttons."""
        icon_size = QSize(16, 16)
        
        if hasattr(self.ui, 'openFolder') and self.ui.openFolder:
            self.ui.openFolder.setIcon(qta.icon('fa5s.folder-open'))
            self.ui.openFolder.setIconSize(icon_size)
        
        if hasattr(self.ui, 'openFiles') and self.ui.openFiles:
            self.ui.openFiles.setIcon(qta.icon('fa5s.images'))
            self.ui.openFiles.setIconSize(icon_size)
        
        if hasattr(self.ui, 'outputLocationButton') and self.ui.outputLocationButton:
            self.ui.outputLocationButton.setIcon(qta.icon('fa5s.folder'))
            self.ui.outputLocationButton.setIconSize(icon_size)
        
        if hasattr(self.ui, 'stopButton') and self.ui.stopButton:
            self.ui.stopButton.setIcon(qta.icon('fa5s.stop', color='red'))
            self.ui.stopButton.setIconSize(QSize(18, 18))
            self.ui.stopButton.setEnabled(False)
        
        if hasattr(self.ui, 'repeatButton') and self.ui.repeatButton:
            self.ui.repeatButton.setIcon(qta.icon('fa5s.redo'))
            self.ui.repeatButton.setIconSize(QSize(18, 18))
            self.ui.repeatButton.setEnabled(False)
        
        if hasattr(self.ui, 'resetButton') and self.ui.resetButton:
            self.ui.resetButton.setIcon(qta.icon('fa5s.times-circle'))
            self.ui.resetButton.setIconSize(QSize(18, 18))
        
        if hasattr(self.ui, 'colorPickerButton') and self.ui.colorPickerButton:
            color_hex = get_solid_bg_color()
            self._update_color_button(color_hex)
        
        if hasattr(self.ui, 'whatsappButton') and self.ui.whatsappButton:
            self.ui.whatsappButton.setIcon(qta.icon('fa5b.whatsapp', color='#25D366'))
            self.ui.whatsappButton.setIconSize(icon_size)
    
    def _init_connections(self):
        """Initialize signal-slot connections."""
        if hasattr(self.ui, 'openFolder') and self.ui.openFolder:
            self.ui.openFolder.clicked.connect(self._open_folder_dialog)
        
        if hasattr(self.ui, 'openFiles') and self.ui.openFiles:
            self.ui.openFiles.clicked.connect(self._open_files_dialog)
        
        if hasattr(self.ui, 'stopButton') and self.ui.stopButton:
            self.ui.stopButton.clicked.connect(self._on_stop_clicked)
        
        if hasattr(self.ui, 'repeatButton') and self.ui.repeatButton:
            self.ui.repeatButton.clicked.connect(self._on_repeat_clicked)
        
        if hasattr(self.ui, 'resetButton') and self.ui.resetButton:
            self.ui.resetButton.clicked.connect(self._on_reset_clicked)
        
        if hasattr(self.ui, 'checkBox') and self.ui.checkBox:
            self.ui.checkBox.stateChanged.connect(self._on_auto_crop_changed)
        
        if hasattr(self.ui, 'solidBgCheckBox') and self.ui.solidBgCheckBox:
            self.ui.solidBgCheckBox.stateChanged.connect(self._on_solid_bg_changed)
        
        if hasattr(self.ui, 'colorPickerButton') and self.ui.colorPickerButton:
            self.ui.colorPickerButton.clicked.connect(self._on_color_picker_clicked)
        
        if hasattr(self.ui, 'unifiedMarginSpinBox') and self.ui.unifiedMarginSpinBox:
            self.ui.unifiedMarginSpinBox.valueChanged.connect(self._on_unified_margin_changed)
        
        if hasattr(self.ui, 'saveMaskCheckBox') and self.ui.saveMaskCheckBox:
            self.ui.saveMaskCheckBox.stateChanged.connect(self._on_save_mask_changed)
        
        if hasattr(self.ui, 'jpgExportCheckBox') and self.ui.jpgExportCheckBox:
            self.ui.jpgExportCheckBox.stateChanged.connect(self._on_jpg_export_changed)
        
        if hasattr(self.ui, 'jpgQualitySpinBox') and self.ui.jpgQualitySpinBox:
            self.ui.jpgQualitySpinBox.valueChanged.connect(self._on_jpg_quality_changed)

        if hasattr(self.ui, 'modelComboBox') and self.ui.modelComboBox:
            self.ui.modelComboBox.currentTextChanged.connect(self._on_model_changed)
        
        # Multi-handle slider for levels
        if hasattr(self.ui, 'levelsMultiSlider') and self.ui.levelsMultiSlider:
            self.ui.levelsMultiSlider.valuesChanged.connect(self._on_levels_changed)

        if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton:
            # Use clicked to trigger mask creation or refresh; clicking always initiates mask generation
            try:
                self.ui.configureMaskButton.clicked.connect(self._on_configure_mask_clicked)
            except Exception:
                # Fallback: connect to toggled handler
                self.ui.configureMaskButton.toggled.connect(self._on_levels_enabled_changed)
        
        if hasattr(self.ui, 'outputLocationButton') and self.ui.outputLocationButton:
            self.ui.outputLocationButton.clicked.connect(self._on_output_location_clicked)
        
        if hasattr(self.ui, 'clearOutputButton') and self.ui.clearOutputButton:
            self.ui.clearOutputButton.clicked.connect(self._on_clear_output_clicked)
        
        if hasattr(self.ui, 'whatsappButton') and self.ui.whatsappButton:
            self.ui.whatsappButton.clicked.connect(self._open_whatsapp)
        
        if hasattr(self.ui, 'resetLevelsButton') and self.ui.resetLevelsButton:
            self.ui.resetLevelsButton.clicked.connect(self._on_reset_levels_clicked)

        # Always on top checkbox
        if hasattr(self.ui, 'alwaysOnTopCheckBox') and self.ui.alwaysOnTopCheckBox:
            try:
                self.ui.alwaysOnTopCheckBox.stateChanged.connect(self._on_always_on_top_changed)
                # ensure initial click toggles set_mid_manual and is wired
            except Exception:
                pass

    
    def _on_reset_levels_clicked(self):
        """Reset slider levels ke nilai recommended."""
        try:
            from APP.helpers.image_utils import get_levels_config
            rec_black, rec_mid, rec_white = get_levels_config(use_recommended=True)
        except Exception:
            rec_black, rec_mid, rec_white = (20, 128, 235)

        try:
            # Set values on the multi-slider if available
            try:
                if hasattr(self.ui, 'levelsMultiSlider') and self.ui.levelsMultiSlider:
                    self.ui.levelsMultiSlider.setValues(rec_black, rec_mid, rec_white, emit=False)
                    # Reset mid to auto mode when resetting levels
                    try:
                        self.ui.levelsMultiSlider.set_mid_manual(False)
                    except Exception:
                        pass
            except Exception:
                pass

            # Ensure values saved and labels updated
            try:
                set_levels_black_point(rec_black)
                set_levels_mid_point(rec_mid)
                set_levels_white_point(rec_white)
            except Exception:
                pass

            if hasattr(self.ui, 'blackPointValue'):
                self.ui.blackPointValue.setText(str(rec_black))
            if hasattr(self.ui, 'midPointValue'):
                self.ui.midPointValue.setText(str(rec_mid))
            if hasattr(self.ui, 'whitePointValue'):
                self.ui.whitePointValue.setText(str(rec_white))

            # Update mask preview jika aktif
            self._update_mask_preview_if_needed()
        except Exception as e:
            print(f"Error resetting levels: {e}")

    def _load_settings(self):
        """Load settings from config and apply to UI."""
        if hasattr(self.ui, 'checkBox') and self.ui.checkBox:
            self.ui.checkBox.setChecked(get_auto_crop_enabled())
        
        if hasattr(self.ui, 'solidBgCheckBox') and self.ui.solidBgCheckBox:
            self.ui.solidBgCheckBox.setChecked(get_solid_bg_enabled())
            self._update_solid_bg_controls()
        
        if hasattr(self.ui, 'unifiedMarginSpinBox') and self.ui.unifiedMarginSpinBox:
            self.ui.unifiedMarginSpinBox.setValue(get_unified_margin())
        
        if hasattr(self.ui, 'saveMaskCheckBox') and self.ui.saveMaskCheckBox:
            self.ui.saveMaskCheckBox.setChecked(get_save_mask_enabled())
        
        if hasattr(self.ui, 'jpgExportCheckBox') and self.ui.jpgExportCheckBox:
            self.ui.jpgExportCheckBox.setChecked(get_jpg_export_enabled())
        
        if hasattr(self.ui, 'jpgQualitySpinBox') and self.ui.jpgQualitySpinBox:
            self.ui.jpgQualitySpinBox.setValue(get_jpg_quality())
            self._update_jpg_quality_controls()

        # Populate model selection combobox
        if hasattr(self.ui, 'modelComboBox') and self.ui.modelComboBox:
            try:
                models = model_manager.get_available_models()
                
                # Disconnect signal before manipulating combobox
                try:
                    self.ui.modelComboBox.currentTextChanged.disconnect(self._on_model_changed)
                except Exception:
                    pass
                
                self.ui.modelComboBox.clear()
                self.ui.modelComboBox.addItems(models)
                selected = get_selected_model()
                
                if selected and selected in models:
                    self.ui.modelComboBox.setCurrentText(selected)
                elif selected:
                    # Try a case-insensitive match first
                    match = next((m for m in models if m.lower() == selected.lower()), None)
                    if match:
                        self.ui.modelComboBox.setCurrentText(match)
                    else:
                        # Add the previously selected model to the list so it persists in the UI even if it's not in the available list
                        self.ui.modelComboBox.addItem(selected)
                        self.ui.modelComboBox.setCurrentText(selected)
                elif models:
                    self.ui.modelComboBox.setCurrentIndex(0)

                # Reconnect the signal
                try:
                    self.ui.modelComboBox.currentTextChanged.connect(self._on_model_changed)
                except Exception:
                    pass

                # Prepare (download) the selected model in background if needed
                # Use the signal's emit method as callback so it is thread-safe and runs slot in GUI thread
                threading.Thread(
                    target=lambda: model_manager.prepare_model(model_name=self.ui.modelComboBox.currentText(), callback=self.downloadProgress.emit),
                    daemon=True
                ).start()
            except Exception as e:
                print(f"Error populating model list: {str(e)}")
        
        # Initialize multi-handle slider values from config
        try:
            b = get_levels_black_point()
            m = get_levels_mid_point()
            w = get_levels_white_point()
            if hasattr(self.ui, 'levelsMultiSlider') and self.ui.levelsMultiSlider:
                self.ui.levelsMultiSlider.setValues(b, m, w, emit=False)
            if hasattr(self.ui, 'blackPointValue'):
                self.ui.blackPointValue.setText(str(b))
            if hasattr(self.ui, 'midPointValue'):
                self.ui.midPointValue.setText(str(m))
            if hasattr(self.ui, 'whitePointValue'):
                self.ui.whitePointValue.setText(str(w))
        except Exception:
            pass
        
        if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton:
            # This button is GUI-only and should start unchecked
            self.ui.configureMaskButton.setChecked(False)
        # Apply enabled/disabled state to the slider controls
        self._update_levels_controls()

        # Initialize Always-on-top checkbox from config and apply
        try:
            from APP.helpers.config_manager import get_always_on_top
            if hasattr(self.ui, 'alwaysOnTopCheckBox') and self.ui.alwaysOnTopCheckBox:
                self.ui.alwaysOnTopCheckBox.setChecked(get_always_on_top())
                try:
                    # Apply window flag
                    self.setWindowFlag(Qt.WindowStaysOnTopHint, get_always_on_top())
                    # make it effective and bring to front if enabled
                    if get_always_on_top():
                        try:
                            self.show()
                            self.raise_()
                            self.activateWindow()
                        except Exception:
                            pass
                    else:
                        try:
                            self.show()
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        
        self._update_output_location_display()
    
    def _update_output_location_display(self):
        """Update the output location button text based on current setting."""
        output_location = get_output_location()
        if hasattr(self.ui, 'outputLocationButton') and self.ui.outputLocationButton:
            if output_location:
                folder_name = os.path.basename(output_location)
                display_text = f" {folder_name[:12]}..." if len(folder_name) > 12 else f" {folder_name}"
                self.ui.outputLocationButton.setText(display_text)
                self.ui.outputLocationButton.setToolTip(f"Output saat ini: {output_location}\nKlik untuk ubah")
            else:
                self.ui.outputLocationButton.setText(" Folder Output")
                self.ui.outputLocationButton.setToolTip("Pilih lokasi output (kosongkan untuk default: folder PNG)")
        
        if hasattr(self.ui, 'clearOutputButton') and self.ui.clearOutputButton:
            self.ui.clearOutputButton.setEnabled(bool(output_location))
    
    def _on_black_point_changed(self, value):
        """Handle black point slider change."""
        try:
            set_levels_black_point(value)
            if hasattr(self.ui, 'blackPointValue'):
                self.ui.blackPointValue.setText(str(value))
            print(f"Black point set to: {value}")
            # Realtime update mask preview if in mask mode
            self._update_mask_preview_if_needed()
        except Exception as e:
            print(f"Error saving black point: {str(e)}")
    
    def _on_mid_point_changed(self, value):
        """Handle mid point slider change."""
        try:
            set_levels_mid_point(value)
            if hasattr(self.ui, 'midPointValue'):
                self.ui.midPointValue.setText(str(value))
            print(f"Mid point set to: {value}")
            self._update_mask_preview_if_needed()
        except Exception as e:
            print(f"Error saving mid point: {str(e)}")
    
    def _on_white_point_changed(self, value):
        """Compatibility handler for single value changes (kept for backward compatibility)."""
        try:
            set_levels_white_point(value)
            if hasattr(self.ui, 'whitePointValue'):
                self.ui.whitePointValue.setText(str(value))
            print(f"White point set to: {value}")
            self._update_mask_preview_if_needed()
        except Exception as e:
            print(f"Error saving white point: {str(e)}")

    def _on_levels_changed(self, black, mid, white):
        """Handler for combined levels changes from the multi-handle slider."""
        try:
            set_levels_black_point(int(black))
            set_levels_mid_point(int(mid))
            set_levels_white_point(int(white))

            if hasattr(self.ui, 'blackPointValue'):
                self.ui.blackPointValue.setText(str(int(black)))
            if hasattr(self.ui, 'midPointValue'):
                self.ui.midPointValue.setText(str(int(mid)))
            if hasattr(self.ui, 'whitePointValue'):
                self.ui.whitePointValue.setText(str(int(white)))

            # Realtime update mask preview if in mask mode
            self._update_mask_preview_if_needed()
        except Exception as e:
            print(f"Error saving levels: {str(e)}")

    def _update_mask_preview_if_needed(self):
        """Update mask preview in realtime if in mask mode."""
        if not getattr(self.image_preview, 'mask_mode', False):
            return
        # Only update if mask_mode is True and mask_before_path exists
        mask_before = getattr(self.image_preview, 'mask_before_path', None)
        mask_adj_temp = None
        if not mask_before or not os.path.exists(mask_before):
            return
        # Path for adjusted mask
        base = os.path.splitext(os.path.basename(mask_before))[0].replace('_mask_temp','')
        temp_dir = os.path.join(os.path.dirname(__file__), '../../temp')
        import time
        mask_adj_temp = os.path.join(temp_dir, f'{base}_mask_adj_temp_{int(time.time()*1000)}.png')
        try:
            from APP.helpers.image_utils import apply_levels_to_mask
            from PIL import Image
            import time
            mask_img = Image.open(mask_before)
            black = get_levels_black_point()
            mid = get_levels_mid_point()
            white = get_levels_white_point()
            # Determine if we should use binary mask for extreme settings (match the real processing logic)
            try:
                using_extreme_settings = (white < 10) or (black > 240) or (mid < 10)
            except Exception:
                using_extreme_settings = False

            if using_extreme_settings:
                from APP.helpers.image_utils import create_binary_mask
                # Choose threshold similarly to the main processing
                threshold = 127
                if white < 10:
                    threshold = max(10, white * 10)
                elif black > 240:
                    threshold = min(240, black)
                mask_adj = create_binary_mask(mask_img, threshold=threshold)
            else:
                mask_adj = apply_levels_to_mask(mask_img, black, mid, white)

            # Save adjusted mask to a uniquely named temp file so preview always reloads
            unique_mask_adj = os.path.join(temp_dir, f'{base}_mask_adj_temp_{int(time.time()*1000)}.png')
            mask_adj.save(unique_mask_adj)

            # Cleanup older temp-adjust files for this base (keep the one we just saved)
            try:
                self._cleanup_temp_mask_adj_files(base, keep_filename=unique_mask_adj, age_seconds=60)
            except Exception:
                pass

            # Show the adjusted mask right away (switch to adjusted view so sliders take effect immediately)
            self.image_preview.set_mask_images(mask_before, unique_mask_adj, preserve_zoom=True, show_before=False)
            try:
                # Ensure the after/adjusted image is visible without any user interaction
                self.image_preview.show_after()
            except Exception:
                pass
        except Exception as e:
            print(f"Error realtime mask preview: {e}")
    def _on_mask_progress(self, value, message):
        """Update UI progress for mask generation."""
        try:
            if not hasattr(self, 'progress_bar'):
                return
            if value is None or value == 0:
                self.progress_bar.setRange(0, 0)
                self.progress_bar.show()
                self.progress_bar.setFormat(message)
            else:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(int(value))
                if message:
                    self.progress_bar.setFormat(message)
                if int(value) >= 100:
                    QTimer.singleShot(500, lambda: self.progress_bar.hide())
        except Exception:
            pass

    def _on_mask_generated(self, mask_path, ori_path):
        """Handle mask generated from worker."""
        try:
            # Stop thread
            try:
                if hasattr(self, '_mask_thread') and self._mask_thread:
                    self._mask_thread.quit()
                    if not self._mask_thread.wait(500):
                        self._mask_thread.terminate()
                        self._mask_thread.wait()
            except Exception:
                pass

            # Hide busy indicator
            try:
                if hasattr(self, 'progress_bar'):
                    self.progress_bar.hide()
            except Exception:
                pass

            # Mark as not in progress
            try:
                self._mask_in_progress = False
            except Exception:
                pass

            # Re-enable the configure button now that worker finished
            try:
                if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton:
                    self.ui.configureMaskButton.setEnabled(True)
            except Exception:
                pass

            # Generate adjusted mask and display
            try:
                from APP.helpers.image_utils import apply_levels_to_mask
                from PIL import Image
                mask_img = Image.open(mask_path)
                black = get_levels_black_point()
                mid = get_levels_mid_point()
                white = get_levels_white_point()
                mask_adj = apply_levels_to_mask(mask_img, black, mid, white)

                base = os.path.splitext(os.path.basename(mask_path))[0].replace('_mask_temp','')
                temp_dir = os.path.dirname(mask_path)
                import time
                mask_adj_temp = os.path.join(temp_dir, f'{base}_mask_adj_temp_{int(time.time()*1000)}.png')
                mask_adj.save(mask_adj_temp)

                # Cleanup older temp-adjust files for this base (keep the one we just saved)
                try:
                    self._cleanup_temp_mask_adj_files(base, keep_filename=mask_adj_temp, age_seconds=60)
                except Exception:
                    pass

                # Display mask preview (start showing before by default for a freshly generated mask)
                show_before = True
                self.image_preview.set_mask_images(mask_path, mask_adj_temp, preserve_zoom=True, show_before=show_before)

                # If Ubah Levels is active, ensure sliders are enabled and apply current slider values to refresh preview
                try:
                    if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton and self.ui.configureMaskButton.isChecked():
                        self._update_levels_controls()
                        # Force an immediate update using current slider values (this will also show the adjusted mask)
                        self._update_mask_preview_if_needed()
                        # Also explicitly trigger handlers to ensure preview updates even if slider values didn't change
                        try:
                            # Update labels and config from the multi-handle slider
                            try:
                                if hasattr(self.ui, 'levelsMultiSlider') and self.ui.levelsMultiSlider:
                                    b,m,w = self.ui.levelsMultiSlider.getValues()
                                    self._on_levels_changed(b, m, w)
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception as e:
                    print(f"Error applying sliders after mask generation: {e}")

                # Clean up temporary files for this base (do not remove very recent ones)
                try:
                    try:
                        base_cleanup = os.path.splitext(os.path.basename(mask_path))[0].replace('_mask_temp','')
                    except Exception:
                        base_cleanup = None
                    if base_cleanup:
                        self._cleanup_temp_mask_adj_files(base_cleanup, keep_filename=mask_adj_temp, age_seconds=60)
                except Exception:
                    pass
            except Exception as e:
                print(f"Error creating adjusted mask after generation: {e}")
                QMessageBox.warning(self, "Error", f"Gagal membuat preview mask: {e}")
        except Exception as e:
            print(f"Error in _on_mask_generated: {e}")

    def _on_mask_error(self, msg):
        """Handle mask worker error: show message, uncheck box and cleanup."""
        try:
            QMessageBox.warning(self, 'Error', f"Gagal membuat mask: {msg}")
        except Exception:
            pass
        try:
            # Unset in-progress flag
            try:
                self._mask_in_progress = False
            except Exception:
                pass
            # Revert checkbox to unchecked in a deterministic way
            self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
            # Ensure button is enabled so the user can try again
            try:
                if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton:
                    self.ui.configureMaskButton.setEnabled(True)
            except Exception:
                pass
        except Exception:
            pass
        try:
            if hasattr(self, 'progress_bar'):
                self.progress_bar.hide()
        except Exception:
            pass

    def _on_configure_mask_clicked(self, checked=False):
        """Clicked handler for the configure mask button. Always starts/restarts mask generation and keeps the button checked."""
        try:
            # Keep the button checked to indicate mask/adjust mode
            self._set_levels_checkbox_state(True, block_signals=True, update_controls=True)

            # If a worker is already running, inform the user and don't start another
            if getattr(self, '_mask_in_progress', False):
                try:
                    QMessageBox.information(self, "Tunggu", "Proses pembuatan mask sedang berjalan. Silakan tunggu hingga selesai.")
                except Exception:
                    pass
                return

            # Start (or restart) the mask worker
            self._start_mask_worker()
        except Exception as e:
            print(f"Error in _on_configure_mask_clicked: {e}")
            try:
                self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
            except Exception:
                pass

    def _start_mask_worker(self, current_path=None):
        """Start the MaskWorker using selected/current preview file, prompting user if needed.

        If current_path is provided it will be used; otherwise the function picks a sensible source.
        """
        try:
            # Determine path to use
            chosen = None
            try:
                if current_path:
                    chosen = current_path
                else:
                    selected = self.file_table.selectionModel().selectedRows()
                    if selected:
                        chosen = self.file_table.get_file_path(selected[0].row())
            except Exception:
                chosen = None

            # Fallback to current preview file
            if not chosen:
                try:
                    chosen = self.image_preview.get_current_file_path()
                except Exception:
                    chosen = None

            # Helper to detect processed outputs
            def looks_like_processed(p):
                if not p:
                    return False
                name = os.path.basename(p).lower()
                return ('_transparent' in name) or ('_mask' in name) or ('_mask_adjusted' in name) or name.endswith('_transparent.png')

            if looks_like_processed(chosen):
                stem = os.path.splitext(os.path.basename(chosen))[0]
                stem = re.sub(r'(_transparent.*|_mask.*|_mask_adjusted.*)$', r'', stem, flags=re.IGNORECASE)
                found = None
                for r in range(self.file_table.rowCount()):
                    candidate = self.file_table.get_file_path(r)
                    if candidate and os.path.splitext(os.path.basename(candidate))[0].lower() == stem.lower():
                        found = candidate
                        break
                if found:
                    chosen = found

            # If still no usable original, ask user to pick from loaded files
            if not chosen or not os.path.exists(chosen):
                try:
                    ret = QMessageBox.question(
                        self,
                        "Tidak ada gambar",
                        "Tidak ada gambar asli yang cocok untuk preview mask. Pilih file sumber dari daftar ter-load?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                except Exception:
                    ret = QMessageBox.StandardButton.No

                if ret == QMessageBox.StandardButton.Yes:
                    row_count = self.file_table.rowCount()
                    if row_count <= 0:
                        QMessageBox.warning(self, "Tidak ada file ter-load", "Tidak ada file pada daftar. Silakan muat file ke daftar dan pilih satu terlebih dahulu.")
                        self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
                        return
                    items = []
                    path_map = []
                    for r in range(row_count):
                        p = self.file_table.get_file_path(r)
                        if p and os.path.exists(p):
                            items.append(os.path.basename(p))
                            path_map.append(p)
                    if not items:
                        QMessageBox.warning(self, "Tidak ada file tersedia", "Tidak ada file yang dapat dipilih. Silakan periksa daftar file.")
                        self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
                        return
                    item, ok = QInputDialog.getItem(self, "Pilih file sumber", "Pilih file dari daftar ter-load:", items, 0, False)
                    if not ok or not item:
                        # User cancelled — revert and keep preview/zoom unchanged
                        self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
                        return
                    idx = items.index(item)
                    chosen = path_map[idx]
                else:
                    # User chose No — revert and keep preview
                    self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
                    return

            # Start worker using chosen
            temp_dir = os.path.join(os.path.dirname(__file__), '../../temp')
            os.makedirs(temp_dir, exist_ok=True)

            # Abort previous worker if running
            try:
                if hasattr(self, '_mask_thread') and self._mask_thread and self._mask_thread.isRunning():
                    try:
                        self._mask_worker.abort = True
                    except Exception:
                        pass
                    try:
                        self._mask_thread.quit()
                        self._mask_thread.wait(200)
                    except Exception:
                        pass
            except Exception:
                pass

            model_name = self.ui.modelComboBox.currentText() if hasattr(self.ui, 'modelComboBox') and self.ui.modelComboBox else None
            self._mask_worker = MaskWorker(chosen, temp_dir, model_name=model_name)
            self._mask_thread = QThread()
            self._mask_worker.moveToThread(self._mask_thread)
            self._mask_thread.started.connect(self._mask_worker.run)
            self._mask_worker.finished.connect(self._on_mask_generated)
            self._mask_worker.error.connect(self._on_mask_error)
            self._mask_worker.progress.connect(self._on_mask_progress)

            # Mark and start
            self._mask_in_progress = True
            try:
                if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton:
                    self.ui.configureMaskButton.setEnabled(False)
            except Exception:
                pass

            # quick cleanup
            try:
                base = os.path.splitext(os.path.basename(chosen))[0]
                self._cleanup_temp_mask_adj_files(base, keep_filename=None, age_seconds=3600)
            except Exception:
                pass

            if hasattr(self, 'progress_bar'):
                self.progress_bar.setRange(0, 0)
                self.progress_bar.show()

            try:
                self._update_levels_controls()
            except Exception:
                pass

            self._mask_thread.start()

        except Exception as e:
            print(f"_start_mask_worker error: {e}")
            try:
                self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
            except Exception:
                pass

    def _update_color_button(self, color_hex):
        """Update color picker button background."""
        if hasattr(self.ui, 'colorPickerButton') and self.ui.colorPickerButton:
            self.ui.colorPickerButton.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_hex};
                    border: 1px solid #888;
                    border-radius: 4px;
                }}
            """)
    
    def _update_solid_bg_controls(self):
        """Update enabled state of solid background controls."""
        if hasattr(self.ui, 'solidBgCheckBox') and self.ui.solidBgCheckBox:
            is_enabled = self.ui.solidBgCheckBox.isChecked()
            
            if hasattr(self.ui, 'colorPickerButton') and self.ui.colorPickerButton:
                self.ui.colorPickerButton.setEnabled(is_enabled)
    
    def _update_jpg_quality_controls(self):
        """Update enabled state of JPG quality controls."""
        if hasattr(self.ui, 'jpgExportCheckBox') and self.ui.jpgExportCheckBox:
            is_enabled = self.ui.jpgExportCheckBox.isChecked()
            
            if hasattr(self.ui, 'jpgQualitySpinBox') and self.ui.jpgQualitySpinBox:
                self.ui.jpgQualitySpinBox.setEnabled(is_enabled)
            
            if hasattr(self.ui, 'jpgQualityLabel') and self.ui.jpgQualityLabel:
                self.ui.jpgQualityLabel.setEnabled(is_enabled)

    def _update_levels_controls(self):
        """Enable or disable levels sliders and value labels according to the checkbox."""
        is_enabled = False
        if hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton:
            is_enabled = self.ui.configureMaskButton.isChecked()

        names = (
            'blackPointSlider', 'midPointSlider', 'whitePointSlider',
            'blackPointValue', 'midPointValue', 'whitePointValue'
        )

        for name in names:
            if hasattr(self.ui, name) and getattr(self.ui, name):
                try:
                    getattr(self.ui, name).setEnabled(is_enabled)
                except Exception:
                    pass

    def _on_always_on_top_changed(self, state):
        """Handle Always-on-top checkbox change and persist the value."""
        is_checked = (state != 0)
        try:
            from APP.helpers.config_manager import set_always_on_top
            set_always_on_top(is_checked)
        except Exception:
            pass
        try:
            # Apply window flag and ensure window updates
            self.setWindowFlag(Qt.WindowStaysOnTopHint, is_checked)
            # If enabling, bring window to front; if disabling, ensure flag cleared
            try:
                if is_checked:
                    self.show()
                    self.raise_()
                    self.activateWindow()
                else:
                    self.show()
            except Exception:
                pass
        except Exception:
            pass

    def _set_levels_checkbox_state(self, checked, block_signals=True, update_controls=True):
        """Set the configure mask button state programmatically, with optional signal blocking and UI updates."""
        if not (hasattr(self.ui, 'configureMaskButton') and self.ui.configureMaskButton):
            return
        try:
            if block_signals:
                self.ui.configureMaskButton.blockSignals(True)
            self.ui.configureMaskButton.setChecked(bool(checked))
            if block_signals:
                self.ui.configureMaskButton.blockSignals(False)
            if update_controls:
                try:
                    self._update_levels_controls()
                except Exception:
                    pass
        except Exception:
            pass

    def _cleanup_temp_mask_adj_files(self, base, keep_filename=None, age_seconds=300):
        """Remove old temporary adjusted mask files for a given base name in temp dir.

        Args:
            base (str): base filename (without suffix) to match
            keep_filename (str|None): full path to keep (do not delete)
            age_seconds (int): minimum age in seconds to remove files
        """
        try:
            temp_dir = os.path.join(os.path.dirname(__file__), '../../temp')
            if not os.path.exists(temp_dir):
                return
            now = None
            try:
                import time
                now = time.time()
            except Exception:
                now = None
            for fname in os.listdir(temp_dir):
                if not fname.startswith(f"{base}_"):
                    continue
                full = os.path.join(temp_dir, fname)
                if keep_filename and os.path.abspath(full) == os.path.abspath(keep_filename):
                    continue
                # Only target known temp patterns we create
                if not ("mask_adj_temp_" in fname or fname.endswith('_ori_temp.png') or fname.endswith('_mask_temp.png')):
                    continue
                try:
                    # If age_seconds is set, only remove files older than age_seconds
                    if now is not None:
                        mtime = os.path.getmtime(full)
                        if (now - mtime) < age_seconds:
                            # too new, skip for now
                            continue
                    os.remove(full)
                except Exception:
                    pass
        except Exception:
            pass

    def _cleanup_all_old_temp_files(self, age_seconds=86400):
        """Remove any old temp files we previously left around (mask_adj_temp, ori_temp, mask_temp)."""
        try:
            temp_dir = os.path.join(os.path.dirname(__file__), '../../temp')
            if not os.path.exists(temp_dir):
                return
            now = None
            try:
                import time
                now = time.time()
            except Exception:
                now = None
            for fname in os.listdir(temp_dir):
                full = os.path.join(temp_dir, fname)
                if not ("mask_adj_temp_" in fname or fname.endswith('_ori_temp.png') or fname.endswith('_mask_temp.png')):
                    continue
                try:
                    if now is not None:
                        mtime = os.path.getmtime(full)
                        if (now - mtime) < age_seconds:
                            continue
                    os.remove(full)
                except Exception:
                    pass
        except Exception:
            pass

    def _cleanup_temp_on_exit(self):
        """Immediate cleanup of the temp folder used by the app. Removes files and subfolders left in temp.

        This is called on application close to ensure no leftover temporary files remain.
        """
        try:
            temp_dir = os.path.join(os.path.dirname(__file__), '../../temp')
            if not os.path.exists(temp_dir):
                return
            import shutil
            for fname in os.listdir(temp_dir):
                full = os.path.join(temp_dir, fname)
                try:
                    if os.path.isfile(full) or os.path.islink(full):
                        os.remove(full)
                    elif os.path.isdir(full):
                        shutil.rmtree(full, ignore_errors=True)
                except Exception:
                    pass
            # Attempt to remove the temp directory itself if empty
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
        except Exception:
            pass

    def _on_levels_enabled_changed(self, state):
        """Handle 'Ubah Levels' checkbox change (GUI-only)."""
        is_checked = (state != 0)
        print(f"Levels enabled changed - Interpreted as: {'checked' if is_checked else 'unchecked'}")
        try:
            # If a mask generation is already in progress, ignore repeat checks and inform user
            if getattr(self, '_mask_in_progress', False) and is_checked:
                try:
                    QMessageBox.information(self, "Tunggu", "Proses pembuatan mask sedang berjalan. Silakan tunggu hingga selesai sebelum mengaktifkan lagi.")
                except Exception:
                    pass
                # Revert the checkbox to unchecked in deterministic way
                try:
                    self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
                except Exception:
                    pass
                return

            self._update_levels_controls()
            print(f"Levels GUI state updated: {is_checked}")
        except Exception as e:
            print(f"Error updating levels controls: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal mengupdate UI Levels: {str(e)}")

# If checkbox was unchecked, abort any running worker and restore preview (preserve zoom)
        if not is_checked:
            try:
                if hasattr(self, '_mask_thread') and self._mask_thread and self._mask_thread.isRunning():
                    try:
                        self._mask_worker.abort = True
                    except Exception:
                        pass
                    try:
                        self._mask_thread.quit()
                        self._mask_thread.wait(200)
                    except Exception:
                        pass
                # Reset in-progress flag
                try:
                    self._mask_in_progress = False
                except Exception:
                    pass
            except Exception:
                pass
            # Hide progress bar
            try:
                if hasattr(self, 'progress_bar'):
                    self.progress_bar.hide()
            except Exception:
                pass
            # Restore normal image preview - preserve zoom
            try:
                if self.image_preview.before_path:
                    self.image_preview.set_images(self.image_preview.before_path, self.image_preview.after_path, preserve_zoom=True)
            except Exception:
                pass
            return

        # --- Custom logic for mask preview ---
        if is_checked:
            # Delegate to a helper that starts the mask worker and handles UI state
            try:
                self._start_mask_worker()
            except Exception as e:
                print(f"Error starting mask flow: {e}")
                try:
                    self._set_levels_checkbox_state(False, block_signals=True, update_controls=True)
                except Exception:
                    pass
            return

            # Proses rembg untuk masking ke temp (jika belum ada)
            import time
            from APP.helpers import image_utils
            temp_dir = os.path.join(os.path.dirname(__file__), '../../temp')
            os.makedirs(temp_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(current_path))[0]
            ori_temp = os.path.join(temp_dir, f'{base}_ori_temp.png')
            mask_temp = os.path.join(temp_dir, f'{base}_mask_temp.png')
            import time
            mask_adj_temp = os.path.join(temp_dir, f'{base}_mask_adj_temp_{int(time.time()*1000)}.png')

            # Only reprocess if not already exists
            if not (os.path.exists(ori_temp) and os.path.exists(mask_temp)):
                try:
                    # Use rembg to get mask (only_mask=True)
                    import rembg
                    from PIL import Image
                    input_img = Image.open(current_path)
                    # Save ori to temp
                    input_img.save(ori_temp)
                    # Get mask
                    mask_img = rembg.remove(input_img, only_mask=True)
                    mask_img.save(mask_temp)
                    # Keep original mask as-is for preview (do not invert)
                    pass
                except Exception as e:
                    print(f"Error rembg mask preview: {e}")
                    QMessageBox.warning(self, "Error", f"Gagal membuat mask preview: {e}")
                    return

            # Proses adjustment levels ke mask_adj_temp
            try:
                from APP.helpers.image_utils import apply_levels_to_mask
                from PIL import Image
                mask_img = Image.open(mask_temp)
                black = get_levels_black_point()
                mid = get_levels_mid_point()
                white = get_levels_white_point()
                # Mirror the real processing behaviour for extreme values
                using_extreme_settings = (white < 10) or (black > 240) or (mid < 10)
                if using_extreme_settings:
                    from APP.helpers.image_utils import create_binary_mask
                    threshold = 127
                    if white < 10:
                        threshold = max(10, white * 10)
                    elif black > 240:
                        threshold = min(240, black)
                    mask_adj = create_binary_mask(mask_img, threshold=threshold)
                else:
                    mask_adj = apply_levels_to_mask(mask_img, black, mid, white)
                # Save to uniquely named file so preview updates correctly (avoid QPixmap caching)
                unique_mask_adj = os.path.join(temp_dir, f'{base}_mask_adj_temp_{int(time.time()*1000)}.png')
                mask_adj.save(unique_mask_adj)
                mask_adj_temp = unique_mask_adj
            except Exception as e:
                print(f"Error adjust mask preview: {e}")
                QMessageBox.warning(self, "Error", f"Gagal membuat mask adjustment: {e}")
                return

            # Tampilkan mask ori dan mask hasil adjustment di preview
            show_before = getattr(self.image_preview, 'showing_before', True)
            self.image_preview.set_mask_images(mask_temp, mask_adj_temp, preserve_zoom=True, show_before=show_before)
        else:
            # Kembali ke mode preview gambar normal
            if self.image_preview.before_path:
                self.image_preview.set_images(self.image_preview.before_path, self.image_preview.after_path)
            else:
                self.image_preview.clear()

    def _on_auto_crop_changed(self, state):
        """Handle auto crop checkbox state change."""
        is_checked = (state != 0)
        print(f"Auto crop checkbox changed - Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            set_auto_crop_enabled(is_checked)
            print(f"Auto crop setting saved successfully: {is_checked}")
        except Exception as e:
            print(f"Error saving auto crop setting: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal menyimpan pengaturan potong otomatis: {str(e)}")
    
    def _on_solid_bg_changed(self, state):
        """Handle solid background checkbox state change."""
        is_checked = (state != 0)
        print(f"Solid background checkbox changed - Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            set_solid_bg_enabled(is_checked)
            self._update_solid_bg_controls()
            print(f"Solid background setting saved successfully: {is_checked}")
        except Exception as e:
            print(f"Error saving solid background setting: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal menyimpan pengaturan background solid: {str(e)}")
    
    def _on_color_picker_clicked(self):
        """Open color picker dialog."""
        try:
            current_color_hex = get_solid_bg_color()
            current_color = QColor(current_color_hex)
            
            color = QColorDialog.getColor(current_color, self, "Pilih Warna Background")
            
            if color.isValid():
                color_hex = color.name().upper()
                set_solid_bg_color(color_hex)
                self._update_color_button(color_hex)
                print(f"Background color changed to: {color_hex}")
        except Exception as e:
            print(f"Error in color picker: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal mengubah warna: {str(e)}")
    
    def _on_unified_margin_changed(self, value):
        """Handle unified margin spinbox value change."""
        try:
            set_unified_margin(value)
            print(f"Unified margin set to: {value}px")
        except Exception as e:
            print(f"Error saving unified margin: {str(e)}")
    
    def _on_save_mask_changed(self, state):
        """Handle save mask checkbox state change."""
        is_checked = (state != 0)
        print(f"Save mask checkbox changed - Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            set_save_mask_enabled(is_checked)
            print(f"Save mask setting saved successfully: {is_checked}")
        except Exception as e:
            print(f"Error saving save mask setting: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal menyimpan pengaturan mask: {str(e)}")
    
    def _on_jpg_export_changed(self, state):
        """Handle JPG export checkbox state change."""
        is_checked = (state != 0)
        print(f"JPG export checkbox changed - Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            set_jpg_export_enabled(is_checked)
            self._update_jpg_quality_controls()
            print(f"JPG export setting saved successfully: {is_checked}")
        except Exception as e:
            print(f"Error saving JPG export setting: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal menyimpan pengaturan ekspor JPG: {str(e)}")
    
    def _on_jpg_quality_changed(self, value):
        """Handle JPG quality spinbox value change."""
        try:
            set_jpg_quality(value)
            print(f"JPG quality set to: {value}")
        except Exception as e:
            print(f"Error saving JPG quality: {str(e)}")
    


    def _on_download_progress_ui(self, model_name, progress):
        """Slot executed in GUI thread to update UI for download progress.

        Throttles updates to avoid overloading the event loop.
        """
        try:
            import time
            now = time.monotonic()

            # Initialize throttling state
            if not hasattr(self, '_last_download_ui_time'):
                self._last_download_ui_time = 0.0
                self._last_download_ui_progress = -1.0

            # Throttle: only update if at least 150ms elapsed OR progress changed by >=1%, but always update 100%
            if progress >= 100.0:
                pass  # Always update for 100%
            elif (now - self._last_download_ui_time) < 0.15 and abs(progress - self._last_download_ui_progress) < 1.0:
                return

            self._last_download_ui_time = now
            self._last_download_ui_progress = progress

            # Save previous progress state once
            if not self._download_in_progress:
                self._download_in_progress = True
                self._saved_progress_value = self.progress_bar.value() if hasattr(self, 'progress_bar') else 0
                self._saved_progress_format = self.progress_bar.format() if hasattr(self, 'progress_bar') else None
                # Remember whether the progress bar was hidden before download started
                try:
                    self._download_saved_hidden = not self.progress_bar.isVisible()
                except Exception:
                    self._download_saved_hidden = False

            # Ensure the progress bar is visible and shows download progress
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setRange(0, 100)
                self.progress_bar.show()
                # Update value; avoid forcing z-order changes which can be expensive
                self.progress_bar.setValue(int(progress))
                # Keep consistent format; only change format text
                self.progress_bar.setFormat(f"Downloading {model_name}: %p% ({int(progress)}%)")

            # If download completed, mark as completed and show notification then restore progress bar
            if progress >= 100 and model_name != self._last_completed_download_model:
                try:
                    # Mark as completed BEFORE showing modal dialog to avoid duplicate dialogs if multiple signals arrive
                    self._last_completed_download_model = model_name
                    QMessageBox.information(self, "Model Siap", f"Model {model_name} telah berhasil diunduh dan siap digunakan.")
                    self._restore_progress_bar()
                except Exception:
                    pass

            # If download in progress for a different model, clear the completed marker
            try:
                if progress < 100 and (self._last_completed_download_model is not None and model_name != self._last_completed_download_model):
                    self._last_completed_download_model = None
            except Exception:
                pass

        except Exception:
            pass

    def _download_progress_callback(self, model_name, progress):
        """Compatibility callback (can be used by non-signal callers). Emits the GUI signal."""
        try:
            # Forward to the signal which will be delivered in GUI thread
            self.downloadProgress.emit(model_name, float(progress))
        except Exception as e:
            print(f"Error emitting GUI download progress signal: {str(e)}")

    def _restore_progress_bar(self):
        """Restore progress bar to previous state after download finished."""
        try:
            if hasattr(self, 'progress_bar'):
                if self._saved_progress_value is not None:
                    self.progress_bar.setValue(self._saved_progress_value)
                    if self._saved_progress_format:
                        self.progress_bar.setFormat(self._saved_progress_format)
                else:
                    self.progress_bar.hide()

        finally:
            # Restore/clear flags
            self._download_in_progress = False
            self._saved_progress_value = None
            self._saved_progress_format = None
            # If progress bar was hidden before download, hide it now; otherwise restore format
            try:
                if hasattr(self, 'progress_bar'):
                    if getattr(self, '_download_saved_hidden', False):
                        self.progress_bar.hide()
                    else:
                        self.progress_bar.setFormat("%p% - %v / %m")
            except Exception:
                pass
            finally:
                # Clear saved-hidden flag
                try:
                    self._download_saved_hidden = False
                except Exception:
                    pass

    def _on_model_changed(self, model_name):
        """Handle model combobox selection change."""
        try:
            print(f"Model changed to: {model_name}")
            set_selected_model(model_name)
        except Exception as e:
            print(f"Error saving selected model: {str(e)}")

        # Download the selected model in the background (non-blocking) and show progress
        def download_worker():
            success = model_manager.prepare_model(model_name=model_name, callback=self._download_progress_callback)
            # Ensure UI updated after download completes
            def finish_ui():
                try:
                    if success:
                        # Show completion briefly then restore
                        self.progress_bar.setValue(100)
                        self.progress_bar.setFormat(f"Downloaded {model_name}")
                        QTimer.singleShot(1200, self._restore_progress_bar)
            
                        print(f"Model {model_name} siap untuk digunakan")
                    else:
                        try:
                            QMessageBox.warning(self, "Gagal", f"Gagal mengunduh model: {model_name}")
                        except Exception:
                            pass
                        self._restore_progress_bar()
                except Exception as e:
                    print(f"Error updating UI after download: {str(e)}")

            QTimer.singleShot(0, finish_ui)

        threading.Thread(target=download_worker, daemon=True).start()
    
    def _on_output_location_clicked(self):
        """Handle output location button click."""
        current_location = get_output_location()
        start_dir = current_location if current_location else os.path.expanduser("~")
        
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Pilih Folder Output",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if folder_path:
            set_output_location(folder_path)
            self._update_output_location_display()
            print(f"Output location set to: {folder_path}")
    
    def _on_clear_output_clicked(self):
        """Clear output location to use default."""
        set_output_location(None)
        self._update_output_location_display()
        print("Output location cleared - using default PNG folder")
    
    def _open_whatsapp(self):
        """Open WhatsApp group link."""
        try:
            webbrowser.open(self.WHATSAPP_GROUP_LINK)
            print(f"Opened WhatsApp link: {self.WHATSAPP_GROUP_LINK}")
        except Exception as e:
            print(f"Error opening WhatsApp: {str(e)}")
            QMessageBox.warning(self, "Error", f"Gagal membuka WhatsApp: {str(e)}")
    
    def _open_folder_dialog(self):
        """Handle open folder button click."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Pilih Folder Gambar",
            os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly
        )
        
        if folder_path:
            self._reset_ui_state()
            self._process_files([folder_path])
    
    def _open_files_dialog(self):
        """Handle open files button click."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Pilih Gambar",
            os.path.expanduser("~"),
            "Gambar (*.jpg *.jpeg *.png *.bmp *.webp)"
        )
        
        if file_paths:
            self._reset_ui_state()
            self._process_files(file_paths)
    
    def _on_stop_clicked(self):
        """Handle stop button click."""
        if self.worker:
            self.worker.abort = True
            print("Stop requested - aborting current operation")
            
            if hasattr(self.ui, 'stopButton') and self.ui.stopButton:
                self.ui.stopButton.setEnabled(False)
            
            QTimer.singleShot(100, self._finalize_stop)
    
    def _finalize_stop(self):
        """Finalize the stop operation."""
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(3000):
                self.thread.terminate()
                self.thread.wait()
        
        self.thread = None
        self.worker = None
        
        self.progress_bar.hide()
        self._reset_ui_state()
        
        QMessageBox.information(self, "Dihentikan", "Proses dihentikan oleh pengguna")
    
    def _on_repeat_clicked(self):
        """Handle repeat button click."""
        if self.last_processed_files:
            self._reset_ui_state()
            self._process_files(self.last_processed_files)
    
    def _process_files(self, file_paths):
        """Start processing files."""
        self.last_processed_files = file_paths.copy()
        
        # Create session in database
        output_dir = get_output_location()
        self.current_session_id = self.db.create_session(output_dir)
        
        # Store output_dir for later use in _get_output_path
        self.current_output_dir = output_dir
        
        # Hide DND area, show split view
        self.drop_area.hide()
        self.split_view.show()
        
        if hasattr(self.ui, 'resetButton') and self.ui.resetButton:
            self.ui.resetButton.show()
        
        # Populate table
        self.file_table.clear_all()
        self.file_id_map.clear()
        
        for idx, file_path in enumerate(file_paths):
            try:
                file_size = os.path.getsize(file_path)
            except:
                file_size = 0
            
            file_id = self.db.add_file(self.current_session_id, file_path, file_size)
            self.file_table.add_file(file_path, file_id)
            self.file_id_map[idx] = file_id
        
        # Auto select first row to show preview
        if self.file_table.rowCount() > 0:
            self.file_table.selectRow(0)
            first_file_path = self.file_table.get_file_path(0)
            if first_file_path:
                # Show before image immediately
                print(f"Auto-selecting first file: {first_file_path}")
                self.image_preview.set_images(first_file_path, None)
        
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        
        if hasattr(self.ui, 'stopButton') and self.ui.stopButton:
            self.ui.stopButton.setEnabled(True)
        
        if hasattr(self.ui, 'repeatButton') and self.ui.repeatButton:
            self.ui.repeatButton.setEnabled(False)
        
        self.worker = RemBgWorker(file_paths, output_dir=output_dir)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.process_files)
        self.worker.finished.connect(self._on_processing_finished)
        self.worker.progress.connect(self._update_progress)
        self.worker.file_completed.connect(self._on_file_completed)
        # Connect download progress from worker to the MainWindow signal (will be delivered in GUI thread)
        self.worker.download_progress.connect(self.downloadProgress)
        # Connect status updates from worker to show to user
        self.worker.status_update.connect(lambda msg: print(f"Model status: {msg}"))
        
        self.thread.start()
    
    def _update_progress(self, value, message="", current_file_path=None):
        """Update progress bar."""
        try:
            # Make sure the progressbar is visible and uses consistent format while processing files
            if hasattr(self, 'progress_bar'):
                if not self.progress_bar.isVisible():
                    self.progress_bar.show()
                self.progress_bar.setFormat("%p% - %v / %m")

                self.progress_bar.setValue(value)
        except Exception as e:
            print(f"Error updating processing progress UI: {str(e)}")
        
        # Find row index for current file
        if current_file_path:
            for row in range(self.file_table.rowCount()):
                if self.file_table.get_file_path(row) == current_file_path:
                    self.file_table.update_file_status(row, 'processing')
                    file_id = self.file_id_map.get(row)
                    if file_id:
                        self.db.update_file_status(file_id, 'processing')
                    
                    # Auto-select this row and show preview
                    self.file_table.selectRow(row)
                    # Show before image while processing
                    self.image_preview.set_images(current_file_path, None)
                    break
    
    def _update_preview_image(self, file_path):
        """Update the preview image."""
        if self.dnd_label_1:
            self.dnd_label_1.hide()
        if self.dnd_label_2:
            self.dnd_label_2.hide()
        if self.dnd_label_3:
            self.dnd_label_3.hide()
        
        margins = 10
        self.preview_image.setGeometry(
            margins,
            margins,
            self.drop_area.width() - (margins * 2),
            self.drop_area.height() - (margins * 2)
        )
        
        if self.preview_image.setImagePath(file_path):
            self.preview_image.show()
    
    def _on_file_completed(self, file_path):
        """Handle file completion."""
        # Find row index and update status
        for row in range(self.file_table.rowCount()):
            if self.file_table.get_file_path(row) == file_path:
                self.file_table.update_file_status(row, 'completed')
                output_path = self._get_output_path(file_path)
                print(f"File completed: {file_path}")
                print(f"Looking for output at: {output_path}")
                print(f"Output exists: {os.path.exists(output_path) if output_path else False}")
                
                file_id = self.file_id_map.get(row)
                if file_id:
                    self.db.update_file_status(file_id, 'completed', output_path)
                
                # Check if this row is selected
                selected_rows = self.file_table.selectionModel().selectedRows()
                if selected_rows and selected_rows[0].row() == row:
                    # Show after image (output) now that it's complete
                    if output_path and os.path.exists(output_path):
                        print(f"Updating preview with output: {output_path}")
                        self.image_preview.set_images(file_path, output_path)
                    else:
                        print(f"Output not found, keeping before image")
                break
    
    def _on_processing_finished(self, processing_time, file_count):
        """Handle processing completion."""
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        
        self.thread = None
        self.worker = None
        
        self.progress_bar.hide()
        
        if hasattr(self.ui, 'stopButton') and self.ui.stopButton:
            self.ui.stopButton.setEnabled(False)
        
        if hasattr(self.ui, 'repeatButton') and self.ui.repeatButton and self.last_processed_files:
            self.ui.repeatButton.setEnabled(True)
        
        minutes = int(processing_time // 60)
        seconds = int(processing_time % 60)
        time_str = f"{minutes} menit {seconds} detik" if minutes > 0 else f"{seconds} detik"
        
        QMessageBox.information(
            self,
            "Selesai",
            f"Pemrosesan selesai!\n\n"
            f"Total file: {file_count}\n"
            f"Waktu: {time_str}"
        )
    
    def _reset_ui_state(self):
        """Reset UI to initial state."""
        if self.preview_image:
            self.preview_image.hide()
        
        if self.dnd_label_1 and hasattr(self, 'original_label1_text'):
            self.dnd_label_1.setText(self.original_label1_text)
            self.dnd_label_1.show()
        
        if self.dnd_label_2 and hasattr(self, 'original_label2_text'):
            self.dnd_label_2.setText(self.original_label2_text)
            self.dnd_label_2.show()
        
        if self.dnd_label_3 and hasattr(self, 'original_label3_text'):
            self.dnd_label_3.setText(self.original_label3_text)
            self.dnd_label_3.show()
        
        if hasattr(self.ui, 'stopButton') and self.ui.stopButton:
            self.ui.stopButton.setEnabled(False)
        
        if hasattr(self.ui, 'repeatButton') and self.ui.repeatButton:
            self.ui.repeatButton.setEnabled(bool(self.last_processed_files))
    
    def _on_dnd_area_clicked(self, event):
        """Handle click on DND area to open file dialog."""
        if self.drop_area.isVisible() and not self.split_view.isVisible():
            self._open_files_dialog()
    
    def _on_file_selected(self, row, file_path):
        """Handle file selection from table."""
        print(f"File selected: row={row}, path={file_path}")
        
        # Get output path if exists
        output_path = self._get_output_path(file_path)
        print(f"Output path: {output_path}, exists={os.path.exists(output_path) if output_path else False}")
        
        # Show preview
        if output_path and os.path.exists(output_path):
            print(f"Setting preview with before={file_path}, after={output_path}")
            self.image_preview.set_images(file_path, output_path)
        else:
            print(f"Setting preview with only before={file_path}")
            self.image_preview.set_images(file_path, None)
    
    def _on_file_double_clicked(self, file_path):
        """Handle double-click on file to open location."""
        folder_path = os.path.dirname(file_path)
        
        if sys.platform == 'win32':
            # Windows: open folder and select file
            subprocess.run(['explorer', '/select,', os.path.normpath(file_path)])
        elif sys.platform == 'darwin':
            # macOS
            subprocess.run(['open', '-R', file_path])
        else:
            # Linux
            subprocess.run(['xdg-open', folder_path])
    
    def _on_reset_clicked(self):
        """Handle reset button click."""
        self.file_table.clear_all()
        self.image_preview.clear()
        self.file_id_map.clear()
        self.current_session_id = None
        
        # Hide split view, show DND area
        self.split_view.hide()
        self.drop_area.show()
        
        if hasattr(self.ui, 'resetButton') and self.ui.resetButton:
            self.ui.resetButton.hide()
        
        self._reset_ui_state()

    def closeEvent(self, event):
        """Save current model selection on close to ensure persistence. Reset levels_enabled to False."""
        try:
            if hasattr(self.ui, 'modelComboBox') and self.ui.modelComboBox:
                current = self.ui.modelComboBox.currentText()
                try:
                    from APP.helpers.config_manager import set_selected_model, get_selected_model
                    # Only write if different to avoid unnecessary file writes
                    if current and current != get_selected_model():
                        set_selected_model(current)
                        print(f"Saved model selection on close: {current}")
                except Exception as e:
                    print(f"Warning: failed to save selected model or reset levels_enabled on close: {str(e)}")
        except Exception:
            pass
        finally:
            return super().closeEvent(event)

    def _get_output_path(self, input_path):
        """Get output path for a given input file."""
        # Use the same output_dir that was used by the worker
        output_dir = self.current_output_dir if hasattr(self, 'current_output_dir') and self.current_output_dir else None
        
        if not output_dir:
            # Use default PNG folder
            input_dir = os.path.dirname(input_path)
            output_dir = os.path.join(input_dir, "PNG")
        
        filename = os.path.splitext(os.path.basename(input_path))[0]
        
        # Try to find the actual output file (with timestamp)
        # Pattern: filename_transparent_*.png
        import glob
        
        # Search in multiple possible locations
        search_dirs = [
            output_dir,  # Main output dir
            os.path.join(output_dir, "PNG"),  # Subfolder PNG (created by image_utils)
        ]
        
        all_matches = []
        for search_dir in search_dirs:
            pattern = os.path.join(search_dir, f"{filename}_transparent*.png")
            print(f"Searching for output with pattern: {pattern}")
            matches = glob.glob(pattern)
            if matches:
                print(f"Found {len(matches)} matches in {search_dir}")
                all_matches.extend(matches)
        
        if all_matches:
            # Return the most recent one
            result = max(all_matches, key=os.path.getmtime)
            print(f"Returning most recent from all matches: {result}")
            return result
        
        # Fallback to expected paths without timestamp
        for search_dir in search_dirs:
            fallback = os.path.join(search_dir, f"{filename}_transparent.png")
            if os.path.exists(fallback):
                print(f"Found fallback: {fallback}")
                return fallback
        
        # Final fallback
        fallback = os.path.join(output_dir, f"{filename}_transparent.png")
        print(f"No matches found, returning final fallback: {fallback}")
        return fallback
    
    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_area.setProperty("dragActive", True)
            self.drop_area.style().unpolish(self.drop_area)
            self.drop_area.style().polish(self.drop_area)
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event."""
        self.drop_area.setProperty("dragActive", False)
        self.drop_area.style().unpolish(self.drop_area)
        self.drop_area.style().polish(self.drop_area)
        event.accept()
    
    def dropEvent(self, event):
        """Handle drop event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
            self.drop_area.setProperty("dragActive", False)
            self.drop_area.style().unpolish(self.drop_area)
            self.drop_area.style().polish(self.drop_area)
            
            file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
            
            self._reset_ui_state()
            self._process_files(file_paths)
        else:
            event.ignore()
    
    def resizeEvent(self, event):
        """Handle resize event."""
        super().resizeEvent(event)
        
        if hasattr(self, 'preview_image') and self.preview_image.isVisible():
            margins = 10
            self.preview_image.setGeometry(
                margins,
                margins,
                self.drop_area.width() - (margins * 2),
                self.drop_area.height() - (margins * 2)
            )
    
    def closeEvent(self, event):
        """Handle window close event to save current model selection, abort workers, and clean temp files."""
        try:
            if hasattr(self.ui, 'modelComboBox') and self.ui.modelComboBox:
                current_model = self.ui.modelComboBox.currentText()
                if current_model:
                    set_selected_model(current_model)
            # No persistence for 'Ubah Levels' - it's GUI-only, so nothing else to save on close
        except Exception:
            pass

        # Attempt to gracefully abort any running workers/threads
        try:
            # Main processing worker
            try:
                if hasattr(self, 'worker') and self.worker:
                    try:
                        self.worker.abort = True
                    except Exception:
                        pass
                if hasattr(self, 'thread') and self.thread and getattr(self.thread, 'isRunning', lambda: False)():
                    try:
                        self.thread.quit()
                        self.thread.wait(500)
                    except Exception:
                        pass
            except Exception:
                pass

            # Mask worker
            try:
                if hasattr(self, '_mask_worker') and self._mask_worker:
                    try:
                        self._mask_worker.abort = True
                    except Exception:
                        pass
                if hasattr(self, '_mask_thread') and self._mask_thread and getattr(self._mask_thread, 'isRunning', lambda: False)():
                    try:
                        self._mask_thread.quit()
                        self._mask_thread.wait(500)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

        # Remove temporary files immediately to leave no leftover junk
        try:
            self._cleanup_temp_on_exit()
        except Exception:
            pass

        finally:
            super().closeEvent(event)
