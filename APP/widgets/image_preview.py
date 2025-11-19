"""Image preview widget with zoom, pan, and before/after toggle."""

import os
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QMouseEvent


class ImagePreviewWidget(QWidget):
    """Widget untuk preview gambar dengan zoom dan pan."""
    
    file_double_clicked = Signal(str)  # Signal untuk double-click
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.before_path = None
        self.after_path = None
        self.showing_before = False
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.view = ImageGraphicsView(self)
        layout.addWidget(self.view)
        
    def set_images(self, before_path, after_path=None):
        """Set before and after images."""
        self.before_path = before_path
        self.after_path = after_path
        self.showing_before = False
        self._update_display()
        
    def show_before(self):
        """Show before image."""
        if self.before_path:
            self.showing_before = True
            self._update_display(preserve_zoom=True)
            
    def show_after(self):
        """Show after image."""
        if self.after_path:
            self.showing_before = False
            self._update_display(preserve_zoom=True)
        elif self.before_path:
            self.showing_before = False
            self._update_display(preserve_zoom=True)
            
    def toggle_before_after(self, show_before):
        """Toggle between before and after."""
        if show_before:
            self.show_before()
        else:
            self.show_after()
    
    def get_current_file_path(self):
        """Get current displayed file path."""
        if self.showing_before:
            return self.before_path
        elif self.after_path:
            return self.after_path
        else:
            return self.before_path
            
    def clear(self):
        """Clear preview."""
        self.before_path = None
        self.after_path = None
        self.showing_before = False
        self.view.clear()
        
    def _update_display(self, preserve_zoom=False):
        """Update displayed image."""
        if self.showing_before and self.before_path:
            self.view.set_image(self.before_path, preserve_zoom=preserve_zoom)
        elif not self.showing_before and self.after_path:
            self.view.set_image(self.after_path, preserve_zoom=preserve_zoom)
        elif self.before_path:
            self.view.set_image(self.before_path, preserve_zoom=preserve_zoom)
        else:
            self.view.clear()


class ImageGraphicsView(QGraphicsView):
    """Graphics view dengan zoom dan pan."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_view()
        self.current_scale = 1.0
        self.is_panning = False
        self.is_right_clicking = False
        self.pan_start = QPointF()
        self.pan_button = None  # Track which button initiated pan
        
    def _setup_view(self):
        """Setup view properties."""
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.pixmap_item = None
        
    def set_image(self, image_path, preserve_zoom=False):
        """Load and display image."""
        if not os.path.exists(image_path):
            return
            
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        
        # Save current transform and scroll position if preserving zoom
        saved_transform = None
        saved_h_scroll = None
        saved_v_scroll = None
        if preserve_zoom and self.pixmap_item:
            saved_transform = self.transform()
            saved_h_scroll = self.horizontalScrollBar().value()
            saved_v_scroll = self.verticalScrollBar().value()
            
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        
        if preserve_zoom and saved_transform:
            # Restore zoom level and scroll position
            self.setTransform(saved_transform)
            if saved_h_scroll is not None:
                self.horizontalScrollBar().setValue(saved_h_scroll)
            if saved_v_scroll is not None:
                self.verticalScrollBar().setValue(saved_v_scroll)
        else:
            # Fit to view
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.current_scale = self.transform().m11()
        
    def clear(self):
        """Clear scene."""
        self.scene.clear()
        self.pixmap_item = None
        self.current_scale = 1.0
        
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming."""
        if event.angleDelta().y() > 0:
            factor = 1.25
        else:
            factor = 0.8
            
        self.current_scale *= factor
        
        if self.current_scale < 0.1:
            self.current_scale = 0.1
            return
        elif self.current_scale > 10.0:
            self.current_scale = 10.0
            return
            
        self.scale(factor, factor)
        
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for panning and toggle."""
        if event.button() == Qt.LeftButton:
            # Left-click drag for panning
            self.is_panning = True
            self.pan_start = event.pos()
            self.pan_button = Qt.LeftButton
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MiddleButton:
            # Middle-click drag for panning
            self.is_panning = True
            self.pan_start = event.pos()
            self.pan_button = Qt.MiddleButton
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.RightButton:
            # Right-click to show before
            self.is_right_clicking = True
            parent_widget = self.parent()
            while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                parent_widget = parent_widget.parent()
            if parent_widget:
                parent_widget.show_before()
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for panning."""
        if self.is_panning:
            delta = event.pos() - self.pan_start
            self.pan_start = event.pos()
            
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release."""
        if (event.button() == Qt.LeftButton or event.button() == Qt.MiddleButton) and self.is_panning:
            # Only stop panning if the released button matches the one that started panning
            if event.button() == self.pan_button:
                self.is_panning = False
                self.pan_button = None
                self.setCursor(Qt.ArrowCursor)
            event.accept()
        elif event.button() == Qt.RightButton and self.is_right_clicking:
            # Right-click release to show after
            self.is_right_clicking = False
            parent_widget = self.parent()
            while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                parent_widget = parent_widget.parent()
            if parent_widget:
                parent_widget.show_after()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click to open file location."""
        if event.button() == Qt.LeftButton:
            parent_widget = self.parent()
            while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                parent_widget = parent_widget.parent()
            if parent_widget:
                file_path = parent_widget.get_current_file_path()
                if file_path:
                    parent_widget.file_double_clicked.emit(file_path)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
