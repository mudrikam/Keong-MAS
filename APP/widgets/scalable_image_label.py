"""Scalable image label widget with rounded corners."""

import os
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QSizePolicy


class ScalableImageLabel(QLabel):
    """A QLabel that displays images scaled to fit while maintaining aspect ratio."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.scaled_pixmap = None
        self.image_path = None
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("""
            QLabel {
                padding: 5px;
                background-color: transparent;
            }
        """)
        
    def setImagePath(self, path):
        """Load and display an image from the given path."""
        if not os.path.exists(path):
            return False
            
        self.image_path = str(path)
        self.original_pixmap = QPixmap(self.image_path)
        self.updatePixmap()
        return not self.original_pixmap.isNull()
        
    def updatePixmap(self):
        """Scale the pixmap to fit the label size."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            width = max(10, self.width() - 24)
            height = max(10, self.height() - 24)
            
            self.scaled_pixmap = self.original_pixmap.scaled(
                width,
                height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.update()
    
    def paintEvent(self, event):
        """Custom paint event to draw rounded image."""
        super().paintEvent(event)
        
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap and not self.scaled_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            x = (self.width() - self.scaled_pixmap.width()) // 2
            y = (self.height() - self.scaled_pixmap.height()) // 2
            
            rect = QRectF(x, y, self.scaled_pixmap.width(), self.scaled_pixmap.height())
            
            path = QPainterPath()
            path.addRoundedRect(rect, 12, 12)
            
            painter.setClipPath(path)
            painter.drawPixmap(int(rect.x()), int(rect.y()), self.scaled_pixmap)
    
    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)
        self.updatePixmap()
        
    def sizeHint(self):
        return QSize(200, 200)
        
    def minimumSizeHint(self):
        return QSize(10, 10)
