"""Main UI layout creation for Keong-MAS."""

from PySide6.QtCore import Qt, QSize
import qtawesome as qta
import os
import json
from PySide6.QtGui import QPixmap, QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QCheckBox, QSpinBox, QSlider, QGroupBox, QSplitter, QComboBox
)
from APP.widgets import FileTableWidget, ImagePreviewWidget
from APP.widgets.multi_handle_slider import MultiHandleSlider
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton


def create_main_ui(parent):
    """Create and return the main UI layout."""
    central_widget = QWidget(parent)
    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(10, 10, 10, 10)
    
    # Content area (DND or Split View)
    content_stack = QWidget()
    content_layout = QVBoxLayout(content_stack)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(0)
    
    drop_area = _create_drop_area()
    content_layout.addWidget(drop_area, 1)  # Stretch factor 1
    
    split_view = _create_split_view()
    split_view.hide()
    content_layout.addWidget(split_view, 1)  # Stretch factor 1
    
    main_layout.addWidget(content_stack, 1)  # Stretch factor 1
    
    controls_container, controls_dict = _create_controls()
    main_layout.addWidget(controls_container)
    
    menu_bar = parent.menuBar()

    file_menu = menu_bar.addMenu('File')
    action_open_folder = QAction('Buka Folder', parent)
    action_open_folder.setObjectName('actionOpenFolder')
    action_open_folder.setIcon(qta.icon('fa5s.folder-open'))
    file_menu.addAction(action_open_folder)
    action_open_files = QAction('Pilih File', parent)
    action_open_files.setObjectName('actionOpenFiles')
    action_open_files.setIcon(qta.icon('fa5s.images'))
    file_menu.addAction(action_open_files)
    file_menu.addSeparator()
    action_exit = QAction('Tutup', parent)
    action_exit.setObjectName('actionExit')
    action_exit.setIcon(qta.icon('fa5s.sign-out-alt'))
    file_menu.addAction(action_exit)

    output_menu = menu_bar.addMenu('Output')
    action_output_folder = QAction('Folder Output', parent)
    action_output_folder.setObjectName('actionOutputFolder')
    action_output_folder.setIcon(qta.icon('fa5s.folder'))
    output_menu.addAction(action_output_folder)

    model_menu = menu_bar.addMenu('Model')
    action_show_model_dialog = QAction('Pilih Model...', parent)
    action_show_model_dialog.setObjectName('actionShowModelDialog')
    action_show_model_dialog.setIcon(qta.icon('fa5s.cogs'))
    model_menu.addAction(action_show_model_dialog)

    help_menu = menu_bar.addMenu('About')
    action_about = QAction('Tentang', parent)
    action_about.setObjectName('actionAbout')
    action_about.setIcon(qta.icon('fa5s.info-circle'))
    help_menu.addAction(action_about)
    action_wa_group = QAction('Grup WA', parent)
    action_wa_group.setObjectName('actionWAGroup')
    action_wa_group.setIcon(qta.icon('fa5b.whatsapp', color='#25D366'))
    help_menu.addAction(action_wa_group)

    # Model selection dialog
    class ModelDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle('Pilih Model')
            self.setModal(True)
            layout = QVBoxLayout(self)
            self.label = QLabel('Pilih model untuk segmentasi:')
            layout.addWidget(self.label)
            self.combo = QComboBox(self)
            self.combo.setFixedWidth(260)
            self.combo.setObjectName('modelDialogCombo')
            layout.addWidget(self.combo)

            btn_row = QHBoxLayout()
            btn_row.addStretch()

            self.save_btn = QPushButton('Simpan')
            self.save_btn.setObjectName('saveModelButton')
            self.save_btn.setIcon(qta.icon('fa5s.check'))
            self.save_btn.setIconSize(QSize(12, 12))
            self.save_btn.setFixedHeight(26)
            self.save_btn.setFixedWidth(84)
            btn_row.addWidget(self.save_btn)

            layout.addLayout(btn_row)

            self.save_btn.clicked.connect(self.accept)

        def set_models(self, models):
            self.combo.clear()
            self.combo.addItems(models)
        def set_current(self, text):
            self.combo.setCurrentText(text)

    model_dialog = ModelDialog(parent)

    # About dialog
    class AboutDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle('Tentang Keong-MAS')
            self.setModal(True)
            self.setFixedWidth(520)

            # Load version from project config.json
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
            with open(config_path, 'r', encoding='utf-8') as _cf:
                cfg = json.load(_cf)
            _app_version = cfg['app']['version']

            main_layout = QHBoxLayout(self)
            main_layout.setContentsMargins(16, 12, 16, 12)
            main_layout.setSpacing(12)

            left_frame = QFrame()
            left_frame.setFixedWidth(140)
            left_layout = QVBoxLayout(left_frame)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(8)
            left_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

            icon_label = QLabel()
            icon_label.setFixedSize(128, 128)
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "APP", "res", "Keong-MAS.ico")
            icon = QIcon(icon_path)
            pix = icon.pixmap(QSize(256, 256))
            if pix.isNull():
                print(f"AboutDialog: icon not found at {icon_path}")
            else:
                pix = pix.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_label.setPixmap(pix)
            left_layout.addWidget(icon_label)

            main_layout.addWidget(left_frame)

            # Right content
            right_widget = QWidget()
            right_layout = QVBoxLayout(right_widget)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(6)

            title = QLabel('Keong-MAS')
            title.setObjectName('title')
            title_font = QFont()
            title_font.setPointSize(16)
            title_font.setBold(True)
            title.setFont(title_font)
            right_layout.addWidget(title)

            subtitle = QLabel('Kecilin Ongkos, Masking Auto Selesai')
            subtitle.setObjectName('subtitle')
            right_layout.addWidget(subtitle)

            developer = cfg['app']['developer']
            license_text = cfg['app']['license']
            about_text = cfg['app']['about']

            version_label = QLabel(f"Version: {_app_version}")
            version_label.setObjectName('versionLabel')
            right_layout.addWidget(version_label)

            developer_label = QLabel(f"Developer: {developer}")
            developer_label.setObjectName('developerLabel')
            right_layout.addWidget(developer_label)

            license_label = QLabel(f"License: {license_text}")
            license_label.setObjectName('licenseLabel')
            right_layout.addWidget(license_label)

            desc = QLabel(about_text)
            desc.setObjectName('desc')
            desc.setWordWrap(True)
            desc.setFixedHeight(52)
            right_layout.addWidget(desc)

            main_layout.addWidget(right_widget)

            self.adjustSize()

    about_dialog = AboutDialog(parent)

    ui_dict = {
        'drop_area_frame': drop_area,
        'dnd_label_1': drop_area.findChild(QLabel, 'dnd_label_1'),
        'dnd_label_2': drop_area.findChild(QLabel, 'dnd_label_2'),
        'dnd_label_3': drop_area.findChild(QLabel, 'dnd_label_3'),
        'split_view': split_view,
        'file_table': split_view.widget(0),
        'image_preview': split_view.widget(1),
        'actionOpenFolder': action_open_folder,
        'actionOpenFiles': action_open_files,
        'actionOutputFolder': action_output_folder,
        'actionShowModelDialog': action_show_model_dialog,
        'actionAbout': action_about,
        'actionWAGroup': action_wa_group,
        'actionExit': action_exit,
        'modelDialog': model_dialog,
        'aboutDialog': about_dialog,
        **controls_dict
    }
    
    return central_widget, ui_dict


