from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.texture_sets import TextureSet, TextureValidationIssue, detect_role
from app.utils import scale_px


class TextureSetValidationDialog(QDialog):
    def __init__(
        self,
        texture_set: TextureSet,
        issues: list[TextureValidationIssue],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Texture Set Validation")
        self.resize(scale_px(720, self), scale_px(560, self))

        title = QLabel(f"{texture_set.title}    {len(texture_set.items)} file(s)")
        title.setStyleSheet("QLabel { color: #f2f5f8; font-weight: 600; }")

        report = QTextEdit()
        report.setReadOnly(True)
        report.setLineWrapMode(QTextEdit.NoWrap)
        report.setPlainText(self._report_text(texture_set, issues))

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(report, 1)
        layout.addWidget(close_button, 0, Qt.AlignRight)

    def _report_text(self, texture_set: TextureSet, issues: list[TextureValidationIssue]) -> str:
        lines = ["Validation", ""]
        for issue in issues:
            lines.append(f"[{issue.severity}] {issue.message}")

        lines.extend(["", "Files", ""])
        for item in texture_set.items:
            role = detect_role(item) or "unknown"
            dimensions = item.metadata.get("dimensions", "")
            detail = f" ({dimensions})" if dimensions else ""
            lines.append(f"{role:10}  {item.display_name}{detail}")

        return "\n".join(lines)
