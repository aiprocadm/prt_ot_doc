"""Unit: committees срез-4 — чистый сборщик печатной формы протокола (DOCX)."""

from __future__ import annotations

from io import BytesIO

from docx import Document

from app.domains.committees.print_form import (
    CommitteeProtocolPrintData,
    DecisionBlock,
    build_protocol_docx,
    kind_label,
    quorum_label,
)


def _data(**over) -> CommitteeProtocolPrintData:
    base = dict(
        committee_name="Комитет ОТ завода",
        kind_label="Комитет по охране труда",
        protocol_no="3/2026",
        held_at="2026-08-03 10:00",
        location="Зал совещаний",
        quorum_text="Кворум: есть (3 из 4, порог 66%)",
        attendance=[("Иванов И.И.", True), ("Петров П.П.", False)],
        invited=["Сидоров С.С."],
        agenda=["О состоянии травматизма"],
        decisions=[
            DecisionBlock(
                seq=1,
                agenda_title="О состоянии травматизма",
                text="Усилить контроль на участке №2",
                votes_for=3,
                votes_against=0,
                votes_abstain=1,
                outcome_label="Принято",
                tasks=[("Иванов И.И.", "2026-09-01", "Открыта")],
            )
        ],
    )
    base.update(over)
    return CommitteeProtocolPrintData(**base)


def _all_text(docx_bytes: bytes) -> str:
    doc = Document(BytesIO(docx_bytes))
    parts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


def test_docx_contains_header_and_sections():
    text = _all_text(build_protocol_docx(_data()))
    assert "ПРОТОКОЛ № 3/2026" in text
    assert "Комитет ОТ завода" in text
    assert "Комитет по охране труда" in text
    assert "Зал совещаний" in text
    assert "Кворум: есть (3 из 4, порог 66%)" in text


def test_docx_lists_attendance_and_invited():
    text = _all_text(build_protocol_docx(_data()))
    assert "Иванов И.И." in text
    assert "Петров П.П." in text
    assert "Сидоров С.С." in text


def test_docx_decision_with_votes_and_tasks():
    text = _all_text(build_protocol_docx(_data()))
    assert "Усилить контроль на участке №2" in text
    assert "За: 3" in text and "Против: 0" in text and "Воздержались: 1" in text
    assert "Принято" in text
    assert "2026-09-01" in text


def test_docx_empty_sections_render_dash():
    text = _all_text(
        build_protocol_docx(
            _data(attendance=[], invited=[], agenda=[], decisions=[], location=None)
        )
    )
    assert "ПРОТОКОЛ № 3/2026" in text
    assert "—" in text


def test_kind_label_vocab():
    assert kind_label("osms") == "Комитет по охране труда"
    assert kind_label("unknown-code") == "unknown-code"


def test_quorum_label_variants():
    assert quorum_label(True, 3, 4, None) == "Кворум: есть (3 из 4, простое большинство)"
    assert quorum_label(True, 3, 4, 66) == "Кворум: есть (3 из 4, порог 66%)"
    assert quorum_label(None, None, None, None) == "Кворум: —"
