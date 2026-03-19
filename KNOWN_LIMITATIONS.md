# Known limitations

- Branding preview renders resolved section content and metadata, not a full WYSIWYG PDF canvas.
- Layout preset editor is production-usable for CRUD-like maintenance, but not yet a full template catalog with version history.
- Repository still contains historical documentation snapshots; canonical docs are the files linked from root `README.md`.
- Full end-to-end document issuance smoke still depends on environment services such as PostgreSQL, Redis, S3/MinIO, Celery and LibreOffice.
