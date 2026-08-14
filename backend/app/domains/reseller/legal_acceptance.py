"""Принятие юридического текста (BIZ-52 срез-11, Доп. №1 разд. 52.2).

Срез-5 научил партнёра ПУБЛИКОВАТЬ оферту, политику ПДн и текст согласия.
Кто и когда их принял — не записывалось нигде: документ есть, доказательства
акцепта нет. Для оферты это половина работы — она и существует ради ответа на
вопрос «на каких условиях работает этот клиент».

Правила здесь чистые (без базы): что считать принятым, что просрочено новой
редакцией и как опознать текст, под которым подписались.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


def document_fingerprint(body: str) -> str:
    """Отпечаток текста, под которым подписались.

    Одной ссылки на редакцию мало. Строку можно поправить в обход
    версионирования — руками в базе, ошибочной миграцией, восстановлением из
    бэкапа, — и тогда «принята редакция 3» будет указывать на текст, которого
    человек не видел. Отпечаток отвечает на вопрос «а тот ли это текст»
    независимо от того, что случилось со строкой.

    Приём взят у `PdnConsent` (SEC-66) — там `text_sha256` ровно за этим.
    """

    return sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AcceptanceState:
    """Что действует и принято ли оно этим человеком."""

    kind: str
    #: Номер действующей редакции. `None` — текста нет вовсе.
    current_version: int | None
    #: Номер принятой редакции. `None` — не принимал ничего.
    accepted_version: int | None

    @property
    def exists(self) -> bool:
        return self.current_version is not None

    @property
    def accepted(self) -> bool:
        """Принято ли ИМЕННО действующее.

        Принятая старая редакция — это «не принято»: условия изменились, и
        согласие с прежними не переносится на новые. Иначе публикация новой
        оферты молча считалась бы принятой всеми.
        """

        return self.exists and self.accepted_version == self.current_version

    @property
    def outdated(self) -> bool:
        """Принята прежняя редакция, вышла новая.

        Отдельно от «не принимал вовсе»: человеку, уже подписавшему прежнюю
        версию, показывают «условия изменились», а не «примите оферту» — это
        разные сообщения, и путать их значит пугать человека без причины.
        """

        if self.current_version is None or self.accepted_version is None:
            return False
        return self.accepted_version < self.current_version


def pending_kinds(states: list[AcceptanceState]) -> list[str]:
    """Что ещё требует подписи. Порядок сохраняется — он задан списком видов."""

    return [state.kind for state in states if state.exists and not state.accepted]
