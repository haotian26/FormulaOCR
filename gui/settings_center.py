"""Modern categorized settings window for FormulaOCR."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QKeySequenceEdit,
    QSpinBox,
    QStackedWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .api_settings import APISettingsDialog
from .hotkey import HotkeyBinding
from .layout import line_icon
from .settings import AppSettings, LayoutRestoreMode


class ClearableKeySequenceEdit(QKeySequenceEdit):
    """Shortcut editor where Escape explicitly means no shortcut."""

    def __init__(self, sequence: QKeySequence, parent=None) -> None:
        super().__init__(sequence, parent)
        # FormulaOCR supports one global chord, not multi-step sequences.
        self.setMaximumSequenceLength(1)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.setKeySequence(QKeySequence())
            event.accept()
            return
        super().keyPressEvent(event)


class SettingsPage(QWidget):
    dirty_changed = Signal(bool)

    def __init__(self, title: str, description: str, parent=None) -> None:
        super().__init__(parent)
        self._dirty = False
        self._saved_snapshot = None
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._hide_saved_feedback)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)
        heading = QLabel(title, self)
        heading.setObjectName("settingsPageTitle")
        root.addWidget(heading)
        subtitle = QLabel(description, self)
        subtitle.setObjectName("settingsPageDescription")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(12)
        root.addLayout(self.body_layout, stretch=1)
        self.save_feedback = QLabel("", self)
        self.save_feedback.setObjectName("settingsSaveFeedback")
        self.save_feedback.hide()
        self.save_button = QPushButton("保存", self)
        self.save_button.setObjectName("primaryAction")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        footer = QHBoxLayout()
        footer.addWidget(self.save_feedback)
        footer.addStretch(1)
        footer.addWidget(self.save_button)
        root.addLayout(footer)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def snapshot(self):
        return None

    def initialize_clean(self) -> None:
        self._saved_snapshot = self.snapshot()
        self._set_dirty_state(False)

    def _set_dirty_state(self, dirty: bool, save_enabled: bool | None = None) -> None:
        changed = dirty != self._dirty
        self._dirty = dirty
        self.save_button.setEnabled(dirty if save_enabled is None else save_enabled)
        if dirty:
            self._hide_saved_feedback()
        if changed:
            self.dirty_changed.emit(dirty)

    def _hide_saved_feedback(self) -> None:
        self._feedback_timer.stop()
        self.save_feedback.clear()
        self.save_feedback.hide()

    def _show_saved_feedback(self) -> None:
        self.save_feedback.setText("✓ 已保存")
        self.save_feedback.show()
        self._feedback_timer.start(1500)

    def refresh_dirty(self) -> None:
        current = self.snapshot()
        self._set_dirty_state(current != self._saved_snapshot)

    def mark_dirty(self, *_args) -> None:
        self.refresh_dirty()

    def mark_clean(self, feedback: bool = True) -> None:
        self._saved_snapshot = self.snapshot()
        self._set_dirty_state(False)
        if feedback:
            self._show_saved_feedback()

    def save(self) -> None:  # pragma: no cover - implemented by pages
        self.mark_clean()


class GeneralSettingsPage(SettingsPage):
    def __init__(self, settings: AppSettings, window, parent=None) -> None:
        super().__init__("常规", "调整识别完成后的复制行为和窗口关闭后的运行方式。", parent)
        self.settings = settings
        self.window = window
        self.auto_copy = QCheckBox("识别完成后自动复制 Word 格式", self)
        self.auto_copy.setChecked(settings.auto_copy)
        self.hide_dock = QCheckBox("关闭主窗口后隐藏 Dock 图标，菜单栏继续运行", self)
        self.hide_dock.setChecked(settings.hide_dock_on_close)
        self.body_layout.addWidget(self.auto_copy)
        self.body_layout.addWidget(self.hide_dock)
        self.body_layout.addStretch(1)
        self.auto_copy.toggled.connect(self.mark_dirty)
        self.hide_dock.toggled.connect(self.mark_dirty)
        self.initialize_clean()

    def snapshot(self):
        return (self.auto_copy.isChecked(), self.hide_dock.isChecked())

    def save(self) -> None:
        self.settings.set_auto_copy(self.auto_copy.isChecked())
        self.settings.set_hide_dock_on_close(self.hide_dock.isChecked())
        self.window.auto_copy_checkbox.setChecked(self.auto_copy.isChecked())
        if not self.hide_dock.isChecked():
            self.window._set_dock_icon_visible(True)
        self.window.status_label.setText("常规设置已保存")
        self.mark_clean()


class LayoutSettingsPage(SettingsPage):
    def __init__(self, settings: AppSettings, window, parent=None) -> None:
        super().__init__("界面与布局", "选择启动时如何恢复窗口尺寸、分隔比例和历史抽屉状态。", parent)
        self.settings = settings
        self.window = window
        self.mode = QComboBox(self)
        self.mode.addItem("记住尺寸，历史关闭", LayoutRestoreMode.REMEMBER_CLOSED_HISTORY)
        self.mode.addItem("完整恢复上次状态", LayoutRestoreMode.REMEMBER_ALL)
        self.mode.addItem("每次使用优化默认布局", LayoutRestoreMode.SMART_DEFAULT)
        self.mode.setCurrentIndex(max(0, self.mode.findData(settings.layout_restore_mode)))
        form = QFormLayout()
        form.addRow("启动时布局", self.mode)
        self.body_layout.addLayout(form)
        hint = QLabel("窗口大小、图片/结果比例和 LaTeX/预览比例会在退出前保存。")
        hint.setWordWrap(True)
        self.body_layout.addWidget(hint)
        reset = QPushButton("立即重置布局", self)
        reset.setObjectName("secondaryAction")
        reset.clicked.connect(self.window.reset_layout)
        self.body_layout.addWidget(reset)
        self.body_layout.addStretch(1)
        self.mode.currentIndexChanged.connect(self.mark_dirty)
        self.initialize_clean()

    def snapshot(self):
        return (str(self.mode.currentData()),)

    def save(self) -> None:
        self.settings.set_layout_restore_mode(str(self.mode.currentData()))
        self.window._layout_mode = self.window._read_layout_mode()
        self.window._save_layout_state()
        self.window.status_label.setText("界面与布局设置已保存")
        self.mark_clean()


class HotkeySettingsPage(SettingsPage):
    def __init__(self, settings: AppSettings, window, parent=None) -> None:
        super().__init__("快捷键", "按下新的截图快捷键；按 Esc 可清空快捷键。", parent)
        self.settings = settings
        self.window = window
        try:
            binding = HotkeyBinding.from_storage(settings.hotkey)
            sequence = binding.qt_sequence() if binding else QKeySequence()
        except ValueError:
            sequence = QKeySequence()
        self.edit = ClearableKeySequenceEdit(sequence, self)
        self.edit.setToolTip("按 Esc 清空快捷键")
        self.body_layout.addWidget(self.edit)
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("settingsInlineError")
        self.error_label.setWordWrap(True)
        self.body_layout.addWidget(self.error_label)
        self.body_layout.addStretch(1)
        self.edit.keySequenceChanged.connect(self._refresh_hotkey_state)
        self.initialize_clean()

    def snapshot(self):
        try:
            binding = HotkeyBinding.from_qt_sequence(self.edit.keySequence())
        except ValueError as exc:
            return ("invalid", str(exc))
        return ("valid", binding.storage if binding else "")

    def _refresh_hotkey_state(self, *_args) -> None:
        current = self.snapshot()
        valid = current[0] == "valid"
        self.error_label.setText("" if valid else str(current[1]))
        dirty = current != self._saved_snapshot
        self._set_dirty_state(dirty, save_enabled=valid and dirty)

    def save(self) -> None:
        try:
            binding = HotkeyBinding.from_qt_sequence(self.edit.keySequence())
        except ValueError as exc:
            QMessageBox.warning(self, "快捷键无效", str(exc))
            return
        if not self.window._hotkey.set_binding(binding):
            QMessageBox.warning(self, "快捷键未启用", "请检查 macOS 输入监控权限。")
            return
        self.settings.set_hotkey(binding.storage if binding else "")
        self.window._saved_hotkey_binding = binding
        self.window.status_label.setText("截图快捷键已保存")
        self.mark_clean()


class HistorySettingsPage(SettingsPage):
    def __init__(self, settings: AppSettings, window, parent=None) -> None:
        super().__init__("历史记录", "设置本机最多保留的识别记录数量。", parent)
        self.settings = settings
        self.window = window
        self.limit = QSpinBox(self)
        self.limit.setRange(20, 2000)
        self.limit.setValue(settings.history_limit)
        form = QFormLayout()
        form.addRow("最多保留", self.limit)
        self.body_layout.addLayout(form)
        self.body_layout.addStretch(1)
        self.limit.valueChanged.connect(self.mark_dirty)
        self.initialize_clean()

    def snapshot(self):
        return (self.limit.value(),)

    def save(self) -> None:
        value = self.limit.value()
        count = self.window.history_list.count()
        if value < count:
            answer = QMessageBox.question(
                self,
                "清理较早记录",
                f"新上限会删除最旧的 {count - value} 条记录，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.settings.set_history_limit(value)
        if self.window._history_store is not None:
            self.window._history_store.set_limit(value)
            self.window._refresh_history_list()
        self.window.status_label.setText(f"历史记录上限已保存：{value} 条")
        self.mark_clean()


class SettingsCenter(QDialog):
    """Resizable settings center with independent per-page saves."""

    closed = Signal()

    def __init__(self, window, initial_page: str = "general", parent=None) -> None:
        super().__init__(parent or window)
        self.setObjectName("settingsCenter")
        self.window = window
        self.setWindowTitle("FormulaOCR 设置")
        self.setModal(False)
        self.resize(760, 560)
        self.setMinimumSize(680, 500)
        self._pages: dict[str, QWidget] = {}

        self.sidebar = QListWidget(self)
        self.sidebar.setObjectName("settingsSidebar")
        self.sidebar.setFixedWidth(172)
        self.sidebar.setSpacing(3)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("settingsStack")
        entries = (
            ("general", "常规", "settings"),
            ("layout", "界面与布局", "restore"),
            ("hotkey", "快捷键", "history"),
            ("api", "自定义模型与 API", "api"),
            ("history", "历史记录", "history"),
        )
        pages = {
            "general": GeneralSettingsPage(window._settings, window, self),
            "layout": LayoutSettingsPage(window._settings, window, self),
            "hotkey": HotkeySettingsPage(window._settings, window, self),
            "api": APISettingsDialog(window._settings.api_profiles, self),
            "history": HistorySettingsPage(window._settings, window, self),
        }
        icon_color = self.palette().color(QPalette.ColorRole.Text)
        for page_id, label, icon_name in entries:
            item = QListWidgetItem(line_icon(icon_name, icon_color), label)
            item.setData(Qt.ItemDataRole.UserRole, page_id)
            self.sidebar.addItem(item)
            page = pages[page_id]
            if page_id == "api":
                page.setWindowFlags(Qt.WindowType.Widget)
                page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                page.settings_saved.connect(window._refresh_api_controls)
            self.stack.addWidget(page)
            self._pages[page_id] = page
            if hasattr(page, "dirty_changed"):
                page.dirty_changed.connect(lambda _dirty, p=page: self._update_title(p))
        self.sidebar.currentRowChanged.connect(self._show_row)
        self.sidebar.setCurrentRow(max(0, next((i for i, entry in enumerate(entries) if entry[0] == initial_page), 0)))

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.sidebar)
        content.addWidget(self.stack, stretch=1)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(content)

    def _show_row(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _update_title(self, _page) -> None:
        self.setWindowTitle("FormulaOCR 设置 · 有未保存更改")
        if not any(getattr(page, "is_dirty", False) or getattr(getattr(page, "save_button", None), "isEnabled", lambda: False)() for page in self._pages.values()):
            self.setWindowTitle("FormulaOCR 设置")

    def show_page(self, page_id: str) -> None:
        for row in range(self.sidebar.count()):
            if self.sidebar.item(row).data(Qt.ItemDataRole.UserRole) == page_id:
                self.sidebar.setCurrentRow(row)
                break
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        dirty = [page for page in self._pages.values() if getattr(page, "is_dirty", False) or getattr(getattr(page, "save_button", None), "isEnabled", lambda: False)()]
        if dirty:
            answer = QMessageBox.question(
                self,
                "未保存更改",
                "仍有设置未保存，确定放弃这些更改吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
        self.closed.emit()
