"""FormulaOCR GUI workflow with screen capture and custom hotkeys."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QEvent, QProcess, QThread, QTimer, QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QCheckBox,
    QDialog,
    QAbstractItemView,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMainWindow,
    QMessageBox,
    QKeySequenceEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QComboBox,
    QStackedWidget,
    QStackedLayout,
    QSizePolicy,
    QSystemTrayIcon,
    QStyle,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from clipboard.manager import ClipboardManager
from converter import MathMLConversionError, latex_to_mathml
from ocr.result import OCRResult
from ocr.postprocess import normalize_latex
from api.providers import RemoteOCRResult

from .settings import AppSettings, LayoutRestoreMode
from .hotkey import GlobalHotkey, HotkeyBinding
from .screen_capture import DesktopCapture, ScreenRecordingPermission, SelectionOverlay
from .math_preview import FormulaPreview
from .worker import EngineFactory, OCRWorker, default_engine_factory
from .api_worker import APIWorker
from .api_settings import APISettingsDialog
from .history import HistoryRecord, HistoryStore
from .layout import HistoryDrawerPanel, HistoryOverlay, PanelHeader, SectionCard, line_icon, set_accessible_button
from .settings_center import SettingsCenter


class HotkeySequenceEdit(QKeySequenceEdit):
    """Shortcut editor where Escape explicitly means no global shortcut."""

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.setKeySequence(QKeySequence())
            event.accept()
            return
        super().keyPressEvent(event)


class FormulaPasteEdit(QPlainTextEdit):
    """Text editor that routes image paste to the OCR workflow.

    A standard paste action on the main window cannot see Cmd+V while a
    QPlainTextEdit has focus: the editor handles the platform paste shortcut
    first.  Intercept only image pastes here and leave ordinary text pastes
    to Qt's native editor implementation.
    """

    image_paste_requested = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            if clipboard is not None and not clipboard.image().isNull():
                self.image_paste_requested.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class FormulaOCRWindow(QMainWindow):
    """Open an image, recognize it, preview LaTeX and copy the result."""

    recognize_requested = Signal(str)
    api_recognize_requested = Signal(object, object)

    def __init__(
        self,
        engine_factory: EngineFactory | None = None,
        clipboard_manager: ClipboardManager | None = None,
        settings: AppSettings | None = None,
        capture_factory=None,
        screen_permission: ScreenRecordingPermission | None = None,
        hotkey: GlobalHotkey | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("FormulaOCR")
        self.resize(1120, 760)
        self.setMinimumSize(900, 650)
        self._engine_factory = engine_factory
        self._clipboard = clipboard_manager or ClipboardManager()
        self._settings = settings or AppSettings()
        self._current_image: Path | None = None
        self._current_image_bytes: bytes | None = None
        self._temporary_capture: Path | None = None
        self._preview_source = QPixmap()
        self._capture_factory = capture_factory or DesktopCapture.capture
        self._screen_permission = screen_permission or ScreenRecordingPermission()
        self._overlay: SelectionOverlay | None = None
        self._capture_pending = False
        self._native_capture_process: QProcess | None = None
        self._use_native_capture = (
            sys.platform == "darwin"
            and capture_factory is None
            and shutil.which("/usr/sbin/screencapture") is not None
        )
        self._quitting = False
        self._shutdown_started = False
        self._native_status_item = None
        self._api_profiles = []
        self._api_selected_profile_id = ""
        self._api_pending = False
        self._local_original_latex = ""
        self._api_original_latex = ""
        self._api_result: RemoteOCRResult | None = None
        try:
            self._history_store: HistoryStore | None = HistoryStore(limit=self._settings.history_limit)
            self._history_error: str | None = None
        except Exception as exc:
            self._history_store = None
            self._history_error = str(exc)
        self._history_record_id: str | None = None
        self._history_loading = False
        self._history_save_timer = QTimer(self)
        self._history_save_timer.setSingleShot(True)
        self._history_save_timer.setInterval(500)
        self._history_save_timer.timeout.connect(self._flush_history_draft)
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(300)
        self._layout_save_timer.timeout.connect(self._save_layout_state)
        self._layout_mode = self._read_layout_mode()
        self._layout_restored = False
        self._style_applying = False
        self.has_tray_menu = False
        app = QApplication.instance()
        self._application_state_connected = False
        if app is not None:
            # Use the application state signal instead of an application-wide
            # Python event filter. The latter can receive native macOS reopen
            # events during launch and is unsafe with the PySide wrapper in a
            # frozen app.
            app.applicationStateChanged.connect(self._on_application_state_changed)
            self._application_state_connected = True

        self.open_button = QPushButton("打开图片")
        self.open_button.setObjectName("primaryAction")
        self.open_button.clicked.connect(self.open_image)
        self.paste_button = QPushButton("粘贴图片")
        self.paste_button.clicked.connect(self.paste_image)
        self.capture_button = QPushButton("截图 OCR")
        self.capture_button.clicked.connect(self.capture_screen)
        self.api_button = QPushButton(self)
        self.api_button.setText("API 重识别")
        self.api_button.clicked.connect(self.recognize_with_api)
        self.api_button.setVisible(False)
        self.api_profile_button = QPushButton(self)
        self.api_profile_button.setObjectName("apiProfileChip")
        self.api_profile_button.clicked.connect(self.show_api_profile_menu)
        self.api_profile_button.setVisible(False)
        self.status_label = QLabel("请选择一张公式图片")
        self.status_label.setWordWrap(True)

        self.preview_label = QLabel("图片预览")
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(360, 220)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.local_latex_edit = FormulaPasteEdit()
        self.local_latex_edit.setPlaceholderText("OCR 结果将在这里显示")
        self.local_latex_edit.setReadOnly(False)
        self.local_latex_edit.setMinimumSize(320, 220)
        self.api_latex_edit = FormulaPasteEdit()
        self.api_latex_edit.setPlaceholderText("API 结果将在这里显示")
        self.api_latex_edit.setReadOnly(False)
        self.api_latex_edit.setMinimumSize(320, 220)
        self.latex_stack = QStackedWidget()
        self.latex_stack.addWidget(self.local_latex_edit)
        self.latex_stack.addWidget(self.api_latex_edit)
        self.latex_edit = self.local_latex_edit
        self.formula_preview = FormulaPreview()
        self.local_latex_edit.image_paste_requested.connect(self.paste_image)
        self.api_latex_edit.image_paste_requested.connect(self.paste_image)
        self.local_latex_edit.textChanged.connect(self._update_formula_preview)
        self.api_latex_edit.textChanged.connect(self._update_formula_preview)
        self.local_latex_edit.textChanged.connect(self._schedule_history_draft_save)
        self.api_latex_edit.textChanged.connect(self._schedule_history_draft_save)

        self.auto_copy_checkbox = QCheckBox("识别完成后自动复制 Word 格式")
        self.auto_copy_checkbox.setChecked(self._settings.auto_copy)
        self.auto_copy_checkbox.toggled.connect(self._settings.set_auto_copy)

        self.history_button = QToolButton(self)
        set_accessible_button(self.history_button, "历史", "打开或关闭识别历史")
        self.history_button.setObjectName("navButton")
        self.history_button.setCheckable(True)
        self.history_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        icon_color = self.palette().color(QPalette.ColorRole.Text)
        self.history_button.setIcon(line_icon("history", icon_color))
        self.history_button.setIconSize(QSize(20, 20))
        self.history_button.clicked.connect(self._toggle_history_sidebar)
        self.settings_button = QToolButton(self)
        self.settings_button.setToolTip("打开 FormulaOCR 设置")
        self.settings_button.setAccessibleName("打开 FormulaOCR 设置")
        self.settings_button.setObjectName("navButton")
        self.settings_button.setAutoRaise(True)
        self.settings_button.setIcon(line_icon("settings", icon_color))
        self.settings_button.setIconSize(QSize(20, 20))
        self.settings_button.clicked.connect(lambda: self.show_settings_center("general"))

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        action_row = QHBoxLayout(toolbar)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(self.history_button)
        action_row.addWidget(self.open_button)
        action_row.addWidget(self.paste_button)
        action_row.addWidget(self.capture_button)
        action_row.addWidget(self.api_button)
        action_row.addWidget(self.api_profile_button)
        action_row.addStretch(1)
        self.toolbar_status = QLabel("离线识别")
        self.toolbar_status.setObjectName("toolbarStatus")
        action_row.addWidget(self.toolbar_status)
        action_row.addWidget(self.settings_button)

        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(6)
        self.content_splitter.addWidget(self.preview_label)
        self.result_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.result_splitter.setChildrenCollapsible(False)
        self.result_splitter.setHandleWidth(6)
        latex_panel = QWidget()
        latex_panel.setObjectName("sectionCard")
        latex_layout = QVBoxLayout(latex_panel)
        latex_layout.setContentsMargins(0, 0, 8, 0)
        latex_header = PanelHeader("LaTeX", latex_panel)
        latex_layout.addWidget(latex_header)
        latex_layout.addWidget(self.latex_stack, stretch=1)
        preview_panel = QWidget()
        preview_panel.setObjectName("sectionCard")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(8, 0, 0, 0)
        preview_header = PanelHeader("公式预览", preview_panel)
        preview_layout.addWidget(preview_header)
        preview_layout.addWidget(self.formula_preview, stretch=1)
        result_toolbar = QFrame()
        result_toolbar.setObjectName("resultToolbar")
        result_actions = QHBoxLayout(result_toolbar)
        result_actions.setContentsMargins(0, 0, 0, 0)
        result_actions.setSpacing(8)
        result_title = QLabel("识别结果")
        result_title.setObjectName("resultToolbarTitle")
        result_actions.addWidget(result_title)
        self.source_selector = QComboBox(self)
        self.source_selector.setObjectName("sourceSelector")
        self.source_selector.addItem("内置", "local")
        self.source_selector.setEnabled(False)
        self.source_selector.currentIndexChanged.connect(self._on_source_changed)
        result_actions.addWidget(self.source_selector)
        self.undo_button = QToolButton(self)
        self.undo_button.setObjectName("resultIconButton")
        self.undo_button.setIcon(line_icon("undo", self.palette().color(QPalette.ColorRole.Text)))
        self.undo_button.setToolTip("撤销")
        self.undo_button.setAccessibleName("撤销")
        self.redo_button = QToolButton(self)
        self.redo_button.setObjectName("resultIconButton")
        self.redo_button.setIcon(line_icon("redo", self.palette().color(QPalette.ColorRole.Text)))
        self.redo_button.setToolTip("重做")
        self.redo_button.setAccessibleName("重做")
        self.restore_button = QPushButton("恢复原文", self)
        self.restore_button.setToolTip("恢复当前来源的识别原文")
        self.undo_button.clicked.connect(lambda: self.latex_edit.undo())
        self.redo_button.clicked.connect(lambda: self.latex_edit.redo())
        self.restore_button.clicked.connect(self.restore_original_result)
        for button in (self.undo_button, self.redo_button, self.restore_button):
            button.setEnabled(False)
            result_actions.addWidget(button)
        result_actions.addStretch(1)
        self.copy_word_button = QPushButton("复制 Word")
        self.copy_latex_button = QPushButton("复制 LaTeX")
        self.copy_word_button.setEnabled(False)
        self.copy_latex_button.setEnabled(False)
        self.copy_word_button.clicked.connect(self.copy_word)
        self.copy_latex_button.clicked.connect(self.copy_latex)
        result_actions.addWidget(self.copy_word_button)
        result_actions.addWidget(self.copy_latex_button)
        content_result = QVBoxLayout()
        content_result.setContentsMargins(0, 0, 0, 0)
        content_result.setSpacing(8)
        content_result.addWidget(result_toolbar)
        content_result.addWidget(self.result_splitter, stretch=1)
        self.result_splitter.addWidget(latex_panel)
        self.result_splitter.addWidget(preview_panel)
        self.result_splitter.setSizes([520, 520])
        result_container = QWidget()
        result_container.setLayout(content_result)
        self.content_splitter.addWidget(result_container)
        self.content_splitter.setSizes([350, 460])
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 2)
        footer_panel = QFrame()
        footer_panel.setObjectName("footerPanel")
        footer_layout = QVBoxLayout(footer_panel)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.addWidget(self.auto_copy_checkbox)
        footer_layout.addWidget(self.status_label)
        main_content = QWidget()
        main_content_layout = QVBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(8)
        main_content_layout.addWidget(self.content_splitter, stretch=1)
        main_content_layout.addWidget(footer_panel, stretch=0)
        self.history_panel = self._build_history_sidebar()
        self.history_overlay = HistoryOverlay()
        self.history_overlay.set_drawer(self.history_panel)
        self.history_overlay.closed.connect(lambda: self.history_button.setChecked(False))
        self.history_panel.grip.width_changed.connect(self._on_history_width_changed)
        self.workspace_host = QWidget()
        host_layout = QStackedLayout(self.workspace_host)
        host_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addWidget(main_content)
        host_layout.addWidget(self.history_overlay)
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(toolbar)
        layout.addWidget(self.workspace_host, stretch=1)
        self._thread = QThread(self)
        self._worker = OCRWorker(engine_factory or default_engine_factory)
        self._worker.moveToThread(self._thread)
        self.recognize_requested.connect(self._worker.recognize, Qt.ConnectionType.QueuedConnection)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._thread.start()

        self._api_thread = QThread(self)
        self._api_worker = APIWorker()
        self._api_worker.moveToThread(self._api_thread)
        self.api_recognize_requested.connect(self._api_worker.recognize, Qt.ConnectionType.QueuedConnection)
        self._api_worker.result_ready.connect(self._on_api_result)
        self._api_worker.error.connect(self._on_api_error)
        self._api_thread.start()

        self._hotkey = hotkey or GlobalHotkey(parent=self)
        self._hotkey.activated.connect(self.capture_screen)
        try:
            saved_binding = HotkeyBinding.from_storage(self._settings.hotkey)
        except ValueError:
            saved_binding = HotkeyBinding.from_storage(None)
        if hotkey is None:
            self._hotkey.stop()
            self._hotkey.set_binding(saved_binding)
        self._hotkey.start()
        self._saved_hotkey_binding = saved_binding
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.content_splitter.splitterMoved.connect(lambda _pos, _index: self._schedule_layout_save())
        self.result_splitter.splitterMoved.connect(lambda _pos, _index: self._schedule_layout_save())
        self._apply_modern_style()
        self._hotkey_dialog: QDialog | None = None
        self.hotkey_edit: HotkeySequenceEdit | None = None
        self.hotkey_save_button: QPushButton | None = None
        self._window_settings_dialog: QDialog | None = None
        self._history_settings_dialog: QDialog | None = None
        self._settings_center: SettingsCenter | None = None
        self._dock_icon_hidden = False
        self._paste_action = QAction("粘贴图片", self)
        self._paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self._paste_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._paste_action.triggered.connect(self._route_paste_shortcut)
        self.addAction(self._paste_action)
        self._setup_settings_menu()
        self._refresh_history_list()
        self._refresh_api_controls()
        QTimer.singleShot(0, self._restore_layout_state)
        self.tray_icon = None
        if sys.platform == "darwin" and QApplication.platformName() != "offscreen":
            try:
                from .macos_status_item import MacStatusItem

                self._native_status_item = MacStatusItem(self)
                self.has_tray_menu = True
            except Exception:
                self._native_status_item = None
        if self._native_status_item is None:
            self.tray_icon = self._setup_tray()
            self.has_tray_menu = self.tray_icon is not None

    def _read_layout_mode(self) -> str:
        value = getattr(self._settings, "layout_restore_mode", LayoutRestoreMode.REMEMBER_CLOSED_HISTORY)
        return value if value in LayoutRestoreMode.ALL else LayoutRestoreMode.REMEMBER_CLOSED_HISTORY

    def _modern_stylesheet(self) -> str:
        palette = self.palette()
        window = palette.color(QPalette.ColorRole.Window).name()
        base = palette.color(QPalette.ColorRole.Base).name()
        text = palette.color(QPalette.ColorRole.Text).name()
        alternate = palette.color(QPalette.ColorRole.AlternateBase).name()
        accent = palette.color(QPalette.ColorRole.Highlight).name()
        border = palette.color(QPalette.ColorRole.Mid).name()
        return f"""
        QMainWindow {{ background: {window}; color: {text}; }}
        QFrame#toolbar {{ background: transparent; }}
        QLabel#toolbarStatus {{ color: {palette.color(QPalette.ColorRole.PlaceholderText).name()}; padding: 5px 8px; }}
        QToolButton#navButton {{ border: 0; border-radius: 8px; padding: 6px; min-width: 30px; min-height: 30px; color: {text}; }}
        QToolButton#navButton:hover {{ background: {alternate}; }}
        QToolButton#navButton:checked {{ background: {accent}; color: white; }}
        QPushButton {{ border: 1px solid {border}; border-radius: 8px; padding: 6px 12px; min-height: 28px; background: {base}; color: {text}; }}
        QPushButton:hover {{ border-color: {accent}; }}
        QPushButton:pressed {{ background: {alternate}; }}
        QPushButton#apiProfileChip {{ border-radius: 14px; padding: 5px 12px; min-height: 26px; color: {text}; background: {alternate}; }}
        QPushButton#apiProfileChip:hover {{ border-color: {accent}; }}
        QPushButton#primaryAction {{ background: {accent}; color: white; border-color: {accent}; font-weight: 600; }}
        QPushButton#primaryAction:hover {{ background: {accent}; }}
        QPushButton#primaryAction:disabled {{ background: {alternate}; color: {palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()}; border-color: {border}; font-weight: 400; }}
        QPushButton#secondaryAction {{ background: transparent; }}
        QFrame#resultToolbar {{ min-height: 44px; }}
        QLabel#resultToolbarTitle {{ font-size: 15px; font-weight: 700; }}
        QComboBox#sourceSelector {{ min-height: 30px; border-radius: 15px; padding: 3px 12px; background: {alternate}; }}
        QComboBox#sourceSelector::drop-down {{ width: 0px; border: 0px; }}
        QToolButton#resultIconButton {{ border: 0; border-radius: 8px; min-width: 30px; min-height: 30px; padding: 5px; }}
        QToolButton#resultIconButton:hover {{ background: {alternate}; }}
        QDialog#settingsCenter {{ background: {window}; }}
        QListWidget#settingsSidebar {{ background: {alternate}; border: 0; padding: 8px; outline: 0; }}
        QListWidget#settingsSidebar::item {{ min-height: 34px; padding: 4px 10px; border-radius: 7px; }}
        QListWidget#settingsSidebar::item:selected {{ background: {accent}; color: white; }}
        QLabel#settingsPageTitle {{ font-size: 20px; font-weight: 700; }}
        QLabel#settingsPageDescription {{ color: {palette.color(QPalette.ColorRole.PlaceholderText).name()}; }}
        QLabel#settingsSaveFeedback {{ color: #2da44e; padding-right: 8px; }}
        QLabel#settingsInlineError {{ color: #d1242f; }}
        QFrame#sectionCard {{ background: {base}; border: 1px solid {border}; border-radius: 10px; }}
        QFrame#panelHeader {{ background: transparent; border: 0; }}
        QLabel#panelTitle {{ font-weight: 600; font-size: 14px; }}
        QLabel#previewLabel {{ background: {base}; border: 1px solid {border}; border-radius: 10px; }}
        QPlainTextEdit {{ background: {base}; border: 1px solid {border}; border-radius: 8px; padding: 8px; selection-background-color: {accent}; }}
        QComboBox, QSpinBox {{ min-height: 28px; border-radius: 7px; padding: 2px 8px; }}
        QSplitter::handle {{ background: transparent; }}
        QSplitter::handle:hover {{ background: {accent}; border-radius: 3px; }}
        QFrame#footerPanel {{ background: transparent; }}
        QFrame#historyDrawer {{ background: {window}; border: 1px solid {border}; border-radius: 12px; }}
        QLabel#drawerTitle {{ font-size: 16px; font-weight: 700; }}
        QLabel#drawerCount {{ color: {palette.color(QPalette.ColorRole.PlaceholderText).name()}; }}
        QListWidget {{ background: {base}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
        QListWidget::item {{ padding: 8px; border-radius: 7px; }}
        QListWidget::item:selected {{ background: {accent}; color: white; }}
        """

    def _apply_modern_style(self) -> None:
        if self._style_applying:
            return
        self._style_applying = True
        try:
            self.setStyleSheet(self._modern_stylesheet())
        finally:
            self._style_applying = False

    def _on_history_width_changed(self, width: int) -> None:
        setter = getattr(self._settings, "set_layout_value", None)
        if setter is not None:
            setter("history_width", int(width))
        self._schedule_layout_save()

    def _schedule_layout_save(self) -> None:
        if not self._layout_restored:
            return
        self._layout_save_timer.start()

    def _save_layout_state(self) -> None:
        if not self._layout_restored or self._layout_mode == LayoutRestoreMode.SMART_DEFAULT:
            return
        setter = getattr(self._settings, "set_layout_value", None)
        if setter is None:
            return
        setter("version", 3)
        setter("geometry", self.saveGeometry())
        setter("content_splitter", self.content_splitter.saveState())
        setter("result_splitter", self.result_splitter.saveState())
        setter("history_width", self.history_overlay.drawer_width)
        setter("history_open", self.history_overlay.isVisible())
        sync = getattr(self._settings, "sync", None)
        if sync is not None:
            sync()

    def _restore_layout_state(self) -> None:
        if self._layout_restored:
            return
        self._layout_mode = self._read_layout_mode()
        restored = False
        value_getter = getattr(self._settings, "layout_value", lambda _key, default=None: default)
        if self._layout_mode != LayoutRestoreMode.SMART_DEFAULT:
            version = value_getter("version", 0)
            geometry = value_getter("geometry", None)
            try:
                if int(version) == 3 and geometry:
                    restored = self.restoreGeometry(geometry)
                    self.content_splitter.restoreState(value_getter("content_splitter", b""))
                    self.result_splitter.restoreState(value_getter("result_splitter", b""))
                    width = int(value_getter("history_width", 320))
                    self.history_overlay.set_drawer_width(width)
            except (TypeError, ValueError, RuntimeError):
                restored = False
        if not restored:
            self.resize(1120, 760)
            self.content_splitter.setSizes([350, 460])
            self.result_splitter.setSizes([520, 520])
            self.history_overlay.set_drawer_width(320)
        # The recommended mode always starts with the drawer closed.
        if self._layout_mode == LayoutRestoreMode.REMEMBER_ALL and bool(value_getter("history_open", False)):
            self.history_button.setChecked(True)
            self.history_overlay.show_drawer(animate=False)
        else:
            self.history_button.setChecked(False)
            self.history_overlay.hide_drawer(animate=False)
        self._layout_restored = True

    def reset_layout(self) -> None:
        self._layout_save_timer.stop()
        if hasattr(self._settings, "remove_layout_values"):
            self._settings.remove_layout_values()
        self._layout_mode = self._read_layout_mode()
        self.resize(1120, 760)
        self.content_splitter.setSizes([350, 460])
        self.result_splitter.setSizes([520, 520])
        self.history_overlay.set_drawer_width(320)
        self.history_button.setChecked(False)
        self.history_overlay.hide_drawer(animate=False)
        self._layout_restored = True
        self.status_label.setText("界面布局已重置")

    def show_layout_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("界面与布局")
        dialog.setModal(False)
        dialog.resize(520, 250)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("启动时布局"))
        options = QComboBox(dialog)
        options.addItem("记住尺寸，历史关闭", LayoutRestoreMode.REMEMBER_CLOSED_HISTORY)
        options.addItem("完整恢复上次状态", LayoutRestoreMode.REMEMBER_ALL)
        options.addItem("每次使用优化默认布局", LayoutRestoreMode.SMART_DEFAULT)
        options.setCurrentIndex(max(0, options.findData(self._read_layout_mode())))
        layout.addWidget(options)
        hint = QLabel("窗口大小、图片/结果比例和 LaTeX/预览比例会在退出前保存。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        reset = QPushButton("立即重置布局", dialog)
        save = QPushButton("保存", dialog)
        save.setObjectName("primaryAction")
        buttons.addWidget(reset)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        def save_layout() -> None:
            setter = getattr(self._settings, "set_layout_restore_mode", None)
            if setter is not None:
                setter(str(options.currentData()))
            self._layout_mode = self._read_layout_mode()
            if self._layout_mode == LayoutRestoreMode.SMART_DEFAULT:
                self.reset_layout()
            else:
                self._save_layout_state()
            self.status_label.setText("界面布局设置已保存")
            dialog.accept()

        reset.clicked.connect(self.reset_layout)
        save.clicked.connect(save_layout)
        dialog.show()

    def _build_history_sidebar(self) -> QWidget:
        panel = HistoryDrawerPanel(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        header = QHBoxLayout()
        title = QLabel("识别历史")
        title.setObjectName("drawerTitle")
        header.addWidget(title)
        count = QLabel()
        count.setObjectName("drawerCount")
        self.history_count_label = count
        header.addWidget(count)
        header.addStretch(1)
        collapse = QToolButton()
        collapse.setText("×")
        collapse.setToolTip("关闭历史抽屉")
        collapse.setAccessibleName("关闭历史抽屉")
        collapse.clicked.connect(self._toggle_history_sidebar)
        header.addWidget(collapse)
        layout.addLayout(header)
        self.history_list = QListWidget(panel)
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.history_list.itemClicked.connect(self._load_history_item)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._history_context_menu)
        layout.addWidget(self.history_list, stretch=1)
        actions = QHBoxLayout()
        self.delete_history_button = QPushButton("删除所选")
        self.delete_history_button.clicked.connect(self._delete_selected_history)
        self.delete_all_history_button = QPushButton("全部删除")
        self.delete_all_history_button.clicked.connect(self._delete_all_history)
        actions.addWidget(self.delete_history_button)
        actions.addWidget(self.delete_all_history_button)
        layout.addLayout(actions)
        if self._history_store is None:
            panel.setToolTip(f"历史记录不可用：{self._history_error or '未知错误'}")
        return panel

    def _toggle_history_sidebar(self) -> None:
        if self.history_overlay.isVisible():
            self.history_overlay.hide_drawer()
        else:
            self.history_button.setChecked(True)
            self.history_overlay.show_drawer()

    @staticmethod
    def _history_label(record: HistoryRecord) -> str:
        timestamp = datetime.fromtimestamp(record.updated_at).strftime("%m-%d %H:%M")
        source = "内置 + API" if record.has_api else "内置"
        draft = record.api_draft_latex if record.active_source == "api" and record.api_draft_latex else record.local_draft_latex
        summary = " ".join(draft.split())
        if len(summary) > 42:
            summary = summary[:39] + "…"
        return f"{timestamp} · {source}\n{summary or '（空结果）'}"

    def _refresh_history_list(self, selected_id: str | None = None) -> None:
        if not hasattr(self, "history_list"):
            return
        records = self._history_store.list_records() if self._history_store is not None else []
        selected_id = selected_id or self._history_record_id
        self.history_list.blockSignals(True)
        self.history_list.clear()
        selected_item = None
        for record in records:
            item = QListWidgetItem(self._history_label(record))
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setToolTip(record.image_path)
            thumbnail = QPixmap(record.image_path)
            if not thumbnail.isNull():
                item.setIcon(QIcon(thumbnail.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            self.history_list.addItem(item)
            if record.id == selected_id:
                selected_item = item
        if selected_item is not None:
            selected_item.setSelected(True)
            self.history_list.setCurrentItem(selected_item)
        self.history_list.blockSignals(False)
        enabled = bool(self._history_store is not None and self.history_list.count())
        if hasattr(self, "history_count_label"):
            self.history_count_label.setText(str(self.history_list.count()))
        self.delete_history_button.setEnabled(enabled)
        self.delete_all_history_button.setEnabled(enabled)

    def _history_context_menu(self, position) -> None:
        item = self.history_list.itemAt(position)
        if item is None:
            return
        self.history_list.setCurrentItem(item)
        menu = QMenu(self)
        action = menu.addAction("删除此记录")
        if menu.exec(self.history_list.mapToGlobal(position)) == action:
            self._delete_history_ids([str(item.data(Qt.ItemDataRole.UserRole))])

    def _delete_selected_history(self) -> None:
        ids = [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.history_list.selectedItems()]
        self._delete_history_ids(ids)

    def _delete_all_history(self) -> None:
        if self._history_store is None or not self.history_list.count():
            return
        answer = QMessageBox.question(
            self,
            "删除全部历史",
            "确定删除全部识别历史和本地图片吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            current = self._history_record_id
            self._history_store.delete_all()
            self._refresh_history_list()
            if current:
                self._clear_current_result()

    def _delete_history_ids(self, ids: list[str]) -> None:
        if self._history_store is None or not ids:
            return
        answer = QMessageBox.question(
            self,
            "删除识别历史",
            f"确定删除选中的 {len(set(ids))} 条历史和对应图片吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        current_deleted = bool(self._history_record_id and self._history_record_id in ids)
        self._history_store.delete_many(ids)
        self._refresh_history_list()
        if current_deleted:
            item = self.history_list.item(0)
            if item is not None:
                self._load_history_item(item)
            else:
                self._clear_current_result()

    def _clear_current_result(self) -> None:
        self._flush_history_draft()
        self._history_record_id = None
        self._current_image = None
        self._current_image_bytes = None
        self._preview_source = QPixmap()
        self.preview_label.clear()
        self.local_latex_edit.clear()
        self.api_latex_edit.clear()
        self._local_original_latex = ""
        self._api_original_latex = ""
        self._api_result = None
        self.source_selector.clear()
        self.source_selector.addItem("内置", "local")
        self.source_selector.setEnabled(False)
        self._set_active_source("local")
        self.copy_word_button.setEnabled(False)
        self.copy_latex_button.setEnabled(False)
        self.status_label.setText("请选择一张公式图片")
        self._refresh_api_controls()

    def _history_png_bytes(self) -> bytes | None:
        if self._preview_source.isNull():
            return self._current_image_bytes
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not self._preview_source.toImage().save(buffer, "PNG"):
            return self._current_image_bytes
        return bytes(buffer.data())

    def _create_history_record(self, result: OCRResult, render_error: str | None) -> None:
        if self._history_store is None or not self._current_image_bytes:
            return
        try:
            record = self._history_store.create_local(
                self._history_png_bytes() or self._current_image_bytes,
                local_raw_latex=result.raw_latex,
                local_draft_latex=result.formatted_latex,
                local_render_error=render_error,
            )
        except Exception as exc:
            self._history_error = str(exc)
            self.status_label.setToolTip(f"历史记录保存失败：{exc}")
            return
        self._history_record_id = record.id
        self._refresh_history_list(record.id)

    def _schedule_history_draft_save(self) -> None:
        if not self._history_loading and self._history_record_id and self._history_store is not None:
            self._history_save_timer.start()

    def _flush_history_draft(self) -> None:
        if self._history_loading or not self._history_record_id or self._history_store is None:
            return
        try:
            source = "api" if self.latex_stack.currentIndex() else "local"
            self._history_store.update_draft(self._history_record_id, source, self.latex_edit.toPlainText())
            self._history_store.set_active_source(self._history_record_id, source)
            self._refresh_history_list(self._history_record_id)
        except Exception as exc:
            self.status_label.setToolTip(f"历史草稿保存失败：{exc}")

    def _load_history_item(self, item: QListWidgetItem) -> None:
        if self._history_store is None:
            return
        record_id = str(item.data(Qt.ItemDataRole.UserRole))
        record = self._history_store.get(record_id)
        if record is None:
            self._refresh_history_list()
            return
        try:
            image_path = Path(record.image_path)
            pixmap = QPixmap(str(image_path))
            image_bytes = image_path.read_bytes()
        except (OSError, ValueError) as exc:
            self.status_label.setText(f"历史图片无法读取：{exc}")
            return
        if pixmap.isNull():
            self.status_label.setText("历史图片无法读取")
            return
        self._flush_history_draft()
        self._history_loading = True
        self._history_record_id = record.id
        self._current_image = image_path
        self._current_image_bytes = image_bytes
        self._temporary_capture = None
        self._preview_source = pixmap
        self._update_preview()
        self._local_original_latex = record.local_draft_latex
        self.local_latex_edit.setPlainText(record.local_draft_latex)
        self._api_original_latex = record.api_draft_latex or ""
        self.api_latex_edit.setPlainText(self._api_original_latex)
        api_index = self.source_selector.findData("api")
        if record.api_draft_latex:
            if api_index < 0:
                self.source_selector.addItem(f"API · {record.api_profile_name or '配置'}", "api")
            else:
                self.source_selector.setItemText(api_index, f"API · {record.api_profile_name or '配置'}")
            self._api_result = RemoteOCRResult(
                raw_latex=record.api_raw_latex or record.api_draft_latex,
                provider_type="history",
                profile_name=record.api_profile_name or "历史 API",
                model=record.api_model or "",
                elapsed_ms=0.0,
            )
            self.source_selector.setEnabled(True)
        elif api_index >= 0:
            self.source_selector.removeItem(api_index)
            self._api_result = None
        self._set_active_source(record.active_source if record.api_draft_latex else "local")
        self._history_loading = False
        self.open_button.setEnabled(True)
        self.paste_button.setEnabled(True)
        self.capture_button.setEnabled(True)
        self.status_label.setText(f"已载入历史：{datetime.fromtimestamp(record.updated_at).strftime('%Y-%m-%d %H:%M')}")
        self._refresh_api_controls()

    def open_image(self) -> None:
        if self._api_pending:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开公式图片",
            str(Path.home()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;所有文件 (*)",
        )
        if file_path:
            self.start_ocr(Path(file_path))

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.matches(QKeySequence.StandardKey.Paste):
            focus = QApplication.focusWidget()
            if not isinstance(focus, (QPlainTextEdit, QKeySequenceEdit, HotkeySequenceEdit)):
                self._route_paste_shortcut()
                event.accept()
                return
        super().keyPressEvent(event)

    def _route_paste_shortcut(self) -> None:
        """Paste image into OCR, while preserving ordinary editor text paste."""
        focus = QApplication.focusWidget()
        if isinstance(focus, QPlainTextEdit):
            if not QApplication.clipboard().image().isNull():
                self.paste_image()
            else:
                focus.paste()
            return
        self.paste_image()

    def paste_image(self) -> None:
        if self._api_pending:
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            self.status_label.setText("剪贴板中没有图片")
            return
        fd, filename = tempfile.mkstemp(prefix="formulaocr-paste-", suffix=".png")
        os.close(fd)
        path = Path(filename)
        if not image.save(str(path), "PNG"):
            path.unlink(missing_ok=True)
            self._on_error("无法保存剪贴板图片")
            return
        self.start_ocr(path, temporary=True)

    def start_ocr(self, image_path: Path, temporary: bool = False) -> None:
        self._flush_history_draft()
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self._on_error(f"无法读取图片: {image_path}")
            return
        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            self._on_error(f"无法读取图片数据: {exc}")
            return
        self._current_image = image_path
        self._current_image_bytes = image_bytes
        self._history_record_id = None
        self._cleanup_temporary_capture()
        if temporary:
            self._temporary_capture = image_path
        self._preview_source = pixmap
        self._update_preview()
        self.latex_edit.clear()
        self.api_latex_edit.clear()
        self._local_original_latex = ""
        self._api_original_latex = ""
        self._api_result = None
        api_index = self.source_selector.findData("api")
        if api_index >= 0:
            self.source_selector.removeItem(api_index)
        self.source_selector.setEnabled(False)
        self._set_active_source("local")
        self.formula_preview.set_latex("")
        self.copy_word_button.setEnabled(False)
        self.copy_latex_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.paste_button.setEnabled(False)
        self.capture_button.setEnabled(False)
        self.api_button.setEnabled(False)
        self.status_label.setText(f"正在 OCR: {image_path.name}")
        self.recognize_requested.emit(str(image_path))

    def capture_screen(self) -> None:
        if self._api_pending or self._overlay is not None or self._capture_pending:
            return
        if not self._screen_permission.is_authorized():
            requested = self._screen_permission.request()
            if requested:
                self.status_label.setText("屏幕录制权限已更新，请再次启动截图")
            else:
                self.status_label.setText("需要 macOS 屏幕录制权限：请在系统设置中允许 FormulaOCR")
            return
        if self._use_native_capture:
            self._start_native_capture()
            return
        self._start_custom_capture()

    def _start_native_capture(self) -> None:
        self._capture_pending = True
        self._capture_window_was_visible = self.isVisible()
        if self._capture_window_was_visible:
            self.hide()
            QApplication.processEvents()
        process = QProcess(self)
        self._native_capture_process = process
        process.finished.connect(self._native_capture_finished)
        process.errorOccurred.connect(self._native_capture_error)
        process.start("/usr/sbin/screencapture", ["-i", "-s", "-c", "-x"])

    def _native_capture_error(self, _error) -> None:
        process = self._native_capture_process
        if process is not None and process.state() == QProcess.ProcessState.NotRunning:
            self._finish_native_capture(False, "macOS 截图工具启动失败")

    def _native_capture_finished(self, exit_code: int, _status) -> None:
        if exit_code != 0:
            self._finish_native_capture(False, "已取消截图")
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            self._finish_native_capture(False, "未获得截图，请重新选择区域")
            return
        fd, filename = tempfile.mkstemp(prefix="formulaocr-capture-", suffix=".png")
        os.close(fd)
        path = Path(filename)
        if not image.save(str(path), "PNG"):
            path.unlink(missing_ok=True)
            self._finish_native_capture(False, "无法保存 macOS 截图")
            return
        self._finish_native_capture(True)
        self.start_ocr(path, temporary=True)

    def _finish_native_capture(self, success: bool, message: str = "") -> None:
        process = self._native_capture_process
        self._native_capture_process = None
        if process is not None:
            process.deleteLater()
        self._capture_pending = False
        self._show_after_capture()
        if not success and message:
            self.status_label.setText(message)

    def _start_custom_capture(self) -> None:
        was_visible = self.isVisible()
        self._capture_pending = True
        self._capture_window_was_visible = was_visible
        if was_visible:
            self.hide()
            QApplication.processEvents()
        QTimer.singleShot(120, self._capture_after_hide)

    def _capture_after_hide(self) -> None:
        if not self._capture_pending:
            return
        self._capture_pending = False
        try:
            capture = self._capture_factory()
        except Exception as exc:
            self._show_after_capture()
            self.status_label.setText(f"截图失败：{exc}")
            return
        self.capture_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.paste_button.setEnabled(False)
        self.status_label.setText("拖动选择公式区域，按 Esc 取消")
        self._overlay = SelectionOverlay(capture)
        self._overlay.selected.connect(self._on_screen_selected)
        self._overlay.cancelled.connect(self._on_selection_cancelled)
        self._overlay.show()

    def _setup_settings_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("设置")
        self._populate_settings_menu(settings_menu)

    def _build_settings_menu(self, parent: QWidget) -> QMenu:
        menu = QMenu(parent)
        self._populate_settings_menu(menu)
        return menu

    def _populate_settings_menu(self, settings_menu: QMenu) -> None:
        """Keep the rail, menu-bar and tray settings entry points consistent."""

        entries = (
            ("自定义模型与 API…", lambda: self.show_settings_center("api")),
            ("修改截图快捷键…", lambda: self.show_settings_center("hotkey")),
            ("窗口行为…", lambda: self.show_settings_center("general")),
            ("界面与布局…", lambda: self.show_settings_center("layout")),
            ("历史记录…", lambda: self.show_settings_center("history")),
        )
        for label, callback in entries:
            action = QAction(label, settings_menu)
            action.triggered.connect(callback)
            settings_menu.addAction(action)

    def show_settings_center(self, page_id: str = "general") -> None:
        if self._settings_center is None:
            self._settings_center = SettingsCenter(self, page_id, self)
            center = self._settings_center
            center.closed.connect(lambda c=center: self._discard_settings_center(c))
        self._settings_center.show_page(page_id)

    def _discard_settings_center(self, center: SettingsCenter) -> None:
        if self._settings_center is center:
            self._settings_center = None
        center.deleteLater()

    def show_api_settings(self) -> None:
        if getattr(self, "_api_settings_dialog", None) is not None:
            self._api_settings_dialog.show()
            self._api_settings_dialog.raise_()
            self._api_settings_dialog.activateWindow()
            return
        dialog = APISettingsDialog(self._settings.api_profiles, self)
        dialog.settings_saved.connect(self._refresh_api_controls)
        dialog.finished.connect(lambda _result: setattr(self, "_api_settings_dialog", None))
        dialog.show()
        self._api_settings_dialog = dialog

    def _load_api_profiles(self) -> list:
        store = getattr(self._settings, "api_profiles", None)
        if store is None:
            self._api_profiles = []
            self._api_selected_profile_id = ""
            return self._api_profiles
        try:
            profiles = store.load_profiles()
        except RuntimeError:
            profiles = []
        self._api_profiles = profiles
        if not self._api_selected_profile_id or not any(
            p.id == self._api_selected_profile_id and p.enabled for p in profiles
        ):
            active_id = self._settings.api_profiles.active_profile_id
            active = next((p for p in profiles if p.id == active_id and p.enabled), None)
            active = active or next((p for p in profiles if p.enabled), None)
            self._api_selected_profile_id = active.id if active else ""
        return profiles

    def _refresh_api_controls(self) -> None:
        profiles = self._load_api_profiles()
        store = getattr(self._settings, "api_profiles", None)
        enabled = bool(store is not None and store.api_enabled and any(p.enabled for p in profiles))
        self.api_button.setVisible(enabled)
        self.api_profile_button.setVisible(enabled)
        if hasattr(self, "toolbar_status"):
            self.toolbar_status.setText("API 已启用" if enabled else "离线识别")
        active_profile = self._active_api_profile()
        self.api_button.setText("API 重识别")
        self.api_profile_button.setText((active_profile.name if active_profile else "选择配置")[:24])
        self.api_profile_button.setToolTip(active_profile.name if active_profile else "选择 API 配置")
        self.api_button.setEnabled(bool(
            self._current_image_bytes
            and self._local_original_latex
            and self._api_profile_ready(active_profile)
            and not self._api_pending
        ))

    def show_api_profile_menu(self) -> None:
        menu = QMenu(self)
        for profile in self._api_profiles:
            if not profile.enabled:
                continue
            action = QAction(profile.name or "未命名配置", menu)
            action.setCheckable(True)
            action.setChecked(profile.id == self._api_selected_profile_id)
            action.triggered.connect(lambda _checked=False, pid=profile.id: self._select_api_profile(pid))
            menu.addAction(action)
        if menu.isEmpty():
            menu.addAction(QAction("请先在设置中配置 API", menu))
        menu.exec(self.api_profile_button.mapToGlobal(self.api_profile_button.rect().bottomLeft()))

    def _select_api_profile(self, profile_id: str) -> None:
        self._api_selected_profile_id = profile_id
        store = getattr(self._settings, "api_profiles", None)
        if store is not None:
            store.set_active_profile_id(profile_id)
        profile = next((p for p in self._api_profiles if p.id == profile_id), None)
        if profile is not None:
            self.api_profile_button.setText(profile.name[:24])
        self._refresh_api_controls()

    def _active_api_profile(self):
        return next((p for p in self._api_profiles if p.id == self._api_selected_profile_id and p.enabled), None)

    @staticmethod
    def _api_profile_ready(profile) -> bool:
        if profile is None or not profile.base_url.strip():
            return False
        if profile.provider_type == "mathpix":
            return bool(profile.app_id.strip() and profile.app_key)
        return bool(profile.api_key and profile.model.strip())

    def recognize_with_api(self) -> None:
        profile = self._active_api_profile()
        if not self._api_profile_ready(profile) or not self._current_image_bytes:
            self.status_label.setText("请先在设置中配置并启用 API")
            return
        self._api_pending = True
        self.api_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.paste_button.setEnabled(False)
        self.capture_button.setEnabled(False)
        self.status_label.setText(f"正在使用 API：{profile.name}")
        self.api_recognize_requested.emit(profile, self._current_image_bytes)

    def _on_api_result(self, result: RemoteOCRResult) -> None:
        self._api_pending = False
        self._api_result = result
        self._api_original_latex = normalize_latex(result.raw_latex)
        self.api_latex_edit.setPlainText(self._api_original_latex)
        self.source_selector.setEnabled(True)
        if self.source_selector.findData("api") < 0:
            self.source_selector.addItem(f"API · {result.profile_name}", "api")
        else:
            self.source_selector.setItemText(self.source_selector.findData("api"), f"API · {result.profile_name}")
        self._set_active_source("api")
        render_error = self._latex_render_error(self._api_original_latex)
        self.copy_word_button.setEnabled(render_error is None)
        if self._history_store is not None and self._history_record_id:
            try:
                self._history_store.update_api(
                    self._history_record_id,
                    api_raw_latex=result.raw_latex,
                    api_draft_latex=self._api_original_latex,
                    api_profile_name=result.profile_name,
                    api_model=result.model,
                    api_render_error=render_error,
                )
                self._refresh_history_list(self._history_record_id)
            except Exception as exc:
                self.status_label.setToolTip(f"API 历史保存失败：{exc}")
        self.open_button.setEnabled(True)
        self.paste_button.setEnabled(True)
        self.capture_button.setEnabled(True)
        confidence = f"，confidence {result.confidence:.2f}" if result.confidence is not None else ""
        if render_error is None:
            self.status_label.setText(f"API 完成：{result.profile_name}，耗时 {result.elapsed_ms:.1f} ms{confidence}")
        else:
            self.status_label.setText(f"API 完成但无法渲染：{render_error}")
        self._refresh_api_controls()
        if render_error is None and self.auto_copy_checkbox.isChecked():
            self.copy_word()

    def _on_api_error(self, message: str) -> None:
        self._api_pending = False
        self.open_button.setEnabled(True)
        self.paste_button.setEnabled(True)
        self.capture_button.setEnabled(True)
        self.status_label.setText(f"API 识别失败，已保留内置结果：{message}")
        self._refresh_api_controls()

    def _set_active_source(self, source: str) -> None:
        index = 1 if source == "api" and self._api_result is not None else 0
        self.latex_stack.setCurrentIndex(index)
        self.source_selector.blockSignals(True)
        self.source_selector.setCurrentIndex(index)
        self.source_selector.blockSignals(False)
        self.latex_edit = self.api_latex_edit if index else self.local_latex_edit
        has_result = bool(self._local_original_latex or self._api_original_latex)
        self.undo_button.setEnabled(has_result)
        self.redo_button.setEnabled(has_result)
        self.restore_button.setEnabled(has_result)
        self._update_formula_preview()
        if not self._history_loading and self._history_record_id and self._history_store is not None:
            self._history_store.set_active_source(self._history_record_id, "api" if index else "local")

    def _on_source_changed(self, _index: int) -> None:
        self._set_active_source(str(self.source_selector.currentData()))

    def restore_original_result(self) -> None:
        original = self._api_original_latex if self.latex_stack.currentIndex() else self._local_original_latex
        if original:
            self.latex_edit.setPlainText(original)
            self.status_label.setText("已恢复当前来源的原始识别结果")

    def show_history_settings(self) -> None:
        if self._history_settings_dialog is not None:
            self._history_settings_dialog.show()
            self._history_settings_dialog.raise_()
            self._history_settings_dialog.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("历史记录")
        dialog.setModal(False)
        dialog.resize(420, 150)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("最多保留的历史记录数（20–2000）"))
        spin = QSpinBox(dialog)
        spin.setRange(20, 2000)
        spin.setValue(self._settings.history_limit)
        layout.addWidget(spin)
        save = QPushButton("保存", dialog)
        layout.addWidget(save)

        def save_history_limit() -> None:
            value = spin.value()
            count = self.history_list.count()
            if value < count:
                answer = QMessageBox.question(
                    dialog,
                    "清理较早记录",
                    f"新上限会删除最旧的 {count - value} 条记录，是否继续？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self._settings.set_history_limit(value)
            if self._history_store is not None:
                self._history_store.set_limit(value)
                self._refresh_history_list()
            self.status_label.setText(f"历史记录上限已保存：{value} 条")
            dialog.accept()

        save.clicked.connect(save_history_limit)
        self._history_settings_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_history_settings_dialog", None))
        dialog.show()

    def show_window_settings(self) -> None:
        if self._window_settings_dialog is not None:
            self._window_settings_dialog.show()
            self._window_settings_dialog.raise_()
            self._window_settings_dialog.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("窗口行为")
        dialog.setModal(False)
        dialog.resize(460, 130)
        layout = QVBoxLayout(dialog)
        option = QCheckBox("关闭主窗口后隐藏 Dock 图标（菜单栏继续运行）", dialog)
        option.setChecked(self._settings.hide_dock_on_close)

        def update_option(enabled: bool) -> None:
            self._settings.set_hide_dock_on_close(enabled)
            if not enabled:
                self._set_dock_icon_visible(True)

        option.toggled.connect(update_option)
        layout.addWidget(option)
        close_button = QPushButton("关闭", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        self._window_settings_dialog = dialog
        dialog.finished.connect(lambda _result: self._clear_window_settings_dialog())
        dialog.show()

    def _clear_window_settings_dialog(self) -> None:
        self._window_settings_dialog = None

    def _set_dock_icon_visible(self, visible: bool) -> None:
        """Switch the macOS activation policy while retaining the menu-bar icon."""
        if sys.platform != "darwin" or QApplication.platformName() == "offscreen":
            self._dock_icon_hidden = not visible
            return
        try:
            from AppKit import (
                NSApplication,
                NSApplicationActivationPolicyAccessory,
                NSApplicationActivationPolicyRegular,
            )

            policy = NSApplicationActivationPolicyRegular if visible else NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(policy)
        except Exception:
            # Non-macOS/offscreen tests have no activation-policy API.
            pass
        self._dock_icon_hidden = not visible

    def show_hotkey_settings(self) -> None:
        if self._hotkey_dialog is not None:
            self._hotkey_dialog.show()
            self._hotkey_dialog.raise_()
            self._hotkey_dialog.activateWindow()
            return
        self._hotkey.stop()
        dialog = QDialog(self)
        dialog.setWindowTitle("截图快捷键")
        dialog.setModal(False)
        dialog.resize(420, 110)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("按下新的快捷键；按 Esc 清空快捷键"))
        row = QHBoxLayout()
        current = self._saved_hotkey_binding.qt_sequence() if self._saved_hotkey_binding else QKeySequence()
        self.hotkey_edit = HotkeySequenceEdit(current, dialog)
        self.hotkey_edit.setToolTip("按 Esc 清空快捷键")
        self.hotkey_save_button = QPushButton("保存", dialog)
        self.hotkey_save_button.setEnabled(False)
        self.hotkey_edit.keySequenceChanged.connect(self._on_hotkey_edit_changed)
        self.hotkey_save_button.clicked.connect(self.save_hotkey)
        row.addWidget(self.hotkey_edit, stretch=1)
        row.addWidget(self.hotkey_save_button)
        layout.addLayout(row)
        self._hotkey_dialog = dialog
        self._update_hotkey_save_state()
        dialog.finished.connect(self._hotkey_dialog_finished)
        dialog.show()

    def _hotkey_dialog_finished(self, _result: int) -> None:
        self._hotkey.set_binding(self._saved_hotkey_binding)
        self._hotkey.start()
        self._clear_hotkey_dialog()

    def _clear_hotkey_dialog(self) -> None:
        self._hotkey_dialog = None
        self.hotkey_edit = None
        self.hotkey_save_button = None

    def _hotkey_sequence_storage(self, sequence: QKeySequence) -> str | None:
        try:
            binding = HotkeyBinding.from_qt_sequence(sequence)
        except ValueError:
            return None
        return binding.storage if binding is not None else ""

    def _on_hotkey_edit_changed(self, _sequence: QKeySequence) -> None:
        self._update_hotkey_save_state()

    def _update_hotkey_save_state(self) -> None:
        if self.hotkey_edit is None or self.hotkey_save_button is None:
            return
        current = self._hotkey_sequence_storage(self.hotkey_edit.keySequence())
        saved = self._saved_hotkey_binding.storage if self._saved_hotkey_binding else ""
        self.hotkey_save_button.setEnabled(current != saved)

    def save_hotkey(self) -> None:
        if self.hotkey_edit is None:
            return
        try:
            binding = HotkeyBinding.from_qt_sequence(self.hotkey_edit.keySequence())
        except ValueError as exc:
            if self._saved_hotkey_binding is None:
                self.hotkey_edit.setKeySequence(QKeySequence())
            else:
                self.hotkey_edit.setKeySequence(self._saved_hotkey_binding.qt_sequence())
            self.status_label.setText(f"快捷键无效：{exc}")
            return
        if not self._hotkey.set_binding(binding):
            self.status_label.setText("快捷键未能启用，请检查 macOS 输入监控权限")
            return
        self._settings.set_hotkey(binding.storage if binding is not None else "")
        self._saved_hotkey_binding = binding
        self.hotkey_edit.setKeySequence(binding.qt_sequence() if binding else QKeySequence())
        self._update_hotkey_save_state()
        self.status_label.setText(
            "截图快捷键已清空"
            if binding is None
            else f"快捷键已保存：{binding.display}"
        )

    def _on_screen_selected(self, image) -> None:
        self._overlay = None
        self.capture_button.setEnabled(True)
        self.open_button.setEnabled(True)
        fd, filename = tempfile.mkstemp(prefix="formulaocr-capture-", suffix=".png")
        os.close(fd)
        path = Path(filename)
        if not image.save(str(path), "PNG"):
            path.unlink(missing_ok=True)
            self._on_error("无法保存截图临时文件")
            self._show_after_capture()
            return
        self.start_ocr(path, temporary=True)
        self._show_after_capture()

    def _on_selection_cancelled(self) -> None:
        self._overlay = None
        self.capture_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.paste_button.setEnabled(True)
        self.status_label.setText("已取消截图")
        self._show_after_capture()

    def _show_after_capture(self) -> None:
        if getattr(self, "_capture_window_was_visible", False):
            self.showNormal()
            self.raise_()
            self.activateWindow()
        self._capture_window_was_visible = False
        self._overlay = None

    def _on_result(self, image_path: str, result: OCRResult) -> None:
        self._finalize_ocr_result(image_path, replace(
            result,
            initial_raw_latex=result.raw_latex,
            candidate_count=1,
            validation_status="single_pass",
        ))

    @staticmethod
    def _latex_render_error(latex: str) -> str | None:
        """Return a clear error without rewriting the model output."""

        if re.match(r"^\s*(?:\\boxed\s*\{\s*)?\\(?:phantom|hphantom|vphantom)\b", latex):
            return "识别结果包含不可见占位符 \\phantom，未显示公式"
        try:
            latex_to_mathml(latex)
        except (MathMLConversionError, TypeError) as exc:
            return f"公式无法渲染：{exc}"
        return None

    def _finalize_ocr_result(self, image_path: str, result: OCRResult) -> None:
        self.open_button.setEnabled(True)
        self.capture_button.setEnabled(True)
        self.paste_button.setEnabled(True)
        self._local_original_latex = result.formatted_latex
        self.local_latex_edit.setPlainText(self._local_original_latex)
        self._set_active_source("local")
        render_error = self._latex_render_error(result.formatted_latex)
        self.copy_word_button.setEnabled(render_error is None)
        self.copy_latex_button.setEnabled(True)
        if render_error is None:
            self.status_label.setText(f"完成：{Path(image_path).name}，耗时 {result.elapsed_ms:.1f} ms")
        else:
            self.status_label.setText(f"完成但无法渲染：{render_error}")
        if render_error is None and self.auto_copy_checkbox.isChecked():
            self.copy_word()
        self._create_history_record(result, render_error)
        self._refresh_api_controls()
        self._cleanup_temporary_capture()

    def _update_formula_preview(self) -> None:
        self.formula_preview.set_latex(self.latex_edit.toPlainText())

    def _on_error(self, message: str) -> None:
        self.open_button.setEnabled(True)
        self.capture_button.setEnabled(True)
        self.paste_button.setEnabled(True)
        self.status_label.setText(f"OCR 失败：{message}")
        self._api_pending = False
        self._refresh_api_controls()
        self._cleanup_temporary_capture()

    def _cleanup_temporary_capture(self) -> None:
        if self._temporary_capture is not None:
            self._temporary_capture.unlink(missing_ok=True)
            self._temporary_capture = None

    def copy_word(self) -> None:
        latex = self.latex_edit.toPlainText()
        if not latex:
            return
        try:
            self._clipboard.copy_word(latex)
        except Exception as exc:
            self.status_label.setText(f"复制 Word 失败：{exc}")
            return
        self.status_label.setText("已复制 Word 格式（含 LaTeX fallback）")

    def copy_latex(self) -> None:
        latex = self.latex_edit.toPlainText()
        if not latex:
            return
        self._clipboard.copy_latex(latex)
        self.status_label.setText("已复制 LaTeX")

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._update_preview()

    def _update_preview(self) -> None:
        if self._preview_source.isNull():
            return
        scaled = self._preview_source.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        icon_pixmap = QPixmap(24, 24)
        icon_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(icon_pixmap)
        painter.setBrush(Qt.GlobalColor.darkBlue)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawEllipse(2, 2, 20, 20)
        painter.end()
        tray = QSystemTrayIcon(QIcon(icon_pixmap), self)
        menu = QMenu(self)
        show_action = QAction("打开 FormulaOCR", self)
        capture_action = QAction("截图 OCR", self)
        quit_action = QAction("退出", self)
        show_action.triggered.connect(self._show_from_tray)
        capture_action.triggered.connect(self.capture_screen)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(show_action)
        menu.addAction(capture_action)
        settings_menu = menu.addMenu("设置")
        self._populate_settings_menu(settings_menu)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self._show_from_tray() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        return tray

    def _show_from_tray(self) -> None:
        self._set_dock_icon_visible(True)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        """Restore a hidden window when macOS activates the app from the Dock."""
        if state == Qt.ApplicationState.ApplicationActive and not self._quitting and not self.isVisible():
            QTimer.singleShot(0, self._show_from_tray)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._schedule_layout_save()
        super().resizeEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self._apply_modern_style()
        super().changeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape and self.history_overlay.isVisible():
            self.history_overlay.hide_drawer()
            event.accept()
            return
        super().keyPressEvent(event)

    def quit_application(self) -> None:
        self._quitting = True
        self._disconnect_application_state()
        QApplication.quit()

    def _disconnect_application_state(self) -> None:
        if not self._application_state_connected:
            return
        app = QApplication.instance()
        if app is not None:
            try:
                app.applicationStateChanged.disconnect(self._on_application_state_changed)
            except (RuntimeError, TypeError):
                pass
        self._application_state_connected = False

    def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._quitting = True
        self._layout_save_timer.stop()
        self._save_layout_state()
        self._history_save_timer.stop()
        self._flush_history_draft()
        self._disconnect_application_state()
        if self._native_status_item is not None:
            self._native_status_item.close()
            self._native_status_item = None
        if self._history_store is not None:
            try:
                self._history_store.close()
            except Exception:
                pass
            self._history_store = None
        self._hotkey.stop()
        if self._native_capture_process is not None:
            self._native_capture_process.terminate()
            self._native_capture_process = None
            self._capture_pending = False
        if self._overlay is not None:
            self._overlay.cancel()
            self._overlay = None
        self._cleanup_temporary_capture()
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        if self._api_thread.isRunning():
            self._api_thread.quit()
            self._api_thread.wait(3000)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.has_tray_menu and not self._quitting:
            if self._settings.hide_dock_on_close:
                self._set_dock_icon_visible(False)
            self.hide()
            event.ignore()
            return
        self.shutdown()
        super().closeEvent(event)
