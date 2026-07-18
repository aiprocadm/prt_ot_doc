from __future__ import annotations

from app.modules.search.service import SearchService


def test_build_entity_url_supports_jobs_and_templates() -> None:
    assert SearchService._build_entity_url("jobs", "job-1") == "/jobs/job-1"
    assert SearchService._build_entity_url("templates", "tpl-1") == "/templates/tpl-1"
