# API Coverage Overview

| Сущность | Операция | Endpoint | Метод | Статус |
| --- | --- | --- | --- | --- |
| health | ping (liveness) | `/health`, `/healthz` | GET | есть |
| health | readiness | `/ready`, `/readyz` | GET | есть |
| auth | login | `/api/v1/auth/login` | POST | есть |
| auth | refresh | `/api/v1/auth/refresh` | POST | есть |
| auth | текущий пользователь | `/api/v1/auth/me` | GET | есть |
| auth | admin ping (RBAC) | `/api/v1/auth/admin/ping` | GET | есть |
| tenant | list | `/api/v1/tenants` | GET | есть |
| tenant | get by id | `/api/v1/tenants/{tenant_id}` | GET | есть |
| tenant | create | — | — | нет |
| tenant | update/delete | — | — | нет |
| company | list | `/api/v1/companies` | GET | есть |
| company | get by id | `/api/v1/companies/{company_id}` | GET | есть |
| company | create | `/api/v1/companies` | POST | есть |
| company | update | `/api/v1/companies/{company_id}` | PATCH | есть |
| company | delete/archive | `/api/v1/companies/{company_id}` | DELETE | есть |
| site | list | `/api/v1/sites` | GET | есть |
| site | get by id | `/api/v1/sites/{site_id}` | GET | есть |
| site | create | `/api/v1/sites` | POST | есть |
| site | update | `/api/v1/sites/{site_id}` | PATCH | есть |
| site | delete/archive | `/api/v1/sites/{site_id}` | DELETE | есть |
| workplace | list | `/api/v1/workplaces` | GET | есть |
| workplace | get by id | `/api/v1/workplaces/{workplace_id}` | GET | есть |
| workplace | create | `/api/v1/workplaces` | POST | есть |
| workplace | update | `/api/v1/workplaces/{workplace_id}` | PATCH | есть |
| workplace | delete/archive | `/api/v1/workplaces/{workplace_id}` | DELETE | есть |
| person | list | `/api/v1/persons` | GET | есть |
| person | legacy list | `/api/v1/employees` | GET | есть |
| person | get by id | `/api/v1/persons/{person_id}` | GET | есть |
| person | create | `/api/v1/persons` | POST | есть |
| person | update | `/api/v1/persons/{person_id}` | PATCH | есть |
| person | delete/archive | `/api/v1/persons/{person_id}` | DELETE | есть |
| training | list courses | `/api/v1/training/courses` | GET | есть |
| training | create course | `/api/v1/training/courses` | POST | есть |
| training | get course | `/api/v1/training/courses/{course_id}` | GET | есть |
| training | update course | `/api/v1/training/courses/{course_id}` | PATCH | есть |
| training | archive course | `/api/v1/training/courses/{course_id}` | DELETE | есть |
| training | assign plan | `/api/v1/training/plans` | POST | есть |
| training | get plan | `/api/v1/training/plans/{plan_id}` | GET | есть |
| training | register session | `/api/v1/training/sessions` | POST | есть |
| training | issue certificate | `/api/v1/training/certificates` | POST | есть |
| training | list expiring certificates | `/api/v1/training/certificates/expiring` | GET | есть |
| document | generate | `/api/v1/documents/generate` | POST | есть |
| document | generation task status | `/api/v1/documents/tasks/{task_id}` | GET | есть |
| document | status update | `/api/v1/documents/{document_id}/status` | PATCH | есть |
| document | list/get | — | — | нет |
| pack | list | `/api/v1/packs` | GET | есть |
| pack | generate bundle (async) | `/api/v1/packs/generate` | POST | есть |
| pack | run pack scenario | `/api/v1/packs/run` | POST | есть |
| pack | download generated archive (latest) | `/api/v1/packs/download` | GET | есть |
| pack | download archive by id | `/api/v1/packs/{pack_id}/download-archive` | GET | есть |
| pack | CRUD (design time) | — | — | нет |
| risk | list per tenant/site | `/api/v1/risks` | GET | есть |
| risk | create hazard | `/api/v1/risk/hazards` | POST | есть |
| risk | create control | `/api/v1/risk/controls` | POST | есть |
| risk | set matrix | `/api/v1/risk/matrix` | PUT | есть |
| risk | assess scenario | `/api/v1/risk/assess` | POST | есть |
| npa | list acts/clauses | `/api/v1/npa` | GET | есть |
| npa | CRUD | — | — | нет |
| task | get by id (async tasks) | `/api/v1/tasks/{task_id}` | GET | есть |
| file | upload | `/api/v1/files/upload` | POST | есть |
| file | upload template | `/api/v1/files/upload-template` | POST | есть |
| file | get by id | `/api/v1/files/{file_id}` | GET | есть |
| file | download | `/api/v1/files/{file_id}/download` | GET | есть |
| file | delete | — | — | нет |
| audit log | list events | `/api/v1/audit` | GET | есть |

## Пакеты документов

- `POST /api/v1/packs/generate` — асинхронно ставит сборку ZIP-пакета в очередь Celery, возвращает `task_id`/`status_url` и записывает результат в Redis backend. Поддерживает idempotency-key, включает подбор шаблонов пакета, подстановку данных (компания, площадка, работники) и загрузку результатов в файловое хранилище.
- `POST /api/v1/packs/run` — ставит генерацию документов в очередь задач.
- `GET /api/v1/packs/download` — скачивание готового ZIP-архива пакета (прямая загрузка или redirect в S3/MinIO).
- `GET /api/v1/tasks/{task_id}` — статус фоновой задачи (pipeline/Celery). Для успешных пакетов в поле `result` есть `zip_storage_key` и перечень файлов в архиве.
