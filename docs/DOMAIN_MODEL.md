# Domain model reference

Документ описывает фактическое состояние ORM (SQLAlchemy) и миграций Alembic.
Все ссылки и ограничения собраны из `backend/app/models/*` и `backend/app/migrations/versions/*`.

## Общие договорённости
- **TenantBaseModel** — каждая tenant-aware таблица содержит `id` (UUIDv4),
  `tenant_id` (FK → `tenant.id`), `created_at`, `updated_at`, `version`, а также
  soft-delete поле `deleted_at`, если модель миксует `SoftDeleteMixin`.
- **SharedModel** — глобальные справочники без `tenant_id`, но с теми же
  таймстемпами и версионированием.
- Все JSON-поля используют `jsonb` в PostgreSQL и обычный `json` в SQLite.

## Tenancy & access control

### Tenant (`tenant`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| `id` | UUID | NO | PK, UUIDv4. |
| `slug` | varchar(64) | NO | Уникальный идентификатор аренды (`uq_tenant_slug`). |
| `name` | varchar(255) | NO | Публичное имя. |
| `contact_email` | varchar(255) | NO | Техконтакт. |
| `is_active` | bool | NO, default `true` | Флаг активности. |
| `settings` | json | NO, default `{}` | Настройки аренды. |
| `created_at`/`updated_at`/`version` | timestamptz/int | NO | Аудит. |

**Связи:** родитель для всех моделей с `tenant_id`.

### User (`user`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя TenantBaseModel + `deleted_at` | — | — | |
| `email` | varchar(320) | NO | Индекс `ix_user_email` вместе с `tenant_id` (уникальность). |
| `full_name` | varchar(255) | NO | — |
| `role` | enum — см. ниже | NO | Роль доступа. Полный список — `RoleEnum` в `backend/app/models/models.py`. |
| `hashed_password` | varchar(255) | NO | Хэш. |
| `is_active` | bool | NO, default `true` | — |
| `last_login_at` | timestamptz | YES | Последний логин. |
| `company_id` | UUID FK→company | YES | Работодатель (SET NULL). |

**Роли (`RoleEnum`):**

| Значение | Описание |
| --- | --- |
| `owner` | Владелец арендатора |
| `admin` | Администратор |
| `ot_pb_lead` | Руководитель ОТиПБ |
| `ot_head` | Начальник отдела ОТ |
| `ot_specialist` | Специалист ОТ |
| `pb_engineer` | Инженер ПБ |
| `ecologist` | Эколог |
| `hr` | HR |
| `lawyer` | Юрист |
| `accountant` | Бухгалтер |
| `line_manager` | Линейный руководитель |
| `manager` | Менеджер |
| `executor` | Исполнитель |
| `worker` | Рабочий / сотрудник |
| `employee` | Сотрудник (синоним `worker`) |
| `clerk` | Делопроизводитель |
| `teacher` | Преподаватель |
| `student` | Обучающийся |
| `contractor_inspector` | Проверяющий-подрядчик |
| `inspector_contractor` | Псевдоним `contractor_inspector` |
| `auditor_ro` | Аудитор (только чтение) |
| `client_admin` | Администратор клиентского портала |
| `client_user` | Пользователь клиентского портала |
| `client` | Внешний клиент |

**Связи:** `User` → `Company` (многие-к-одному), создаёт `Document`, `DocumentGenerationJob`.

### ApiKey (`api_key`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя TenantBaseModel | — | — | |
| `name` | varchar(128) | NO | Уникален в рамках аренды (`uq_api_key_tenant_name`). |
| `key_prefix` | varchar(32) | NO | Уникальный префикс. |
| `key_hash` | varchar(128) | NO | Argon/Bcrypt hash. |
| `scopes` | varchar(255) | NO, default `"api:read"` | Пробел-разделённый список. |
| `is_active` | bool | NO, default `true` | Флаг. |
| `last_used_at` | timestamptz | YES | Последнее обращение. |

