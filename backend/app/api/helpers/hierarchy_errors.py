"""Перевод нарушений иерархии арендаторов в ответ HTTP (BIZ-52, разд. 52.1).

Правила иерархии живут в домене и про HTTP не знают. Отображение «нарушение →
код ответа» нужно двум дверям сразу (`routes/tenants.py` и
`routes/platform_tenants.py`), поэтому лежит здесь: два отображения однажды
разошлись бы, и одна и та же причина отказа получила бы разные коды в
зависимости от ручки.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.errors import api_problem_detail
from app.domains.reseller import HierarchyViolation

#: Нарушения, которые описывают ЗАПРОС, а не право. Отдельный список, потому что
#: 403 на «в теле указан несуществующий id» сбивал бы с толку: дело не в правах.
_BAD_REQUEST_CODES = frozenset({"TENANT_PARENT_NOT_FOUND"})


def hierarchy_http_error(exc: HierarchyViolation, *, error_type: str) -> HTTPException:
    status_code = (
        status.HTTP_400_BAD_REQUEST
        if exc.code in _BAD_REQUEST_CODES
        else status.HTTP_403_FORBIDDEN
    )
    return HTTPException(
        status_code=status_code,
        detail=api_problem_detail(code=exc.code, message=exc.message, error_type=error_type),
    )
