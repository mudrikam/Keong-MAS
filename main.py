import os
import sys
import time
import tempfile
from pathlib import Path

# Add the current directory to the path so Python can find the APP module
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from PySide6.QtCore import Qt, QUrl, QSize, Signal, QThread, QObject, QRectF, QTimer
from PySide6.QtGui import QIcon, QGuiApplication, QImage, QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLabel, 
    QProgressBar, QMessageBox, QFrame, QWidget,
    QFileDialog, QPushButton, QCheckBox, QSizePolicy,
    QColorDialog, QSpinBox
)
from PySide6.QtUiTools import QUiLoader
import qtawesome as qta

# Import for Windows taskbar icon
import ctypes

import rembg
from PIL import Image
from APP.helpers import model_manager
from APP.helpers.config_manager import (
    get_auto_crop_enabled, set_auto_crop_enabled, 
    get_solid_bg_enabled, set_solid_bg_enabled,
    get_solid_bg_color, set_solid_bg_color,
    get_unified_margin, set_unified_margin,
    get_save_mask_enabled, set_save_mask_enabled
)
import json

# Worker class to handle background removal in a separate thread
class RemBgWorker(QObject):
    progress = Signal(int, str, str)  # Progress percentage, status message, and current file path
    finished = Signal(float, int)  # Send processing time and file count
    file_completed = Signal(str)  # Path to the completed file
    status_update = Signal(str)  # General status updates

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths
        self.abort = False
        self.start_time = 0
        self.processed_files_count = 0

    def process_files(self):
        self.start_time = time.time()
        self.processed_files_count = 0
        total_files = len(self.file_paths)
        processed = 0
        
        for file_path in self.file_paths:
            if self.abort:
                break
                
            try:
                # Check if it's an image file we can process                
                if Path(file_path).is_file() and Path(file_path).suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.bmp']:
                    self.process_image(file_path)
                    processed += 1
                    self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}", None)                
                elif Path(file_path).is_dir():
                    # Handle directories
                    image_files = self.get_image_files_in_dir(file_path)
                    for img_path in image_files:
                        if self.abort:
                            break                        
                        self.process_image(img_path)
                        processed += 1
                        self.progress.emit(int(processed / total_files * 100), f"File {processed}/{total_files}", None)
                else:
                    # Skip non-image files
                    processed += 1
                    self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}", None)
            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")                
                processed += 1
                self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}", None)
        
        processing_time = time.time() - self.start_time        
        self.finished.emit(processing_time, self.processed_files_count)
        
    def get_image_files_in_dir(self, directory):
        image_files = []
        for root, dirs, files in os.walk(directory):
            # Skip any directory named "PNG" (case-insensitive)
            if os.path.basename(root).upper() == "PNG":
                print(f"Skipping PNG output directory: {root}")
                continue
                
            # Skip processing inside PNG directories by removing them from the dirs list
            dirs[:] = [d for d in dirs if d.upper() != "PNG"]
            
            # Process image files
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                    image_files.append(os.path.join(root, file))
        return image_files      

    def process_image(self, image_path):
        try:
            # Create output directory
            output_dir = os.path.join(os.path.dirname(image_path), 'PNG')
            os.makedirs(output_dir, exist_ok=True)
            
            # Setup input and output paths
            input_path = Path(image_path)
            file_name = input_path.stem
            output_path = os.path.join(output_dir, f"{file_name}.png")
            mask_path = os.path.join(output_dir, f"{file_name}_mask.png")
              # Update status - preparing image
            status_msg = f"Menyiapkan: {file_name}"
            self.progress.emit(5, status_msg, image_path)
            
            # Import helper untuk progress bar
            from APP.helpers.ui_helpers import download_progress_callback
              # Gunakan model default
            self.progress.emit(10, f"Menyiapkan model: {os.path.basename(image_path)}", image_path)
            print(f"Menyiapkan model default...")
            model_name = model_manager.prepare_model(callback=download_progress_callback)
            print(f"Menggunakan model {model_name}")
            
            # Process with rembg for main transparent image            
            self.progress.emit(20, f"Memuat gambar: {os.path.basename(image_path)}", image_path)
            input_img = Image.open(image_path)
            
            try:                # Buat session untuk model dengan parameter yang lebih stabil
                print(f"Membuat session dengan model {model_name}...")                
                session = rembg.new_session(model_name)
                  # Generate the main transparent image
                self.progress.emit(30, f"Memproses: Menghapus latar belakang...", image_path)
                print(f"Menghapus latar belakang gambar...")
                input_size = input_img.size
                
                # Generate main transparent image with optimized parameters                
                # Setting alpha_matting_foreground_threshold and alpha_matting_background_threshold
                # can help avoid the Cholesky decomposition error
                self.progress.emit(40, f"Memproses: Menerapkan alpha matting...", image_path)
                output_img = rembg.remove(
                    input_img, 
                    alpha_matting=True,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=10,
                    alpha_matting_erode_size=10,
                    session=session
                )
                
                # Periksa ukuran output untuk mencegah hasil yang tidak normal
                output_size = output_img.size
                print(f"Ukuran input: {input_size[0]}x{input_size[1]}, ukuran output: {output_size[0]}x{output_size[1]}")
                if output_size[0] > input_size[0] * 2 or output_size[1] > input_size[1] * 2:
                    print(f"PERINGATAN: Ukuran output tidak normal! Menyesuaikan ukuran...")
                    output_img = output_img.resize(input_size, Image.LANCZOS)
                self.progress.emit(50, f"Menyimpan gambar transparan...", image_path)
                output_img.save(output_path)
                print(f"Gambar transparan disimpan ke {output_path}")
                  # Generate and save the mask separately
                self.progress.emit(60, f"Membuat mask...", image_path)
                print(f"Menghasilkan mask...")
                output_mask = rembg.remove(input_img, only_mask=True, session=session)
                
                # Pastikan mask memiliki ukuran yang sama dengan gambar input
                if output_mask.size != input_size:
                    print(f"PERINGATAN: Ukuran mask tidak sama dengan input! Menyesuaikan ukuran...")
                    output_mask = output_mask.resize(input_size, Image.LANCZOS)
                
                output_mask.save(mask_path)
                print(f"Mask disimpan ke {mask_path}")
            except Exception as e:
                print(f"Error saat memproses dengan rembg: {str(e)}")
                raise                
            # Import and use the image_utils helper to create a third enhanced image
            try:                    
                self.progress.emit(70, f"Menghasilkan gambar transparan yang disempurnakan...", image_path)
                from APP.helpers.image_utils import (
                    enhance_transparency, combine_with_mask, enhance_transparency_with_levels,
                    get_levels_config, cleanup_original_temp_files
                )
                from APP.helpers.config_manager import get_save_mask_enabled
                
                # Get the save_mask setting from config
                save_mask = get_save_mask_enabled()
                print(f"Save mask setting from config: {save_mask}")
                
                # Get default extreme levels values for sharper edges
                black_point, mid_point, white_point = get_levels_config(use_recommended=False)
                  # Rename our paths clearly for the four types of files
                original_transparent_path = output_path  # Already saved earlier
                original_mask_path = mask_path          # Already saved earlier
                
                # Setup paths for new files
                output_dir = os.path.dirname(image_path)
                file_name = input_path.stem
                adjusted_mask_path = os.path.join(output_dir, f"{file_name}_mask_adjusted.png")
                final_transparent_path = os.path.join(output_dir, f"{file_name}_transparent.png")
                  # Report status
                self.progress.emit(65, f"Menghasilkan mask yang diatur levels-nya...", image_path)
                print(f"Langkah 1: Menerapkan levels adjustment pada mask...")
                
                # Step 2: Create enhanced transparency image using the levels-adjusted mask
                self.progress.emit(80, f"Membuat gambar transparan dengan mask yang diatur levels...", image_path)
                print(f"Langkah 2: Membuat gambar transparan dengan mask yang sudah diatur levels-nya...")
                
                # Call the enhanced function passing the save_mask parameter
                # Set cleanup_temp_files_after to False so we can control cleanup timing
                enhanced_path = enhance_transparency_with_levels(
                    original_transparent_path, original_mask_path,
                    output_suffix="_transparent", 
                    black_point=black_point, mid_point=mid_point, white_point=white_point,
                    save_adjusted_mask=True,  # Always create the adjusted mask initially
                    cleanup_temp_files_after=False,  # Don't clean up yet - we need the mask for later steps
                    save_mask=save_mask  # This will be used at final cleanup
                )
                
                print(f"Berhasil membuat gambar dengan levels adjustment: {enhanced_path}")
                
                # If there was a problem with the levels adjustment (rare), we have alternative methods
                if not enhanced_path:
                    print(f"Levels adjustment tidak berhasil, menggunakan metode standar...")
                    enhanced_path = combine_with_mask(original_transparent_path, original_mask_path, output_suffix="_transparent")
                    print(f"Berhasil membuat gambar dengan metode standar: {enhanced_path}")
                
                # Summary of files saved
                print(f"File yang disimpan:")
                print(f"1. Gambar transparan asli: {original_transparent_path}")
                print(f"2. Mask asli: {original_mask_path}")
                print(f"3. Mask yang diatur levels: {os.path.join(output_dir, f'{file_name}_mask_adjusted.png')}")
                print(f"4. Gambar transparan final: {enhanced_path}")
                
                # Apply auto-cropping if enabled in settings
                try:
                    from APP.helpers.image_crop import crop_transparent_image
                    from APP.helpers.config_manager import get_auto_crop_enabled, get_unified_margin
                    
                    auto_crop_enabled = get_auto_crop_enabled()
                    if auto_crop_enabled:
                        self.progress.emit(90, f"Melakukan auto crop...", image_path)
                        print(f"Auto crop enabled (dari config.json), cropping image...")
                        
                        # Correctly determine the adjusted mask path
                        # First, check if we're already in a PNG folder
                        mask_dir = os.path.dirname(original_mask_path)
                        
                        # Make sure to use the PNG directory for the adjusted mask
                        if os.path.basename(mask_dir).upper() == 'PNG':
                            # Already in PNG folder
                            png_dir = mask_dir
                        else:
                            # Need to use the PNG subfolder
                            png_dir = os.path.join(os.path.dirname(original_mask_path), 'PNG')
                        
                        # Use same filename logic as in image_utils.py
                        mask_to_use = os.path.join(png_dir, f'{file_name}_mask_adjusted.png')
                        
                        print(f"Looking for adjusted mask at: {mask_to_use}")
                        
                        # Get the unified margin value
                        unified_margin = get_unified_margin()
                        print(f"Using unified margin: {unified_margin}px (dari config.json)")
                        
                        # Apply cropping with explicit margin parameter
                        cropped_path = crop_transparent_image(
                            enhanced_path if enhanced_path else original_transparent_path, 
                            mask_to_use, 
                            output_path=None,  # Overwrite the input file
                            threshold=unified_margin  # Use unified margin value directly
                        )
                        
                        if cropped_path:
                            print(f"5. Auto-cropped image saved at: {cropped_path}")
                            # Update our reference to the final image path
                            enhanced_path = cropped_path
                    else:
                        print(f"Auto crop disabled (dari config.json), skipping crop step")
                except Exception as crop_error:
                    print(f"Warning: Auto crop error: {str(crop_error)}")
                    
                    # Still try to do cleanup if crop failed
                    if not save_mask:
                        png_dir = os.path.dirname(enhanced_path) if enhanced_path else os.path.dirname(original_transparent_path)
                        mask_path_adjusted = os.path.join(png_dir, f"{file_name}_mask_adjusted.png")
                        if os.path.exists(mask_path_adjusted):
                            try:
                                os.remove(mask_path_adjusted)
                                print(f"Removed mask file after crop error: {mask_path_adjusted}")
                            except:
                                pass
                    
                    # Always clean up the original temp files
                    cleanup_original_temp_files(original_transparent_path, original_mask_path)
                
                # After processing auto crop, add solid background if enabled
                try:
                    from APP.helpers.solid_background import add_solid_background
                    
                    # Get unified margin directly from config
                    unified_margin = get_unified_margin()
                    
                    # Always pass the enhanced path to the solid background function 
                    # which will automatically use the _transparent.png version
                    solid_bg_path = add_solid_background(enhanced_path, margin=unified_margin)
                    
                    if solid_bg_path:
                        print(f"6. Image with solid background saved at: {solid_bg_path} (margin: {unified_margin}px)")
                except Exception as bg_error:
                    print(f"Warning: Solid background error: {str(bg_error)}")
                    import traceback
                    traceback.print_exc()
                    
                    # Still try to do cleanup even if solid background failed
                    if not save_mask:
                        png_dir = os.path.dirname(enhanced_path)
                        mask_path_adjusted = os.path.join(png_dir, f"{file_name}_mask_adjusted.png")
                        if os.path.exists(mask_path_adjusted):
                            try:
                                os.remove(mask_path_adjusted)
                                print(f"Removed mask file after solid bg error: {mask_path_adjusted}")
                            except:
                                pass
                            
                    # Always clean up the original temp files
                    cleanup_original_temp_files(original_transparent_path, original_mask_path)
                
                # Now do final cleanup after all operations that need the mask are complete
                # Get the full mask path for cleanup
                png_dir = os.path.dirname(enhanced_path)
                mask_path_adjusted = os.path.join(png_dir, f"{file_name}_mask_adjusted.png")
                
                # Only clean up the adjusted mask if save_mask is False
                if not save_mask and os.path.exists(mask_path_adjusted):
                    print(f"Cleaning up adjusted mask: {mask_path_adjusted}")
                    try:
                        os.remove(mask_path_adjusted)
                        print(f"Removed mask file: {mask_path_adjusted}")
                    except Exception as rm_err:
                        print(f"Error removing mask file: {str(rm_err)}")
                else:
                    print(f"Keeping mask file: {mask_path_adjusted} (save_mask={save_mask})")
                
                # Always clean up the original temp files
                cleanup_original_temp_files(original_transparent_path, original_mask_path)
                
                # Always emit the path to the final transparent PNG for preview
                png_dir = os.path.dirname(enhanced_path)
                final_transparent_path = os.path.join(png_dir, f"{file_name}_transparent.png")
                
                # If the final transparent PNG exists, use it for preview
                if os.path.exists(final_transparent_path):
                    self.file_completed.emit(final_transparent_path)
                    print(f"Emitting file_completed with final transparent PNG: {final_transparent_path}")
                else:
                    # Fallback to the enhanced path if the final transparent doesn't exist
                    self.file_completed.emit(enhanced_path if enhanced_path else original_transparent_path)
                    print(f"Emitting file_completed with fallback path: {enhanced_path}")
                    
                model_info = f" (model: {model_name})" if 'model_name' in locals() else ""
                print(f"Semua pemrosesan selesai{model_info}")
                
            except Exception as e:
                print(f"Error saat membuat gambar transparan: {str(e)}")
                enhanced_path = None
                self.file_completed.emit(output_path)
            
            self.processed_files_count += 1
        except Exception as e:
            print(f"Error removing background from {image_path}: {str(e)}")

class ScalableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.image_path = None
        self.rounded_pixmap = None
        # Set size policy to allow the widget to shrink
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Remove background styling, only keep minimal padding
        self.setStyleSheet("""
            QLabel {
                padding: 5px;
                background-color: transparent;
            }
        """)
        
    def setImagePath(self, path):
        """Menyimpan path gambar dan memuat pixmap original"""
        if not os.path.exists(path):
            return False
            
        # Ensure path is a string to avoid any type issues
        self.image_path = str(path)
        self.original_pixmap = QPixmap(self.image_path)
        self.updatePixmap()
        return not self.original_pixmap.isNull()
        
    def updatePixmap(self):
        """Menyesuaikan ukuran gambar sesuai dengan ukuran label"""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Handle potential zero-sized widget
            width = max(10, self.width() - 24)  # Account for padding and border
            height = max(10, self.height() - 24)
            
            # Create a scaled version of the pixmap
            self.scaled_pixmap = self.original_pixmap.scaled(
                width, 
                height,
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # Don't set the pixmap directly - we'll draw it in paintEvent
            self.setMinimumSize(100, 100)
            self.update()  # Force a repaint
    
    def paintEvent(self, event):
        """Override paint event to draw rounded image"""
        super().paintEvent(event)
        
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap and not self.scaled_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Calculate centered position
            pixmap_rect = self.scaled_pixmap.rect()
            x = (self.width() - pixmap_rect.width()) // 2
            y = (self.height() - pixmap_rect.height()) // 2
            
            # Create a rounded rect path with stronger radius
            radius = 20  # Increased border radius for the image
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(x, y, pixmap_rect.width(), pixmap_rect.height()),
                radius, radius
            )
            
            # Set the clipping path to the rounded rectangle
            painter.setClipPath(path)
            
            # Draw the pixmap inside the clipping path
            painter.drawPixmap(x, y, self.scaled_pixmap)
    
    def resizeEvent(self, event):
        """Event yang terpanggil saat widget di-resize"""
        super().resizeEvent(event)
        self.updatePixmap()
        
    # Override size hint methods to allow widget to shrink
    def sizeHint(self):
        return QSize(200, 200)
        
    def minimumSizeHint(self):
        return QSize(10, 10)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Load UI from file
        loader = QUiLoader()
        ui_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "APP", "gui", "main_window.ui")
        self.ui = loader.load(ui_file_path)
        
        # Set window properties
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.minimumSize())
        self.resize(self.ui.size())
        
        # Set icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "APP", "res", "Keong-MAS.ico")
        self.setWindowIcon(QIcon(icon_path))
        
        # Setup central widget
        self.setCentralWidget(QWidget())
        self.centralWidget().setLayout(QVBoxLayout())
        self.centralWidget().layout().addWidget(self.ui)
        
        # Set icons on buttons using QtAwesome
        self.setup_button_icons()
        
        # Access the drop area frame
        self.drop_area = self.ui.findChild(QFrame, "drop_area_frame")
        self.drop_area.setAcceptDrops(False)  # We'll handle drops at the main window level
        
        # Create image preview label (initially hidden)
        self.preview_image = ScalableImageLabel(self.drop_area)
        # Position the preview image in the center of the drop area with margins
        margins = 20
        self.preview_image.setGeometry(
            margins, 
            margins + 40, # Extra space for the labels at the top
            self.drop_area.width() - (margins * 2), 
            self.drop_area.height() - (margins * 2) - 80 # Additional margin for labels
        )
        self.preview_image.hide()  # Hide initially
        
        # Access the drag and drop labels for modification during processing
        self.dnd_label_1 = self.ui.findChild(QLabel, "dnd_label_1")
        self.dnd_label_2 = self.ui.findChild(QLabel, "dnd_label_2")
        self.dnd_label_3 = self.ui.findChild(QLabel, "dnd_label_3")
        
        # Store original text for reverting
        if self.dnd_label_1 and self.dnd_label_2 and self.dnd_label_3:
            self.original_label1_text = self.dnd_label_1.text()
            self.original_label2_text = self.dnd_label_2.text()
            self.original_label3_text = self.dnd_label_3.text()
        
        # Create progress bar (hidden by default)
        self.progress_bar = QProgressBar(self.ui)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v / %m")
        self.progress_bar.hide()
        
        # Insert progress bar above the drop area (not replacing it)
        # Find the drop area's parent layout
        parent_layout = self.drop_area.parentWidget().layout()
        drop_area_index = parent_layout.indexOf(self.drop_area)
        
        # Insert the progress bar before the drop area
        parent_layout.insertWidget(drop_area_index, self.progress_bar)
        
        # Setup drag and drop
        self.setAcceptDrops(True)        # Connect the Open Folder and Open Files buttons
        self.open_folder_btn = self.ui.findChild(QPushButton, "openFolder")
        self.open_files_btn = self.ui.findChild(QPushButton, "openFiles")
        self.stop_button = self.ui.findChild(QPushButton, "stopButton")
        if self.stop_button:
            self.stop_button.setEnabled(False)
            self.stop_button.setStyleSheet("""
                QPushButton:enabled { background-color: #e74c3c; }
            """)
            self.stop_button.clicked.connect(self.on_stop_clicked)
        
        if self.open_folder_btn:
            self.open_folder_btn.clicked.connect(self.open_folder_dialog)
        
        if self.open_files_btn:
            self.open_files_btn.clicked.connect(self.open_files_dialog)
        
        # Connect the checkbox for auto crop setting
        self.auto_crop_checkbox = self.ui.findChild(QCheckBox, "checkBox")
        if self.auto_crop_checkbox:
            # Add tooltip to explain what the checkbox does
            self.auto_crop_checkbox.setToolTip(
                "Ketika diaktifkan, gambar akan otomatis dipotong untuk menghilangkan ruang kosong di sekitar objek.\n"
                "Pengaturan ini disimpan dalam config.json."
            )
            
            # Load and set the initial checkbox state from config
            is_auto_crop_enabled = get_auto_crop_enabled()
            print(f"Initial auto crop setting from config.json: {is_auto_crop_enabled}")
            
            # Block signals during initial setup to prevent triggering stateChanged
            self.auto_crop_checkbox.blockSignals(True)
            self.auto_crop_checkbox.setChecked(is_auto_crop_enabled)
            self.auto_crop_checkbox.blockSignals(False)
            
            # Connect checkbox state change to save configuration
            self.auto_crop_checkbox.stateChanged.connect(self.on_auto_crop_changed)
        
        # Connect the solid background controls
        self.solid_bg_checkbox = self.ui.findChild(QCheckBox, "solidBgCheckBox")
        self.color_picker_button = self.ui.findChild(QPushButton, "colorPickerButton")
        self.unified_margin_spinbox = self.ui.findChild(QSpinBox, "unifiedMarginSpinBox")
        
        if self.solid_bg_checkbox and self.color_picker_button:
            # Load initial values from config
            is_solid_bg_enabled = get_solid_bg_enabled()
            current_color = get_solid_bg_color()
            
            # Set up tooltip
            self.solid_bg_checkbox.setToolTip(
                "Ketika diaktifkan, gambar transparant akan dibuatkan versi dengan latar belakang solid.\n"
                "Pengaturan ini disimpan dalam config.json."
            )
            
            # Set initial control states
            self.solid_bg_checkbox.blockSignals(True)
            self.solid_bg_checkbox.setChecked(is_solid_bg_enabled)
            self.solid_bg_checkbox.blockSignals(False)
            
            # Set the color button background color
            self.update_color_button(current_color)
            
            # Connect signals
            self.solid_bg_checkbox.stateChanged.connect(self.on_solid_bg_changed)
            self.color_picker_button.clicked.connect(self.on_color_picker_clicked)
            
            # Update control states based on checkbox
            self.update_solid_bg_controls()
        
        # Connect the unified margin control
        if self.unified_margin_spinbox:
            # Load initial value from config
            current_margin = get_unified_margin()
            
            # Set the initial value
            self.unified_margin_spinbox.blockSignals(True)
            self.unified_margin_spinbox.setValue(current_margin)
            self.unified_margin_spinbox.blockSignals(False)
            
            # Connect signal
            self.unified_margin_spinbox.valueChanged.connect(self.on_unified_margin_changed)
        
        # Connect the save mask checkbox
        self.save_mask_checkbox = self.ui.findChild(QCheckBox, "saveMaskCheckBox")
        if self.save_mask_checkbox:
            # Set up tooltip
            self.save_mask_checkbox.setToolTip(
                "Ketika diaktifkan, file mask akan disimpan bersama output gambar.\n"
                "Jika dinonaktifkan, file mask akan dihapus."
            )
            
            # Load and set initial state
            is_save_mask_enabled = get_save_mask_enabled()
            print(f"Initial save mask setting from config.json: {is_save_mask_enabled}")
            
            # Block signals during initial setup
            self.save_mask_checkbox.blockSignals(True)
            self.save_mask_checkbox.setChecked(is_save_mask_enabled)
            self.save_mask_checkbox.blockSignals(False)
            
            # Connect the signal
            self.save_mask_checkbox.stateChanged.connect(self.on_save_mask_changed)
        
        # Worker thread for processing
        self.worker = None
        self.thread = None

    def setup_button_icons(self):
        """Setup icons for all buttons using QtAwesome"""
        # Find all required buttons
        self.open_folder_btn = self.ui.findChild(QPushButton, "openFolder")
        self.open_files_btn = self.ui.findChild(QPushButton, "openFiles")
        self.stop_button = self.ui.findChild(QPushButton, "stopButton")
        self.color_picker_button = self.ui.findChild(QPushButton, "colorPickerButton")
        self.whatsapp_button = self.ui.findChild(QPushButton, "whatsappButton")
        
        # Set icons with proper sizing
        if self.open_folder_btn:
            folder_icon = qta.icon('fa5s.folder-open')
            self.open_folder_btn.setIcon(folder_icon)
            self.open_folder_btn.setIconSize(QSize(16, 16))
        
        if self.open_files_btn:
            files_icon = qta.icon('fa5s.file-image')
            self.open_files_btn.setIcon(files_icon)
            self.open_files_btn.setIconSize(QSize(16, 16))
        
        if self.stop_button:
            stop_icon = qta.icon('fa5s.stop')
            self.stop_button.setIcon(stop_icon)
            self.stop_button.setIconSize(QSize(16, 16))
            self.stop_button.setEnabled(False)
            self.stop_button.setStyleSheet("""
                QPushButton:enabled { background-color: #e74c3c; }
            """)
        
        if self.color_picker_button:
            # Set the eyedropper icon to black for better visibility on light backgrounds
            eyedropper_icon = qta.icon('fa5s.eye-dropper', color='black')
            self.color_picker_button.setIcon(eyedropper_icon)
            self.color_picker_button.setIconSize(QSize(16, 16))
        
        if self.whatsapp_button:
            whatsapp_icon = qta.icon('fa5b.whatsapp', color='#25D366')
            self.whatsapp_button.setIcon(whatsapp_icon)
            self.whatsapp_button.setIconSize(QSize(16, 16))
            self.whatsapp_button.clicked.connect(self.open_whatsapp)
    
    def open_whatsapp(self):
        """Open WhatsApp with the provided group link"""
        try:
            # Use the provided WhatsApp group link
            whatsapp_url = "https://chat.whatsapp.com/CMQvDxpCfP647kBBA6dRn3"
            
            # Use QUrl to open the URL in the default browser
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(whatsapp_url))
        except Exception as e:
            print(f"Error opening WhatsApp: {str(e)}")

    def update_color_button(self, color_hex):
        """Update the color button background to match the selected color"""
        if self.color_picker_button:
            style = f"background-color: {color_hex}; border: 1px solid #888;"
            self.color_picker_button.setStyleSheet(style)
    
    def update_solid_bg_controls(self):
        """Update the enabled state of solid background controls"""
        if hasattr(self, 'solid_bg_checkbox') and self.solid_bg_checkbox:
            is_enabled = self.solid_bg_checkbox.isChecked()
            
            if hasattr(self, 'color_picker_button') and self.color_picker_button:
                self.color_picker_button.setEnabled(is_enabled)
    
    def on_solid_bg_changed(self, state):
        """Handle solid background checkbox state change"""
        is_checked = (state != 0)  # Consider anything not "Unchecked" as checked
        
        print(f"Solid background checkbox changed - Raw state: {state}, Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            # Update the config
            if set_solid_bg_enabled(is_checked):
                print(f"Solid background {'enabled' if is_checked else 'disabled'} and saved to config")
                print(f"Solid background {'diaktifkan' if is_checked else 'dinonaktifkan'} dan disimpan")
                
                # Update control states
                self.update_solid_bg_controls()
                
                # Verify setting
                current = get_solid_bg_enabled()
                if current != is_checked:
                    print(f"WARNING: Config value doesn't match expected value!")
                    self.solid_bg_checkbox.blockSignals(True)
                    self.solid_bg_checkbox.setChecked(current)
                    self.solid_bg_checkbox.blockSignals(False)
                    self.update_solid_bg_controls()
        except Exception as e:
            print(f"Error updating solid background setting: {str(e)}")
    
    def on_color_picker_clicked(self):
        """Open color picker dialog when the color button is clicked"""
        try:
            # Get current color from config
            current_color = get_solid_bg_color()
            initial_color = QColor(current_color)
            
            # Open color dialog
            color = QColorDialog.getColor(initial_color, self, "Select Background Color")
            
            # If a valid color was selected
            if color.isValid():
                # Convert to hex format
                color_hex = color.name().upper()
                
                # Save to config
                if set_solid_bg_color(color_hex):
                    print(f"Background color set to {color_hex} and saved to config")
                    print(f"Background color set to {color_hex}")
                    
                    # Update button appearance
                    self.update_color_button(color_hex)
        except Exception as e:
            print(f"Error setting background color: {str(e)}")
    
    def on_unified_margin_changed(self, value):
        """Handle unified margin spinbox value change"""
        try:
            # Save the new margin value to config
            if set_unified_margin(value):
                print(f"Unified margin set to {value}px and saved to config")
                print(f"Margin set to {value}px for all operations")
        except Exception as e:
            print(f"Error setting unified margin: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_save_mask_changed(self, state):
        """Handle save mask checkbox state change"""
        is_checked = (state != 0)  # Consider anything not "Unchecked" as checked
        
        print(f"Save mask checkbox changed - Raw state: {state}, Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            # Update the config
            if set_save_mask_enabled(is_checked):
                print(f"Save mask {'enabled' if is_checked else 'disabled'} and saved to config")
                print(f"Save mask {'diaktifkan' if is_checked else 'dinonaktifkan'} dan disimpan")
                
                # Verify setting
                current = get_save_mask_enabled()
                if current != is_checked:
                    print(f"WARNING: Config value doesn't match expected value!")
                    self.save_mask_checkbox.blockSignals(True)
                    self.save_mask_checkbox.setChecked(current)
                    self.save_mask_checkbox.blockSignals(False)
        except Exception as e:
            print(f"Error updating save mask setting: {str(e)}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.drop_area.setProperty("dragActive", True)
            self.drop_area.style().unpolish(self.drop_area)
            self.drop_area.style().polish(self.drop_area)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_area.setProperty("dragActive", False)
        self.drop_area.style().unpolish(self.drop_area)
        self.drop_area.style().polish(self.drop_area)
        event.accept()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.drop_area.setProperty("dragActive", False)
            self.drop_area.style().unpolish(self.drop_area)
            self.drop_area.style().polish(self.drop_area)
            
            # Get dropped files/folders
            file_paths = []
            for url in event.mimeData().urls():
                file_paths.append(url.toLocalFile())
            
            # Start processing
            if file_paths:
                # Reset UI state before starting new processing
                self.reset_ui_state()
                self.process_files(file_paths)
        else:
            event.ignore()    
    def process_files(self, file_paths):
        # Show progress bar without hiding drop area
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        
        # Hide the drop instructions and show waiting message
        if hasattr(self, 'dnd_label_1') and self.dnd_label_1:
            self.dnd_label_1.setText("Memproses Gambar...")
        
        if hasattr(self, 'dnd_label_2') and self.dnd_label_2:
            self.dnd_label_2.setText("Mohon tunggu sebentar")
        
        if hasattr(self, 'dnd_label_3') and self.dnd_label_3:
            self.dnd_label_3.setText("")
            
        # Hide the preview image while starting new process
        if hasattr(self, 'preview_image'):
            self.preview_image.hide()
            
        # Enable the stop button during processing
        if hasattr(self, 'stop_button') and self.stop_button:
            self.stop_button.setEnabled(True)
        
        # Create worker and thread
        self.worker = RemBgWorker(file_paths)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        # Connect signals
        self.thread.started.connect(self.worker.process_files)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.progress.connect(self.update_progress)
        self.worker.file_completed.connect(self.on_file_completed)
        
        # Start processing
        self.thread.start()

    def update_progress(self, value, message="", current_file_path=None):
        self.progress_bar.setValue(value)
        if message:
            self.progress_bar.setFormat(f"{value}% - {message}")
            
            # Update the second label with the current file name
            if hasattr(self, 'dnd_label_2') and self.dnd_label_2:
                # Extract just the filename if it's a full path
                if ":" in message and os.path.sep in message:
                    # Try to extract just the filename part
                    try:
                        filename = message.split(os.path.sep)[-1]
                        if len(filename) > 0:
                            message = filename
                    except:
                        pass  # Keep the original message if parsing fails
                self.dnd_label_2.setText(message)
                
        # If this update includes a current processing file path, update the preview
        if current_file_path and hasattr(self, 'preview_image'):
            # Check if it's a valid file path and exists
            if os.path.exists(current_file_path):
                self.update_preview_image(current_file_path)    
    def update_preview_image(self, file_path):
        """Update the preview image to show the file that is currently being processed"""
        # Hide all labels when showing preview
        if hasattr(self, 'dnd_label_1') and self.dnd_label_1:
            self.dnd_label_1.hide()
        
        if hasattr(self, 'dnd_label_2') and self.dnd_label_2:
            self.dnd_label_2.hide()
        
        if hasattr(self, 'dnd_label_3') and self.dnd_label_3:
            self.dnd_label_3.hide()
            
        # Position and size the preview image to fill the entire drop area
        margins = 10
        self.preview_image.setGeometry(
            margins, 
            margins, 
            self.drop_area.width() - (margins * 2), 
            self.drop_area.height() - (margins * 2)
        )
        
        # Load the image and show it
        if self.preview_image.setImagePath(file_path):            
            self.preview_image.show()
            print(f"Showing preview for current processing file: {os.path.basename(file_path)}")

    def on_file_completed(self, file_path):
        """When a file has been processed, update the preview"""
        # Show preview of the completed file
        if os.path.exists(file_path) and hasattr(self, 'preview_image'):
            # Hide all labels in the drop area
            if hasattr(self, 'dnd_label_1') and self.dnd_label_1:
                self.dnd_label_1.hide()
            
            if hasattr(self, 'dnd_label_2') and self.dnd_label_2:
                self.dnd_label_2.hide()
                
            if hasattr(self, 'dnd_label_3') and self.dnd_label_3:
                self.dnd_label_3.hide()
                
            # Properly size and position the preview image
            margins = 10
            self.preview_image.setGeometry(
                margins, 
                margins, 
                self.drop_area.width() - (margins * 2), 
                self.drop_area.height() - (margins * 2)
            )
            
            print(f"Attempting to load preview image from: {file_path}")
            
            # Load the image and show it
            if self.preview_image.setImagePath(file_path):
                self.preview_image.show()
                print(f"Showing final preview for: {os.path.basename(file_path)}")
            else:
                print(f"Failed to load preview image from: {file_path}")
                
                # Try finding alternative paths if the main one fails
                if "_transparent.png" not in file_path:
                    base_dir = os.path.dirname(file_path)
                    file_name = os.path.splitext(os.path.basename(file_path))[0]
                    alt_path = os.path.join(base_dir, f"{file_name}_transparent.png")
                    
                    if os.path.exists(alt_path) and self.preview_image.setImagePath(alt_path):
                        self.preview_image.show()
                        print(f"Showing alternative preview for: {os.path.basename(alt_path)}")

    def resizeEvent(self, event):
        """Event that triggers when the main window is resized"""
        super().resizeEvent(event)
        
        # Update the preview image geometry if it's visible
        if hasattr(self, 'preview_image') and self.preview_image.isVisible():
            margins = 20
            label_height = 40 if hasattr(self, 'dnd_label_1') and self.dnd_label_1 else 0
            self.preview_image.setGeometry(
                margins, 
                margins + label_height, 
                self.drop_area.width() - (margins * 2), 
                self.drop_area.height() - (margins * 2) - (label_height * 2)
            )
    
    def on_processing_finished(self, processing_time, file_count):
        # Cleanup with proper thread termination
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(3000):  # Wait 3 seconds max
                print("WARNING: Thread did not terminate properly, forcing termination")
                self.thread.terminate()
                self.thread.wait()
        
        self.thread = None
        self.worker = None
        
        # Hide progress bar without affecting drop area
        self.progress_bar.hide()
        
        # Disable the stop button
        if hasattr(self, 'stop_button') and self.stop_button:
            self.stop_button.setEnabled(False)
            print("Stop button disabled after processing completed")
        
        # Calculate minutes and seconds
        minutes = int(processing_time // 60)
        seconds = int(processing_time % 60)
        
        # Format time string in Indonesian
        if minutes > 0:
            time_str = f"{minutes} menit {seconds} detik"
        else:
            time_str = f"{seconds} detik"
        
        # Retrieve the success message setting from config
        show_full_message = True
        try:
            # Load config file to check if we should show full message
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.loads(f.read())
                    show_full_message = config.get("show_success_stats", True)
        except Exception as e:
            print(f"Error reading config for success message: {e}")
        
        # Notify user with statistics in Indonesian
        if show_full_message:
            QMessageBox.information(
                self, 
                "Proses Selesai", 
                f"Semua gambar telah diproses dan disimpan di folder PNG.\n\n"
                f"Statistik Proses:\n"
                f"• Jumlah file: {file_count} gambar\n"
                f"• Waktu proses: {time_str}"
            )
        
        # The preview will remain visible after processing, but we'll provide a way to start new processes

    def reset_ui_state(self):
        """Reset the UI to its original state for new processing"""
        # Hide the preview image
        if hasattr(self, 'preview_image'):
            self.preview_image.hide()
            
        # Reset label texts to original values and make them visible
        if hasattr(self, 'dnd_label_1') and self.dnd_label_1 and hasattr(self, 'original_label1_text'):
            self.dnd_label_1.setText(self.original_label1_text)
            self.dnd_label_1.show()
            
        if hasattr(self, 'dnd_label_2') and self.dnd_label_2 and hasattr(self, 'original_label2_text'):
            self.dnd_label_2.setText(self.original_label2_text)
            self.dnd_label_2.show()
            
        if hasattr(self, 'dnd_label_3') and self.dnd_label_3 and hasattr(self, 'original_label3_text'):
            self.dnd_label_3.setText(self.original_label3_text)
            self.dnd_label_3.show()
            
        # Disable stop button if it exists
        if hasattr(self, 'stop_button') and self.stop_button:
            self.stop_button.setEnabled(False)
            
    def open_folder_dialog(self):
        """Handles the Open Folder button click by opening a folder dialog"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Pilih Folder Gambar",
            os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly
        )
        
        if folder_path:
            # Reset UI state before starting new processing
            self.reset_ui_state()
            # Start processing using the same method as for drag and drop
            self.process_files([folder_path])
            
    def open_files_dialog(self):
        """Handles the Open Files button click by opening a file dialog"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Pilih Gambar",
            os.path.expanduser("~"),
            "Gambar (*.jpg *.jpeg *.png *.bmp *.webp)"
        )
        
        if file_paths:
            # Reset UI state before starting new processing
            self.reset_ui_state()
            # Start processing using the same method as for drag and drop
            self.process_files(file_paths)

    def on_auto_crop_changed(self, state):
        """Handles the Auto Crop Background checkbox state change"""
        # In Qt, CheckState has these values:
        # Qt.Unchecked = 0
        # Qt.PartiallyChecked = 1 
        # Qt.Checked = 2
        is_checked = (state != 0)  # Consider anything not "Unchecked" as checked
        
        print(f"Checkbox state changed - Raw state: {state}, Interpreted as: {'checked' if is_checked else 'unchecked'}")
        
        try:
            # Update the config file with the new setting
            if set_auto_crop_enabled(is_checked):
                print(f"Auto crop setting {'enabled' if is_checked else 'disabled'} and saved to config")
                
                # Show a brief notification that the setting was saved
                print(f"Auto crop {'diaktifkan' if is_checked else 'dinonaktifkan'} dan disimpan")
                
                # Verify the setting was saved by reading it back
                current = get_auto_crop_enabled()
                print(f"Verified setting in config: {'enabled' if current else 'disabled'}")
                
                # Check if the values match
                if current != is_checked:
                    print(f"WARNING: Config value doesn't match expected value!")
                    # Force checkbox to match config
                    self.auto_crop_checkbox.blockSignals(True)
                    self.auto_crop_checkbox.setChecked(current)
                    self.auto_crop_checkbox.blockSignals(False)
            else:
                print(f"Failed to save auto crop setting to config")
                
                # If saving failed, revert the checkbox to match the current setting
                current_setting = get_auto_crop_enabled()
                if current_setting != is_checked:
                    print(f"Reverting checkbox to match config: {current_setting}")
                    self.auto_crop_checkbox.blockSignals(True)
                    self.auto_crop_checkbox.setChecked(current_setting)
                    self.auto_crop_checkbox.blockSignals(False)
        except Exception as e:
            print(f"Error in on_auto_crop_changed: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_stop_clicked(self):
        """Handle the Stop button click"""
        if hasattr(self, 'worker') and self.worker:
            # Set the abort flag to True
            self.worker.abort = True
            
            # Disable the stop button (will be re-enabled in next process)
            if hasattr(self, 'stop_button') and self.stop_button:
                self.stop_button.setEnabled(False)
                
            print("Processing aborted by user")
            
            # Show a short message
            QMessageBox.information(self, "Proses Dihentikan", "Proses penghapusan latar belakang telah dihentikan.")
            
            # Reset UI after a short delay
            QTimer.singleShot(500, self.reset_ui_state)

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set application ID for Windows taskbar icon
    if sys.platform == 'win32':
        # This is needed to display the app icon on the taskbar
        myappid = 'keongmas.backgroundremover.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()