### Feature (`feature`) и FeatureEnablement (`featureenablement`)
- `Feature`: shared-таблица с `code` (уникален) и `title`.
- `FeatureEnablement`: TenantBaseModel с полями `feature_id` (CASCADE),
  `on` (bool), `config_json` (json). Уникальность `tenant_id + feature_id`.

### IdempotencyKey (`idempotency_keys`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя TenantBaseModel | — | — | |
| `endpoint` | varchar(255) | NO | Имя действия. |
| `key` | varchar(128) | NO | Ключ клиента. |
| `status` | enum(`pending`,`succeeded`,`failed`) | NO | Текущее состояние. |
| `request_hash` | varchar(128) | YES | Контроль тела запроса. |
| `path` | varchar(512) | YES | HTTP path. |
| `method` | varchar(16) | YES | HTTP метод. |
| `status_code` | int | YES | Ответ сервера. |
| `response_body` | text | YES | Тело ответа. |
| `result_json` | json | YES | Структурированный результат. |

**Ограничения:** `tenant_id+endpoint+key` уникальны, индекс для быстрого поиска.

## Files & storage

### File (`file`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя TenantBaseModel | — | — | |
| `storage_key` | varchar(512) | NO | Уникален в рамках аренды (`ix_file_storage_key`). |
| `bucket` | varchar(255) | NO | Имя бакета. |
| `sha256` | char(64) | NO | `ix_file_sha256`. |
| `size` | bigint | NO | Размер. |
| `mime` | varchar(128) | NO | MIME-тип. |
| `meta_json` | json | NO, default `{}` | Произвольные метаданные. |
| `is_quarantined` | bool | NO, default `true` | Разрешение скачивания. |
| `scan_status` | enum(`pending`,`in_progress`,`clean`,`infected`,`error`) | NO | AV состояние. |
| `clamav_signature` | varchar(255) | YES | Сигнатура угрозы. |
| `clamav_scanned_at` | timestamptz | YES | Время скана. |

**Связи:** логотипы `Company`, файлы `Document`, `DocumentVersion`, `DocumentGenerationJob` выходы.

## Companies & people

### Company (`company`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `name` | varchar(255) | NO | Уникален в паре с `tenant_id`. |
| `inn` (`tax_id`) / `kpp` / `ogrn` | varchar(32) | YES | Реквизиты. |
| `activity_type` | varchar(128) | YES | Основной вид деятельности. |
| `okved_codes` | json | NO, default `[]` | Коды ОКВЭД. |
| `legal_address` (`address`) / `actual_address` | varchar(255) | YES | Адреса. |
| `director` | varchar(255) | YES | ФИО директора. |
| Банковские поля (`bank_name`, `bank_bik`, `bank_account`) | varchar | YES | — |
| `phone_numbers` | json | NO, default `[]` | Телефоны. |
| `contact_person` / `contact_phone` / `contact_email` | varchar | YES | Ответственный за ОТ/ПБ. |
| `email` | varchar(320) | YES | Email. |
| `logo_file_id` / `stamp_file_id` | UUID FK→file | YES | Медиа. |
| `work_types` / `hazardous_factors` | json | NO, default `[]` | Вид деятельности и факторы риска. |
| `is_hazardous_production_facility` | bool | NO, default `false` | Признак ОПО. |
| `has_dangerous_objects` | bool | NO, default `false` | Есть опасные объекты/оборудование. |

### Position (`position`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `company_id` | UUID FK→company | NO | Работодатель. |
| `name` | varchar(255) | NO | Уникальна вместе с `company_id`. |
| `description` | varchar(255) | YES | Комментарий. |
| `safety_category` | varchar(64) | YES | Категория по ОТ/ПБ. |
| `working_conditions_class` | varchar(32) | YES | Класс условий труда. |
| `hazardous_factors` | json | NO, default `[]` | Вредные факторы для должности. |
| `hazards` | m2m RiskHazard | — | Через `position_hazard` с опциональной привязкой к файлу. |

