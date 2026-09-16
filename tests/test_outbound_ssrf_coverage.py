"""Сторож: у каждого исходящего вызова назван рубеж SSRF (SEC-64 §64.3, срез-206).

ЧТО НАШЛА СВЕРКА. Критерий приёмки 70.1 требует: «SSRF-защита вебхуков/интеграций:
приватные диапазоны отклоняются (тест)». Сторож ``core/ssrf_guard.py`` есть и
стоял на ДВУХ местах из девяти. Два оставшихся были настоящими дырами.

**Дыра первая, серьёзная: второй путь доставки вебхуков.** У доставки их два —
служба ``services/webhooks.py`` (проверка была) и обход очереди в
``tasks/_core.py`` (проверки не было). Второй постил по адресу, который задал
арендатор, и клал до 1000 знаков ОТВЕТА в ``last_response_body``. Это поле
арендатор читает ручкой журнала доставок. То есть это был не слепой SSRF, а
**SSRF с выносом**: эндпоинт на внутренний адрес возвращал наружу содержимое
закрытой сети.

Это тот же класс, что срез-191: у вебхуков две дорожки, подпись починили на
одной, и половина доставок пришла с несходящейся подписью. Правило: **у доставки
два пути — правило ставится на оба.**

**Дыра вторая, моя вчерашняя:** единый вход (срез-204) ходит на адреса, которые
задаёт администратор заказчика, и проверки там не было вовсе.

ЧТО СТЕРЕЖЁТ ЭТОТ ТЕСТ. Каждый файл, создающий исходящий HTTP-клиент, обязан
быть в реестре: либо он проверяет адрес сторожем, либо объявлен исключением
С ПРИЧИНОЙ. Третьего состояния нет — новый вызов не заведётся молча.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_outbound_ssrf_coverage.py -v``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend" / "app"

#: Файлы, где исходящий вызов идёт на адрес, заданный АРЕНДАТОРОМ или
#: настройкой: адрес обязан пройти ``assert_safe_webhook_url``.
GUARDED_CALLERS: frozenset[str] = frozenset(
    {
        "services/webhooks.py",
        "modules/notifications/providers/webhook.py",
        "tasks/_core.py",
        "api/routes/sso.py",
    }
)

#: Исключения — с ПРИЧИНОЙ. Пустая причина запрещена: «так надо» через полгода
#: читается как «никто не разобрался».
EXEMPT_CALLERS: dict[str, str] = {
    "services/integrations/http_edo.py": (
        "адрес оператора ЭДО приходит НАСТРОЙКОЙ окружения (EDO_INTEGRATION_BASE_URL) "
        "и проверяется при старте валидатором `assert_safe_http_base_url` в core/config.py; "
        "арендатор его не задаёт"
    ),
    "core/anti_bot.py": (
        "адрес службы проверки «человек ли это» берётся из ЗАКРЫТОГО списка в коде "
        "(PROVIDER_URLS: Cloudflare Turnstile и Google reCAPTCHA); настройкой выбирается "
        "только НАЗВАНИЕ службы, а не адрес, поэтому подменить его ни арендатору, ни "
        "пользователю нечем — в отличие от вебхуков, где адрес задаёт заказчик (разд. 64.3)"
    ),
    "modules/notifications/providers/telegram.py": (
        "адрес зашит в код (api.telegram.org) и не приходит ни от арендатора, "
        "ни из настройки — подменить его нечем"
    ),
}

_CLIENT_RE = re.compile(r"httpx\.(Async)?Client\s*\(")


def _callers() -> set[str]:
    found: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if _CLIENT_RE.search(text):
            found.add(str(path.relative_to(BACKEND)))
    return found


def test_каждый_исходящий_вызов_описан() -> None:
    """ГЛАВНАЯ ПРОВЕРКА: новый вызов наружу не заведётся молча."""

    described = GUARDED_CALLERS | set(EXEMPT_CALLERS)
    missing = sorted(_callers() - described)

    assert not missing, (
        "появились исходящие HTTP-вызовы без записи о рубеже SSRF:\n  "
        + "\n  ".join(missing)
        + "\nЛибо проверяйте адрес `assert_safe_webhook_url` и добавьте файл в "
        "GUARDED_CALLERS, либо объявите исключение в EXEMPT_CALLERS с причиной."
    )


def test_в_реестре_нет_записей_о_снятых_вызовах() -> None:
    described = GUARDED_CALLERS | set(EXEMPT_CALLERS)
    stale = sorted(described - _callers())

    assert not stale, f"записи о файлах, где исходящего вызова уже нет: {stale}"


def test_защищённый_вызов_действительно_зовёт_сторожа() -> None:
    """Запись в реестре — это обещание. Проверяем, что в файле и правда есть
    вызов сторожа, а не только строка в списке.

    ГРАНИЦА ЭТОЙ ПРОВЕРКИ НАЗВАНА ЧЕСТНО: она читает ТЕКСТ и считает живым
    вызов, спрятанный в мёртвую ветку (``if False:``). Это выяснилось мутацией —
    она не покраснела. Поэтому поведение проверяется отдельно и по-настоящему:
    ``tests/test_tasks.py::test_dispatch_outbox_events_blocks_internal_urls`` и
    ``tests/api/test_sso_ssrf.py``. Текстовый список ловит ПОЯВЛЕНИЕ нового
    вызова наружу; что рубеж работает — доказывают они."""

    without_guard = sorted(
        name
        for name in GUARDED_CALLERS
        if "assert_safe_webhook_url" not in (BACKEND / name).read_text(encoding="utf-8")
    )

    assert not without_guard, "эти файлы числятся защищёнными, но сторожа не зовут: " + ", ".join(
        without_guard
    )


def test_у_исключения_названа_причина() -> None:
    for name, reason in EXEMPT_CALLERS.items():
        assert reason.strip(), f"{name}: пустая причина"
        assert len(reason) > 30, f"{name}: причина слишком короткая, чтобы что-то объяснить"


def test_файл_не_бывает_одновременно_защищённым_и_исключением() -> None:
    assert not GUARDED_CALLERS & set(EXEMPT_CALLERS)


def test_оба_пути_доставки_вебхуков_защищены() -> None:
    """ТО, РАДИ ЧЕГО СРЕЗ. Срез-191 уже показал, что у вебхуков ДВА пути и
    правило легко поставить только на один."""

    assert "services/webhooks.py" in GUARDED_CALLERS
    assert "tasks/_core.py" in GUARDED_CALLERS
