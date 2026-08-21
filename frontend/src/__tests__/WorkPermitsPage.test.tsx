import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import WorkPermitsPage from "@/pages/work-permits/WorkPermitsPage";
import { useAuthStore } from "@/stores/auth";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import type { WorkPermitDto } from "@/types/dto/workPermits";

const listMock = vi.fn();
const countMock = vi.fn();

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: {
    list: (...a: unknown[]) => listMock(...a),
    count: (...a: unknown[]) => countMock(...a),
  },
}));

// Use a non-admin role so isAdminUser() returns false and permission gating is enforced
const setRole = (perms: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["ot_specialist"], permissions: perms } as never,
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });

describe("WorkPermitsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    countMock.mockReset();
    listMock.mockResolvedValue({ items: [], total: 0 });
    countMock.mockResolvedValue(0);
  });

  it("показывает заголовок страницы", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <WorkPermitsPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: /наряды-допуски/i }),
    ).toBeInTheDocument();
  });

  it("скрывает «Новый наряд» без права manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    render(
      <MemoryRouter>
        <WorkPermitsPage />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: /наряды-допуски/i });
    expect(
      screen.queryByRole("button", { name: /новый наряд/i }),
    ).not.toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Свои моки с ДАННЫМИ: соседние тесты мокают пустой список, а замер
    // пустого экрана — самообман (таблица рисуется только при наличии строк).
    const permit: WorkPermitDto = {
      id: "wp1",
      number: "НД-001",
      work_type: "height",
      zone_text: "Цех №1, отметка +12",
      site_id: null,
      equipment_text: null,
      hazards_text: null,
      measures_text: null,
      planned_start: null,
      planned_end: null,
      status: "issued",
      opened_at: null,
      closed_at: null,
      suspended_at: null,
      members: [
        {
          id: "m1",
          person_id: "p1",
          role: "producer",
          electrical_group: null,
          created_at: "2026-08-20T10:00:00Z",
        },
      ],
      subdivision_text: null,
      content_text: null,
      conditions_text: null,
      safety_systems: ["scaffolding"],
      measures_before_text: null,
      measures_during_text: null,
      special_conditions_text: null,
      ppe_text: null,
      type_specific: null,
      created_at: "2026-08-20T10:00:00Z",
      updated_at: "2026-08-20T10:00:00Z",
    };
    listMock.mockResolvedValue({ items: [permit], total: 1 });
    countMock.mockResolvedValue(1);
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);

    render(
      <MemoryRouter>
        <WorkPermitsPage />
      </MemoryRouter>,
    );

    // Наполненное состояние: таблица со строкой наряда, а не пустой экран
    await screen.findByRole("table");
    await screen.findByRole("link", { name: /открыть/i });

    const budget = uxBudgetDelta(document.body, "WorkPermitsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