### Person (`person`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `company_id` | UUID FK→company | NO | Работодатель. |
| `position_id` | UUID FK→position | YES | Должность. |
| `workplace_id` | UUID FK→workplace | YES | Конкретное рабочее место. |
| `first_name` / `last_name` | varchar(100) | NO | ФИО. |
| `middle_name` | varchar(100) | YES | Отчество. |
| `birth_date` | date | YES | Дата рождения. |
| `email` | varchar(320) | YES | Контакт. |
| `phone` | varchar(32) | YES | Телефон. |
| `personnel_number` | varchar(32) | YES | Уникален в рамках аренды. |
| `hired_at` | date | YES | Дата приема. |
| `qualifications` | json | NO, default `[]` | Учёт обучения. |
| `snils` | varchar(32) | YES | СНИЛС. |
| `passport` | varchar(64) | YES | Паспортные данные. |
| `current_ppe` | json | NO, default `[]` | Текущие СИЗ. |
| `working_conditions_class` | varchar(32) | YES | Класс условий труда. |
| `hazardous_factors` | json | NO, default `[]` | Вредные факторы по человеку. |
| `employment_status` | enum(`active`,`on_leave`,`suspended`,`terminated`) | NO | Трудовой статус. |

### Site (`site`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `company_id` | UUID FK→company | NO | Владелец. |
| `name` | varchar(255) | NO | Название площадки. |
| `address` | varchar(255) | YES | Адрес. |
| `geo_json` | json | YES | Границы/координаты. |
| `hazard_class` | varchar(32) | YES | Класс опасности. |
| `site_type` | varchar(64) | YES | Тип площадки/объекта. |
| `contact_name` / `contact_phone` / `contact_email` | varchar | YES | Ответственный на площадке. |
| `is_hazardous_production_facility` | bool | NO, default `false` | ОПО-флаг. |
| `opo_register_number` | varchar(64) | YES | № в реестре ОПО. |

### Workplace (`workplace`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `company_id` | UUID FK→company | NO | Владелец. |
| `site_id` | UUID FK→site | YES | Привязка к площадке. |
| `name` | varchar(255) | NO | Уникально в рамках компании. |
| `description` | text | YES | Характеристика рабочего места. |
| `location` | varchar(255) | YES | Локация/цех/координаты. |
| `working_conditions_class` | varchar(32) | YES | Класс условий труда. |
| `hazards` | m2m RiskHazard | — | Через `workplace_hazard`, можно хранить файл-доказательство. |

### MedicalExam (`medical_exam`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `person_id` | UUID FK→person | NO | Работник. |
| `exam_type` | varchar(128) | NO | Вид осмотра. |
| `exam_date` | date | NO | Дата прохождения. |
| `conclusion` | varchar(255) | YES | Итог. |
| `valid_until` | date | NO | Срок действия. |

### TrainingCourse (`training_course`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | UUID/время/версия/soft-delete. |
| `title` | varchar(255) | NO | Уникален в рамках аренды. |
| `code` | varchar(64) | YES | Код курса. |
| `description` | text | YES | Описание содержания. |
| `duration_hours` | int | YES | Продолжительность. |
| `valid_period_days` | int | YES | Срок действия удостоверения по умолчанию. |
| `metadata_json` | json | NO, default `{}` | Доп. метаданные. |

### TrainingPlan (`training_plan`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `company_id` | UUID FK→company | NO | Компетенция привязана к компании. |
| `position_id` | UUID FK→position | YES | План для должности. |
| `person_id` | UUID FK→person | YES | Индивидуальный план. |
| `course_id` | UUID FK→training_course | NO | Курс из каталога. |
| `assigned_at` | timestamptz | NO | Дата назначения. |
| `due_date` | date | YES | Крайний срок прохождения. |
| `is_mandatory` | bool | NO, default `true` | Обязательность. |

