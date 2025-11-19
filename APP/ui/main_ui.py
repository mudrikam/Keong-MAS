"""Main UI layout creation for Keong-MAS."""

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QCheckBox, QSpinBox, QSlider, QGroupBox, QSplitter
)
from APP.widgets import FileTableWidget, ImagePreviewWidget


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
    
    ui_dict = {
        'drop_area_frame': drop_area,
        'dnd_label_1': drop_area.findChild(QLabel, 'dnd_label_1'),
        'dnd_label_2': drop_area.findChild(QLabel, 'dnd_label_2'),
        'dnd_label_3': drop_area.findChild(QLabel, 'dnd_label_3'),
        'split_view': split_view,
        'file_table': split_view.widget(0),
        'image_preview': split_view.widget(1),
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
    
    # Black Point
    black_label = QLabel("Hitam:")
    black_label.setFixedWidth(40)
    levels_layout.addWidget(black_label)
    
    black_slider = QSlider(Qt.Horizontal)
    black_slider.setObjectName('blackPointSlider')
    black_slider.setRange(0, 100)
    black_slider.setValue(20)
    black_slider.setFixedWidth(70)
    black_slider.setFixedHeight(18)
    black_slider.setToolTip("Titik hitam (0-100)")
    levels_layout.addWidget(black_slider)
    
    black_value = QLabel("20")
    black_value.setObjectName('blackPointValue')
    black_value.setFixedWidth(22)
    levels_layout.addWidget(black_value)
    
    levels_layout.addSpacing(8)
    
    # Mid Point
    mid_label = QLabel("Tengah:")
    mid_label.setFixedWidth(45)
    levels_layout.addWidget(mid_label)
    
    mid_slider = QSlider(Qt.Horizontal)
    mid_slider.setObjectName('midPointSlider')
    mid_slider.setRange(0, 255)
    mid_slider.setValue(70)
    mid_slider.setFixedWidth(70)
    mid_slider.setFixedHeight(18)
    mid_slider.setToolTip("Titik tengah (0-255)")
    levels_layout.addWidget(mid_slider)
    
    mid_value = QLabel("70")
    mid_value.setObjectName('midPointValue')
    mid_value.setFixedWidth(22)
    levels_layout.addWidget(mid_value)
    
    levels_layout.addSpacing(8)
    
    # White Point
    white_label = QLabel("Putih:")
    white_label.setFixedWidth(35)
    levels_layout.addWidget(white_label)
    
    white_slider = QSlider(Qt.Horizontal)
    white_slider.setObjectName('whitePointSlider')
    white_slider.setRange(0, 255)
    white_slider.setValue(200)
    white_slider.setFixedWidth(70)
    white_slider.setFixedHeight(18)
    white_slider.setToolTip("Titik putih (0-255)")
    levels_layout.addWidget(white_slider)
    
    white_value = QLabel("200")
    white_value.setObjectName('whitePointValue')
    white_value.setFixedWidth(22)
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
        'blackPointSlider': black_slider,
        'blackPointValue': black_value,
        'midPointSlider': mid_slider,
        'midPointValue': mid_value,
        'whitePointSlider': white_slider,
        'whitePointValue': white_value,
    }
    
    return container, widgets
