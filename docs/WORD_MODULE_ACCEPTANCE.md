# Word Module Acceptance Matrix

## Scope by phase

### MVP
- Unified quality/error contract (`stage`, `severity`, `code`, `details`).
- Replace engine parity for dry-run/apply with regex and whole-word behavior.
- Quality gate API and pipeline step to block release on critical issues.
- Mapping validation API for required/unmapped field checks.

### Phase 2
- Explicit workflow stages in pipeline vocabulary: `send_for_approval`, `sign`, `send_edo`, `archive`.
- Document list filters extended for metadata search (`template_id`, date range, creator).
- Version compare endpoint remains available as base for richer diffing.

### Phase 3
- Replace execution metrics (`duration_ms`, `rules_count`) in report payload.
- Pipeline step model prepared for quality/workflow stage visibility.

## Test strategy

### Unit
- `tests/test_document_quality_service.py`
  - release blocked on missing required fields
  - warnings-only flow does not block release
- `tests/test_replace_engine_advanced.py`
  - regex replacement
  - whole-word replacement

### Integration (next increment)
- Pipeline run with `quality_gate` in steps.
- Negative scenario where `quality_gate` raises release block.
- End-to-end wizard flow: source -> mapping validate -> run -> quality summary.

### Security and tenancy
- Keep tenant guard assertions on document, job and step entities.
- Keep ABAC/RBAC checks on generation/read/download/status endpoints.

## Release acceptance checklist

1. `quality:check` returns machine-readable issues with severity and stage.
2. `mapping:validate` reports required-field gaps before generation.
3. Replace API applies regex/whole-word/scope options consistently.
4. Pipeline vocabulary includes quality/workflow stages for lifecycle traceability.
5. Document listing supports metadata/date/creator filters for operational search.