def _create_drop_area():
    """Create the drag-and-drop area."""
    drop_frame = QFrame()
    drop_frame.setObjectName('drop_area_frame')
    drop_frame.setMinimumHeight(300)
    drop_frame.setStyleSheet("""
        QFrame#drop_area_frame {
            border: 2px dashed #888;
            border-radius: 8px;
            background-color: rgba(240, 240, 240, 30);
        }
        QFrame#drop_area_frame[dragActive="true"] {
            border: 3px dashed #4a6ea9;
            background-color: rgba(200, 220, 255, 30);
        }
    """)
    
    layout = QVBoxLayout(drop_frame)
    
    layout.addStretch()
    
    label1 = QLabel("Seret gambarmu ke sini")
    label1.setObjectName('dnd_label_1')
    label1.setAlignment(Qt.AlignCenter)
    label1.setStyleSheet("font-size: 28px; font-weight: bold;")
    layout.addWidget(label1, alignment=Qt.AlignHCenter)
    
    label2 = QLabel("Aplikasi ini buat hapus background, itu doang.")
    label2.setObjectName('dnd_label_2')
    label2.setAlignment(Qt.AlignCenter)
    label2.setStyleSheet("font-size: 12px;")
    layout.addWidget(label2, alignment=Qt.AlignHCenter)
    
    label3 = QLabel("Gak usah klik aneh-aneh. Taruh aja, kelar.")
    label3.setObjectName('dnd_label_3')
    label3.setAlignment(Qt.AlignCenter)
    layout.addWidget(label3, alignment=Qt.AlignHCenter)
    
    layout.addStretch()
    
    return drop_frame


