# toggle_switch.py (PyQt5)
from PyQt5.QtCore import Qt, QRectF, QPropertyAnimation, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from PyQt5.QtWidgets import QAbstractButton

class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, checked=False, width=50, height=28,
                 bg_on="green", bg_off="#c6c6c6"):
        super().__init__(parent)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)

        self._w = width
        self._h = height
        self._radius = self._h / 2
        self._bg_on = QColor(bg_on)
        self._bg_off = QColor(bg_off)

        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(self._w, self._h)

    def sizeHint(self):
        return self.minimumSize()

    def hitButton(self, pos):
        return True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self._w, self._h)

        # Track
        bg = self._bg_on if self.isChecked() else self._bg_off
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(rect, self._radius, self._radius)

        # Knob
        margin = 2
        d = self._h - 2 * margin  # knob diameter
        x_left = margin
        x_right = self._w - margin - d
        x = x_left + (x_right - x_left) * self._offset

        knob_rect = QRectF(x, margin, d, d)
        p.setBrush(QBrush(QColor("white")))
        p.setPen(QPen(QColor(0, 0, 0, 40)))
        p.drawEllipse(knob_rect)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            super().mouseReleaseEvent(e)
            self._animate()
        else:
            super().mouseReleaseEvent(e)

    def _animate(self):
        self._anim.stop()
        start = self._offset
        end = 1.0 if self.isChecked() else 0.0
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def getOffset(self):
        return self._offset

    def setOffset(self, v):
        self._offset = float(v)
        self.update()

    offset = pyqtProperty(float, fget=getOffset, fset=setOffset)