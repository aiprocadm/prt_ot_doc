"""OPS-74, разд. 74.2: правила раската схемы по ВСЕМ арендаторам.

ТЗ: «Миграция по всем схемам арендаторов: schema-per-tenant означает N схем;
миграция должна безопасно и **отслеживаемо** пройти по всем, **с прогрессом и
возможностью паузы**».

ЧТО БЫЛО. Скрипт умел обновить ОДНОГО арендатора по имени
(`scripts/migrate_tenant.py`). На тридцати клиентах это ещё «запустить тридцать
раз», на трёхстах — уже нет: непонятно, где остановились, нельзя приостановить
на пике нагрузки и нельзя продолжить с места после обрыва связи.

Здесь — ЧИСТЫЕ ПРАВИЛА без базы и файлов, чтобы их можно было проверить
тестами: что делать дальше, как считать прогресс, где законно останавливаться и
чем кончился раскат.

РЕШЕНИЯ, КОТОРЫЕ ВАЖНЕЕ КОДА.

* **Пауза срабатывает МЕЖДУ арендаторами, а не внутри одного.** Остановка
  посреди одного арендатора оставила бы его схему на полпути — ровно то
  состояние, из которого потом никто не знает, как выходить.
* **Ошибка одного не останавливает раскат.** Иначе один сломанный клиент
  заморозит обновление всех остальных. Ошибки собираются и называются в конце
  поимённо — молча пропускать их нельзя.
* **Уже сделанные пропускаются.** Раскат обязан продолжаться с места обрыва;
  «начать сначала» на трёхстах арендаторах — это часы лишней работы и лишний
  риск.
* **Порядок устойчивый (по имени).** Случайный порядок сделал бы отчёты
  несравнимыми между запусками и мешал бы понять, где именно остановились.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "RolloutOutcome",
    "RolloutSummary",
    "format_progress",
    "plan_rollout",
    "summarize",
]


@dataclass(frozen=True)
class RolloutOutcome:
    """Чем кончился раскат у одного арендатора."""

    slug: str
    status: str  # "done" | "failed" | "skipped"
    detail: str = ""


@dataclass
class RolloutSummary:
    """Итог раската: что сделано, что пропущено, что упало — поимённо."""

    done: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.failed

    def as_lines(self) -> list[str]:
        lines = [
            f"обновлено: {len(self.done)}",
            f"пропущено (уже было): {len(self.skipped)}",
            f"с ошибкой: {len(self.failed)}",
        ]
        # Ошибки называются ПОИМЁННО: счётчик «с ошибкой: 3» не даёт понять,
        # к кому идти, и такой отчёт никто не дочитывает до конца.
        lines += [f"  ОШИБКА {slug}: {detail}" for slug, detail in self.failed]
        return lines


def plan_rollout(all_slugs: list[str], already_done: set[str]) -> list[str]:
    """Кого ещё предстоит обновить, в устойчивом порядке.

    Порядок по имени — чтобы два запуска были сравнимы, а «остановились на
    таком-то» означало одно и то же место.
    """

    return sorted({slug for slug in all_slugs if slug} - set(already_done))


def format_progress(position: int, total: int, slug: str) -> str:
    """Строка прогресса: где мы и кого делаем сейчас.

    Без имени арендатора прогресс бесполезен: «17 из 300» не подскажет, на ком
    раскат встал, если он встанет.
    """

    percent = int(position * 100 / total) if total else 100
    return f"[{position}/{total}, {percent}%] {slug}"


def summarize(outcomes: list[RolloutOutcome]) -> RolloutSummary:
    summary = RolloutSummary()
    for item in outcomes:
        if item.status == "done":
            summary.done.append(item.slug)
        elif item.status == "skipped":
            summary.skipped.append(item.slug)
        else:
            summary.failed.append((item.slug, item.detail))
    return summary
