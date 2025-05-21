import os
import sys
import time
import tempfile
from pathlib import Path

# Add the current directory to the path so Python can find the APP module
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from PySide6.QtCore import Qt, QUrl, QSize, Signal, QThread, QObject
from PySide6.QtGui import QIcon, QGuiApplication, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLabel, 
    QProgressBar, QMessageBox, QFrame, QWidget,
    QFileDialog
)
from PySide6.QtUiTools import QUiLoader

# Import for Windows taskbar icon
import ctypes

import rembg
from PIL import Image
from APP.helpers import model_manager

# Worker class to handle background removal in a separate thread
class RemBgWorker(QObject):
    progress = Signal(int, str)  # Progress percentage and status message
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
                    self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}")
                elif Path(file_path).is_dir():
                    # Handle directories
                    image_files = self.get_image_files_in_dir(file_path)
                    for img_path in image_files:
                        if self.abort:
                            break                        
                        self.process_image(img_path)
                        processed += 1
                        self.progress.emit(int(processed / total_files * 100), f"File {processed}/{total_files}")
                else:
                    # Skip non-image files
                    processed += 1
                    self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}")
            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")
                processed += 1
                self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}")
        
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
            self.progress.emit(5, status_msg)
            
            # Import helper untuk progress bar
            from APP.helpers.ui_helpers import download_progress_callback
              # Gunakan model default
            self.progress.emit(10, f"Menyiapkan model: {os.path.basename(image_path)}")
            print(f"Menyiapkan model default...")
            model_name = model_manager.prepare_model(callback=download_progress_callback)
            print(f"Menggunakan model {model_name}")
            
            # Process with rembg for main transparent image
            self.progress.emit(20, f"Memuat gambar: {os.path.basename(image_path)}")
            input_img = Image.open(image_path)
            
            try:                # Buat session untuk model dengan parameter yang lebih stabil
                print(f"Membuat session dengan model {model_name}...")
                session = rembg.new_session(model_name)
                  # Generate the main transparent image
                self.progress.emit(30, f"Memproses: Menghapus latar belakang...")
                print(f"Menghapus latar belakang gambar...")
                input_size = input_img.size
                
                # Generate main transparent image with optimized parameters
                # Setting alpha_matting_foreground_threshold and alpha_matting_background_threshold
                # can help avoid the Cholesky decomposition error
                self.progress.emit(40, f"Memproses: Menerapkan alpha matting...")
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
                self.progress.emit(50, f"Menyimpan gambar transparan...")
                output_img.save(output_path)
                print(f"Gambar transparan disimpan ke {output_path}")
                
                # Generate and save the mask separately
                self.progress.emit(60, f"Membuat mask...")
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
                raise                # Import and use the image_utils helper to create a third enhanced image
            try:                  
                self.progress.emit(70, f"Menghasilkan gambar transparan yang disempurnakan...")
                from APP.helpers.image_utils import (
                    enhance_transparency, combine_with_mask, enhance_transparency_with_levels,
                    get_levels_config
                )                # Get default extreme levels values for sharper edges
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
                self.progress.emit(65, f"Menghasilkan mask yang diatur levels-nya...")
                print(f"Langkah 1: Menerapkan levels adjustment pada mask...")
                
                # Step 2: Create enhanced transparency image using the levels-adjusted mask
                self.progress.emit(80, f"Membuat gambar transparan dengan mask yang diatur levels...")
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
        
        # Create progress bar (hidden by default)
        self.progress_bar = QProgressBar(self.ui)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v / %m")
        self.progress_bar.hide()
        
        # Add progress bar to layout (it will replace the drop area when active)
        self.ui.centralWidget().layout().addWidget(self.progress_bar)
        
        # Setup drag and drop
        self.setAcceptDrops(True)
        
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
                self.process_files(file_paths)
        else:
            event.ignore()
    
    def process_files(self, file_paths):
        # Hide drop area and show progress bar
        self.drop_area.hide()
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        
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
    def update_progress(self, value, message=""):
        self.progress_bar.setValue(value)
        if message:
            self.progress_bar.setFormat(f"{value}% - {message}")
    
    def on_file_completed(self, file_path):
        # Could show status message if needed
        pass      
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
        
        # Show drop area again
        self.progress_bar.hide()
        self.drop_area.show()
        
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