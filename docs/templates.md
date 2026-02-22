# Template engine (NEXT-18)

## Selection rule
Template selection is strict by pair `(code, version)`.
If an exact pair is not found API returns `404`.

## Linting
At template version upload service parses `word/document.xml`, `word/header*.xml`, `word/footer*.xml`.
Collected index is stored in `templateversion.placeholder_index`:
- `placeholders`
- `blocks` (`if/for/endif/endfor`)
- `field_paths`
- `stats`
- `errors`

## Delete semantics
Deleting a template version that is referenced by document versions/jobs is rejected with:
`409 {"code":"template_version_in_use"}`.

## Passport format
Every rendered DOCX includes document passport with:
- `template_code`
- `template_version`
- `generated_at`
- `generated_by`
- `tenant_id`
- `sha256_input_data`
- `npa_binding_id`
- `correlation_id`

Passport is embedded into:
1. `docProps/custom.xml` (`passport_json`)
2. hidden paragraph `PTD-PASSPORT:{base64(json)}` (or visible variant by flag)
