"""OPS-73 (разд. 73.2): реестр устаревающих путей API.

ТЗ: «Нельзя просто выключить старую версию — на ней живут интеграции клиентов
и reseller'ов». Устаревание — управляемый процесс из пяти этапов (анонс,
параллельная работа, предупреждения, мониторинг, отключение), и первым четырём
нужен ОДИН источник правды: что устарело, когда выключим, чем заменить.

Реестр — данные, а не код: объявить эндпоинт устаревшим значит добавить запись,
а middleware, метрики и контрактный тест читают её сами. Тот же приём, что в
реестре целей импорта (OPS-71) и реестре RLS (SEC-65): списку, который стерегут
несколько потребителей, нельзя позволить жить в нескольких местах.

Первая запись — НЕ выдуманная: legacy-роутер файлов ``/api/v1/files-legacy``
уже давно живёт «до миграции клиентов» (в production он принудительно выключен,
см. ``config._enforce_files_legacy_off``), но снаружи об этом не сообщалось
никак — потребитель узнал бы об отключении фактом отключения. Ровно та ситуация,
которую разд. 73.2 запрещает.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = [
    "API_DEPRECATIONS",
    "ApiDeprecation",
    "deprecation_for_path",
]


@dataclass(frozen=True)
class ApiDeprecation:
    """Одна устаревающая поверхность API (путь или семейство путей)."""

    # Префикс пути ПОСЛЕ хоста, включая /api/v1: матчинг по startswith.
    path_prefix: str
    # Когда устаревание объявлено (этап «Анонс» из разд. 73.2).
    deprecated_since: date
    # Когда поверхность будет отключена. Разд. 73.2 требует срок 6–12 месяцев;
    # контрактный тест проверяет дистанцию при ДОБАВЛЕНИИ записи.
    sunset: date
    # Чем пользоваться вместо. Пустого значения не бывает: «этого больше не
    # будет» без «куда переходить» — это не deprecation, а угроза.
    successor: str
    # Ссылка на раздел документации с планом миграции.
    docs_url: str = "https://github.com/aiprocadm/prt_ot_doc/blob/main/docs/API_VERSIONING.md"


# Реестр устаревших поверхностей. Порядок не важен; матчится самый длинный
# подходящий префикс (частный путь может устареть раньше общего).
API_DEPRECATIONS: tuple[ApiDeprecation, ...] = (
    ApiDeprecation(
        path_prefix="/api/v1/files-legacy",
        deprecated_since=date(2026, 7, 30),
        # 12 месяцев — верхняя граница вилки разд. 73.2: у файлового API самые
        # инертные потребители (интеграции, скрипты выгрузки).
        sunset=date(2027, 7, 30),
        successor="/api/v1/files",
    ),
)


def deprecation_for_path(path: str) -> ApiDeprecation | None:
    """Запись реестра для пути (самый длинный совпавший префикс) или ``None``."""

    best: ApiDeprecation | None = None
    for entry in API_DEPRECATIONS:
        if path.startswith(entry.path_prefix) and (
            best is None or len(entry.path_prefix) > len(best.path_prefix)
        ):
            best = entry
    return best
