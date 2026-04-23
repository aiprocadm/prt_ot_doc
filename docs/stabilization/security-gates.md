# Security Gates (Stabilization)

_Last updated: 2026-04-20._

This document defines the mandatory security gates in `.github/workflows/ci.yml`, including fail thresholds, scope exclusions, and exception handling.

## Security exception registry

All temporary security exceptions are tracked in `.github/security-exceptions.yml` using this schema:

```yaml
exceptions:
  - id: CVE-2026-0000            # finding identifier (CVE/GHSA/rule id)
    tool: trivy                  # scanner name
    category: vulnerability      # vulnerability | secret | sast | container
    owner: team-platform         # accountable owner
    reason: "Waiting for upstream fix"
    expires_on: 2026-06-30       # ISO date, required
    created_on: 2026-04-20       # optional
    ticket: SEC-1234             # optional
    scope:                       # optional
      paths:
        - backend/
```

CI enforces that every exception has `owner`, `reason`, and `expires_on`, and fails if any entry is expired (`expires_on < today`).

## Gate inventory

| Gate | CI job | Tooling | Fail condition | Scope exclusions |
|---|---|---|---|---|
| Exception metadata validity | `security-exceptions` | `scripts/ci/check_security_exceptions.py` | Any missing required metadata or expired exception. | None. |
| Dependency vulnerability scanning | `dependency-vulnerability-scan` | Trivy filesystem dependency scan (`vuln-type=library`) | Any `HIGH`/`CRITICAL` dependency finding after applying active Trivy exceptions. | Ignores `LOW`/`MEDIUM`; ignores unfixed findings (`ignore-unfixed=true`). |
| Secret scanning | `secret-scan` | Gitleaks | Any detected secret pattern in current workspace scan. | Historic git history is excluded (`--no-git`) to avoid re-failing on already-rewritten history outside this branch scope. |
| SAST/static analysis | `sast-static-analysis` | Bandit (`-lll -iii`) | Any `HIGH` severity + `HIGH` confidence Python finding. | `LOW`/`MEDIUM` severity and lower-confidence findings are non-blocking in this gate. |
| Container image scanning | `container-image-scan` | Docker build + Trivy image scan | Any `HIGH`/`CRITICAL` image finding after applying active Trivy exceptions. | Ignores `LOW`/`MEDIUM`; ignores unfixed findings (`ignore-unfixed=true`). |
| SBOM generation | `sbom-generation` | Anchore SBOM action (CycloneDX JSON) | Job fails if SBOM cannot be generated from the built API image. | Does not perform policy blocking on package severity itself; this job is evidence/artifact generation. |

## Operational notes

- High/Critical vulnerability blocking is intentionally centralized in Trivy dependency and container gates.
- SAST blocking is intentionally limited to high-confidence/high-severity findings to reduce false-positive noise.
- Exception records are temporary only and must include a concrete owner and remediation rationale.
- SBOM is uploaded as a CI artifact (`sbom-cyclonedx`) for audit and downstream supply-chain tooling.

## CODEOWNERS ownership intent

High-risk security and platform surfaces are protected with mandatory owner review via `.github/CODEOWNERS`.

Protected ownership domains:

- **Auth and session perimeter** — `backend/app/api/routes/auth*`, auth dependencies, middleware, and session handling paths.
- **Authorization policy core** — `backend/app/modules/rbac_abac/**`.
- **File processing/storage chain** — `backend/app/modules/files/**` plus file-facing API/domain paths.
- **File routing perimeter** — `backend/app/api/v1/route_groups.py` (canonical `/files` vs legacy `/files-legacy` registration boundary).
- **Data plane** — `backend/app/migrations/**`.
- **Delivery/runtime perimeter** — `.github/workflows/**`, `proxy/**`, `infra/**`, `config/**`.

Intent:

1. Ensure policy/sign-in/session semantics are reviewed by designated security owners.
2. Require specialist review for RBAC/ABAC and file-storage changes that can create lateral security impact.
3. Prevent unreviewed migration and infrastructure drift in production-critical surfaces.

## Escalation policy for blocked owner review

If required owner review is blocked (owner unavailable, SLA breach, or incident urgency), use this path:

1. **T+0 (request opened):** assign the mapped CODEOWNERS team and add context (risk, rollback plan, blast radius).
2. **T+4 business hours:** escalate to the on-call/platform incident lead and post the escalation in the PR thread.
3. **T+1 business day:** escalate to engineering management + security lead for temporary delegate approval assignment.
4. **Emergency break-glass:** only for incident containment or legal/compliance hotfixes; requires:
   - explicit incident/ticket reference in PR,
   - two approvers (incident lead + delegate),
   - follow-up retro PR within 1 business day to restore normal ownership review.

All escalations must be auditable in PR comments and linked to the relevant incident or ticket.
