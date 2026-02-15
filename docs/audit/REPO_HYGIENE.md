# REPO_HYGIENE

## Что изменено
- Переведён devcontainer на dockerless-first и удалён compose-оверлей `.devcontainer/docker-compose.yml`.
- Перемещён `FRONTEND_AUDIT.md` в `docs/audit/FRONTEND_AUDIT.md` как historical audit.
- Обновлён индекс `docs/README.md` и ссылки в `README.md` на единые source-of-truth документы.
- Добавлены/обновлены audit-артефакты: `ARCHITECTURE_MAP.md`, `FAILURE_MAP.md`, `TZ_COMPLIANCE.md`.

## Почему
- Убрать зависимость Codespaces от docker socket внутри контейнера.
- Сконцентрировать аудит-материалы в `docs/audit/*`.
- Уменьшить дублирование инструкций и неоднозначность путей запуска/тестов.

## Текущая структура (целевой вид)
- `docs/spec/*` — требования (source of truth).
- `docs/audit/*` — результаты проверок и GAP-листы.
- `docs/runbook-codespaces.md` + `docs/testing.md` — оперативные run/test инструкции.
- `scripts/*` — только DevX/bootstrap/utility.


## Служебные каталоги и файлы
- `proxy/` — nginx-конфиги для compose/deployment сценариев; для Codespaces dockerless не обязателен, но оставлен как infra-артефакт.
- `integration_tests/` — отдельный testpath для интеграционных проверок (виден в VS Code Testing panel через `python.testing.pytestArgs`).
- `sitecustomize.py` и `vscode_pytest.py` — оставлены осознанно для стабильной discovery в Codespaces и VS Code; источник env-defaults единый: `test_env_defaults.py`.
