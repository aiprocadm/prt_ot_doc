# Диагностика 5 падающих тестов (99.5% baseline)

**Дата:** 2026-04-29  
**Статус:** 1039/1044 тестов пройдены (99.5% pass rate)  
**Scope:** 5 existing failures, не регрессии от текущих изменений

---

## Краткая таблица

| # | Тест | Файл | Причина (гипотеза) | Исправление (quick guess) | Приоритет |
|---|------|------|-------------------|---------------------------|-----------|
| 1 | `test_backup_command_json` | `tests/test_cli_commands.py:19` | Typer/Click version incompatibility | Pin `click<9.0, typer>=0.12` | **HIGH** |
| 2 | `test_render_command_invokes_pipeline` | `tests/test_cli_main.py:157` | Click ParamType validator / async mock | Update test mocking pattern for async | **HIGH** |
| 3 | `test_binary_exists_with_paths` | `tests/test_core_config_utils.py:31` | Windows Path.exists() edge case | Add explicit `os.path.exists()` for absolute paths | **MEDIUM** |
| 4 | `test_login_rate_limit` | `tests/test_rate_limit.py:60` | Rate limiter state leak or reset timing | Verify `limiter.reset()` is called before each test | **MEDIUM** |
| 5 | `test_jobs_ws_stream_endpoint` | `tests/test_jobs_api.py:357` | WebSocket fixture or HTTPX config | Check HTTPX WebSocket support; may need `httpx-ws` lib | **LOW** |

---

## Step-by-step диагностика (для волны 29+)

### Шаг 1: Подготовка окружения (10 мин)

```bash
# Создать venv
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (Unix/WSL)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Set PYTHONPATH
$env:PYTHONPATH = "backend"  # PowerShell
# export PYTHONPATH=backend  # Unix
```

### Шаг 2: Запустить каждый тест с verbose

```bash
# Test 1: CLI backup command
pytest tests/test_cli_commands.py::test_backup_command_json -v -s

# Test 2: CLI render command
pytest tests/test_cli_main.py::test_render_command_invokes_pipeline -v -s

# Test 3: binary exists
pytest tests/test_core_config_utils.py::test_binary_exists_with_paths -v -s

# Test 4: rate limit
pytest tests/test_rate_limit.py::test_login_rate_limit -v -s

# Test 5: WebSocket stream
pytest tests/test_jobs_api.py::test_jobs_ws_stream_endpoint -v -s

# Or all 5 at once (faster):
pytest tests/test_cli_commands.py::test_backup_command_json \
        tests/test_cli_main.py::test_render_command_invokes_pipeline \
        tests/test_core_config_utils.py::test_binary_exists_with_paths \
        tests/test_rate_limit.py::test_login_rate_limit \
        tests/test_jobs_api.py::test_jobs_ws_stream_endpoint \
        -v --tb=short
```

---

## Гипотезы и исправления

### Test 1: `test_backup_command_json` — SystemExit(2)

**Файл:** `tests/test_cli_commands.py:19-24`

**Код теста:**
```python
def test_backup_command_json(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["backup", "--triggered-by", "ci", "--json"])
    assert result.exit_code == 0
    assert '"operation": "backup"' in result.stdout
    assert '"triggered_by": "ci"' in result.stdout
```

**Гипотеза:** Typer/Click version drift.

**Проверить:**
```bash
python -c "import typer; import click; print(f'Typer: {typer.__version__}, Click: {click.__version__}')"
```

**Ожидание:** `Typer: >=0.12, Click: <9.0`

**Исправление:**
1. Если версия Click 9.0+, обновить `requirements.txt` с `click<9.0`.
2. Если версии правильные, запустить с `-v` и посмотреть трейс ошибки; может быть issue в парсинге `--json` флага.

---

### Test 2: `test_render_command_invokes_pipeline` — Click ParamType error

**Файл:** `tests/test_cli_main.py:157-223`

**Код теста:**
```python
def test_render_command_invokes_pipeline(monkeypatch, runner, tmp_path):
    # ...
    monkeypatch.setattr("app.cli.main._resolve_template", fake_resolve)
    monkeypatch.setattr("app.cli.main.AsyncSessionLocal", lambda tenant=None: fake_session_factory(tenant=tenant))
    monkeypatch.setattr("app.cli.main.PipelineService", lambda: FakePipelineService())
    
    result = runner.invoke(cli, ["render", "tpl-01", str(payload_path), "--tenant", "explicit-tenant", "--json"])
    assert result.exit_code == 0
```

**Гипотеза:** Async function patching или ParamType validation.

**Проверить:**
- Есть ли error в трейсе про `context_path` параметр (Path type)?
- Click 9.0 изменил handling параметров Path — может нужен `Path(..., exists=False)` или аналог.

**Исправление:**
1. Добавить `Path(..., exists=False, allow_dash=False)` в типизацию параметра, если используется Click ParamType.
2. Или убедиться, что `tmp_path` существует на диске перед тестом.

---

### Test 3: `test_binary_exists_with_paths` — binary detection assertion

**Файл:** `tests/test_core_config_utils.py:31-46`

