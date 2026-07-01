"""FileService package (ARCH-4 slice 10 — god-class decomposed via mixins).

Import surface unchanged: ``from app.modules.files.service import FileService, …`` and the
mock-patch target ``app.modules.files.service.s3.*`` resolve as before.
"""

# Module-level names re-exported so mock-patch targets ``app.modules.files.service.<name>``
# (s3.*, av.scan_file, OutboxService.*, av_scan_file_job.delay) resolve as before the split.
from app.domains.files import s3  # noqa: F401
from app.modules.files import av  # noqa: F401
from app.modules.files.service._base import (  # noqa: F401  re-export public helpers + s3
    MAX_INDEX_BYTES,
    MAX_INDEX_CHARS,
    _mask_pii,
    _normalize_name_part,
    _reject_dangerous_double_extension,
    _safe_filename,
    _sha256_bytes,
    build_artifact_name,
    compute_sha256_stream,
    resolve_presign_ttl,
)
from app.modules.files.service._functions import (  # noqa: F401  re-export module functions
    _upsert_file_search_document,
    complete_upload,
    create_upload_session,
    index_file_content,
    index_file_record,
    index_file_version,
    issue_download_url,
)
from app.modules.files.service.service import FileService  # noqa: F401
from app.services.outbox import OutboxService  # noqa: F401
from app.tasks import av_scan_file_job  # noqa: F401

__all__ = ["FileService"]
