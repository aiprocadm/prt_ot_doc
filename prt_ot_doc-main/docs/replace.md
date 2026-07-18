# Replace v1

## CSV format

`from;to` per line, UTF-8 (BOM supported), empty lines and `#` comments ignored.

## Limits

- up to 5000 rules.
- snippet preview max 200 chars.

## Scope

`body`, `tables`, `hdr`, `ftr`, `shapes`.

## Report format

`report_json`:
- `total_hits`
- `total_rules`
- `by_rule`
- `sample_diffs`

CSV columns:
`rule_from,rule_to,location,count,before_snippet,after_snippet`
