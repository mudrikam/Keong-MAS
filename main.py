"""
Keong-MAS (Kecilin Ongkos, Masking Auto Selesai)
Background Removal Application

Main entry point for the application.
"""

import sys
import os

# Suppress ONNX Runtime error messages before any imports
os.environ['ORT_LOGGING_LEVEL'] = '3'  # ERROR level only

# Set up CUDA DLL paths BEFORE any imports
cuda_bin = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin"
cudnn_bin = r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin\12.6"
if hasattr(os, 'add_dll_directory'):
    if os.path.isdir(cuda_bin):
        os.add_dll_directory(cuda_bin)
    if os.path.isdir(cudnn_bin):
        os.add_dll_directory(cudnn_bin)

# Also prepend to PATH
if os.path.isdir(cuda_bin):
    os.environ['PATH'] = cuda_bin + os.pathsep + os.environ.get('PATH', '')
if os.path.isdir(cudnn_bin):
    os.environ['PATH'] = cudnn_bin + os.pathsep + os.environ.get('PATH', '')

# Ensure project root is on sys.path BEFORE importing local packages
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    # insert at front to ensure local APP package is preferred
    sys.path.insert(0, current_dir)

# Apply GPU fixes BEFORE any imports that might load ONNX Runtime
from APP.helpers.gpu_fix import ensure_cuda_accessible
result = ensure_cuda_accessible()
# AutoFix runs silently; messages are recorded for diagnostics but not printed during normal startup.

from PySide6.QtWidgets import QApplication
from APP.windows import MainWindow


def set_windows_app_id():
    """Set Windows application ID for taskbar icon."""
    if sys.platform == 'win32':
        try:
            import ctypes
            myappid = 'keong.mas.removerbackground.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            print(f"Failed to set Windows app ID: {e}")


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    set_windows_app_id()
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
