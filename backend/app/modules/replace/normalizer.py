from __future__ import annotations

from docx.text.paragraph import Paragraph


def normalize_paragraph_runs(paragraph: Paragraph) -> None:
    if len(paragraph.runs) < 2:
        return
    head = paragraph.runs[0]
    combined = "".join(run.text for run in paragraph.runs)
    head.text = combined
    for run in list(paragraph.runs)[1:]:
        paragraph._element.remove(run._element)