### TrainingSession (`training_session`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя | — | — | |
| `person_id` | UUID FK→person | NO | Участник обучения. |
| `course_id` | UUID FK→training_course | NO | Проходимый курс. |
| `plan_id` | UUID FK→training_plan | YES | План, по которому идёт обучение. |
| `status` | enum(`scheduled`,`in_progress`,`completed`,`failed`) | NO | Статус попытки. |
| `started_at` / `completed_at` | timestamptz | YES | Фактическое время. |
| `score` | int | YES | Результат теста. |
| `notes` | text | YES | Комментарии. |

### TrainingCertificate (`training_certificate`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `person_id` | UUID FK→person | NO | Владелец удостоверения. |
| `course_id` | UUID FK→training_course | NO | Курс, по которому выдано удостоверение. |
| `session_id` | UUID FK→training_session | YES | Попытка обучения. |
| `plan_id` | UUID FK→training_plan | YES | План, по которому выдано удостоверение. |
| `file_id` | UUID FK→file | YES | Сканы/скреплённые файлы. |
| `number` | varchar(64) | YES | Номер удостоверения. |
| `issued_at` | date | NO, default `today` | Дата выдачи. |
| `valid_until` | date | YES | Срок действия. |

### Training (`training`)
- Упрощённый журнал обучения с полями `person_id`, `course_name`, `status` (`draft`/`scheduled`/`completed`), `scheduled_at`, `completed_at`, `expires_at`. Сохранён для обратной совместимости.

### Permit (`permit`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя | — | — | UUID/время/версия. |
| `person_id` | UUID FK→person | NO | Владелец удостоверения. |
| `position_id` | UUID FK→position | YES | Должность, для которой выдан допуск. |
| `permit_type` | varchar(128) | NO | Вид допуска/удостоверения. |
| `issued_at` | date | NO, default `today` | Дата выдачи. |
| `valid_until` | date | YES | Окончание срока действия. |
| `status` | enum(`active`,`expired`,`revoked`) | NO | Текущий статус. |

### PPENorm (`ppenorm`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| `position_id` | UUID FK→position | NO | Должность. |
| `hazard_id` | UUID FK→risk_hazards | NO | Опасность. |
| `item_name` | varchar(255) | NO | СИЗ. |
| `quantity` | int | NO, default `1` | Количество. |
| `interval_days` | int | NO, default `365` | Интервал замены. |

### PPEIssue (`ppeissue`)
| `person_id`, `item_name`, `issued_at`, `expires_at`, `returned_at`, `status` (`issued`/`returned`/`lost`).

### WarehousePPE (`warehouseppe`)
| Справочник складских остатков: `item_name`, `quantity`, `location`.

## Templates & packs

### Template (`template`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя TenantBaseModel | — | — | |
| `name` | varchar(255) | NO | Уникален в паре с `tenant_id`. |
| `description` | varchar(1024) | YES | Описание. |
| `metadata_json` | json | NO, default `{}` | Конфигурация шаблона. |
| `storage_key` | varchar(512) | YES | Ключ для хранения шаблона. |

### TemplateVersion (`templateversion`)
| `template_id` (FK), `version` (int, уникален per template), `checksum` (bytes), `status` (`draft`/`active`/`archived`), `payload_key` (varchar(512)).

### PackageProfile (`packageprofile`)
| `name`, `description`, `config` (json). Имя уникально в рамках аренды.

### PackagePreset (`packagepreset`)
| `profile_id`, `name`, `payload` (json). Пресеты принадлежат профилю.

### DocumentPack (`document_pack`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `code` | varchar(128) | NO | Уникален per tenant. |
| `name` | varchar(255) | NO | Название. |
| `description` | text | YES | Описание. |
| `is_active` | bool | NO, default `true` | Активность. |
| `module` | enum(`ot`,`fire_safety`,`health`,`custom`) | NO | Область применения. |
| `scenario_type` | enum(`document_batch`,`report`,`workflow`) | NO | Сценарий. |

