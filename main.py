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
from PySide6.QtGui import QIcon, QGuiApplication, QImage, QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLabel, 
    QProgressBar, QMessageBox, QFrame, QWidget,
    QFileDialog, QPushButton, QCheckBox, QSizePolicy
)
from PySide6.QtUiTools import QUiLoader

# Import for Windows taskbar icon
import ctypes

import rembg
from PIL import Image
from APP.helpers import model_manager

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
        for root, _, files in os.walk(directory):
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
                    get_levels_config
                )# Get default extreme levels values for sharper edges
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
                
                # Call the enhanced function which now saves the adjusted mask separately
                enhanced_path = enhance_transparency_with_levels(
                    original_transparent_path, original_mask_path,
                    output_suffix="_transparent", 
                    black_point=black_point, mid_point=mid_point, white_point=white_point,
                    save_adjusted_mask=True  # This will save the adjusted mask as a separate file
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
                    from APP.helpers.image_crop import get_auto_crop_setting, get_crop_threshold, crop_transparent_image
                    if get_auto_crop_setting():
                        self.progress.emit(90, f"Melakukan auto crop...", image_path)
                        print(f"Auto crop enabled, cropping image...")
                          # The path to use for cropping (use the enhanced path if available)
                        image_to_crop = enhanced_path if enhanced_path else original_transparent_path
                        
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
                        threshold = get_crop_threshold()
                        
                        # Apply cropping
                        cropped_path = crop_transparent_image(
                            image_to_crop, 
                            mask_to_use, 
                            output_path=None,  # Overwrite the input file
                            threshold=threshold
                        )
                        
                        if cropped_path:
                            print(f"5. Auto-cropped image saved at: {cropped_path}")
                            # Update our reference to the final image path
                            enhanced_path = cropped_path
                except Exception as crop_error:
                    print(f"Warning: Auto crop error: {str(crop_error)}")
                
                model_info = f" (model: {model_name})" if 'model_name' in locals() else ""
                print(f"Semua pemrosesan selesai{model_info}")
                self.file_completed.emit(enhanced_path if enhanced_path else original_transparent_path)
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
            # Load and set the initial checkbox state from config
            from APP.helpers.image_crop import get_auto_crop_setting, update_auto_crop_setting
            is_auto_crop_enabled = get_auto_crop_setting()
            self.auto_crop_checkbox.setChecked(is_auto_crop_enabled)
            
            # Connect checkbox state change to save configuration
            self.auto_crop_checkbox.stateChanged.connect(self.on_auto_crop_changed)
        
        # Worker thread for processing
        self.worker = None
        self.thread = None

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
            
            # Load the image and show it
            if self.preview_image.setImagePath(file_path):
                self.preview_image.show()
                print(f"Showing final preview for: {os.path.basename(file_path)}")

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
        
        # Calculate minutes and seconds
        minutes = int(processing_time // 60)
        seconds = int(processing_time % 60)
          # Format time string in Indonesian
        if minutes > 0:
            time_str = f"{minutes} menit {seconds} detik"
        else:
            time_str = f"{seconds} detik"
          
        # Notify user with statistics in Indonesian
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
        from APP.helpers.image_crop import update_auto_crop_setting
        is_checked = state == Qt.Checked
        update_auto_crop_setting(is_checked)
        print(f"Auto crop setting {'enabled' if is_checked else 'disabled'}")

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