**Код теста:**
```python
def test_binary_exists_with_paths(tmp_path, monkeypatch):
    binary = tmp_path / "custom" / "bin"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    assert config.binary_exists(str(binary))
    assert config.binary_exists(str(binary.parent)) is True  # <-- может падать здесь
    assert config.binary_exists(str(tmp_path / "missing")) is False

    path_binary = tmp_path / "bin"
    path_binary.write_text("#!/bin/sh\n")
    path_binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert config.binary_exists("bin") is True
```

**Гипотеза:** Windows Path.exists() или chmod(0o755) issue.

**Проверить:**
- На Windows, `chmod(0o755)` может не работать как ожидается.
- `Path.exists()` для директории должна вернуть True, но может быть issue с перемонтированием файловой системы.

**Исправление:**
1. Добавить явный check на Windows и skip/xfail этот тест для Windows:
   ```python
   import sys
   @pytest.mark.skipif(sys.platform == "win32", reason="chmod 0o755 doesn't work on Windows")
   def test_binary_exists_with_paths(tmp_path, monkeypatch):
       ...
   ```
2. Или использовать `os.path.exists()` вместо `Path.exists()` в тесте.

---

### Test 4: `test_login_rate_limit` — 429 instead of 200

**Файл:** `tests/test_rate_limit.py:60-94`

**Код теста:**
```python
@pytest.mark.anyio("asyncio")
async def test_login_rate_limit(async_client, sessionmaker):
    assert login_per_identity() == "2/minute"
    # ...
    for _ in range(2):
        response = await async_client.post("/api/v1/auth/login", json=payload, headers=login_headers)
        response = await async_client.post("/api/v1/auth/login", json=payload, headers=login_headers)
        assert response.status_code == 200

    limited = await async_client.post("/api/v1/auth/login", json=payload, headers=login_headers)
    assert limited.status_code == 429  # <-- может быть 200 (limiter didn't reset)
```

**Гипотеза:** Rate limiter state не сбрасывается между тестами.

**Проверить:**
```bash
# Смотри fixture в test_rate_limit.py
@pytest.fixture(autouse=True)
def _configure_rate_limits(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_IDENTITY", "2/minute")
    # ...
    limiter.reset()  # <- должна быть эта строка
```

**Исправление:**
1. Убедиться, что `limiter.reset()` вызывается в `@pytest.fixture(autouse=True)` **before** каждого теста.
2. Если это так, может быть issue с state leak из другого теста (например, `test_upload_rate_limit` выше может не очищать состояние).
3. Добавить explicit `await limiter.reset()` в начало `test_login_rate_limit`.

---

### Test 5: `test_jobs_ws_stream_endpoint` — PermissionError (websocket/OS-level)

**Файл:** `tests/test_jobs_api.py:357-397`

**Код теста:**
```python
async def test_jobs_ws_stream_endpoint(async_client, make_auth_headers, sessionmaker, data_factory):
    # ... setup ...
    response = await async_client.get(f"/api/v1/jobs/ws/jobs/{job.id}", headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "step_status_changed" in response.text
```

**Гипотеза:** WebSocket или SSE (Server-Sent Events) fixture issue; PermissionError обычно указывает на сокет/OS-level проблему.

**Проверить:**
- Порты 8000/5173 не заняты? (pytest может конфликтовать с dev сервером)
- HTTPX поддерживает WebSocket? (нужна ли `httpx-ws` или иная дополнительная lib?)
- Async event loop правильно настроена? (см. `@pytest.mark.anyio("asyncio")`).

**Исправление:**
1. Добавить `allow_redirects=False` и `follow_redirects=False` в async_client:
   ```python
   response = await async_client.get(
       f"/api/v1/jobs/ws/jobs/{job.id}",
       headers=headers,
       allow_redirects=False
   )
   ```
2. Если тест использует WebSocket, может потребоваться дополнительная lib (`pip install httpx-ws`).
3. Или рассмотреть, поддерживает ли Starlette SSE correct headers при usage async generator.

---

## Процедура исправления (для волны 29+)

1. **Создать новую ветку** для fixing:
   ```bash
   git checkout -b fix/failing-tests-diagnostics
   ```

2. **Запустить каждый тест с `-v --tb=long`** для получения точного трейса.

3. **Применить исправление** согласно гипотезе выше.

4. **Прогнать только этот тест:**
   ```bash
   pytest tests/test_xxx.py::test_name -v
   ```

5. **Если успешно, прогнать полный pytest:**
   ```bash
   pytest tests/ -v --tb=short --junitxml=artifacts/backend-junit.xml
   ```

6. **Commit и PR:**
   ```bash
   git add ...
   git commit -m "fix: resolve 5 failing tests (CLI, config, rate limit, WebSocket)"
   ```

---

## Ссылки

- `AI_IMPLEMENTATION_REPORT.md` — волна 27 (полный pytest, 1039/1044)
- `docs/TESTING.md` — базовые команды проверок
- `docs/TEST_BASELINE.md` — must-pass checklist
- `requirements.txt`, `requirements-dev.txt` — зависимости (Typer, Click, Pydantic, pytest)
