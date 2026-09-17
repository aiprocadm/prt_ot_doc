from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.external_perimeter import (
    assert_not_locked_out,
    enforce_portal_traffic,
    record_auth_failure,
)
from app.core.security import AccessContext, abac, issue_portal_session_token, verify_token
from app.core.tenant import tenant_prefix_path
from app.db.session import rearm_session_tenant_context
from app.db.tenant_read_guard import allow_cross_tenant_read
from app.models.models import (
    ClientPackagePreset,
    ClientPackageRun,
    ClientPortalToken,
    ClientRequestTicket,
    ClientRequestTicketStatus,
    PackageEvent,
    PackageRequirement,
    PackageRequirementStatus,
    PackageRequirementType,
    PackageRunStatus,
    Tenant,
)
from app.modules.packs.definitions import PACK_DEFINITIONS_BY_CODE
from app.modules.packs.operations import resolve_pipeline_profile
from app.services import portal_otp_delivery as otp_delivery
from app.services import sms_gateway
from app.services.file_storage import FileStorageService
from app.services.portal_otp_delivery import send_otp_code

router = APIRouter(prefix="/portal", tags=["client-portal"])
internal_router = APIRouter(prefix="/packages", tags=["packages"])
presets_router = APIRouter(prefix="/presets/packages", tags=["package-presets"])


# Служебные ручки портала (наборы для клиентов, разбор запросов) зовут экраны
# сотрудников, а не пункт меню «Кабинет клиента» — тот стоит за
# modules/client_portal (карта прав экрана). Круг здесь — прежний.
_STAFF_READ_ROLES = [
    "admin",
    "owner",
    "hr",
    "line_manager",
    "manager",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "accountant",
    "auditor_ro",
]
_STAFF_WRITE_ROLES = ["admin", "owner", "ot_specialist"]


def _staff_tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


