"""Подтверждение владения доменом партнёра (BIZ-52, разд. 52.2).

ЧТО БЫЛО. Остаток строки: «только домен и поддомен партнёра (инфраструктурный
пункт: DNS и сертификаты вне кода)». DNS и сертификаты снаружи — это правда. Но
из неё не следует, что кода здесь нет.

ЧЕГО НЕЛЬЗЯ БЫЛО ДЕЛАТЬ. Просто дать партнёру записать домен в настройку. Тогда
любой партнёр заявляет ЧУЖОЙ домен, и платформа начинает отдавать под ним его
бренд и его страницу входа. Это подмена сайта чужими руками.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Владение подтверждается
TXT-записью с одноразовым словом:

    _ptd-verify.partner.example.  IN  TXT  "ptd-verify=<слово>"

Почему именно TXT, а не файл на сайте: домен ещё НЕ указывает на платформу в
момент подтверждения — иначе получается замкнутый круг (чтобы подтвердить, надо
переключить DNS; чтобы переключить, надо подтвердить). TXT-запись заводится
независимо и понимается всеми регистраторами.

РАЗРЕШАЮЩИЙ ВЫНЕСЕН ПАРАМЕТРОМ. Проверка ходит в DNS, а тесты не должны
зависеть от сети и от настоящих доменов. Поэтому ``resolve_txt`` передаётся
снаружи: в бою это dnspython, в проверках — подставной.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass

#: Приставка, под которой ищется запись. Отдельная метка, а не корень домена:
#: в корне у партнёра уже лежат чужие TXT-записи (почта, проверки других служб),
#: и добавлять к ним свою — верный способ что-нибудь сломать.
VERIFICATION_PREFIX = "_ptd-verify"

#: Значение записи. Приставка нужна, чтобы наша запись отличалась от соседних.
TOKEN_VALUE_PREFIX = "ptd-verify="

STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"

#: Имя домена: метки из букв, цифр и дефисов, дефис не с краю, общая длина 253.
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN_RE = re.compile(rf"^{_LABEL}(?:\.{_LABEL})+$")


class DomainError(ValueError):
    """Домен нельзя принять. Сообщение предназначено человеку."""


@dataclass(frozen=True)
class VerificationCheck:
    """Итог одной проверки DNS."""

    verified: bool
    detail: str
    expected_record: str
    expected_value: str


def normalize_domain(raw: str | None) -> str:
    """Привести домен к каноническому виду или отказать.

    Нижний регистр и без завершающей точки: «Partner.Example.» и
    «partner.example» — один домен, а две строки в таблице с глобальной
    уникальностью означали бы, что уникальности нет.
    """

    value = (raw or "").strip().lower().rstrip(".")
    if value.startswith("http://") or value.startswith("https://"):
        value = value.split("//", 1)[1].split("/", 1)[0]
    if not value:
        raise DomainError("Домен не указан")
    if len(value) > 253:
        raise DomainError("Домен длиннее 253 символов")
    if not _DOMAIN_RE.match(value):
        raise DomainError(
            "Домен выглядит неверно: ожидается вид partner.example, без протокола и пути"
        )
    return value


def new_token() -> str:
    """Одноразовое слово для TXT-записи (32 знака, 128 бит энтропии)."""

    return secrets.token_hex(16)


def expected_record(domain: str) -> str:
    return f"{VERIFICATION_PREFIX}.{domain}"


def expected_value(token: str) -> str:
    return f"{TOKEN_VALUE_PREFIX}{token}"


def check(
    domain: str,
    token: str,
    *,
    resolve_txt: Callable[[str], Iterable[str]],
) -> VerificationCheck:
    """Проверить TXT-запись. Разрешающий передаётся снаружи (см. шапку модуля).

    Отсутствие записи и ошибка разрешения — РАЗНЫЕ вещи, и обе честно
    называются: «записи нет» человек чинит сам, «DNS не ответил» значит
    повторить позже, а не переделывать запись.
    """

    record = expected_record(domain)
    want = expected_value(token)
    try:
        values = list(resolve_txt(record))
    except Exception as exc:
        return VerificationCheck(
            verified=False,
            detail=f"DNS не ответил по записи {record}: {type(exc).__name__}. Повторите позже.",
            expected_record=record,
            expected_value=want,
        )

    cleaned = [str(value).strip().strip('"') for value in values]
    if not cleaned:
        return VerificationCheck(
            verified=False,
            detail=f"TXT-записи {record} не найдено. Заведите её у регистратора и повторите.",
            expected_record=record,
            expected_value=want,
        )
    if want not in cleaned:
        # Соседние записи — норма; сообщаем, что нашей среди них нет.
        return VerificationCheck(
            verified=False,
            detail=(
                f"В TXT-записях {record} нет нужного значения. "
                f"Найдено значений: {len(cleaned)}."
            ),
            expected_record=record,
            expected_value=want,
        )
    return VerificationCheck(
        verified=True,
        detail="Владение доменом подтверждено",
        expected_record=record,
        expected_value=want,
    )


def dns_txt_resolver(timeout: float = 5.0) -> Callable[[str], list[str]]:
    """Боевой разрешающий. Импорт внутри: в проверках он не нужен."""

    def _resolve(name: str) -> list[str]:
        import dns.resolver  # noqa: PLC0415 - тяжёлый импорт только в бою

        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answers = resolver.resolve(name, "TXT")
        out: list[str] = []
        for answer in answers:
            for chunk in getattr(answer, "strings", []):
                out.append(chunk.decode("utf-8", "replace"))
        return out

    return _resolve


__all__ = [
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_VERIFIED",
    "TOKEN_VALUE_PREFIX",
    "VERIFICATION_PREFIX",
    "DomainError",
    "VerificationCheck",
    "check",
    "dns_txt_resolver",
    "expected_record",
    "expected_value",
    "new_token",
    "normalize_domain",
]
