from app.modules.headers.placeholders import render_placeholders


def test_render_placeholders_dotted_path_and_unresolved() -> None:
    text, unresolved = render_placeholders(
        "{{company.name}} / {{doc.title}} / {{missing.value}}",
        {"company": {"name": "ACME"}, "doc": {"title": "Spec"}},
        strict=True,
    )
    assert "ACME" in text
    assert "Spec" in text
    assert "{{missing.value}}" in text
    assert unresolved == ["missing.value"]