StaffReadAccess = Depends(
    abac(_staff_tenant_resource_id, required_roles=_STAFF_READ_ROLES, action="read packages")
)
StaffWriteAccess = Depends(
    abac(_staff_tenant_resource_id, required_roles=_STAFF_WRITE_ROLES, action="manage packages")
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _hash_token(token: str) -> str:
    salt = get_settings().portal_token_salt
    return hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_required_inputs(required_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in required_inputs:
        requirement_type = str(item.get("type") or "file").lower()
        normalized.append(
            {
                "key": str(item.get("key") or secrets.token_hex(4)),
                "title": str(item.get("title") or "Required data"),
                "type": requirement_type,
                "required": bool(item.get("required", True)),
                "description": item.get("description"),
                "artifact_kind": item.get("artifact_kind", requirement_type),
            }
        )
    return normalized


def _resolve_pipeline(preset: ClientPackagePreset) -> dict[str, Any]:
    required_inputs = _normalize_required_inputs(preset.required_inputs_json or [])
    steps_json = dict(preset.steps_json or {})
    return resolve_pipeline_profile(
        preset_code=preset.code,
        preset_name=preset.name,
        steps=list(steps_json.get("steps") or []),
        required_inputs=required_inputs,
        output_artifacts=list(steps_json.get("output_artifacts") or []),
    )


def _write_package_artifacts(
    *, run: ClientPackageRun, preset: ClientPackagePreset, pipeline: dict[str, Any]
) -> tuple[str | None, str | None, str, dict[str, Any]]:
    storage = FileStorageService.default()
    prefix = f"packages/{run.id}"
    manifest_key = f"{prefix}/manifest.json"
    manifest = {
        "run_id": run.id,
        "preset_code": preset.code,
        "preset_name": preset.name,
        "scenario": pipeline["scenario"],
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "steps": pipeline["steps"],
        "required_inputs": pipeline["required_inputs"],
        "output_artifacts": pipeline["output_artifacts"],
        "pipeline_fingerprint": pipeline.get("pipeline_fingerprint"),
        "generated_at": _utcnow().isoformat(),
    }
    storage.put(
        manifest_key,
        json.dumps(jsonable_encoder(manifest), ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )
    # ЗДЕСЬ РАНЬШЕ ПОДДЕЛЫВАЛИСЬ АРХИВ И PDF: в хранилище клалась строка
    # «ZIP bundle for <код> / <id>» с типом application/zip. Клиент скачивал из
    # кабинета файл, который не открывается ни одним архиватором, — и это
    # выглядело как работающая выдача. Файл, которого нет, честнее отсутствия
    # файла: настоящий архив прикрепляется публикацией результата генерации
    # (`POST /packages/publish`, разд. 50.2 шаг 4).
    qc_report = {
        "scenario": pipeline["scenario"],
        "steps": [
            {"name": step.get("code", step.get("title", "step")), "status": "done"}
            for step in pipeline["steps"]
        ],
        "requirements_total": len(pipeline["required_inputs"]),
        "artifacts": [manifest_key],
        "status_flow": list(pipeline.get("status_flow") or ["running", "generated", "published"]),
        "pipeline_fingerprint": pipeline.get("pipeline_fingerprint"),
    }
    return None, None, manifest_key, qc_report


def _artifact_entry(
    storage: FileStorageService, key: str | None, *, kind: str
) -> dict[str, Any] | None:
    if not key:
        return None
    meta = storage.head(key) or {"key": key}
    return {
        "kind": kind,
        "s3_key": key,
        "signed_url": storage.create_signed_url(key),
        "quarantined": meta.get("quarantined", False),
        "sha256": meta.get("sha256"),
        "size": meta.get("size"),
        "adapter": meta.get("adapter"),
        "scan_status": meta.get("scan_status"),
    }


def _manifest_key_from_run(run: ClientPackageRun) -> str | None:
    artifacts = (run.qc_report_json or {}).get("artifacts") or []
    if not artifacts:
        return None
    return artifacts[-1]


class PackagePresetCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    steps_json: dict[str, Any] = Field(default_factory=dict)
    required_inputs_json: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class PackagePresetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    steps_json: dict[str, Any] | None = None
    required_inputs_json: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class PackageRunCreate(BaseModel):
    preset_code: str
    client_company_id: str | None = None


class PackagePublishRequest(BaseModel):
    """Отдать клиенту УЖЕ сгенерированный комплект (разд. 50.2 шаг 4)."""

    #: Код сценария. Совпадает с кодом встроенного комплекта (`/packs/generate`)
    #: либо с кодом портального пресета, заведённого аутсорсером вручную.
    preset_code: str
    #: Ключ настоящего архива в хранилище — то, что вернула генерация.
    zip_storage_key: str = Field(min_length=1)
    client_company_id: str | None = None


class PortalLinkResponse(BaseModel):
    portal_url: str
    expires_at: datetime


class PortalSessionResponse(BaseModel):
    """SEC-68: результат обмена ссылочного токена на сеансовый."""

    session_token: str
    expires_at: datetime


class PortalOtpResponse(BaseModel):
    """SEC-68 (разд. 68.1): ответ на запрос кода.

    Один и тот же ответ и когда код отправлен, и когда у ссылки привязки нет:
    иначе по ответу можно было бы перебирать, какие ссылки к кому привязаны.
    Адрес получателя в ответе НЕ называется — его знает тот, кому письмо
    пришло, а для пересылающего это была бы подсказка.
    """

    message: str
    expires_in_minutes: int


class PackageTicketCreate(BaseModel):
    title: str
    message: str


class PortalFilesResponse(BaseModel):
    files: list[dict[str, Any]]


class PortalAuth(BaseModel):
    tenant_id: str
    package_run_ids: set[str]
    can_upload: bool = False
    can_tickets: bool = False
    can_download: bool = False


def _serialize_package_run(run: ClientPackageRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "preset_id": run.preset_id,
        "initiated_by_user_id": run.initiated_by_user_id,
        "client_company_id": run.client_company_id,
        "status": run.status.value if isinstance(run.status, PackageRunStatus) else run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "output_zip_s3_key": run.output_zip_s3_key,
        "output_pdf_s3_key": run.output_pdf_s3_key,
        "qc_report_json": run.qc_report_json,
        "error_payload_json": run.error_payload_json,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "deleted_at": run.deleted_at,
    }


def _auth_from_record(record: ClientPortalToken) -> PortalAuth:
    scope = record.scope_json or {}
    package_ids = set(scope.get("package_run_ids") or [record.package_run_id])
    return PortalAuth(
        tenant_id=str(record.tenant_id),
        package_run_ids=package_ids,
        can_upload=bool(scope.get("upload", True)),
        can_tickets=bool(scope.get("tickets", True)),
        can_download=bool(scope.get("download", True)),
    )


def _ensure_link_alive(record: ClientPortalToken) -> None:
    expires_at = _as_utc(record.expires_at)
    if record.revoked_at is not None or expires_at <= _utcnow():
        # Протухший/отозванный токен НЕ считаем попыткой перебора: это обычная
        # ситуация у легитимного клиента со старой ссылкой в почте.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portal token expired or revoked")


def _bind_to_link(session: AsyncSession, record: ClientPortalToken) -> None:
    """Прижать сессию к арендатору, которого назвала ссылка (разд. 64.1).

    ЗАЧЕМ. Внешний контур — самая открытая поверхность продукта, и до этого
    среза его изоляция держалась ТОЛЬКО на списке разрешённых ссылкой прогонов
    (`scope_json`). Запрос приходит без имени организации, поэтому сессия была
    прибита к арендатору по умолчанию — и любой запрос портала шёл «не от того
    имени».

    После опознания ссылки арендатор ИЗВЕСТЕН. Прижимая к нему сессию, мы
    получаем у портала второй рубеж: строки других арендаторов для него просто
    перестают существовать, даже если список прогонов однажды окажется шире,
    чем следует.
    """

    info = getattr(session, "info", None)
    if isinstance(info, dict):
        info["tenant_id"] = str(record.tenant_id)


async def _resolve_link_token(
    request: Request, session: AsyncSession, raw: str, *, burn_use: bool
) -> ClientPortalToken:
    """Найти и проверить ссылочный токен; ``burn_use`` тратит одно использование."""

    token_hash = _hash_token(raw)
    stmt = select(ClientPortalToken).where(ClientPortalToken.token_hash == token_hash)
    # ЗАКОННОЕ ЧТЕНИЕ МИМО АРЕНДАТОРА, названное вслух (разд. 64.1). Ссылка САМА
    # называет арендатора: до того, как она найдена по отпечатку, неизвестно,
    # чья она. Разрешение здесь предельно узкое — один поиск по отпечатку; сразу
    # после него сессия прикалывается к арендатору из ссылки (`_bind_to_link`).
    with allow_cross_tenant_read(
        session, reason="поиск ссылки клиентского портала по отпечатку: арендатор известен из неё"
    ):
        record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        record_auth_failure(request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid portal token")
    _ensure_link_alive(record)
    if not hmac.compare_digest(_hash_token(raw), record.token_hash):
        record_auth_failure(request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid portal token")

    if burn_use:
        # SEC-68 (разд. 68.1 «одноразовость где возможно»): лимит использований.
        if record.max_uses is not None and (record.uses_count or 0) >= record.max_uses:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portal token usage limit reached")
        record.uses_count = (record.uses_count or 0) + 1
        record.last_used_at = _utcnow()
    return record


async def _portal_auth(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_portal_session: Annotated[str | None, Header(alias="X-Portal-Session")] = None,
    x_portal_token: Annotated[str | None, Header(alias="X-Portal-Token")] = None,
) -> PortalAuth:
    """Кто пришёл во внешний контур (разд. 68.1).

    ССЫЛОЧНЫЙ ТОКЕН В АДРЕСЕ ЗДЕСЬ НЕ ПРИНИМАЕТСЯ — и это решение, а не
    недосмотр. ТЗ разд. 68.1 в таблице угроз пишет прямо: «утечка через
    Referer/логи/историю → токен не в query, а лучше в теле/заголовке». Адрес
    страницы попадает в журналы сервера, в историю браузера и в заголовок
    Referer при переходе на любой внешний ресурс; всё это места, куда ключ от
    чужих документов попадать не должен.

    Ссылка из письма от этого НЕ ломается: она остаётся входным билетом для
    двух ручек обмена — ``/otp`` (код получателю) и ``/session`` (обмен на
    короткоживущий сеанс). Дальше портал ходит заголовком
    ``X-Portal-Session``, и токен в адресе больше не фигурирует.

    Срез-213: до этого адрес принимался на КАЖДОЙ ручке портала, то есть
    обменять ссылку на сеанс было можно, но не обязательно, — а мера, которую
    можно обойти, мерой не является.
    """

    # SEC-68 (разд. 68.2): внешний контур ограничивается жёстче внутреннего, и
    # проверка идёт ДО обращения к базе — перебор не должен стоить нам запроса
    # в БД на каждую попытку.
    enforce_portal_traffic(request)
    assert_not_locked_out(request)

    # Сеансовый токен (обмен по разд. 68.1) — приоритетный путь: не тратит
    # использований ссылки, принимается ТОЛЬКО заголовком (в query ему не место).
    if x_portal_session:
        try:
            claims = verify_token(x_portal_session, expected_type="portal_session")
        except HTTPException:
            # Подделка сеансового токена — та же попытка перебора.
            record_auth_failure(request)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid portal session")
        with allow_cross_tenant_read(
            session,
            reason="сеанс клиентского портала: арендатор известен из самой ссылки",
        ):
            record = await session.get(ClientPortalToken, str(claims.get("sub") or ""))
        if record is None:
            record_auth_failure(request)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid portal session")
        # Отзыв ссылки обязан убивать и сеанс — перепроверяем на каждом запросе.
        _ensure_link_alive(record)
        _bind_to_link(session, record)
        return _auth_from_record(record)

    if not x_portal_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Portal token is required in the X-Portal-Token header "
            "(exchange the emailed link for a session at POST /portal/session)",
        )
    record = await _resolve_link_token(request, session, x_portal_token, burn_use=True)
    _bind_to_link(session, record)
    return _auth_from_record(record)


async def _get_run_for_tenant(
    session: AsyncSession, *, run_id: str, tenant_id: str
) -> ClientPackageRun:
    run = await session.get(ClientPackageRun, run_id)
    if run is None or str(run.tenant_id) != str(tenant_id) or run.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


@presets_router.get("")
async def list_presets(
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffReadAccess,
):
    rows = (
        (
            await session.execute(
                select(ClientPackagePreset).where(
                    ClientPackagePreset.tenant_id == tenant.id,
                    ClientPackagePreset.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return rows


@presets_router.post("", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "package_preset")
async def create_preset(
    payload: PackagePresetCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffWriteAccess,
):
    record = ClientPackagePreset(tenant_id=tenant.id, **payload.model_dump())
    session.add(record)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return record


@presets_router.patch("/{preset_id}")
@audit_operation("update", "package_preset")
async def patch_preset(
    preset_id: str,
    payload: PackagePresetPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffWriteAccess,
):
    record = await session.get(ClientPackagePreset, preset_id)
    if record is None or record.tenant_id != tenant.id or record.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(record, key, value)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return record


async def _preset_for_publish(
    session: AsyncSession, tenant: Tenant, code: str
) -> ClientPackagePreset:
    """Портальный пресет для кода сценария; создаётся из каталога при первой выдаче.

    Модель прогона требует пресет, а рабочая генерация (`/packs/generate`) знает
    только встроенные коды каталога. Заставлять аутсорсера заводить руками ещё
    один объект ради того, чтобы отдать клиенту уже готовый архив, — лишний шаг
    ровно там, где ТЗ обещает «не более 4 шагов».

    Создание идемпотентно по коду и берёт название из каталога: это проекция
    сценария на кабинет, а не новые данные из воздуха. Код, которого нет ни в
    портальных пресетах, ни в каталоге, — ошибка, а не повод придумать пресет.
    """

    existing = (
        await session.execute(
            select(ClientPackagePreset).where(
                ClientPackagePreset.code == code,
                ClientPackagePreset.tenant_id == tenant.id,
                ClientPackagePreset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    definition = PACK_DEFINITIONS_BY_CODE.get(code)
    if definition is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Сценарий '{code}' не найден ни среди пресетов кабинета, ни в каталоге комплектов",
        )
    preset = ClientPackagePreset(
        tenant_id=tenant.id,
        code=definition.code,
        name=definition.name,
        steps_json={"steps": [{"code": "generate"}, {"code": "publish_portal"}]},
        required_inputs_json=[],
    )
    session.add(preset)
    await session.flush()
    return preset


@internal_router.post("/publish", status_code=status.HTTP_201_CREATED)
@audit_operation("publish", "package_run")
async def publish_package(
    payload: PackagePublishRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffWriteAccess,
):
    """Отдать клиенту в кабинет УЖЕ сгенерированный комплект (разд. 50.2 шаг 4).

    ТЗ: «результат можно скачать, отправить в ЭДО или в кабинет клиента».
    Скачивание работало, кабинет — нет: контур генерации и контур кабинета
    существовали порознь, а кабинет клал в хранилище строку вместо архива.

    Здесь связываются оба: на вход идёт ключ НАСТОЯЩЕГО архива, полученного
    генерацией, и он же уходит клиенту.
    """

    key = payload.zip_storage_key.strip()
    tenant_prefix = f"{tenant_prefix_path(tenant.slug)}/"
    if not key.startswith(tenant_prefix):
        # Без этой проверки арендатор опубликовал бы в своём кабинете ЧУЖОЙ
        # архив, зная его ключ. Проверка та же, что на скачивании.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Архив не принадлежит этому арендатору")

    storage = FileStorageService.default()
    try:
        exists = storage.has(key)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректный ключ архива") from exc
    if not exists:
        # Иначе в кабинете появилась бы запись «комплект выдан» со ссылкой в
        # никуда — то же враньё, только другими словами.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Архив не найден в хранилище")

    preset = await _preset_for_publish(session, tenant, payload.preset_code.strip())
    now = _utcnow()
    run = ClientPackageRun(
        tenant_id=tenant.id,
        preset_id=preset.id,
        client_company_id=payload.client_company_id,
        status=PackageRunStatus.SUCCESS,
        started_at=now,
        finished_at=now,
        output_zip_s3_key=key,
        qc_report_json={
            "scenario": preset.code,
            "artifacts": [key],
            "status_flow": ["running", "generated", "published"],
            "steps": [{"code": "generate"}, {"code": "publish_portal"}],
        },
    )
    session.add(run)
    await session.flush()
    session.add_all(
        [
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.generated",
                payload_json={"artifacts": [key], "source": "packs.generate"},
            ),
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.published",
                payload_json={"status": "published", "zip_storage_key": key},
            ),
        ]
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(run)
    return run


@internal_router.post("/runs", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "package_run")
async def create_run(
    payload: PackageRunCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffWriteAccess,
):
    preset = (
        await session.execute(
            select(ClientPackagePreset).where(
                ClientPackagePreset.code == payload.preset_code,
                ClientPackagePreset.deleted_at.is_(None),
                ClientPackagePreset.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if preset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    pipeline = _resolve_pipeline(preset)
    run = ClientPackageRun(
        tenant_id=tenant.id,
        preset_id=preset.id,
        client_company_id=payload.client_company_id,
        status=PackageRunStatus.RUNNING,
        started_at=_utcnow(),
        qc_report_json={
            "status_flow": list(
                pipeline.get("status_flow") or ["running", "generated", "published"]
            ),
            "steps": pipeline["steps"],
        },
    )
    session.add(run)
    await session.flush()
    zip_key, pdf_key, manifest_key, qc_report = _write_package_artifacts(
        run=run, preset=preset, pipeline=pipeline
    )
    run.output_zip_s3_key = zip_key
    run.output_pdf_s3_key = pdf_key
    run.qc_report_json = qc_report
    for req in pipeline["required_inputs"]:
        session.add(
            PackageRequirement(
                tenant_id=tenant.id,
                package_run_id=run.id,
                key=req.get("key", secrets.token_hex(4)),
                title=req.get("title", "Required data"),
                type=PackageRequirementType(req.get("type", "file")),
                status=PackageRequirementStatus.MISSING,
                payload_json=req,
            )
        )
        session.add(
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.requirement_registered",
                payload_json={
                    "key": req.get("key"),
                    "type": req.get("type"),
                    "required": req.get("required", True),
                },
            )
        )
    session.add_all(
        [
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.started",
                payload_json={
                    "status": "running",
                    "scenario": pipeline["scenario"],
                    "pipeline_fingerprint": pipeline.get("pipeline_fingerprint"),
                },
            ),
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.generated",
                payload_json={
                    "manifest_key": manifest_key,
                    "artifacts": qc_report["artifacts"],
                    "steps": pipeline["steps"],
                },
            ),
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.status_changed",
                payload_json={"from": "running", "to": "published"},
            ),
            PackageEvent(
                tenant_id=tenant.id,
                package_run_id=run.id,
                type="package_run.published",
                payload_json={
                    "portal_visible": True,
                    "status": "published",
                    "output_artifacts": pipeline["output_artifacts"],
                },
            ),
        ]
    )
    run.status = PackageRunStatus.SUCCESS
    run.finished_at = _utcnow()
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(run)
    return _serialize_package_run(run)


@internal_router.get("/runs")
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffReadAccess,
):
    rows = (
        (
            await session.execute(
                select(ClientPackageRun).where(
                    ClientPackageRun.tenant_id == tenant.id,
                    ClientPackageRun.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_package_run(run) for run in rows]


@internal_router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    _: AccessContext = StaffReadAccess,
):
    return _serialize_package_run(
        await _get_run_for_tenant(session, run_id=run_id, tenant_id=str(tenant.id))
    )


@internal_router.post("/runs/{run_id}/portal-link", response_model=PortalLinkResponse)
@audit_operation("issue_link", "portal_token")
async def create_portal_link(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant: Annotated[Tenant, Depends(get_tenant_record)],
    max_uses: Annotated[
        int | None,
        Query(ge=1, description="Лимит использований ссылки; не задан — без ограничения"),
    ] = None,
    otp_email: Annotated[
        str | None,
        Query(
            max_length=320,
            description=(
                "Привязать ссылку к получателю: войти можно будет только с кодом, "
                "пришедшим на этот адрес. Не задан — привязки нет"
            ),
        ),
    ] = None,
    otp_phone: Annotated[
        str | None,
        Query(
            max_length=32,
            description=(
                "Привязать ссылку к получателю по SMS: войти можно будет только с кодом, "
                "пришедшим на этот номер. Указывается вместо адреса, не вместе с ним"
            ),
        ),
    ] = None,
    _: AccessContext = StaffWriteAccess,
):
    run = await _get_run_for_tenant(session, run_id=run_id, tenant_id=str(tenant.id))
    email_recipient = (otp_email or "").strip()
    phone_recipient = (otp_phone or "").strip()

    # Срез-186: два канала, но получатель ОДИН. Указать оба значило бы задать
    # противоречие — на какой из них слать код, ответа нет.
    if email_recipient and phone_recipient:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Укажите либо адрес, либо номер телефона получателя, но не оба",
        )

    normalized_phone: str | None = None
    if phone_recipient:
        normalized_phone = sms_gateway.normalize_phone(phone_recipient)
        if normalized_phone is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Номер телефона выглядит неверным",
            )

    recipient = email_recipient or normalized_phone or ""
    if recipient:
        if email_recipient and "@" not in email_recipient:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Адрес получателя выглядит неверным",
            )
        # Проверяем ЗДЕСЬ, а не при входе: выдать ссылку с привязкой там, где
        # сообщение уйти не может, значит запереть клиента снаружи — и узнает он
        # об этом позже специалиста, уже получив ссылку.
        channel = otp_delivery.channel_for(recipient)
        if not otp_delivery.channel_ready(channel):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                (
                    "Привязка по SMS требует настроенного поставщика: без него код не дойдёт"
                    if channel == otp_delivery.SMS
                    else "Привязка к получателю требует настроенной почты: без неё код не дойдёт"
                ),
            )
    # 24 байта = 192 бита энтропии (разд. 68.1 требует >= 128).
    plain = secrets.token_urlsafe(24)
    settings = get_settings()
    # Потолок TTL не даёт выдать «вечную» ссылку даже опечаткой в конфиге.
    ttl_hours = max(1, min(settings.portal_token_ttl_hours, settings.portal_token_max_ttl_hours))
    expires_at = _utcnow() + timedelta(hours=ttl_hours)
    session.add(
        ClientPortalToken(
            tenant_id=tenant.id,
            token_hash=_hash_token(plain),
            package_run_id=run.id,
            expires_at=expires_at,
            max_uses=max_uses,
            otp_email=email_recipient or None,
            otp_phone=normalized_phone,
            scope_json={
                "package_run_ids": [run.id],
                "download": True,
                "upload": True,
                "tickets": True,
            },
        )
    )
    await session.commit()
    return PortalLinkResponse(portal_url=f"/portal?token={plain}", expires_at=expires_at)


def _otp_alive(record: ClientPortalToken) -> bool:
    """Код есть и ещё жив."""

    if not record.otp_code_hash or record.otp_expires_at is None:
        return False
    return _as_utc(record.otp_expires_at) > _utcnow()


def _clear_otp(record: ClientPortalToken) -> None:
    record.otp_code_hash = None
    record.otp_expires_at = None
    record.otp_attempts = 0


@router.post("/otp", response_model=PortalOtpResponse)
async def request_portal_otp(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_portal_token: Annotated[str | None, Header(alias="X-Portal-Token")] = None,
    token: Annotated[str | None, Query()] = None,
) -> PortalOtpResponse:
    """SEC-68 (разд. 68.1): выслать одноразовый код на адрес получателя ссылки.

    Ссылка сама по себе больше не пускает: пересланная копия открывается, но
    код уходит ТОМУ, кому ссылку выдавали. Использований ссылки запрос не
    тратит — иначе одноразовая ссылка сгорала бы на попытке войти.

    Ответ одинаков и когда код отправлен, и когда привязки у ссылки нет:
    разный ответ позволял бы перебирать, какие ссылки к кому привязаны.
    """

    enforce_portal_traffic(request)
    assert_not_locked_out(request)
    raw = x_portal_token or token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portal token is required")
    record = await _resolve_link_token(request, session, raw, burn_use=False)

    settings = get_settings()
    ttl = max(1, int(settings.portal_otp_ttl_minutes))
    otp_recipient = record.otp_email or record.otp_phone
    if otp_recipient:
        # Каждый запрос выдаёт НОВЫЙ код и обнуляет счётчик попыток: иначе
        # исчерпав попытки, легитимный получатель остался бы без входа.
        code = f"{secrets.randbelow(1_000_000):06d}"
        record.otp_code_hash = _hash_token(code)
        record.otp_expires_at = _utcnow() + timedelta(minutes=ttl)
        record.otp_attempts = 0
        await session.commit()
        outcome = await send_otp_code(
            tenant_id=str(record.tenant_id),
            recipient=otp_recipient,
            code=code,
            ttl_minutes=ttl,
        )
        if not outcome.delivered:
            # Код уже записан, но не дошёл — гасим его, чтобы «отправлено» не
            # означало «где-то лежит действующий код».
            _clear_otp(record)
            await session.commit()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, outcome.reason)

    return PortalOtpResponse(
        message="Если ссылка привязана к получателю, код отправлен на его адрес",
        expires_in_minutes=ttl,
    )


@router.post("/session", response_model=PortalSessionResponse)
async def create_portal_session(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_portal_token: Annotated[str | None, Header(alias="X-Portal-Token")] = None,
    token: Annotated[str | None, Query()] = None,
    code: Annotated[
        str | None,
        Query(max_length=16, description="Одноразовый код, если ссылка привязана к получателю"),
    ] = None,
) -> PortalSessionResponse:
    """SEC-68 (разд. 68.1): обменять ссылочный токен на короткоживущий сеансовый.

    Ссылка из письма остаётся входным билетом (разосланные ссылки не ломаются),
    но после обмена токен из query больше нигде не фигурирует: сеанс ходит
    ТОЛЬКО заголовком ``X-Portal-Session`` и не тратит использований ссылки —
    одноразовая ссылка (max_uses=1) переживает UI из многих запросов.
    """

    enforce_portal_traffic(request)
    assert_not_locked_out(request)
    raw = x_portal_token or token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portal token is required")
    record = await _resolve_link_token(request, session, raw, burn_use=True)

    settings = get_settings()
    if record.otp_email:
        # SEC-68 (разд. 68.1): ссылка привязана к получателю — одной ссылки мало.
        if not code:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Ссылка привязана к получателю: запросите код и введите его",
            )
        if not _otp_alive(record):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Код не запрашивался или истёк: запросите новый",
            )
        if (record.otp_attempts or 0) >= max(1, int(settings.portal_otp_max_attempts)):
            # Гасим код целиком: следующая попытка должна начинаться с нового
            # кода, иначе счётчик обходится повторными запросами сеанса.
            _clear_otp(record)
            await session.commit()
            record_auth_failure(request)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Слишком много неверных попыток: запросите новый код",
            )
        if not hmac.compare_digest(_hash_token(code.strip()), record.otp_code_hash or ""):
            record.otp_attempts = (record.otp_attempts or 0) + 1
            await session.commit()
            record_auth_failure(request)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код")
        # Код одноразовый: вошли — погасили.
        _clear_otp(record)

    link_expires = _as_utc(record.expires_at)
    session_expires = min(
        _utcnow() + timedelta(minutes=settings.portal_session_ttl_minutes), link_expires
    )
    session_token = issue_portal_session_token(
        token_id=str(record.id),
        tenant=str(record.tenant_id),
        expires_at=session_expires,
    )
    return PortalSessionResponse(session_token=session_token, expires_at=session_expires)


@router.get("/packages")
async def portal_packages(
    auth: Annotated[PortalAuth, Depends(_portal_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    rows = (
        (
            await session.execute(
                select(ClientPackageRun).where(
                    ClientPackageRun.id.in_(auth.package_run_ids),
                    ClientPackageRun.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_package_run(run) for run in rows]


@router.get("/packages/{run_id}")
async def portal_package_details(
    run_id: str,
    auth: Annotated[PortalAuth, Depends(_portal_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if run_id not in auth.package_run_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    run = await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    reqs = (
        (
            await session.execute(
                select(PackageRequirement).where(PackageRequirement.package_run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    events = (
        (
            await session.execute(
                select(PackageEvent)
                .where(PackageEvent.package_run_id == run_id)
                .order_by(PackageEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    tickets = (
        (
            await session.execute(
                select(ClientRequestTicket)
                .where(ClientRequestTicket.package_run_id == run_id)
                .order_by(ClientRequestTicket.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    storage = FileStorageService.default()
    manifest_key = _manifest_key_from_run(run)
    files = [
        item
        for item in [
            _artifact_entry(storage, run.output_zip_s3_key, kind="zip"),
            _artifact_entry(storage, run.output_pdf_s3_key, kind="pdf"),
            _artifact_entry(storage, manifest_key, kind="manifest"),
        ]
        if item
    ]
    status_flow = list(
        (run.qc_report_json or {}).get("status_flow")
        or [run.status.value if hasattr(run.status, "value") else str(run.status)]
    )
    return {
        "run": _serialize_package_run(run),
        "requirements": jsonable_encoder(reqs),
        "events": jsonable_encoder(events),
        "tickets": jsonable_encoder(tickets),
        "files": files,
        "history": {
            "status_flow": status_flow,
            "events_count": len(events),
            "tickets_count": len(tickets),
            "requirements_total": len(reqs),
            "requirements_missing": len(
                [
                    item
                    for item in reqs
                    if getattr(item, "status", None) == PackageRequirementStatus.MISSING
                ]
            ),
        },
    }


@router.get("/packages/{run_id}/files", response_model=PortalFilesResponse)
async def portal_package_files(
    run_id: str,
    auth: Annotated[PortalAuth, Depends(_portal_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if run_id not in auth.package_run_ids or not auth.can_download:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    run = await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    storage = FileStorageService.default()
    files = [
        item
        for item in [
            _artifact_entry(storage, run.output_zip_s3_key, kind="zip"),
            _artifact_entry(storage, run.output_pdf_s3_key, kind="pdf"),
        ]
        if item
    ]
    manifest_key = _manifest_key_from_run(run)
    manifest = _artifact_entry(storage, manifest_key, kind="manifest") if manifest_key else None
    if manifest:
        files.append(manifest)
    return {"files": files}


@router.post("/packages/{run_id}/tickets", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "client_ticket")
async def portal_create_ticket(
    run_id: str,
    payload: PackageTicketCreate,
    auth: Annotated[PortalAuth, Depends(_portal_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if run_id not in auth.package_run_ids or not auth.can_tickets:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    ticket = ClientRequestTicket(
        tenant_id=auth.tenant_id,
        package_run_id=run_id,
        title=payload.title,
        message=payload.message,
        status=ClientRequestTicketStatus.OPEN,
        created_by="portal-token",
    )
    session.add(ticket)
    session.add(
        PackageEvent(
            tenant_id=auth.tenant_id,
            package_run_id=run_id,
            type="ticket.created",
            payload_json={"title": payload.title},
        )
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(ticket)
    return ticket


@router.get("/packages/{run_id}/tickets")
async def portal_list_tickets(
    run_id: str,
    auth: Annotated[PortalAuth, Depends(_portal_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if run_id not in auth.package_run_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    return (
        (
            await session.execute(
                select(ClientRequestTicket).where(ClientRequestTicket.package_run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