def _create_split_view():
    """Create the split view with table and preview."""
    splitter = QSplitter(Qt.Horizontal)
    splitter.setObjectName('split_view')
    
    file_table = FileTableWidget()
    image_preview = ImagePreviewWidget()
    
    splitter.addWidget(file_table)
    splitter.addWidget(image_preview)
    
    splitter.setSizes([400, 400])
    
    return splitter


def _create_controls():
    """Create the bottom control panel."""
    container = QWidget()
    main_layout = QVBoxLayout(container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(5)
    
    # Row 1: Processing options
    row1 = QHBoxLayout()
    row1.setSpacing(6)
    
    mask_cb = QCheckBox("Simpan Mask")
    mask_cb.setObjectName('saveMaskCheckBox')
    mask_cb.setToolTip("Simpan file mask yang sudah disesuaikan")
    row1.addWidget(mask_cb)
    
    jpg_cb = QCheckBox("Ekspor JPG")
    jpg_cb.setObjectName('jpgExportCheckBox')
    jpg_cb.setToolTip("Ekspor versi JPG (tanpa transparansi)")
    row1.addWidget(jpg_cb)
    
    crop_cb = QCheckBox("Potong Otomatis")
    crop_cb.setObjectName('checkBox')
    crop_cb.setToolTip("Potong gambar otomatis sesuai konten")
    row1.addWidget(crop_cb)
    
    solid_cb = QCheckBox("BG Solid")
    solid_cb.setObjectName('solidBgCheckBox')
    solid_cb.setToolTip("Tambahkan background solid")
    row1.addWidget(solid_cb)
    
    color_btn = QPushButton()
    color_btn.setObjectName('colorPickerButton')
    color_btn.setFixedSize(20, 20)
    color_btn.setToolTip("Pilih warna background")
    row1.addWidget(color_btn)
    
    row1.addSpacing(10)
    
    margin_label = QLabel("Margin:")
    margin_label.setFixedWidth(45)
    row1.addWidget(margin_label)
    
    margin_spin = QSpinBox()
    margin_spin.setObjectName('unifiedMarginSpinBox')
    margin_spin.setRange(0, 1000)
    margin_spin.setValue(10)
    margin_spin.setFixedWidth(50)
    margin_spin.setFixedHeight(22)
    margin_spin.setToolTip("Margin untuk pemotongan dan background")
    row1.addWidget(margin_spin)
    
    row1.addSpacing(10)
    
    quality_label = QLabel("Kualitas:")
    quality_label.setObjectName('jpgQualityLabel')
    quality_label.setFixedWidth(50)
    row1.addWidget(quality_label)
    
    quality_spin = QSpinBox()
    quality_spin.setObjectName('jpgQualitySpinBox')
    quality_spin.setRange(1, 100)
    quality_spin.setValue(90)
    quality_spin.setFixedWidth(45)
    quality_spin.setFixedHeight(22)
    quality_spin.setToolTip("Kualitas ekspor JPG (1-100)")
    row1.addWidget(quality_spin)

    # Always-on-top checkbox, placed next to quality controls (persisted)
    always_on_top_cb = QCheckBox("Selalu di atas")
    always_on_top_cb.setObjectName('alwaysOnTopCheckBox')
    always_on_top_cb.setToolTip('Jaga jendela tetap di atas (tersimpan)')
    always_on_top_cb.setFixedHeight(22)
    always_on_top_cb.setFixedWidth(120)
    row1.addWidget(always_on_top_cb)

    # End of row1 controls
    row1.addStretch()
    
    main_layout.addLayout(row1)
    
    # Row 2: Action buttons
    row2 = QHBoxLayout()
    row2.setSpacing(6)
    
    stop_btn = QPushButton()
    stop_btn.setObjectName('stopButton')
    stop_btn.setToolTip("Hentikan proses")
    stop_btn.setFixedSize(28, 28)
    row2.addWidget(stop_btn)
    
    repeat_btn = QPushButton()
    repeat_btn.setObjectName('repeatButton')
    repeat_btn.setToolTip("Ulangi proses terakhir")
    repeat_btn.setFixedSize(28, 28)
    row2.addWidget(repeat_btn)
    
    reset_btn = QPushButton()
    reset_btn.setObjectName('resetButton')
    reset_btn.setToolTip("Reset dan kembali ke DND area")
    reset_btn.setFixedSize(28, 28)
    reset_btn.hide()  # Hidden until files loaded
    row2.addWidget(reset_btn)
    
    row2.addSpacing(10)
    
    open_folder_btn = QPushButton(" Buka Folder")
    open_folder_btn.setObjectName('openFolder')
    open_folder_btn.setFixedHeight(28)
    open_folder_btn.setToolTip("Pilih folder untuk diproses")
    row2.addWidget(open_folder_btn)
    
    open_files_btn = QPushButton(" Pilih File")
    open_files_btn.setObjectName('openFiles')
    open_files_btn.setFixedHeight(28)
    open_files_btn.setToolTip("Pilih file gambar untuk diproses")
    row2.addWidget(open_files_btn)
    
    output_btn = QPushButton(" Folder Output")
    output_btn.setObjectName('outputLocationButton')
    output_btn.setToolTip("Pilih lokasi output (kosongkan untuk default: folder PNG)")
    output_btn.setFixedHeight(28)
    row2.addWidget(output_btn)
    
    clear_output_btn = QPushButton("×")
    clear_output_btn.setObjectName('clearOutputButton')
    clear_output_btn.setToolTip("Reset ke folder output default (PNG)")
    clear_output_btn.setFixedSize(28, 28)
    row2.addWidget(clear_output_btn)

    # Model selection combobox placed near the right side (left of WA button)
    model_label = QLabel("Model:")
    model_label.setObjectName('modelLabel')
    model_label.setFixedWidth(40)
    row2.addWidget(model_label)

    model_combo = QComboBox()
    model_combo.setObjectName('modelComboBox')
    model_combo.setFixedWidth(220)
    # Match other control heights for visual consistency
    model_combo.setFixedHeight(28)
    model_combo.setToolTip("Pilih model (ONNX) untuk fokus segmentasi")
    # Make popup items slightly taller so they line up and are easy to read
    model_combo.setMaxVisibleItems(6)
    view = model_combo.view()
    view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    view.setSpacing(0)
    view.setContentsMargins(0, 0, 0, 0)
    view.setUniformItemSizes(True)
    view.setStyleSheet("""
        QAbstractItemView { outline: none; font-size: 12px; }
        QAbstractItemView::item { padding: 2px 6px; min-height: 20px; }
        QAbstractItemView::item:selected { background: #444444; color: white; }
    """)
    row2.addWidget(model_combo)

    row2.addStretch()
    
    whatsapp_btn = QPushButton(" WA Grup")
    whatsapp_btn.setObjectName('whatsappButton')
    whatsapp_btn.setFixedHeight(28)
    whatsapp_btn.setToolTip("Buka grup WhatsApp Keong-MAS")
    row2.addWidget(whatsapp_btn)
    
    main_layout.addLayout(row2)
    
    # Row 3: Levels Adjustment
    levels_group = QGroupBox("Penyesuaian Levels")
    levels_group.setStyleSheet("QGroupBox { font-weight: normal; padding-top: 8px; }")
    levels_layout = QHBoxLayout(levels_group)
    levels_layout.setSpacing(6)
    levels_layout.setContentsMargins(6, 12, 6, 6)
    
    # Button to enter mask adjustment mode
    configure_mask_btn = QPushButton("Atur Masking")
    configure_mask_btn.setObjectName('configureMaskButton')
    configure_mask_btn.setCheckable(True)
    configure_mask_btn.setChecked(False)
    configure_mask_btn.setToolTip("Klik untuk membuat preview mask dari gambar asli dan menyesuaikan Levels pada preview")
    configure_mask_btn.setFixedHeight(28)
    configure_mask_btn.setFixedWidth(120)
    if hasattr(qta, 'icon') and callable(qta.icon):
        configure_mask_btn.setIcon(qta.icon('fa5s.sliders-h'))
        configure_mask_btn.setIconSize(QSize(14, 14))
    levels_layout.addWidget(configure_mask_btn)

    reset_levels_btn = QPushButton("Reset Levels")
    reset_levels_btn.setObjectName('resetLevelsButton')
    reset_levels_btn.setFixedHeight(28)
    reset_levels_btn.setFixedWidth(120)
    reset_levels_btn.setToolTip("Kembalikan slider ke nilai recommended")
    if hasattr(qta, 'icon') and callable(qta.icon):
        reset_levels_btn.setIcon(qta.icon('fa5s.undo'))
        reset_levels_btn.setIconSize(QSize(12, 12))
    levels_layout.addWidget(reset_levels_btn)
    levels_layout.addSpacing(8)

    levels_slider = MultiHandleSlider()
    levels_slider.setObjectName('levelsMultiSlider')
    levels_slider.setFixedWidth(260)
    levels_layout.addWidget(levels_slider)

    black_value = QLabel("20")
    black_value.setObjectName('blackPointValue')
    black_value.setFixedWidth(30)
    levels_layout.addWidget(black_value)

    mid_value = QLabel("70")
    mid_value.setObjectName('midPointValue')
    mid_value.setFixedWidth(30)
    levels_layout.addWidget(mid_value)

    white_value = QLabel("200")
    white_value.setObjectName('whitePointValue')
    white_value.setFixedWidth(30)
    levels_layout.addWidget(white_value)



    levels_layout.addStretch()

    main_layout.addWidget(levels_group)
    
    # Collect all widgets
    widgets = {
        'saveMaskCheckBox': mask_cb,
        'jpgExportCheckBox': jpg_cb,
        'checkBox': crop_cb,
        'solidBgCheckBox': solid_cb,
        'colorPickerButton': color_btn,
        'unifiedMarginSpinBox': margin_spin,
        'jpgQualityLabel': quality_label,
        'jpgQualitySpinBox': quality_spin,
        'outputLocationButton': output_btn,
        'clearOutputButton': clear_output_btn,
        'stopButton': stop_btn,
        'repeatButton': repeat_btn,
        'resetButton': reset_btn,
        'openFolder': open_folder_btn,
        'openFiles': open_files_btn,
        'whatsappButton': whatsapp_btn,
        'levelsMultiSlider': levels_slider,
        'blackPointValue': black_value,
        'midPointValue': mid_value,
        'whitePointValue': white_value,
        'configureMaskButton': configure_mask_btn,
        'modelComboBox': model_combo,
        'resetLevelsButton': reset_levels_btn,
        # optional widget - may not exist in older versions
        'alwaysOnTopCheckBox': always_on_top_cb,
    }
    
    return container, widgets
