# GAP_REPORT

## Closed in this wave
- Нормализован template catalog contract: `category`, `status`, `scope`.
- Исправлена связка upload version -> `current_version_id`.
- Снижен риск broken generation из-за рассинхрона `Template.code` vs `Template.name`.
- Repo теперь документирует demo access, owner/admin access и user access issuance.

## Remaining gaps
- Scope пока хранится в `metadata_json`, а не в отдельных indexed columns.
- Branch-specific generation опирается на текущую модель `Site`; отдельной branch-сущности нет.
- Полный automatic pipeline chain между всеми document entrypoints ещё не унифицирован.
- Version diff / richer preview / archive action UX остаются следующей волной hardening.
