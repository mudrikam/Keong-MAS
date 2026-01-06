"""
Keong-MAS (Kecilin Ongkos, Masking Auto Selesai)
Background Removal Application

Main entry point for the application.
"""

import sys
import os

# Suppress ONNX Runtime error messages before any imports
os.environ['ORT_LOGGING_LEVEL'] = '3'  # ERROR level only

# Ensure project root is on sys.path BEFORE importing local packages
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    # insert at front to ensure local APP package is preferred
    sys.path.insert(0, current_dir)

# Smart CUDA/cuDNN detection and setup
try:
    from APP.helpers.cuda_finder import setup_cuda_environment
    cuda_summary = setup_cuda_environment()
    
    # Print summary if CUDA/cuDNN found (using ASCII-safe characters)
    if cuda_summary['cuda']['found'] or cuda_summary['cudnn']['found']:
        if cuda_summary['cuda']['found']:
            print(f"[OK] CUDA v{cuda_summary['cuda']['cuda_version']} detected: {cuda_summary['cuda']['cuda_bin']}")
        if cuda_summary['cudnn']['found']:
            cudnn_ver = cuda_summary['cudnn']['cudnn_version']
            cuda_ver = cuda_summary['cudnn']['cuda_version']
            if cuda_ver:
                print(f"[OK] cuDNN v{cudnn_ver} (CUDA {cuda_ver}) detected: {cuda_summary['cudnn']['cudnn_bin']}")
            else:
                print(f"[OK] cuDNN v{cudnn_ver} detected: {cuda_summary['cudnn']['cudnn_bin']}")
        print("=> GPU acceleration enabled")
    else:
        print("[INFO] No CUDA/cuDNN found - will use CPU for processing")
except Exception as e:
    print(f"[WARNING] CUDA detection error (will use CPU): {e}")
    # Continue without GPU - app will fallback to CPU automatically

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
