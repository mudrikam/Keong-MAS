from PySide6.QtCore import Qt, Signal, QRectF, QPoint
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QMouseEvent, QLinearGradient


class MultiHandleSlider(QWidget):
    """A simple horizontal slider with three draggable handles (black, mid, white).

    Emits valuesChanged(black, mid, white) continuously while dragging.
    """
    valuesChanged = Signal(int, int, int)

    def __init__(self, parent=None, minimum=0, maximum=255, black=20, mid=128, white=235):
        super().__init__(parent)
        self._min = int(minimum)
        self._max = int(maximum)
        self._black = int(black)
        self._mid = int(mid)
        self._white = int(white)
        self.setMinimumHeight(28)
        self._active = None  # 'black' | 'mid' | 'white' | None
        self._margin = 8
        self.setMouseTracking(True)
        # Track whether mid was adjusted manually by user
        self._mid_manual = False
        # When mid is manually adjusted we store its relative ratio within [black, white]
        # so that subsequent moves of outer handles preserve that relative position.
        self._mid_ratio = None
        self._drag_start_vals = None

    def set_mid_manual(self, manual: bool):
        """Mark mid as manually adjusted (True) or return to auto mode (False).
        When enabling manual mode compute and store current mid ratio; when disabling,
        clear stored ratio."""
        self._mid_manual = bool(manual)
        if self._mid_manual:
            denom = self._white - self._black
            if denom > 0:
                self._mid_ratio = (self._mid - self._black) / float(denom)
            else:
                self._mid_ratio = 0.5
        else:
            self._mid_ratio = None

    def is_mid_manual(self) -> bool:
        return bool(self._mid_manual)

    def setRange(self, minimum, maximum):
        self._min = int(minimum)
        self._max = int(maximum)
        self.update()

    def setValues(self, black, mid, white, emit=True):
        # ensure proper ints and clamped order
        b = int(max(self._min, min(self._max, black)))
        m = int(max(self._min, min(self._max, mid)))
        w = int(max(self._min, min(self._max, white)))
        # enforce order b <= m <= w
        if m < b:
            m = b
        if w < m:
            w = m
        self._black, self._mid, self._white = b, m, w
        # if mid is manual, ensure stored ratio matches current positions
        if self._mid_manual:
            denom = self._white - self._black
            if denom > 0:
                self._mid_ratio = (self._mid - self._black) / float(denom)
            else:
                self._mid_ratio = 0.5
        self.update()
        if emit:
            self.valuesChanged.emit(self._black, self._mid, self._white)

    def getValues(self):
        return (self._black, self._mid, self._white)

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        track_y = h // 2
        track_h = 6
        left = self._margin
        right = w - self._margin

        # draw track background as gradient based on handle positions
        painter.setPen(Qt.NoPen)
        span = float(self._max - self._min) if (self._max - self._min) != 0 else 1.0
        pos_b = (self._black - self._min) / span
        pos_m = (self._mid - self._min) / span
        pos_w = (self._white - self._min) / span
        grad = QLinearGradient(left, track_y, right, track_y)
        grad.setColorAt(pos_b, QColor(0, 0, 0))
        grad.setColorAt(pos_m, QColor(180, 180, 180))
        grad.setColorAt(pos_w, QColor(255, 255, 255))
        painter.setBrush(QBrush(grad))
        painter.drawRect(left, track_y - track_h // 2, right - left, track_h)
        # subtle border for contrast
        painter.setPen(QPen(QColor(30, 30, 30)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(left, track_y - track_h // 2, right - left, track_h)

        # draw handles as small triangles/rects
        for val, color in ((self._black, QColor(0, 0, 0)), (self._mid, QColor(180, 180, 180)), (self._white, QColor(255, 255, 255))):
            x = self._value_to_x(val)
            # small vertical bar
            painter.setPen(QPen(QColor(30, 30, 30)))
            painter.setBrush(QBrush(color))
            rect = QRectF(x - 4, track_y - 10, 8, 20)
            painter.drawRect(rect)

    def _value_to_x(self, value):
        w = max(10, self.width())
        left = self._margin
        right = w - self._margin
        span = self._max - self._min
        if span <= 0:
            return left
        frac = (value - self._min) / float(span)
        return int(left + frac * (right - left))

    def _x_to_value(self, x):
        w = max(10, self.width())
        left = self._margin
        right = w - self._margin
        if x < left:
            x = left
        if x > right:
            x = right
        frac = (x - left) / float(right - left)
        val = int(self._min + frac * (self._max - self._min))
        return val

    def mousePressEvent(self, event: QMouseEvent):
        x = event.position().x() if hasattr(event, 'position') else event.x()
        # choose nearest handle
        dist_b = abs(self._value_to_x(self._black) - x)
        dist_m = abs(self._value_to_x(self._mid) - x)
        dist_w = abs(self._value_to_x(self._white) - x)
        dmin = min(dist_b, dist_m, dist_w)
        if dmin == dist_b:
            self._active = 'black'
        elif dmin == dist_m:
            self._active = 'mid'
            # user is starting to drag mid -> mark as manual and compute current ratio
            self.set_mid_manual(True)
        else:
            self._active = 'white'
        # remember starting values to compute deltas for relative movement
        self._drag_start_vals = (self._black, self._mid, self._white)
        self._mouse_move_to(x)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._active:
            x = event.position().x() if hasattr(event, 'position') else event.x()
            self._mouse_move_to(x)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._active:
            x = event.position().x() if hasattr(event, 'position') else event.x()
            self._mouse_move_to(x)
            self._active = None
            self._drag_start_vals = None
            event.accept()
        else:
            event.ignore()

    def _mouse_move_to(self, x):
        val = self._x_to_value(x)
        # Store previous values to compute deltas
        old_b, old_m, old_w = self._black, self._mid, self._white

        if self._active == 'black':
            # Move black
            proposed_b = max(self._min, min(self._max, min(val, self._mid)))
            self._black = proposed_b
            if not self._mid_manual or self._mid_ratio is None:
                # Auto center mid between black and white
                self._mid = int((self._black + self._white) / 2)
            else:
                # Preserve stored mid ratio relative to the new [black, white] range
                ratio = self._mid_ratio
                if ratio is None:
                    ratio = 0.5
                self._mid = int(round(max(self._black, min(self._white,
                                                          self._black + ratio * (self._white - self._black)))))
        elif self._active == 'mid':
            # Move mid within [black, white] and mark as manual; store ratio
            m = max(self._black, min(val, self._white))
            self._mid = max(self._min, min(m, self._max))
            self._mid_manual = True
            # compute and store current relative ratio of mid in [black, white]
            denom = self._white - self._black
            if denom > 0:
                self._mid_ratio = (self._mid - self._black) / float(denom)
            else:
                self._mid_ratio = 0.5
        elif self._active == 'white':
            # Move white
            proposed_w = max(self._min, min(self._max, max(val, self._mid)))
            self._white = proposed_w
            if not self._mid_manual or self._mid_ratio is None:
                # Auto center mid between black and white
                self._mid = int((self._black + self._white) / 2)
            else:
                ratio = self._mid_ratio
                if ratio is None:
                    ratio = 0.5
                self._mid = int(round(max(self._black, min(self._white,
                                                          self._black + ratio * (self._white - self._black)))))
        # Ensure ordering and bounds again as safety
        if self._mid < self._black:
            self._mid = self._black
        if self._mid > self._white:
            self._mid = self._white
        self.update()
        self.valuesChanged.emit(self._black, self._mid, self._white)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.setVisible(enabled or True)


if __name__ == '__main__':
    # quick self-test
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QLabel
    import sys

    app = QApplication(sys.argv)
    w = QWidget()
    layout = QVBoxLayout(w)
    s = MultiHandleSlider()
    label = QLabel('Values')

    def on_vals(b, m, wv):
        label.setText(f"{b} {m} {wv}")

    s.valuesChanged.connect(on_vals)
    layout.addWidget(s)
    layout.addWidget(label)
    w.show()
    sys.exit(app.exec())