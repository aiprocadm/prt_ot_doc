from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from app.api.v1.router import _template_version_in_use
from app.modules.templates.linter import lint_template, parse_docx_placeholders


def _docx_bytes(text: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        zf.writestr(
            "word/document.xml",
            (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
                "</w:document>"
            ),
        )
    return buffer.getvalue()


def test_linter_accepts_balanced_nested_if_for() -> None:
    payload = _docx_bytes("{% if employee.active %}{% for item in employee.items %}{{ item.name }}{% endfor %}{% endif %}")

    report = lint_template(payload)

    assert report["errors"] == []
    assert "item.name" in report["found_fields"]
    assert report["blocks"]["conditions"][0]["expr"] == "employee.active"
    assert report["summary"]["loop_count"] == 1
    assert report["summary"]["condition_count"] == 1


def test_linter_reports_unbalanced_and_unknown_directive() -> None:
    payload = _docx_bytes("{% if employee.active %}{{ employee.name }}{% endfor %}{% endifx %}")

    report = lint_template(payload)

    assert "Unexpected endfor" in report["errors"]
    assert any("Unknown directive" in error for error in report["errors"])


def test_parse_placeholders_tracks_dotted_fields() -> None:
    payload = _docx_bytes("{{ employee.name }} {{ employee.position.title }}")

    parsed = parse_docx_placeholders(payload)

    names = {item["name"] for item in parsed["fields"]}
    assert "employee.name" in names
    assert "employee.position.title" in names

def test_parse_placeholders_tracks_locations_in_headers() -> None:
    payload = _docx_bytes("{{ employee.name }}")

    parsed = parse_docx_placeholders(payload)

    item = next(entry for entry in parsed["fields"] if entry["name"] == "employee.name")
    assert item["locations"]
    assert item["locations"][0]["source"] == "word/document.xml"


def test_linter_reports_required_field_warning() -> None:
    payload = _docx_bytes("{{ employee.name }}")

    report = lint_template(payload, required_fields=["employee.name", "employee.position"])

    assert report["errors"] == []
    assert any("employee.position" in warning for warning in report["warnings"])



class _Tenant:
    slug = "tenant-a"
    id = "tenant-a"


class _SessionStub:
    def __init__(self, values: list[int]) -> None:
        self._values = values

    async def scalar(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._values.pop(0)


@pytest.mark.asyncio
async def test_template_version_in_use_considers_template_usage_table() -> None:
    session = _SessionStub([0, 0, 0, 1])

    result = await _template_version_in_use(
        session,  # type: ignore[arg-type]
        tenant=_Tenant(),
        template_version_id="tv-1",
    )

    assert result is True
