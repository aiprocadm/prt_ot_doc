# PDF conversion service v1

- Endpoint `POST /api/v1/files/{file_id}/convert:pdf` creates `PdfConversionRun` and enqueues `pdf.convert` Celery task.
- Timeout is controlled by `options.timeout_s` (default 45s), one retry is executed in task code.
- LibreOffice isolation: per-conversion temporary profile (`/tmp/lo-profile-*`) and bounded concurrency (`LibreOfficePool(workers=4)`).
- Font embedding verification runs with `pdffonts`; non-embedded output fails with `PDF_FONTS_NOT_EMBEDDED`.
- `GET /api/v1/files/pdf-runs/{id}` returns current conversion status.

## Environment

Container image should include:
- libreoffice
- poppler-utils (`pdffonts`)
- fonts-dejavu, fonts-noto-core

Run cache warmup at startup:

```bash
fc-cache -f
```

## Benchmark hint

For local benchmark (not CI): run 30 jobs with 4 workers and measure total duration.