### DocumentPackItem (`document_pack_item`)
| `pack_id`, `template_id`, `template_version_id`, `order`, `required`, `condition` (json). Каскадное удаление при удалении пакета.

## Documents & generation

### DocumentGenerationJob (`documentgenerationjob`) — модели больше нет
Класс удалён срезом-139 (до этого срез-135 удалил его, а срез-138 вернул — модель
читали ручки документов; срез-139 сначала снял чтения, потом модель). Таблица в
базе осталась и ждёт решения владельца о сносе — см. `docs/CLEANUP_CANDIDATES.md`.
Живая генерация документов ведётся через `DocumentJob` (`models/job_engine.py`) и
`PipelineRun` (ниже): строка `Document` создаётся только по завершении прогона.

### Document (`document`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя + `deleted_at` | — | — | |
| `company_id` | UUID FK→company | NO | Собственник. |
| `person_id` | UUID FK→person | YES | Работник. |
| `site_id` | UUID FK→site | YES | Место. |
| `template_id` | UUID FK→template | NO | Базовый шаблон. |
| `template_version_id` | UUID FK→templateversion | YES | Зафиксированная версия. |
| `status` | enum(`draft`,`review`,`signed`,`archived`) | NO | Жизненный цикл. |
| `storage_key` | text | YES | Наследие хранения. |
| `file_id` / `signed_file_id` | UUID FK→file | YES | Файлы. |
| `content_sha256` | char(64) | YES | Контрольная сумма. |
| `created_by` | UUID FK→user | NO | Автор. |
| `created_at` | timestamptz | NO | Время создания. |
| `job_id` | varchar(36) | YES | Наследие: всегда NULL; связи в ORM нет с среза-139, столбец оставлен ради контракта `DocumentRead.job_id` (внешний ключ в базе уйдёт вместе с таблицей `documentgenerationjob`). |

### DocumentVersion (`documentversion`)
| `document_id`, `template_version` (text), `template_version_id`, `data_json`, `file_key`, `file_id`, `version_number`, `status` (`draft`,`locked`,`published`,`archived`), `created_at`.

### PipelineRun (`pipeline_runs`)
| Поле | Тип | Null | Примечание |
| --- | --- | --- | --- |
| Техполя TenantBaseModel | — | — | |
| `template_id` / `template_version_id` | UUID FK | NO | Что выполняем. |
| `status` | enum(`queued`,`running`,`done`,`error`) | NO | Статус пайплайна. |
| `context` | json | NO, default `{}` | Входные данные. |
| `outputs` | json | YES | Результаты. |
| `result_metadata` | json | NO, default `{}` | Техническая информация. |
| `docx_storage_key` / `pdf_storage_key` / `result_s3_key` | varchar(512) | YES | Путь к результатам. |
| `error` | varchar(255) | YES | Причина неуспеха. |
| `idempotency_key` | varchar(128) | NO | Индекс уникальности per tenant. |
| `started_at` / `finished_at` | timestamptz | YES | Таймстемпы. |

## Compliance & legal content

### NPA (`npa`)
| `code`, `title`, `edition_date`, `status` (`active`/`obsolete`). Код уникален per tenant.

### NPABinding (`npa_binding`)
| `npa_id`, `template_version_id` (nullable), `entity_type` (`template_version`,`document`,`pack`), `entity_id`, `context` (json), `ref` (varchar).

### NpaAct (`npa_act`) и NpaClause (`npa_clause`)
- Shared модели. `NpaAct` содержит `code` (уникален глобально), `title`, `edition`, `valid_from`, `valid_to`.
- `NpaClause` хранит `act_id`, `code`, `text`; уникальность кода внутри акта.

### Checklist (`checklist`)
| `npa_code`, `title`, `description`. Уникальность `tenant_id + npa_code + version` (использует `VersionedMixin`).

### Inspection (`inspection`)
| `site_id`, `checklist_id`, `started_at`, `finished_at`, `status` (`planned`,`in_progress`,`completed`,`cancelled`).

