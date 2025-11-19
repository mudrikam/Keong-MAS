"""
Keong-MAS (Kecilin Ongkos, Masking Auto Selesai)
Background Removal Application

Main entry point for the application.
"""

import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

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
