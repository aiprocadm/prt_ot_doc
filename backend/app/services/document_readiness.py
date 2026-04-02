"""Document readiness score and explainability (TZ §9.5)."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.document import Document, DocumentJobStatus, DocumentStatus, DocumentVersion
from app.models.models import TemplateVersionStatus

_UNUSABLE_TEMPLATE_STATUSES = frozenset(
    {
        TemplateVersionStatus.DEPRECATED,
        TemplateVersionStatus.ARCHIVED,
        TemplateVersionStatus.DRAFT,
    }
)


@dataclass(frozen=True, slots=True)
class DocumentReadinessSnapshot:
    score: int
    blockers: list[str]
    recommended_actions: list[str]


def _latest_version(document: Document) -> DocumentVersion | None:
    if not document.versions:
        return None
    return max(document.versions, key=lambda v: (v.version_number, v.created_at))


def compute_document_readiness(document: Document) -> DocumentReadinessSnapshot:
    """Derive a 0–100 score with human-readable blockers and next steps."""

    if document.status == DocumentStatus.REVOKED:
        return DocumentReadinessSnapshot(
            score=0,
            blockers=["Документ отозван"],
            recommended_actions=["Создайте новый документ или обратитесь к администратору аренды"],
        )

    blockers: list[str] = []
    actions: list[str] = []
    score = 0

    tv = document.template_version
    if not document.template_version_id:
        blockers.append("Не привязана версия шаблона")
        actions.append("Выберите опубликованную версию шаблона")
    elif tv is None:
        blockers.append("Версия шаблона не найдена в каталоге")
        actions.append("Восстановите шаблон или перепривяжите версию")
    elif tv.status in _UNUSABLE_TEMPLATE_STATUSES:
        blockers.append(f"Версия шаблона в статусе «{tv.status.value}» не подходит для выдачи")
        actions.append("Перейдите на активную или готовую (active/ready) версию шаблона")
    else:
        score += 25

    if document.company_id:
        score += 10
    else:
        blockers.append("Не указана организация-владелец")

    job = document.job
    if job is not None:
        if job.status == DocumentJobStatus.FAILED:
            blockers.append("Фоновая генерация завершилась с ошибкой")
            actions.append("Проверьте задачу генерации и выполните повторный запуск")
        elif job.status in (DocumentJobStatus.QUEUED, DocumentJobStatus.PROCESSING):
            actions.append("Ожидайте завершения фоновой генерации")
            score += 10
        else:
            score += 20
    else:
        score += 15

    latest = _latest_version(document)
    has_file = bool(
        document.storage_key or document.file_id or (latest and (latest.file_key or latest.file_id))
    )
    if has_file:
        score += 25
    elif document.status != DocumentStatus.DRAFT:
        blockers.append("Нет файла DOCX/PDF для текущей версии")
        actions.append("Запустите генерацию или восстановите файл из хранилища")

    workflow_points = 0
    if latest is not None:
        if document.status in (
            DocumentStatus.REVIEW,
            DocumentStatus.APPROVED,
            DocumentStatus.SIGNED,
            DocumentStatus.ARCHIVED,
        ):
            appr = (latest.approval_status or "").lower()
            if appr in ("approved", "waived", "not_required", "completed"):
                workflow_points += 7
            elif document.status == DocumentStatus.REVIEW:
                actions.append("Завершите согласование по маршруту")
            elif document.status in (
                DocumentStatus.APPROVED,
                DocumentStatus.SIGNED,
                DocumentStatus.ARCHIVED,
            ):
                actions.append("Зафиксируйте статус согласования для версии документа")

        if document.status in (
            DocumentStatus.APPROVED,
            DocumentStatus.SIGNED,
            DocumentStatus.ARCHIVED,
        ):
            sig = (latest.signature_status or "").lower()
            if sig in ("signed", "waived", "not_required"):
                workflow_points += 7
            else:
                actions.append("Выполните подписание или отметьте исключение в карточке версии")

        if document.status in (DocumentStatus.SIGNED, DocumentStatus.ARCHIVED):
            edo = (latest.edo_status or "").lower()
            if edo in ("failed", "rejected", "error"):
                blockers.append("Доставка в ЭДО отклонена или завершилась ошибкой")
                actions.append("Проверьте журнал ЭДО и переотправьте документ")
            elif edo in ("sent", "delivered", "accepted", "pending", "", "none", "not_required"):
                workflow_points += 6

    score += min(20, workflow_points)
    score = max(0, min(100, score))

    uniq_actions = list(dict.fromkeys(actions))

    return DocumentReadinessSnapshot(score=score, blockers=blockers, recommended_actions=uniq_actions)