### Violation (`violation`)
| `inspection_id`, `clause_ref`, `severity` (`low`,`medium`,`high`,`critical`), `photo_key`, `description`.

### CorrectiveAction (`correctiveaction`)
| `violation_id`, `action`, `due_date`, `status` (`pending`,`in_progress`,`completed`,`overdue`).

## Risk management

### RiskMethodology (`riskmethodology`)
| `name` (уникален per tenant), `definition` (json). Хранит конфигурацию расчётов.

### RiskMap (`riskmap`)
| `methodology_id`, `matrix` (json), `recalculated_at`. Описывает фактическую карту рисков.

### RiskHazard (`risk_hazards`)
Shared-like tenant таблица (см. `backend/app/models/risk.py`): `code`, `title`, `module`, `description`, `document_file_id` (FK→file). Индекс `tenant_id+code` уникален. Связи m2m с `Position` и `Workplace` через таблицы `position_hazard` и `workplace_hazard`, в линках хранится опциональный файл-доказательство для конкретной увязки.

### RiskControl (`risk_controls`)
Аналогично hazards: `code`, `title`, `type`, `description`.

### RiskMatrixCell (`risk_matrix`)
| `severity`, `likelihood`, `score`, `band`. Уникальность по `tenant_id+severity+likelihood`.

### RiskAssessment (`risk_assessments`)
| `company_id`, `place_id` (FK→site), `job_title`, `hazard_id`, поля `severity_before/after`, `likelihood_before/after`, `score_before/after`, `band_before/after`, `controls`, `created_by`.

### Risk (`risk`) — модели больше нет
Класс удалён срезом-135: в реестр никто не писал, живые оценки — `RiskAssessment`. Таблица в базе осталась — см. `docs/CLEANUP_CANDIDATES.md`.

## Operations & auditing

### PlanTask (`plantask`)
| `title`, `description`, `due_date`, `status` (`open`,`in_progress`,`done`,`cancelled`).

### Incident (`incident`)
| `title`, `description`, `occurred_at`, `severity` (`low`,`medium`,`high`), `status` (string). Привязан к аренде, но не к компании.

### Asset (`asset`) и Equipment (`equipment`) — моделей больше нет
Классы удалены срезом-135: в таблицы не писал и не читал никто. Таблицы в базе остались — см. `docs/CLEANUP_CANDIDATES.md`.

### WarehousePPE (`warehouseppe`)
Справочник складских остатков (см. выше в People-блоке).

### JournalEntry (`journalentry`)
| `entry_type`, `payload` (json), `occurred_at`. Используется для событийной шины.

### AuditLog (`auditlog`)
| `when`, `user_id`, `action`, `object_type`, `object_id`, `ip`, `details` (json). Индексы по времени, действию и объекту.

### Outbox (`outbox`)
| `event_type`, `payload` (json), `processed_at`. Используется для паттерна transactional outbox.

## Согласование моделей и Pydantic-схем (актуально)
Следующие расхождения, ранее отмеченные здесь, **закрыты в коде**:
- **Person** — `PersonRead` / `PersonCreate` / `PersonUpdate` включают `employment_status`
  (и по-прежнему `phone`, `email`, и др.). Создание/обновление персоны в
  `backend/app/api/routes/persons.py` записывает `employment_status` в ORM.
- **Document** — `DocumentRead` дополнен полями `site_id`, `template_version_id`,
  `file_id`, `signed_file_id`, `content_sha256`, `job_id` (см. `schemas/document.py`).
- **DocumentPack** — `PackListItem` и `_pack_to_list_item` отдают `module` и
  `scenario_type` в строковом виде (значения enum).

Оставшийся технический долг по выдаче (например расширение `DocumentRead` полями
`department_id` / `contract_id` без явного запроса в API) фиксируется отдельно
по мере появления клиентских контрактов.

Обновляя модели/миграции, обязательно синхронизируйте этот документ.
