# RBAC + ABAC

## Roles
Supported platform roles include: owner, admin, methodist, lawyer, project_manager, executor, clerk,
instructor, student, hse_head, hse_specialist, fire_engineer, ecologist, hr, accountant,
line_manager, client, auditor_ro, inspector_contractor.

## Base permissions
Initial baseline permissions:
- templates:read / templates:write
- documents:read / documents:write
- files:read / files:write
- jobs:manage
- audit:read

## ABAC attributes
The policy layer evaluates subject and resource attributes:
- company_id
- site_id
- project_id
- contractor_id
- document_id
- status
- risk_level

Query isolation uses mandatory ABAC filters for list/search endpoints.
