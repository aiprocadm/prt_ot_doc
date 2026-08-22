import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const healthApiMock = vi.hoisted(() => ({
  getComprehensive: vi.fn(),
}));

vi.mock("@/api/health", () => ({
  healthApi: {
    getComprehensive: (...args: unknown[]) =>
      healthApiMock.getComprehensive(...args),
  },
}));

import HealthStatusPage from "@/pages/admin/HealthStatusPage";
import { useHealthStore } from "@/stores/health";

/**
 * Наполненный ответ /health/comprehensive: все три статуса (ok / degraded /
 * failed) и все известные панели зависимости — замер бюджета идёт по экрану
 * с максимумом карточек, а не по пустой заглушке.
 */
const comprehensiveResponse = {
  status: "degraded" as const,
  tenant_id: null,
  timestamp: "2026-08-22T10:00:00Z",
  checks: {
    postgres: {
      name: "postgres",
      status: "ok" as const,
      error: null,
      duration_ms: 12,
      timestamp: "2026-08-22T10:00:00Z",
    },
    redis: {
      name: "redis",
      status: "ok" as const,
      error: null,
      duration_ms: 3,
      timestamp: "2026-08-22T10:00:00Z",
    },
    minio: {
      name: "minio",
      status: "degraded" as const,
      error: null,
      duration_ms: 480,
      timestamp: "2026-08-22T10:00:00Z",
    },
    workers: {
      name: "workers",
      status: "failed" as const,
      error: "Очередь не отвечает",
      duration_ms: 5000,
      timestamp: "2026-08-22T10:00:00Z",
    },
    "1c_integration": {
      name: "1c_integration",
      status: "ok" as const,
      error: null,
      duration_ms: 210,
      timestamp: "2026-08-22T10:00:00Z",
    },
    edo_integration: {
      name: "edo_integration",
      status: "ok" as const,
      error: null,
      duration_ms: 190,
      timestamp: "2026-08-22T10:00:00Z",
    },
    email: {
      name: "email",
      status: "ok" as const,
      error: null,
      duration_ms: 90,
      timestamp: "2026-08-22T10:00:00Z",
    },
  },
};

describe("HealthStatusPage", () => {
  beforeEach(() => {
    healthApiMock.getComprehensive.mockReset();
    healthApiMock.getComprehensive.mockResolvedValue(comprehensiveResponse);
    // Стор — модульный синглтон: между тестами файла состояние не сбрасывается
    // само, возвращаем его к исходному вручную.
    useHealthStore.setState({ data: null, loading: false, error: null });
  });

  it("наполненный экран в UX-бюджете (BIZ-60 волна 5)", async () => {
    await act(async () => {
      render(<HealthStatusPage />);
    });

    // Дожидаемся именно данных, а не скелетона: карточки всех зависимостей
    // и текст ошибки упавшего воркера на экране.
    expect(await screen.findByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Воркеры (Celery)")).toBeInTheDocument();
    expect(screen.getByText("MinIO (S3)")).toBeInTheDocument();
    expect(screen.getByText("Очередь не отвечает")).toBeInTheDocument();
    expect(healthApiMock.getComprehensive).toHaveBeenCalledWith(undefined);

    const budget = uxBudgetDelta(document.body, "HealthStatusPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("«Обновить» запрашивает свежий срез мимо кэша (skip_cache)", async () => {
    const user = userEvent.setup();
    await act(async () => {
      render(<HealthStatusPage />);
    });
    expect(await screen.findByText("PostgreSQL")).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /обновить/i }));
    });

    expect(healthApiMock.getComprehensive).toHaveBeenLastCalledWith({
      skip_cache: true,
    });
  });
});
