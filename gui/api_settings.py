"""Settings dialog for optional remote formula OCR providers."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from api.config import APIProviderProfile, APIProfileStore
from api.providers import DEFAULT_PROMPT

from .api_worker import ModelListWorker


class APISettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, store: APIProfileStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("自定义模型与 API")
        self.resize(720, 510)
        self._profiles = deepcopy(self._load_profiles())
        self._selected_id = ""
        self._dirty = False
        self._saved_snapshot = None
        self._model_request_id = 0
        self._model_request_profile_id = ""
        self._model_request_mode = "fetch"
        self._model_thread: QThread | None = None
        self._model_worker: ModelListWorker | None = None
        self._model_thread_request_id = 0
        self._pending_close = False

        self.enabled = QCheckBox("启用 API 重识别（只有点击 API 按钮时上传图片）", self)
        self.enabled.setChecked(store.api_enabled)
        self.profile_list = QListWidget(self)
        self.profile_list.currentRowChanged.connect(self._select_row)

        self.type_edit = QComboBox(self)
        self.type_edit.addItem("OpenAI-compatible", "openai_compatible")
        self.type_edit.addItem("Mathpix", "mathpix")
        self.name_edit = QLineEdit(self)
        self.base_url_edit = QLineEdit(self)
        self.model_edit = QComboBox(self)
        self.model_edit.setEditable(True)
        self.model_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_edit.setDuplicatesEnabled(False)
        self.model_fetch_button = QPushButton("获取模型", self)
        self.model_fetch_button.clicked.connect(self._fetch_models)
        self.model_status_label = QLabel("", self)
        self.model_status_label.setWordWrap(True)
        model_row = QVBoxLayout()
        model_controls = QHBoxLayout()
        model_controls.setContentsMargins(0, 0, 0, 0)
        model_controls.addWidget(self.model_edit, stretch=1)
        model_controls.addWidget(self.model_fetch_button)
        model_row.addLayout(model_controls)
        model_row.addWidget(self.model_status_label)
        self.model_field = QWidget(self)
        self.model_field.setLayout(model_row)
        self.model_label = QLabel("模型 ID", self)
        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_id_edit = QLineEdit(self)
        self.app_key_edit = QLineEdit(self)
        self.app_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.timeout_edit = QSpinBox(self)
        self.timeout_edit.setRange(5, 120)
        self.timeout_edit.setSuffix(" 秒")
        self.timeout_edit.setValue(45)
        self.prompt_edit = QPlainTextEdit(self)
        self.prompt_edit.setPlaceholderText(DEFAULT_PROMPT)
        self.prompt_edit.setMaximumHeight(90)
        self.profile_enabled = QCheckBox("启用此配置", self)
        self.reset_prompt_button = QPushButton("恢复内置提示词", self)
        self.reset_prompt_button.clicked.connect(lambda: self.prompt_edit.setPlainText(""))
        self.active_edit = QComboBox(self)
        self.active_edit.currentIndexChanged.connect(self._active_changed)

        form = QFormLayout()
        form.addRow("类型", self.type_edit)
        form.addRow("名称", self.name_edit)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow(self.model_label, self.model_field)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("Mathpix App ID", self.app_id_edit)
        form.addRow("Mathpix App Key", self.app_key_edit)
        form.addRow("超时", self.timeout_edit)
        form.addRow("高级提示词", self.prompt_edit)
        form.addRow("配置状态", self.profile_enabled)
        form.addRow("提示词", self.reset_prompt_button)
        form.addRow("当前使用", self.active_edit)

        add_button = QPushButton("新增", self)
        remove_button = QPushButton("删除", self)
        self.test_button = QPushButton("测试配置", self)
        add_button.clicked.connect(self._add_profile)
        remove_button.clicked.connect(self._remove_profile)
        self.test_button.clicked.connect(self._test_profile)
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(add_button)
        list_buttons.addWidget(remove_button)
        list_buttons.addWidget(self.test_button)

        self.save_button = QPushButton("保存", self)
        self.cancel_button = QPushButton("取消", self)
        self.save_feedback = QLabel("", self)
        self.save_feedback.setObjectName("settingsSaveFeedback")
        self.save_feedback.hide()
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._hide_saved_feedback)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_feedback)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)

        left = QVBoxLayout()
        left.addWidget(QLabel("已保存配置"))
        left.addWidget(self.profile_list, stretch=1)
        left.addLayout(list_buttons)
        right = QVBoxLayout()
        right.addWidget(self.enabled)
        right.addLayout(form)
        right.addStretch(1)
        content = QHBoxLayout()
        content.addLayout(left, stretch=1)
        content.addLayout(right, stretch=2)
        layout = QVBoxLayout(self)
        layout.addLayout(content, stretch=1)
        layout.addLayout(buttons)

        self.enabled.toggled.connect(self._mark_dirty)
        for widget in (
            self.name_edit, self.base_url_edit, self.api_key_edit,
            self.app_id_edit, self.app_key_edit,
        ):
            widget.textChanged.connect(self._mark_dirty)
        self.model_edit.currentTextChanged.connect(self._mark_dirty)
        self.prompt_edit.textChanged.connect(self._mark_dirty)
        self.timeout_edit.valueChanged.connect(self._mark_dirty)
        self.profile_enabled.toggled.connect(self._mark_dirty)
        self.type_edit.currentIndexChanged.connect(self._on_type_changed)
        self._refresh_list()
        if self._profiles:
            self.profile_list.setCurrentRow(0)
        else:
            self._set_editor_enabled(False)
        # Initial population is not a user edit; keep the page clean until a
        # field, profile or API switch is changed explicitly.
        self._saved_snapshot = self._snapshot()
        self._set_dirty(False)

    def _load_profiles(self) -> list[APIProviderProfile]:
        try:
            return self.store.load_profiles()
        except RuntimeError:
            self._keychain_error = True
            return []

    def _refresh_list(self) -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in self._profiles:
            suffix = "（停用）" if not profile.enabled else ""
            self.profile_list.addItem(f"{profile.name or '未命名'} · {profile.provider_type}{suffix}")
        self.profile_list.blockSignals(False)
        self.active_edit.blockSignals(True)
        self.active_edit.clear()
        for profile in self._profiles:
            self.active_edit.addItem(profile.name or "未命名", profile.id)
        self.active_edit.blockSignals(False)
        active = self.store.active_profile_id
        index = max(0, self.active_edit.findData(active)) if self._profiles else -1
        if index >= 0:
            self.active_edit.setCurrentIndex(index)

    def _select_row(self, row: int) -> None:
        self._model_request_id += 1
        if self._selected_id:
            self._save_editor()
        if row < 0 or row >= len(self._profiles):
            self._selected_id = ""
            self._set_editor_enabled(False)
            return
        self._selected_id = self._profiles[row].id
        profile = self._profiles[row]
        self._set_editor_enabled(True)
        for widget in (self.type_edit, self.name_edit, self.base_url_edit, self.model_edit, self.api_key_edit, self.app_id_edit, self.app_key_edit, self.timeout_edit, self.prompt_edit):
            widget.blockSignals(True)
        self.type_edit.setCurrentIndex(self.type_edit.findData(profile.provider_type))
        self.name_edit.setText(profile.name)
        self.base_url_edit.setText(profile.base_url)
        self.model_edit.clear()
        if profile.model:
            self.model_edit.addItem(profile.model)
        self.model_edit.setCurrentText(profile.model)
        self.api_key_edit.setText(profile.api_key)
        self.app_id_edit.setText(profile.app_id)
        self.app_key_edit.setText(profile.app_key)
        self.timeout_edit.setValue(profile.timeout_s)
        self.prompt_edit.setPlainText(profile.prompt_override)
        self.profile_enabled.setChecked(profile.enabled)
        for widget in (self.type_edit, self.name_edit, self.base_url_edit, self.model_edit, self.api_key_edit, self.app_id_edit, self.app_key_edit, self.timeout_edit, self.prompt_edit, self.profile_enabled):
            widget.blockSignals(False)
        self.model_status_label.setText("")
        self._update_field_visibility()

    def _set_editor_enabled(self, enabled: bool) -> None:
        self._editor_enabled = enabled
        for widget in (self.type_edit, self.name_edit, self.base_url_edit, self.model_edit, self.model_fetch_button, self.api_key_edit, self.app_id_edit, self.app_key_edit, self.timeout_edit, self.prompt_edit, self.profile_enabled):
            widget.setEnabled(enabled)
        self._update_field_visibility()

    def _update_field_visibility(self) -> None:
        mathpix = self.type_edit.currentData() == "mathpix"
        enabled = getattr(self, "_editor_enabled", True)
        self.model_edit.setEnabled(enabled and not mathpix)
        self.model_fetch_button.setVisible(not mathpix)
        self.model_label.setVisible(not mathpix)
        self.model_field.setVisible(not mathpix)
        self.model_fetch_button.setEnabled(enabled and not mathpix and self._model_thread is None)
        self.api_key_edit.setEnabled(enabled and not mathpix)
        self.app_id_edit.setVisible(mathpix)
        self.app_key_edit.setVisible(mathpix)
        self.prompt_edit.setEnabled(enabled and not mathpix)

    def _current(self) -> APIProviderProfile | None:
        return next((p for p in self._profiles if p.id == self._selected_id), None)

    def _save_editor(self) -> None:
        profile = self._current()
        if profile is None:
            return
        profile.provider_type = str(self.type_edit.currentData())
        profile.name = self.name_edit.text().strip() or "自定义模型"
        profile.base_url = self.base_url_edit.text().strip()
        profile.model = self.model_edit.currentText().strip()
        profile.api_key = self.api_key_edit.text()
        profile.app_id = self.app_id_edit.text().strip()
        profile.app_key = self.app_key_edit.text()
        profile.timeout_s = self.timeout_edit.value()
        profile.prompt_override = self.prompt_edit.toPlainText().strip()
        profile.enabled = self.profile_enabled.isChecked()

    def _add_profile(self) -> None:
        self._save_editor()
        profile = APIProviderProfile()
        self._profiles.append(profile)
        self._refresh_list()
        self.profile_list.setCurrentRow(len(self._profiles) - 1)
        self._mark_dirty()

    def _remove_profile(self) -> None:
        self._save_editor()
        profile = self._current()
        if profile is None:
            return
        self._profiles.remove(profile)
        self._refresh_list()
        if self._profiles:
            self.profile_list.setCurrentRow(0)
        else:
            self._set_editor_enabled(False)
        self._mark_dirty()

    def _active_changed(self, _index: int) -> None:
        self._mark_dirty()

    def _on_type_changed(self, _index: int) -> None:
        if self.type_edit.currentData() == "mathpix" and self.base_url_edit.text().strip() in {"", "https://api.openai.com/v1"}:
            self.base_url_edit.setText("https://api.mathpix.com")
        elif self.type_edit.currentData() == "openai_compatible" and self.base_url_edit.text().strip() == "https://api.mathpix.com":
            self.base_url_edit.setText("https://api.openai.com/v1")
        self._update_field_visibility()
        self._mark_dirty()

    def _mark_dirty(self, *_args) -> None:
        self._save_editor()
        self._set_dirty(self._snapshot() != self._saved_snapshot)

    def _snapshot(self):
        self._save_editor()
        profiles = []
        for profile in self._profiles:
            profiles.append(
                (
                    profile.id,
                    profile.provider_type,
                    profile.name,
                    profile.base_url,
                    profile.model,
                    profile.timeout_s,
                    profile.prompt_override,
                    profile.enabled,
                    profile.api_key,
                    profile.app_id,
                    profile.app_key,
                )
            )
        return (self.enabled.isChecked(), str(self.active_edit.currentData() or ""), tuple(profiles))

    def _set_dirty(self, dirty: bool) -> None:
        changed = dirty != self._dirty
        self._dirty = dirty
        self.save_button.setEnabled(dirty)
        if dirty:
            self._hide_saved_feedback()
        if not changed and not dirty:
            return

    def _hide_saved_feedback(self) -> None:
        self._feedback_timer.stop()
        self.save_feedback.clear()
        self.save_feedback.hide()

    def _show_saved_feedback(self) -> None:
        self.save_feedback.setText("✓ 已保存")
        self.save_feedback.show()
        self._feedback_timer.start(1500)

    def _fetch_models(self) -> None:
        self._start_model_fetch("fetch")

    def _start_model_fetch(self, mode: str) -> None:
        self._save_editor()
        profile = self._current()
        if profile is None:
            return
        if profile.provider_type == "mathpix":
            QMessageBox.information(self, "测试配置", "Mathpix 配置将在下一次 API 重识别时验证。")
            return
        if self._model_thread is not None and self._model_thread.isRunning():
            return
        self._model_request_id += 1
        request_id = self._model_request_id
        self._model_request_profile_id = profile.id
        self._model_request_mode = mode
        request_profile = deepcopy(profile)

        self.model_fetch_button.setText("获取中…")
        self.model_fetch_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.model_status_label.setText("正在获取模型列表…")

        thread = QThread(self)
        worker = ModelListWorker()
        worker.moveToThread(thread)
        worker.models_ready.connect(self._on_models_ready)
        worker.error.connect(self._on_models_error)
        worker.models_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda rid=request_id: self._on_model_thread_finished(rid))
        self._model_thread = thread
        self._model_worker = worker
        self._model_thread_request_id = request_id
        thread.start()
        worker.request.emit(request_id, request_profile)

    def _on_models_ready(self, request_id: int, models: list[str]) -> None:
        is_current = (
            request_id == self._model_request_id
            and self._current() is not None
            and self._current().id == self._model_request_profile_id
        )
        if is_current:
            unique_models: list[str] = []
            seen: set[str] = set()
            for model in models:
                value = str(model).strip()
                if value and value not in seen:
                    seen.add(value)
                    unique_models.append(value)
            current_text = self.model_edit.currentText()
            self.model_edit.blockSignals(True)
            self.model_edit.clear()
            self.model_edit.addItems(unique_models)
            if current_text:
                self.model_edit.setCurrentText(current_text)
            else:
                self.model_edit.setCurrentIndex(-1)
                self.model_edit.setEditText("")
            self.model_edit.blockSignals(False)
            if unique_models:
                self.model_status_label.setText(f"已获取 {len(unique_models)} 个模型，请从下拉菜单选择。")
            else:
                self.model_status_label.setText("端点未返回模型列表，可继续手动填写模型 ID。")
            if self._model_request_mode == "test":
                available = ", ".join(unique_models[:8]) or "端点未提供模型列表"
                QMessageBox.information(self, "测试成功", f"连接成功，可用模型：{available}")

    def _on_models_error(self, request_id: int, message: str) -> None:
        is_current = request_id == self._model_request_id and self._current() is not None and self._current().id == self._model_request_profile_id
        if not is_current:
            return
        self.model_status_label.setText(f"获取模型失败：{message}；当前模型未改变，可手动填写。")
        if self._model_request_mode == "test":
            QMessageBox.warning(self, "测试失败", message)

    def _on_model_thread_finished(self, request_id: int) -> None:
        if request_id != self._model_thread_request_id:
            return
        self._model_thread = None
        self._model_worker = None
        self.model_fetch_button.setText("获取模型")
        self.test_button.setEnabled(True)
        self._update_field_visibility()
        if self._pending_close:
            self._pending_close = False
            QTimer.singleShot(0, self.reject)

    def _test_profile(self) -> None:
        self._start_model_fetch("test")

    def _save(self) -> None:
        self._save_editor()
        try:
            self.store.set_api_enabled(self.enabled.isChecked())
            self.store.save_profiles(self._profiles)
            if self.active_edit.currentData():
                self.store.set_active_profile_id(str(self.active_edit.currentData()))
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._saved_snapshot = self._snapshot()
        self._set_dirty(False)
        self._show_saved_feedback()
        self.settings_saved.emit()

    def accept(self) -> None:
        if self._dirty:
            self._save()
            if self.save_button.isEnabled():
                return
        super().accept()

    def reject(self) -> None:
        if self._model_thread is not None and self._model_thread.isRunning():
            self._pending_close = True
            self._model_request_id += 1
            self.hide()
            self._model_thread.quit()
            return
        super().reject()
