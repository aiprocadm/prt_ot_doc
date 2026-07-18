# AUDIT LOG (IMMUTABLE)

## Field-level diff format

```json
{
  "fields": {
    "name": {"before": "A", "after": "B"},
    "status": {"before": "draft", "after": "approved"}
  }
}
```

## Immutability

- Audit records are append-only.
- ORM-level listeners block UPDATE/DELETE operations for `AuditLog`.

## API

- `GET /api/v1/audit` for history.
- `GET /api/v1/audit/export?from=&to=&entity=&actor=&fmt=jsonl|csv` for export stream.

## Captured metadata

- actor user id
- request IP
- user agent
- request correlation id (`request_id`)
