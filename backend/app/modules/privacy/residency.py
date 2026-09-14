"""Сверка локализации ПДн: объявлено в реестре против фактического развёртывания.

SEC-66, Доп.№3 разд. 66.1 («локализация»).

ЧТО БЫЛО. В реестре обработки есть поле ``storage_location`` — где физически
лежат данные. Строка матрицы честно писала: «Осталось: локализация ПДн — вопрос
хостинга, не кода (поле в реестре есть)». Так и было: арендатор писал в реестре
«RU», и никто никогда не сверял это с тем, где развёрнута система.

ПОЧЕМУ ЭТО ВАЖНО. Реестр обработки — документ, который показывают регулятору.
Строка «данные хранятся в РФ» в нём — УТВЕРЖДЕНИЕ о системе. Если файлы на самом
деле уезжают в хранилище за пределами объявленного региона, утверждение ложно, а
узнать об этом можно только на проверке. Это тот же класс, что пустые адаптеры,
рапортующие об успешной отправке: система говорит о себе то, чего не проверяет.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Хостинг выбирает владелец — это
действительно не код. Но КОД может потребовать, чтобы фактический регион был
ОБЪЯВЛЕН настройкой (``DATA_RESIDENCY_REGION``), и сверить с ним каждую
действующую строку реестра.

ТРИ ИСХОДА СВЕРКИ.

* ``ok`` — объявленное в реестре совпадает с регионом развёртывания.
* ``undeclared_transfer`` — не совпадает, И трансграничная передача НЕ отмечена.
  Это и есть настоящая находка: реестр обещает регулятору одно, система делает
  другое.
* ``declared_transfer`` — не совпадает, но трансграничная передача отмечена
  осознанно. Нарушения нет; строка показывается, потому что такие процессы
  требуют отдельного основания и их полезно видеть списком.

ЧЕГО ЗДЕСЬ НЕТ. Сверка НЕ лезет в настройки хранилища и не пытается угадать
регион по адресу S3: по адресу это не определяется (совместимое хранилище может
стоять где угодно), а угаданное значение, поданное как измеренное, — худший из
возможных ответов. Регион объявляет тот, кто разворачивал систему.
"""

from __future__ import annotations

from dataclasses import dataclass

OK = "ok"
UNDECLARED_TRANSFER = "undeclared_transfer"
DECLARED_TRANSFER = "declared_transfer"

#: Регион по умолчанию, если настройка не задана. РФ — потому что 152-ФЗ и есть
#: причина существования этого реестра.
DEFAULT_REGION = "RU"


@dataclass(frozen=True)
class ResidencyFinding:
    """Результат сверки одной строки реестра."""

    code: str
    name: str
    declared_location: str
    deployment_region: str
    cross_border_transfer: bool
    verdict: str

    @property
    def is_violation(self) -> bool:
        return self.verdict == UNDECLARED_TRANSFER

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "declared_location": self.declared_location,
            "deployment_region": self.deployment_region,
            "cross_border_transfer": self.cross_border_transfer,
            "verdict": self.verdict,
        }


def deployment_region(settings) -> str:
    """Фактический регион развёртывания — объявленный тем, кто разворачивал."""

    raw = (getattr(settings, "data_residency_region", "") or "").strip()
    return (raw or DEFAULT_REGION).upper()


def evaluate_activity(
    *, code: str, name: str, storage_location: str, cross_border_transfer: bool, region: str
) -> ResidencyFinding:
    declared = (storage_location or "").strip().upper()
    if declared == region:
        verdict = OK
    elif cross_border_transfer:
        verdict = DECLARED_TRANSFER
    else:
        verdict = UNDECLARED_TRANSFER
    return ResidencyFinding(
        code=code,
        name=name,
        declared_location=declared,
        deployment_region=region,
        cross_border_transfer=bool(cross_border_transfer),
        verdict=verdict,
    )


def evaluate(activities, *, settings) -> list[ResidencyFinding]:
    """Сверить действующие строки реестра с регионом развёртывания.

    ``activities`` — строки реестра (любые объекты с полями ``code``, ``name``,
    ``storage_location``, ``cross_border_transfer``, ``is_active``).
    Недействующие строки пропускаются: они описывают прошлое, а не систему.
    """

    region = deployment_region(settings)
    findings: list[ResidencyFinding] = []
    for activity in activities:
        if not getattr(activity, "is_active", True):
            continue
        findings.append(
            evaluate_activity(
                code=activity.code,
                name=activity.name,
                storage_location=activity.storage_location,
                cross_border_transfer=activity.cross_border_transfer,
                region=region,
            )
        )
    return findings


def summarize(findings: list[ResidencyFinding]) -> dict[str, object]:
    violations = [f for f in findings if f.is_violation]
    declared = [f for f in findings if f.verdict == DECLARED_TRANSFER]
    return {
        "region": findings[0].deployment_region if findings else DEFAULT_REGION,
        "checked": len(findings),
        "violations": len(violations),
        "declared_transfers": len(declared),
        "compliant": not violations,
        "findings": [f.as_dict() for f in findings if f.verdict != OK],
    }


__all__ = [
    "DECLARED_TRANSFER",
    "DEFAULT_REGION",
    "OK",
    "UNDECLARED_TRANSFER",
    "ResidencyFinding",
    "deployment_region",
    "evaluate",
    "evaluate_activity",
    "summarize",
]
