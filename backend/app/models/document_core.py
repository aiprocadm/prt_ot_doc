"""Progressive compatibility layer for document-core ORM entities.

This module allows new code to stop importing document and template related
models from the mega ``app.models.models`` module while keeping the actual table
ownership unchanged for compatibility with Alembic and legacy imports.
"""

from app.models.document import Document, DocumentSnapshot, DocumentStatus, DocumentVersion
from app.models.models import (
    DocumentPack,
    DocumentPackItem,
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateStatus,
    TemplateUsage,
    TemplateVersion,
    TemplateVersionStatus,
)

__all__ = [
    "Document",
    "DocumentPack",
    "DocumentPackItem",
    "DocumentSnapshot",
    "DocumentStatus",
    "DocumentVersion",
    "PipelineRun",
    "PipelineRunStatus",
    "Template",
    "TemplateStatus",
    "TemplateUsage",
    "TemplateVersion",
    "TemplateVersionStatus",
]
