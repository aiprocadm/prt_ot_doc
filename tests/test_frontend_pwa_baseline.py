from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_vite_config_enables_real_pwa_plugin() -> None:
    vite_config = (REPO_ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")

    assert "VitePWA(" in vite_config
    assert "registerType: \"autoUpdate\"" in vite_config
    assert "manifest:" in vite_config
    assert "runtimeCaching:" in vite_config


def test_frontend_main_registers_generated_service_worker() -> None:
    main_tsx = (REPO_ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
    register_ts = (REPO_ROOT / "frontend/src/pwa/register.ts").read_text(encoding="utf-8")

    assert 'import { registerPwa } from "@/pwa/register";' in main_tsx
    assert "registerPwa();" in main_tsx
    assert 'import { registerSW } from "virtual:pwa-register";' in register_ts
    assert "registerSW({" in register_ts
