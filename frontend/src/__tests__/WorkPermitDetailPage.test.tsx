import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import WorkPermitDetailPage from "@/pages/work-permits/WorkPermitDetailPage";
import { useAuthStore } from "@/stores/auth";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: {
    get: (...a: unknown[]) => getMock(...a),
    readiness: () => Promise.resolve({ ok: true, violations: [] }),
    events: () => Promise.resolve([]),
    getBriefings: () => Promise.resolve([]),
    listSignatures: () => Promise.resolve([]),
    listAdmissions: () => Promise.resolve([]),
    getClosing: () => Promise.resolve(null),
  },
  fetchAllPersons: () => Promise.resolve([]),
}));

const draft = {
  id: "wp1",
  number: "НД-1",
  work_type: "height",
  zone_text: "фасад",
  status: "draft",
  members: [],
  safety_systems: ["fall_arrest"],
  content_text: "монтаж",
  conditions_text: null,
  hazards_text: null,
  measures_before_text: null,
  measures_during_text: null,
  special_conditions_text: null,
  ppe_text: null,
  subdivision_text: null,
  site_id: null,
  equipment_text: null,
  measures_text: null,
  planned_start: null,
  planned_end: null,
  opened_at: null,
  closed_at: null,
  suspended_at: null,
  created_at: "",
  updated_at: "",
};

const renderAt = () =>
  render(
    <MemoryRouter initialEntries={["/work-permits/wp1"]}>
      <Routes>
        <Route path="/work-permits/:id" element={<WorkPermitDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

// Use a non-admin role so isAdminUser() returns false and permission gating is enforced
const setRole = (perms: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["ot_specialist"], permissions: perms } as never,
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });

describe("WorkPermitDetailPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue(draft);
  });

  it("показывает «Выдать» у черновика при праве manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    expect(
      await screen.findByRole("button", { name: /выдать/i }),
    ).toBeInTheDocument();
  });

  it("скрывает действия без права manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    renderAt();
    await screen.findByText(/монтаж/i);
    expect(
      screen.queryByRole("button", { name: /выдать/i }),
    ).not.toBeInTheDocument();
  });

  it("показывает панель подписей ответственных", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    expect(
      await screen.findByText(/подписи ответственных/i),
    ).toBeInTheDocument();
  });

  it("показывает панель ежедневного допуска", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    expect(await screen.findByText(/ежедневный допуск/i)).toBeInTheDocument();
  });

  it("газоопасный наряд не показывает height-секцию «Системы безопасности» (паритет с формой)", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    getMock.mockResolvedValue({
      ...draft,
      work_type: "gas_hazardous",
      safety_systems: ["fall_arrest"], // легаси-утечка данных другого вида
      type_specific: { respiratory_ppe: ["hose_mask"] },
    });
    renderAt();
    expect(
      await screen.findByText(/Защита органов дыхания/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Системы безопасности")).not.toBeInTheDocument();
  });

  it("электроустановки: показывает блок с условием напряжения и техническими мероприятиями", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    getMock.mockResolvedValue({
      ...draft,
      work_type: "electrical",
      type_specific: {
        technical_measures: ["disconnect"],
        voltage_condition: "de_energized",
        voltage_level: "le_1000",
      },
    });
    renderAt();
    expect(
      await screen.findByText(/Меры безопасности в электроустановках/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Со снятием напряжения/i)).toBeInTheDocument();
    expect(screen.getByText(/Класс напряжения/i)).toBeInTheDocument();
    expect(screen.getByText(/До 1000 В/i)).toBeInTheDocument();
  });

  it("земляные работы: показывает блок безопасности с типом крепления и коммуникациями", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    getMock.mockResolvedValue({
      ...draft,
      work_type: "excavation",
      type_specific: { utilities: ["power_cable"], shoring: "shield_bracing" },
    });
    renderAt();
    expect(
      await screen.findByText(/Безопасность земляных работ/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Крепление щитами/i)).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Самое наполненное состояние: право manage показывает кнопки действий и
    // панели подписей/допуска — замер пустого экрана был бы самообманом.
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    await screen.findByText(/монтаж/i);
    await screen.findByText(/подписи ответственных/i);
    await screen.findByText(/ежедневный допуск/i);

    const budget = uxBudgetDelta(document.body, "WorkPermitDetailPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
