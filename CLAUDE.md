# CLAUDE.md

## Running tests

The repo requires Python **3.12.12**. The local machine may have a different version.

### Determine which Python to use

Before running any tests, detect available Python:

```bash
python3.12 -m pytest ...        # if python3.12 is available
python3 -m pytest ...           # fallback: use whatever python3 is present
```

If `python3.12` is not found, run tests with the system Python (`python3` / `python`) and note the version mismatch in your output — **do not abort**. CI will run the canonical pipeline with 3.12.12.

### Version mismatch policy

- **Do not fail or stop** when Python 3.12 is absent. Run tests with the available Python and report results.
- **Do not run `make cs:test`** (full 1200+ test suite) unless Docker and Python 3.12.12 are both confirmed available — that target requires both.
- For partial local runs, prefer targeted pytest invocations (e.g. `python3 -m pytest tests/unit/`) over full Make targets.
- CI is the source of truth for full test results.

### Quick check

```bash
python3 --version          # see what's available
python3.12 --version 2>/dev/null && echo "3.12 ok" || echo "3.12 not found — using fallback"
```
