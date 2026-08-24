"""Small, dependency-free widgets used by the modern FormulaOCR shell."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def line_icon(name: str, color: QColor | None = None, size: int = 18) -> QIcon:
    """Create a small consistent monochrome icon without theme/font glyph drift."""

    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color or QColor("#5f6368"), 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    x, y, s = 2.0, 2.0, float(size - 4)
    if name == "history":
        painter.drawEllipse(x, y, s, s)
        painter.drawLine(size / 2, size / 2, size / 2, 5)
        painter.drawLine(size / 2, size / 2, size - 5, size / 2)
    elif name == "settings":
        painter.drawEllipse(x + 3, y + 3, s - 6, s - 6)
        for angle in range(0, 360, 45):
            import math
            r1 = size / 2 - 6
            r2 = size / 2 - 2
            a = math.radians(angle)
            painter.drawLine(size / 2 + r1 * math.cos(a), size / 2 + r1 * math.sin(a), size / 2 + r2 * math.cos(a), size / 2 + r2 * math.sin(a))
    elif name == "undo":
        painter.drawLine(4, size / 2, size - 4, size / 2)
        painter.drawLine(4, size / 2, 8, size / 2 - 4)
        painter.drawLine(4, size / 2, 8, size / 2 + 4)
    elif name == "redo":
        painter.drawLine(4, size / 2, size - 4, size / 2)
        painter.drawLine(size - 4, size / 2, size - 8, size / 2 - 4)
        painter.drawLine(size - 4, size / 2, size - 8, size / 2 + 4)
    elif name == "restore":
        painter.drawArc(3, 3, size - 6, size - 6, 35 * 16, 285 * 16)
        painter.drawLine(4, 7, 8, 4)
        painter.drawLine(4, 7, 9, 8)
    elif name == "chevron":
        painter.drawLine(4, 6, size / 2, size - 5)
        painter.drawLine(size / 2, size - 5, size - 4, 6)
    elif name == "settings-small":
        painter.drawEllipse(5, 5, size - 10, size - 10)
    elif name == "api":
        painter.drawEllipse(size / 2 - 3, size / 2 - 3, 6, 6)
        painter.drawLine(4, size / 2, size / 2 - 3, size / 2)
        painter.drawLine(size / 2 + 3, size / 2, size - 4, size / 2)
        painter.drawLine(size / 2, 4, size / 2, size / 2 - 3)
        painter.drawLine(size / 2, size / 2 + 3, size / 2, size - 4)
    painter.end()
    return QIcon(canvas)


def set_accessible_button(button: QToolButton, text: str, accessible_name: str) -> None:
    """Apply consistent navigation-button semantics and tooltips."""

    button.setText(text)
    button.setToolTip(accessible_name)
    button.setAccessibleName(accessible_name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAutoRaise(True)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class HistoryOverlay(QWidget):
    """A resizable drawer that floats above the central workspace."""

    closed = Signal()
    width_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("historyOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVisible(False)
        self._drawer: QWidget | None = None
        self._mask = QWidget(self)
        self._mask.setObjectName("historyOverlayMask")
        self._mask.setStyleSheet("background: transparent;")
        self._mask.mousePressEvent = self._mask_mouse_press  # type: ignore[method-assign]
        self._animation: QPropertyAnimation | None = None

    def set_drawer(self, drawer: QWidget) -> None:
        self._drawer = drawer
        drawer.setParent(self)
        drawer.setMinimumWidth(280)
        drawer.setMaximumWidth(420)
        drawer.setFixedWidth(320)
        drawer.setVisible(False)
        shadow = QGraphicsDropShadowEffect(drawer)
        shadow.setBlurRadius(24)
        shadow.setOffset(4, 0)
        shadow.setColor(QColor(0, 0, 0, 70))
        drawer.setGraphicsEffect(shadow)

    @property
    def drawer_width(self) -> int:
        return self._drawer.width() if self._drawer is not None else 320

    def set_drawer_width(self, width: int) -> None:
        if self._drawer is None:
            return
        clamped = max(280, min(420, int(width)))
        self._drawer.setFixedWidth(clamped)
        self.width_changed.emit(clamped)
        self._position_children()

    def _mask_mouse_press(self, event) -> None:
        self.hide_drawer()
        event.accept()

    def _position_children(self) -> None:
        if self._drawer is None:
            return
        self._mask.setGeometry(self.rect())
        self._drawer.setGeometry(0, 0, self.drawer_width, self.height())
        self._drawer.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._position_children()
        super().resizeEvent(event)

    def show_drawer(self, animate: bool = True) -> None:
        if self._drawer is None:
            return
        self.setGeometry(self.parentWidget().rect() if self.parentWidget() is not None else QRect())
        self.setVisible(True)
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._mask.setVisible(True)
        self._drawer.setVisible(True)
        self._position_children()
        width = self.drawer_width
        if not animate:
            self._drawer.setGeometry(0, 0, width, self.height())
            self._drawer.raise_()
            return
        self._drawer.setGeometry(-width, 0, width, self.height())
        self._drawer.raise_()
        self._animation = QPropertyAnimation(self._drawer, b"geometry", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(QRect(-width, 0, width, self.height()))
        self._animation.setEndValue(QRect(0, 0, width, self.height()))
        self._animation.start()

    def hide_drawer(self, animate: bool = True) -> None:
        if not self.isVisible() or self._drawer is None:
            return
        width = self.drawer_width
        if not animate:
            self.setVisible(False)
            self._drawer.setVisible(False)
            self.closed.emit()
            return
        self._animation = QPropertyAnimation(self._drawer, b"geometry", self)
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self._animation.setStartValue(self._drawer.geometry())
        self._animation.setEndValue(QRect(-width, 0, width, self.height()))
        self._animation.finished.connect(self._finish_hide)
        self._animation.start()

    def _finish_hide(self) -> None:
        if self._drawer is not None:
            self._drawer.setVisible(False)
        self.setVisible(False)
        self.closed.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.hide_drawer()
            event.accept()
            return
        super().keyPressEvent(event)


class ResizeGrip(QWidget):
    """Subtle right-edge grip for changing the overlay drawer width."""

    width_changed = Signal(int)

    def __init__(self, drawer: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drawer = drawer
        self._dragging = False
        self._start_x = 0
        self._start_width = drawer.width()
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFixedWidth(8)
        self.setToolTip("拖动调整历史栏宽度")

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_x = event.globalPosition().toPoint().x()
            self._start_width = self._drawer.width()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._dragging:
            delta = event.globalPosition().toPoint().x() - self._start_x
            width = max(280, min(420, self._start_width + delta))
            self._drawer.setFixedWidth(width)
            self.width_changed.emit(width)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._dragging = False
        super().mouseReleaseEvent(event)


class PanelHeader(QFrame):
    """Compact title row used by the editor and preview panels."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panelHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)
        label = QLabel(title, self)
        label.setObjectName("panelTitle")
        layout.addWidget(label)
        self.content_layout = layout


class SectionCard(QFrame):
    """A light-weight card surface that follows the active palette."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


class HistoryDrawerPanel(QFrame):
    """Drawer surface with a narrow, keyboard-independent resize edge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("historyDrawer")
        self._grip = ResizeGrip(self, self)
        self._grip.raise_()

    @property
    def grip(self) -> ResizeGrip:
        return self._grip

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._grip.setGeometry(self.width() - self._grip.width(), 0, self._grip.width(), self.height())
        self._grip.raise_()
        super().resizeEvent(event)
