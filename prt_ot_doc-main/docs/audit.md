# Immutable audit log

## Captured event envelope
Every CRUD/security event stores:
- actor (user/service)
- action, resource_type/resource_id
- timestamp
- request context (ip, user-agent, correlation/request id)
- before_json / after_json / diff_json (field-level)
- optional meta_json

## Immutability
Audit log rows are append-only. Update/delete operations are blocked by ORM hooks and DB-level migration triggers.

## Export and masking
When exporting audit payloads, PII masking is applied for email/phone/passport-shaped fields.
