from app.core.config import Settings


def test_letterhead_flag_defaults_off():
    settings = Settings()
    assert settings.doc_pipeline_letterhead_auto is False
