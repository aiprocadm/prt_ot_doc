"""FileService — assembled from mixins (ARCH-4 slice 10 god-class decomposition)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.service._access import AccessMixin
from app.modules.files.service._fileops import FileOpsMixin
from app.modules.files.service._uploads import UploadMixin


class FileService(AccessMixin, UploadMixin, FileOpsMixin):
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id
