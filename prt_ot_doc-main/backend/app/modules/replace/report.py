from __future__ import annotations

import csv
from collections import defaultdict
from io import StringIO


def build_report(hits: list[dict], rules: list[dict]) -> dict:
    by_rule: dict[tuple[str, str], dict] = defaultdict(lambda: {"hits": 0, "locations": []})
    for hit in hits:
        key = (hit.get("rule_from", ""), hit.get("rule_to", ""))
        by_rule[key]["hits"] += 1
        by_rule[key]["locations"].append(hit.get("location"))
    entries = []
    for rule in rules:
        k = (str(rule.get("from", "")), str(rule.get("to", "")))
        stats = by_rule.get(k, {"hits": 0, "locations": []})
        entries.append({"from": k[0], "to": k[1], **stats})
    return {
        "total_hits": sum(x["hits"] for x in entries),
        "total_rules": len(rules),
        "by_rule": entries,
        "unresolved": [],
        "warnings": [],
        "sample_diffs": [
            {
                "location": h.get("location"),
                "before_snippet": h.get("before", h.get("before_snippet", "")),
                "after_snippet": h.get("after", h.get("after_snippet", "")),
                "context_before": h.get("before", "")[:120],
                "context_after": h.get("after", "")[:120],
            }
            for h in hits[:200]
        ],
    }


def to_csv(report: dict) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["rule_from", "rule_to", "location", "count", "before_snippet", "after_snippet"])
    for item in report.get("sample_diffs", []):
        writer.writerow([
            "",
            "",
            item.get("location", ""),
            1,
            item.get("before_snippet", ""),
            item.get("after_snippet", ""),
        ])
    return buffer.getvalue()
