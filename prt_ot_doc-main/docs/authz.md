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

## Current wave note
- This wave did not change the global permission matrix.
- It did preserve tenant-aware execution in the hardened pipeline/document path and kept provider abstraction boundaries intact.
- A repo-wide read/write/bulk/export/search authz consistency pass is still required.
