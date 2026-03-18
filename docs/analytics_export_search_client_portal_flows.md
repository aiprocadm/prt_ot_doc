# Analytics, Search, Export Center, Client Portal — flow notes

## Dashboard -> drilldown
1. Read-model projections are refreshed by `ProjectionOrchestrator` and specialized projection services.
2. `/api/v1/analytics/dashboard/*` endpoints read KPI widgets from projection tables.
3. Frontend widgets use route/deeplink payload for drill-down to registries.

## Export request -> file
1. User calls `POST /api/v1/exports` with filters/scope.
2. `ExportCenterService` creates or reuses an idempotent `export_jobs` record.
3. Worker updates job status and file reference.
4. User requests signed URL via `GET /api/v1/exports/{id}/download-link`.

## Package projection refresh
1. Domain updates package lifecycle data.
2. Projection worker triggers `rebuild_package_projection_job`.
3. `PackageReadModel` is upserted idempotently.

## Search reindex
1. `POST /api/v1/search/reindex` triggers read-model reindex.
2. `search_index_entries` are regenerated.
3. `/api/v1/search` serves global search from projection entries.

## Client request/upload flow
1. Client user uploads files via `/api/v1/client-portal/uploads`.
2. Client creates support request via `/api/v1/client-portal/requests`.
3. Internal support handles request in `/api/v1/portal-requests/*`.
4. Message history is available for both slices with tenant boundaries.


## BI/DWH export foundation (v2)
1. `POST /api/v1/exports` теперь принимает `dataset_code`, `schema_version`, `anonymized`, `target_type`, `target_config`.
2. `ExportCenterService` создает tenant-safe export job с версией схемы и target contract (`file`, `webhook`, future DWH sink).
3. `GET/POST /api/v1/exports/schedules` дают foundation для scheduled exports.
4. `GET/POST /api/v1/exports/kpis` хранят tenant KPI definitions и locale labels.
5. Delivery history пока хранится в payload job'а как foundation и готова к вынесению в отдельный журнал поставки.
