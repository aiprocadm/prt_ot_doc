# API overview

## Public entrypoint
`/api/v1`

## Core domains relevant to this wave
- `/companies`
- `/sites`
- `/layout-presets`
- `/branding/*`
- `/documents/*`
- `/pipelines/*`
- `/files/*`

## Authentication / tenancy
All business routes require `X-Tenant` and valid auth headers unless explicitly exempted.
