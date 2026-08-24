"""Multi-display screen capture and Retina-aware selection overlay."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


class ScreenRecordingPermission:
    """Call the macOS CoreGraphics screen-recording permission APIs."""

    def __init__(self) -> None:
        self._core_graphics = None
        if __import__("sys").platform != "darwin":
            return
        try:
            self._core_graphics = ctypes.CDLL(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            )
            self._core_graphics.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
            self._core_graphics.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        except (OSError, AttributeError):
            self._core_graphics = None

    def is_authorized(self) -> bool:
        return bool(self._core_graphics and self._core_graphics.CGPreflightScreenCaptureAccess())

    def request(self) -> bool:
        return bool(self._core_graphics and self._core_graphics.CGRequestScreenCaptureAccess())


@dataclass
class DisplaySnapshot:
    geometry: QRect
    pixmap: QPixmap
    scale: float


class DesktopCapture:
    """A synchronized capture of every active display."""

    def __init__(self, snapshots: list[DisplaySnapshot]) -> None:
        if not snapshots:
            raise RuntimeError("No active displays were found")
        self.snapshots = snapshots
        virtual = QRect()
        for snapshot in snapshots:
            virtual = snapshot.geometry if virtual.isNull() else virtual.united(snapshot.geometry)
        self.virtual_geometry = virtual

    @classmethod
    def capture(cls) -> "DesktopCapture":
        snapshots: list[DisplaySnapshot] = []
        for screen in QApplication.screens():
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                raise RuntimeError("Screen capture returned an empty image")
            snapshots.append(
                DisplaySnapshot(
                    geometry=screen.geometry(),
                    pixmap=pixmap,
                    scale=max(1.0, float(pixmap.devicePixelRatio())),
                )
            )
        return cls(snapshots)

    def preview(self) -> QPixmap:
        canvas = QPixmap(self.virtual_geometry.size())
        canvas.fill(QColor(35, 35, 35))
        painter = QPainter(canvas)
        for snapshot in self.snapshots:
            offset = snapshot.geometry.topLeft() - self.virtual_geometry.topLeft()
            preview = snapshot.pixmap.scaled(
                snapshot.geometry.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(offset, preview)
        painter.end()
        return canvas

    def crop(self, selection: QRect) -> QImage:
        selection = selection.normalized()
        if selection.width() < 2 or selection.height() < 2:
            raise ValueError("Selection is too small")
        output_scale = max(snapshot.scale for snapshot in self.snapshots)
        output = QImage(
            round(selection.width() * output_scale),
            round(selection.height() * output_scale),
            QImage.Format.Format_RGBA8888,
        )
        output.fill(Qt.GlobalColor.white)
        painter = QPainter(output)
        for snapshot in self.snapshots:
            intersection = selection.intersected(snapshot.geometry)
            if intersection.isEmpty():
                continue
            source = QRect(
                round((intersection.x() - snapshot.geometry.x()) * snapshot.scale),
                round((intersection.y() - snapshot.geometry.y()) * snapshot.scale),
                round(intersection.width() * snapshot.scale),
                round(intersection.height() * snapshot.scale),
            )
            image = snapshot.pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            part = image.copy(source).scaled(
                round(intersection.width() * output_scale),
                round(intersection.height() * output_scale),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            target = QPoint(
                round((intersection.x() - selection.x()) * output_scale),
                round((intersection.y() - selection.y()) * output_scale),
            )
            painter.drawImage(target, part)
        painter.end()
        return output


class SelectionOverlay(QWidget):
    """Virtual-desktop overlay that emits one selected Retina-aware crop."""

    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, capture: DesktopCapture, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capture = capture
        self._background = capture.preview()
        self._start: QPoint | None = None
        self._selection = QRect()
        self.setGeometry(capture.virtual_geometry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabMouse()
        self.grabKeyboard()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._background)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 115))
        if not self._selection.isNull():
            local = self._selection.translated(-self.geometry().topLeft())
            painter.drawPixmap(local, self._background.copy(local))
            painter.setPen(QPen(QColor(90, 160, 255), 2, Qt.PenStyle.SolidLine))
            painter.drawRect(local)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self.mapToGlobal(event.position().toPoint())
            self._selection = QRect(self._start, self._start)
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._start is not None:
            current = self.mapToGlobal(event.position().toPoint())
            self._selection = QRect(self._start, current).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        current = self.mapToGlobal(event.position().toPoint())
        self._selection = QRect(self._start, current).normalized()
        self._start = None
        try:
            image = self.capture.crop(self._selection)
        except ValueError:
            self.cancel()
            return
        self.releaseKeyboard()
        self.close()
        self.selected.emit(image)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        super().keyPressEvent(event)

    def cancel(self) -> None:
        self.releaseMouse()
        self.releaseKeyboard()
        self.close()
        self.cancelled.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.releaseMouse()
        self.releaseKeyboard()
        super().closeEvent(event)
