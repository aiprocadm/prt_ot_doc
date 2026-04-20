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
