"""Deprecated compat-shim — canonical location is :mod:`app.modules.packs.definitions` (ARCH-1)."""

from __future__ import annotations

from app.modules.packs.definitions import (  # noqa: F401  (compat re-export)
    DEFAULT_PACKS,
    DOCX_MIME,
    PACK_CODE_CEO_SHIELD,
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_NEW_COMPANY,
    PACK_CODE_OPO,
    PACK_CODE_SITE_ACCESS,
    PACK_CODE_WASTE,
    PACK_DEFINITIONS_BY_CODE,
    PackDefinition,
    PackScenario,
    PackTemplateSpec,
)

__all__ = [
    "PackTemplateSpec",
    "PackDefinition",
    "PackScenario",
    "DEFAULT_PACKS",
    "PACK_DEFINITIONS_BY_CODE",
    "DOCX_MIME",
    "PACK_CODE_SITE_ACCESS",
    "PACK_CODE_NEW_COMPANY",
    "PACK_CODE_INCIDENT",
    "PACK_CODE_INSPECTION_PREP",
    "PACK_CODE_OPO",
    "PACK_CODE_WASTE",
    "PACK_CODE_CEO_SHIELD",
]
