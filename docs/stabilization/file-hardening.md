# File Pipeline Hardening (Stabilization)

_Last updated: 2026-04-19._

This document ties file-handling controls to concrete code and tests currently in the repository.

## File surface evidence

- API layer: `backend/app/modules/files/api.py`.
- Service layer: `backend/app/modules/files/service.py`.
- Storage key/signed-url helpers: `backend/app/modules/files/storage.py`.
- AV scanner implementation: `backend/app/modules/files/av.py`.
- Async file tasks: `backend/app/modules/files/tasks.py`.

## Control matrix (current state)

| Threat / risk | Current control in code | Evidence path | Test evidence | Gap status |
|---|---|---|---|---|
| Oversized upload | `max_upload_size` check in service upload-session creation | `backend/app/modules/files/service.py` | `tests/test_files_upload.py` | Partially covered (needs explicit limit-case inventory in doc/tests) |
| Unsupported MIME type upload | allowlist check against settings before issuing upload session | `backend/app/modules/files/service.py` | `tests/test_files_upload.py` | Partially covered |
| Macro-enabled office files upload (`.docm`, `.xlsm`) | explicit filename suffix rejection | `backend/app/modules/files/service.py` | `tests/test_files_upload.py` | Covered in code; verify all blocked suffixes remain tested |
| Cross-tenant file access | tenant-row enforcement in get/reindex/download handlers + tenant-key assertions | `backend/app/modules/files/api.py`, `backend/app/modules/files/storage.py` | `tests/integration/test_cross_tenant_resource_matrix.py`, `tests/test_file_storage.py` | Partially covered |
| Path traversal/object key abuse | `assert_tenant_key` prefix and traversal checks (`../`, `..\\`) | `backend/app/modules/files/storage.py` | `tests/test_file_storage.py`, `tests/services/test_file_storage_service.py` | Partially covered |
| Unscanned files being treated as clean | finalize -> scanning state + AV scan task scheduling | `backend/app/modules/files/service.py`, `backend/app/modules/files/tasks.py` | `tests/test_files_core_next54.py` | Partially covered (failure-mode matrix incomplete) |
| Malware detection quality | scanner module returns simulated verdict by filename markers | `backend/app/modules/files/av.py` | `tests/test_files_core_next54.py` | **Gap:** scanner is simulated/stub, not external AV engine integration |

## Current-state notes

- File finalize path computes SHA-256 and emits outbox event before/around scan flow (`backend/app/modules/files/service.py`).
- Download URL issuance is tenant-scoped in API/service paths (`backend/app/modules/files/api.py`, `backend/app/modules/files/service.py`).
- Key format migration support exists for `tenant/` and `tenants/` prefixes (`backend/app/modules/files/storage.py`).

## Explicit current gaps

1. AV scanner implementation is synthetic and filename-based (`backend/app/modules/files/av.py`), so production-grade malware detection evidence is absent.
2. No consolidated negative-test checklist for all file controls in one place.
3. No dedicated CI gate that isolates file-hardening scenarios as mandatory subset.

## Acceptance criteria for this workstream

- Every hardening control above is linked to at least one automated test.
- Residual risks (including simulated AV behavior) are explicitly accepted or remediated with tracked tasks.
- File hardening checks are part of release evidence package, not ad-hoc run output.
