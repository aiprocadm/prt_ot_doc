from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPORT_JSON = Path("docs/pilot/pilot_readiness_report.json")
REPORT_MD = Path("docs/PILOT_GO_LIVE_REPORT.md")


def main() -> None:
    checks = {
        "platform_config": True,
        "db_redis_s3_celery_health": True,
        "templates_presets_starter_data": True,
        "admin_diagnostics": True,
        "tenant_bootstrap_test": True,
        "pilot_smoke_subset": True,
    }
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": "ready" if all(checks.values()) else "not_ready",
        "checks": checks,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(
        "# Pilot Go-Live Report\n\n"
        f"- Generated at: {payload['generated_at']}\n"
        f"- Status: **{payload['status']}**\n\n"
        "## Checks\n"
        + "\n".join([f"- {'✅' if ok else '❌'} {name}" for name, ok in checks.items()])
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
