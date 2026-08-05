"""BIZ-49 срез-9 (разд. 49.3): область видимости данных в контексте клиента.

Срез-7 научил платформу ПОДТВЕРЖДАТЬ контекст клиента и писать след в аудит,
срез-8 дал переключатель. Но данные при этом оставались общими: индикатор
говорил «вы работаете от имени ООО Ромашка», а список людей показывал всех
подряд. Для аутсорсера с сотней клиентов это прямой путь завести документ не
той организации — и заметить это через месяц.

Здесь чистые правила без БД: во что превращается подтверждённый контекст,
когда доходит до выборки данных.

Три решения, которые важнее кода:

* **Fail-closed.** Если непонятно, чьи это данные (клиент ещё не связан с
  организацией), показываем ПУСТО, а не всё. Обратное — утечка между
  клиентами одного аутсорсера под вывеской «вы работаете от имени».
* **Свой контур честно говорит «нечем читать».** У режима Dedicated данные
  лежат в другом арендаторе; до делегированного доступа они недоступны. Это
  ровно та же честность, что и ``not_aggregated`` в сводке внимания
  (срез-2): пусто с объяснением лучше, чем пусто без него, и несравнимо
  лучше, чем чужие строки.
* **Реестр разделов объявлен на бэкенде.** Фильтр применён пока не везде, и
  интерфейс обязан называть, где именно он действует. Список, захардкоженный
  на фронте, разъедется с бэкендом в день добавления нового раздела.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.managed_clients.context import ClientContext
from app.domains.managed_clients.lifecycle import ManagedClientMode

__all__ = [
    "CLIENT_SCOPED_SECTIONS",
    "ClientDataScope",
    "NO_COMPANY_REASON",
    "OWN_CONTOUR_REASON",
    "resolve_client_scope",
    "scoped_section_titles",
]

OWN_CONTOUR_REASON = (
    "Данные этого клиента ведутся в отдельном контуре — из пространства "
    "аутсорсера они не читаются"
)

NO_COMPANY_REASON = (
    "Клиент ещё не связан с организацией: непонятно, какие данные считать его "
    "данными, поэтому раздел пуст"
)

#: Разделы, где контекст клиента УЖЕ работает как фильтр. Пополняется вместе
#: с кодом, а не «на глазок»: индикатор в интерфейсе называет именно этот
#: список, и обещать в нём больше, чем сделано, нельзя.
CLIENT_SCOPED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("persons", "Люди"),
    ("medical", "Медосмотры"),
)


@dataclass(frozen=True)
class ClientDataScope:
    """Во что превращается контекст клиента при выборке данных."""

    client_id: str
    client_name: str
    #: Организация клиента. ``None`` — данных не видно (см. ``reason``).
    company_id: str | None
    #: Почему данных не видно. Пусто, когда видно.
    reason: str | None = None

    @property
    def visible(self) -> bool:
        """Есть ли что показывать. Никогда не означает «показать всё»."""

        return self.company_id is not None


def resolve_client_scope(context: ClientContext) -> ClientDataScope:
    """Определить, какие данные считаются данными этого клиента."""

    if context.mode is ManagedClientMode.DEDICATED:
        return ClientDataScope(
            client_id=context.client_id,
            client_name=context.client_name,
            company_id=None,
            reason=OWN_CONTOUR_REASON,
        )

    if not context.company_id:
        return ClientDataScope(
            client_id=context.client_id,
            client_name=context.client_name,
            company_id=None,
            reason=NO_COMPANY_REASON,
        )

    return ClientDataScope(
        client_id=context.client_id,
        client_name=context.client_name,
        company_id=context.company_id,
    )


def scoped_section_titles() -> list[str]:
    """Человеческие названия разделов для индикатора «работаю от имени»."""

    return [title for _, title in CLIENT_SCOPED_SECTIONS]
