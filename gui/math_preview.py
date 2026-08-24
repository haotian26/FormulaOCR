"""Offline LaTeX-to-formula preview widget."""

from __future__ import annotations

from html import escape
import re

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from converter import MathMLConversionError, latex_to_mathml


class FormulaPreview(QWidget):
    """Render MathML locally in Qt WebEngine, with a lightweight fallback."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._web_view = None
        self._pending_latex = ""
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(100)
        self._render_timer.timeout.connect(self._render_pending)
        self._fallback = QLabel("等待 LaTeX 结果")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setWordWrap(True)
        self._fallback.setStyleSheet("border: 1px solid #b8b8b8; background: #fafafa;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtWebEngineWidgets import QWebEngineView

            if QApplication.instance() is not None and QApplication.platformName() != "offscreen":
                self._web_view = QWebEngineView(self)
                self._web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
                layout.addWidget(self._web_view)
            else:
                layout.addWidget(self._fallback)
        except ImportError:
            layout.addWidget(self._fallback)

    def set_latex(self, latex: str) -> None:
        self._pending_latex = latex
        self._render_timer.start()

    def _render_pending(self) -> None:
        latex = self._pending_latex
        if not latex.strip():
            if self._web_view is not None:
                self._web_view.setHtml("<html><body></body></html>")
            self._fallback.setText("等待 LaTeX 结果")
            self._fallback.setToolTip("")
            return
        try:
            mathml_fragments = self._to_mathml_fragments(latex)
        except (MathMLConversionError, TypeError) as exc:
            self._set_error(latex, exc)
            return
        body = "".join(
            f'<div class="formula-line">{fragment}</div>'
            for fragment in mathml_fragments
        )
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: 100%; height: 100%; }}
body {{ background: #fafafa; font-family: 'Cambria Math', 'STIX Two Math', serif; }}
.formula-stack {{ box-sizing: border-box; width: 100%; min-height: 100%;
                  padding: 14px 10px; display: flex; flex-direction: column;
                  justify-content: center; gap: 0.55em; overflow: auto; }}
.formula-line {{ box-sizing: border-box; width: 100%; overflow-x: auto;
                 overflow-y: hidden; text-align: center; flex: 0 0 auto; }}
.formula-line math {{ display: block; width: max-content; min-width: 100%;
                      margin: 0 auto; font-size: clamp(14px, 2.4vw, 26px); }}
mspace[linebreak="newline"] {{ display: block; height: 0.45em; }}
</style></head><body><div class="formula-stack">{body}</div></body></html>"""
        if self._web_view is not None:
            self._web_view.setHtml(html)
        self._fallback.setText(latex)
        self._fallback.setToolTip("")

    def _to_mathml_fragments(self, latex: str) -> list[str]:
        """Render aligned OCR output row-by-row so each row can fit the pane."""
        match = re.fullmatch(
            r"\s*\\begin\{(aligned|alignedat\*?|gathered)\}(.*?)"
            r"\\end\{\1\}\s*",
            latex,
            flags=re.DOTALL,
        )
        if not match:
            return [latex_to_mathml(latex)]
        rows = re.split(r"\\\\(?:\s*\[[^]]*\])?", match.group(2))
        fragments = []
        for row in rows:
            cleaned = row.replace("&", "").strip()
            if cleaned:
                fragments.append(latex_to_mathml(cleaned))
        return fragments or [latex_to_mathml(latex)]

    def _set_error(self, latex: str, exc: Exception) -> None:
        if re.match(r"^\s*(?:\\boxed\s*\{\s*)?\\(?:phantom|hphantom|vphantom)\b", latex):
            message = "识别结果包含不可见占位符 \\phantom，未显示公式；可编辑 LaTeX 文本后重新预览"
        elif self._looks_incomplete(latex):
            message = "公式尚未输入完整，补全括号或环境后将自动预览"
        else:
            message = "当前 LaTeX 含有预览暂不支持的命令；LaTeX 文本和 Word 复制仍可用"
        self._fallback.setText(message)
        self._fallback.setToolTip(str(exc))
        if self._web_view is not None:
            self._web_view.setHtml(
                "<html><body style='margin:0;padding:16px;font-family:sans-serif;"
                f"color:#666'>{escape(message)}</body></html>"
            )

    @staticmethod
    def _looks_incomplete(latex: str) -> bool:
        if latex.count("{") != latex.count("}"):
            return True
        begins = len(re.findall(r"\\begin\{[^}]+\}", latex))
        ends = len(re.findall(r"\\end\{[^}]+\}", latex))
        left_delimiters = len(re.findall(r"\\left\b", latex))
        right_delimiters = len(re.findall(r"\\right\b", latex))
        return (
            begins != ends
            or left_delimiters != right_delimiters
            or latex.endswith("\\")
        )
