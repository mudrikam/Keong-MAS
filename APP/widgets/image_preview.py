"""Image preview widget with zoom, pan, and before/after toggle."""

import os
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QMouseEvent
import math


class ImagePreviewWidget(QWidget):
    """Widget untuk preview gambar dengan zoom dan pan.

    Includes a floating navigation widget (top-right) with Zoom In/Out, Reset, and
    a press-and-hold "Before" button that mirrors right-click-hold behavior.
    """
    
    file_double_clicked = Signal(str)  # Signal untuk double-click
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.before_path = None
        self.after_path = None
        self.showing_before = False
        self._setup_ui()
        # Mask preview mode
        self.mask_mode = False
        self.mask_before_path = None
        self.mask_after_path = None
        
    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.view = ImageGraphicsView(self)
        layout.addWidget(self.view)
        
        # Floating navigation (top-right)
        try:
            from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton
            import qtawesome as qta
            self._nav_frame = QFrame(self)
            self._nav_frame.setObjectName('previewNav')
            self._nav_frame.setStyleSheet('''
                QFrame#previewNav {
                    background-color: rgba(30, 30, 30, 180);
                    border-radius: 6px;
                }
                QPushButton { background: transparent; color: white; border: none; }
            ''')
            nav_layout = QHBoxLayout(self._nav_frame)
            nav_layout.setContentsMargins(6, 4, 6, 4)
            nav_layout.setSpacing(6)

            # Press-and-hold before-preview button (mimic right-click hold)
            self._before_hold_btn = QPushButton()
            self._before_hold_btn.setToolTip('Tahan untuk melihat Sebelum (lepas untuk kembali)')
            try:
                self._before_hold_btn.setIcon(qta.icon('fa5s.image'))
            except Exception:
                pass
            # on press -> show before, on release -> show after
            self._before_hold_btn.pressed.connect(lambda: self.show_before())
            self._before_hold_btn.released.connect(lambda: self.show_after())
            nav_layout.addWidget(self._before_hold_btn)

            # Reset zoom
            self._reset_zoom_btn = QPushButton()
            self._reset_zoom_btn.setToolTip('Reset tampilan')
            try:
                self._reset_zoom_btn.setIcon(qta.icon('fa5s.redo'))
            except Exception:
                pass
            self._reset_zoom_btn.clicked.connect(self._on_nav_reset_zoom)
            nav_layout.addWidget(self._reset_zoom_btn)

            # Zoom out (Perkecil)
            self._zoom_out_btn = QPushButton()
            self._zoom_out_btn.setToolTip('Perkecil')
            try:
                self._zoom_out_btn.setIcon(qta.icon('fa5s.search-minus'))
            except Exception:
                pass
            self._zoom_out_btn.clicked.connect(self._on_nav_zoom_out)
            nav_layout.addWidget(self._zoom_out_btn)

            # Zoom slider (10% - 1000%) for fine control
            try:
                from PySide6.QtWidgets import QSlider
                self._zoom_slider = QSlider(Qt.Horizontal)
                self._zoom_slider.setRange(10, 1000)  # 10% .. 1000%
                self._zoom_slider.setFixedWidth(120)
                self._zoom_slider.setFixedHeight(16)
                # Initialize value based on current scale
                try:
                    init_val = int(round(self.view.current_scale * 100))
                except Exception:
                    init_val = 100
                self._zoom_slider.setValue(init_val)
                self._zoom_slider.setToolTip(f"Zoom: {init_val}%")
                self._slider_updating = False
                self._zoom_slider.valueChanged.connect(self._on_nav_zoom_slider_changed)
                nav_layout.addWidget(self._zoom_slider)
            except Exception:
                self._zoom_slider = None

            # Zoom in (Perbesar)
            self._zoom_in_btn = QPushButton()
            self._zoom_in_btn.setToolTip('Perbesar')
            try:
                self._zoom_in_btn.setIcon(qta.icon('fa5s.search-plus'))
            except Exception:
                pass
            self._zoom_in_btn.clicked.connect(self._on_nav_zoom_in)
            nav_layout.addWidget(self._zoom_in_btn)

            self._nav_frame.setLayout(nav_layout)
            self._nav_frame.setFixedHeight(34)
            # Slightly translucent so preview remains visible
            self._nav_frame.setWindowOpacity(0.92)
            self._nav_frame.raise_()
            # Ensure the frame width fits its contents (including the slider)
            try:
                self._nav_frame.adjustSize()
                # Add a bit of padding to avoid clipping
                w = max(self._nav_frame.sizeHint().width(), 160)
                self._nav_frame.setFixedWidth(w)
            except Exception:
                pass
            self._nav_frame.show()
        except Exception:
            self._nav_frame = None

    def set_images(self, before_path, after_path=None, preserve_zoom=False):
        """Set before and after images (normal mode). Optionally preserve zoom."""
        self.before_path = before_path
        self.after_path = after_path
        self.showing_before = False
        self.mask_mode = False
        self._update_display(preserve_zoom=preserve_zoom)

    def set_mask_images(self, before_mask_path, after_mask_path=None, preserve_zoom=False, show_before=None):
        """Set before and after mask images (mask preview mode). Optionally preserve zoom and set which to show."""
        self.mask_before_path = before_mask_path
        self.mask_after_path = after_mask_path
        if show_before is not None:
            self.showing_before = show_before
        else:
            self.showing_before = True  # Start with before (ori mask)
        self.mask_mode = True
        self._update_display(preserve_zoom=preserve_zoom)
        
    def show_before(self):
        """Show before image or mask."""
        if self.mask_mode:
            if self.mask_before_path:
                self.showing_before = True
                self._update_display(preserve_zoom=True)
        else:
            if self.before_path:
                self.showing_before = True
                self._update_display(preserve_zoom=True)
            
    def show_after(self):
        """Show after image or mask."""
        if self.mask_mode:
            if self.mask_after_path:
                self.showing_before = False
                self._update_display(preserve_zoom=True)
            elif self.mask_before_path:
                self.showing_before = False
                self._update_display(preserve_zoom=True)
        else:
            if self.after_path:
                self.showing_before = False
                self._update_display(preserve_zoom=True)
            elif self.before_path:
                self.showing_before = False
                self._update_display(preserve_zoom=True)
            
    def toggle_before_after(self, show_before):
        """Toggle between before and after (image or mask)."""
        if show_before:
            self.show_before()
        else:
            self.show_after()

    def resizeEvent(self, event):
        """Ensure floating nav stays at top-right corner relative to widget size."""
        super().resizeEvent(event)
        try:
            if self._nav_frame:
                margin = 10
                frame_w = self._nav_frame.width()
                # position inside our coords
                x = max(0, self.width() - frame_w - margin)
                y = margin
                self._nav_frame.move(x, y)
                self._nav_frame.raise_()
                # Keep slider in sync when resizing
                self._update_nav_zoom_slider()
                # Make sure nav frame width is enough after resize
                try:
                    if self._nav_frame:
                        self._nav_frame.adjustSize()
                        w = max(self._nav_frame.sizeHint().width(), 160)
                        self._nav_frame.setFixedWidth(w)
                except Exception:
                    pass
        except Exception:
            pass    

    def _on_nav_zoom_out(self):
        """Handle zoom-out button click from nav."""
        try:
            if self.view:
                self.view.zoom_out()
                self._update_nav_zoom_slider()
        except Exception:
            pass

    def _on_nav_reset_zoom(self):
        """Handle reset zoom button click from nav."""
        try:
            if self.view:
                self.view.reset_zoom()
                self._update_nav_zoom_slider()
        except Exception:
            pass

    def _on_nav_zoom_in(self):
        """Handle zoom-in button click from nav."""
        try:
            if self.view:
                self.view.zoom_in()
                self._update_nav_zoom_slider()
        except Exception:
            pass

    def _on_nav_zoom_slider_changed(self, value):
        """Handle slider changes and set the view scale accordingly.

        Uses a logarithmic mapping for the slider so that equal slider steps
        correspond to perceptually-equal zoom changes (linear in log scale).
        """
        try:
            if not hasattr(self, '_zoom_slider') or self._zoom_slider is None:
                return
            # Avoid reacting to programmatic updates
            if getattr(self, '_slider_updating', False):
                return

            # Slider range maps to [min_scale, max_scale] in log-space
            slider_min = self._zoom_slider.minimum()
            slider_max = self._zoom_slider.maximum()
            min_scale = 0.1
            max_scale = 10.0
            # Normalized 0..1
            t = (value - slider_min) / float(slider_max - slider_min)
            # Exponential interpolation between min_scale and max_scale
            target = min_scale * ((max_scale / min_scale) ** t)

            # Compute multiplicative factor from current scale
            try:
                current = self.view.current_scale
                if current <= 0:
                    factor = target
                else:
                    factor = target / current
                # Clamp factor to reasonable range
                if factor <= 0:
                    factor = 1.0
                self.view.scale(factor, factor)
                self.view.current_scale = target
            except Exception:
                pass
            # Update tooltip to reflect true zoom percent
            try:
                self._zoom_slider.setToolTip(f"Zoom: {int(round(self.view.current_scale * 100))}%")
            except Exception:
                pass
        finally:
            # Keep slider visually consistent
            try:
                self._update_nav_zoom_slider()
            except Exception:
                pass

    def _update_nav_zoom_slider(self):
        """Set slider position from current view scale safely (prevents recursion).

        Inverse of the log mapping used by the slider handler.
        """
        try:
            if not hasattr(self, '_zoom_slider') or self._zoom_slider is None:
                return
            # set flag to ignore changes
            self._slider_updating = True
            slider_min = self._zoom_slider.minimum()
            slider_max = self._zoom_slider.maximum()
            min_scale = 0.1
            max_scale = 10.0
            current = max(min_scale, min(max_scale, float(self.view.current_scale)))
            # Compute normalized t in [0,1] such that current = min * (max/min) ** t
            try:
                if current <= min_scale:
                    t = 0.0
                elif current >= max_scale:
                    t = 1.0
                else:
                    t = math.log(current / min_scale) / math.log(max_scale / min_scale)
            except Exception:
                t = 0.0
            val = int(round(slider_min + t * (slider_max - slider_min)))
            val = max(slider_min, min(slider_max, val))
            self._zoom_slider.setValue(val)
            try:
                self._zoom_slider.setToolTip(f"Zoom: {int(round(current * 100))}%")
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._slider_updating = False
            # Ensure nav frame resizes to fit slider
            try:
                if self._nav_frame:
                    self._nav_frame.adjustSize()
                    w = max(self._nav_frame.sizeHint().width(), 160)
                    self._nav_frame.setFixedWidth(w)
            except Exception:
                pass
    def nav_zoom_in(self):
        """Public: programmatic zoom in."""
        self._on_nav_zoom_in()

    def nav_zoom_out(self):
        """Public: programmatic zoom out."""
        self._on_nav_zoom_out()

    def nav_reset_zoom(self):
        """Public: programmatic reset zoom."""
        self._on_nav_reset_zoom()
    def get_current_file_path(self):
        """Get current displayed file path (image or mask)."""
        if self.mask_mode:
            if self.showing_before:
                return self.mask_before_path
            elif self.mask_after_path:
                return self.mask_after_path
            else:
                return self.mask_before_path
        else:
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
        self.mask_before_path = None
        self.mask_after_path = None
        self.showing_before = False
        self.mask_mode = False
        self.view.clear()
        
    def _update_display(self, preserve_zoom=False):
        """Update displayed image or mask, optionally preserving zoom."""
        if self.mask_mode:
            if self.showing_before and self.mask_before_path:
                self.view.set_image(self.mask_before_path, preserve_zoom=preserve_zoom)
            elif not self.showing_before and self.mask_after_path:
                self.view.set_image(self.mask_after_path, preserve_zoom=preserve_zoom)
            elif self.mask_before_path:
                self.view.set_image(self.mask_before_path, preserve_zoom=preserve_zoom)
            else:
                self.view.clear()
        else:
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
        
    def zoom_in(self, factor=1.05):
        """Zoom in the view by a factor and update current_scale.

        Default factor is small (1.05) for fine-grained zooming; pass larger
        factors for coarse zoom.
        """
        factor = float(factor)
        # Compute proposed new scale and clamp to max
        new_scale = self.current_scale * factor
        if new_scale > 10.0:
            factor = 10.0 / max(1e-9, self.current_scale)
            new_scale = 10.0
        self.scale(factor, factor)
        self.current_scale = new_scale

    def zoom_out(self, factor=None):
        """Zoom out the view by a factor and update current_scale.

        If factor is None we use the reciprocal of the default zoom-in for symmetry.
        """
        if factor is None:
            factor = 1.0 / 1.05
        factor = float(factor)
        # Compute proposed new scale and clamp to min
        new_scale = self.current_scale * factor
        if new_scale < 0.1:
            factor = 0.1 / max(1e-9, self.current_scale)
            new_scale = 0.1
        self.scale(factor, factor)
        self.current_scale = new_scale
        # Notify parent nav slider to update so UI stays in sync
        try:
            parent_widget = self.parent()
            while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                parent_widget = parent_widget.parent()
            if parent_widget and hasattr(parent_widget, '_update_nav_zoom_slider'):
                parent_widget._update_nav_zoom_slider()
        except Exception:
            pass

    def reset_zoom(self):
        """Reset zoom to fit the view to the image."""
        try:
            if self.scene and not self.scene.sceneRect().isNull():
                self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
                self.current_scale = self.transform().m11()
                # Notify parent nav slider (e.g., after fitInView) to keep slider synced
                try:
                    parent_widget = self.parent()
                    while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                        parent_widget = parent_widget.parent()
                    if parent_widget and hasattr(parent_widget, '_update_nav_zoom_slider'):
                        parent_widget._update_nav_zoom_slider()
                except Exception:
                    pass
        except Exception:
            pass
        
    def set_image(self, image_path, preserve_zoom=False):
        """Load and display image. If preserve_zoom, keep current zoom and scroll."""
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
            self.setTransform(saved_transform)
            if saved_h_scroll is not None:
                self.horizontalScrollBar().setValue(saved_h_scroll)
            if saved_v_scroll is not None:
                self.verticalScrollBar().setValue(saved_v_scroll)
        else:
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.current_scale = self.transform().m11()
        # Notify parent to update nav slider if present
        parent_widget = self.parent()
        try:
            if parent_widget and hasattr(parent_widget, '_update_nav_zoom_slider'):
                parent_widget._update_nav_zoom_slider()
        except Exception:
            pass        
    def clear(self):
        """Clear scene."""
        self.scene.clear()
        self.pixmap_item = None
        self.current_scale = 1.0
        
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming.

        Default wheel (plain scroll) uses larger increments for faster zooming.
        Holding Ctrl while wheeling performs fine-grained (brake) zoom for detailed adjustments.
        """
        fine = 1.05   # Ctrl-held slow increment (detail)
        coarse = 1.25 # Plain scroll faster increment
        if event.angleDelta().y() > 0:
            # Zoom in: Ctrl -> fine, otherwise coarse
            factor = fine if (event.modifiers() & Qt.ControlModifier) else coarse
        else:
            # Zoom out: Ctrl -> fine reciprocal, otherwise coarse reciprocal
            factor = (1.0 / fine) if (event.modifiers() & Qt.ControlModifier) else (1.0 / coarse)

        # Compute new scale and clamp
        new_scale = self.current_scale * factor
        if new_scale < 0.1:
            factor = 0.1 / max(1e-9, self.current_scale)
            new_scale = 0.1
        elif new_scale > 10.0:
            factor = 10.0 / max(1e-9, self.current_scale)
            new_scale = 10.0

        self.scale(factor, factor)
        self.current_scale = new_scale
        # Notify parent nav slider to update so UI stays in sync
        try:
            parent_widget = self.parent()
            while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                parent_widget = parent_widget.parent()
            if parent_widget and hasattr(parent_widget, '_update_nav_zoom_slider'):
                parent_widget._update_nav_zoom_slider()
        except Exception:
            pass
        
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
            # Right-click to toggle before/after mask or image
            self.is_right_clicking = True
            parent_widget = self.parent()
            while parent_widget and not isinstance(parent_widget, ImagePreviewWidget):
                parent_widget = parent_widget.parent()
            if parent_widget:
                # Toggle before/after
                parent_widget.toggle_before_after(not parent_widget.showing_before)
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
