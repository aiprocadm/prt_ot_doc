import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import WorkPermitDetailPage from "@/pages/work-permits/WorkPermitDetailPage";
import { useAuthStore } from "@/stores/auth";

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

const setRole = (perms: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["ot_specialist"], permissions: perms } as never,
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });

const renderAt = () =>
  render(
    <MemoryRouter initialEntries={["/work-permits/wp1"]}>
      <Routes>
        <Route path="/work-permits/:id" element={<WorkPermitDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

const electricalBase = {
  id: "wp1",
  number: "ЭЛ-1",
  work_type: "electrical",
  zone_text: "РУ-10кВ",
  status: "draft",
  members: [
    {
      id: "m1",
      person_id: "p1",
      role: "foreman",
      electrical_group: "II",
      created_at: "",
    },
  ],
  electrical_group_readiness: {
    ok: false,
    insufficient: [
      {
        person_id: "p1",
        role: "foreman",
        group: "II",
        required: "III",
      },
    ],
  },
  safety_systems: null,
  content_text: "Замена выключателя",
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
  type_specific: { technical_measures: ["disconnect"], voltage_condition: "de_energized" },
  created_at: "",
  updated_at: "",
};

describe("WorkPermitElectricalGroups", () => {
  beforeEach(() => {
    getMock.mockReset();
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
  });

  it("показывает бейдж группы у члена бригады электронаряда", async () => {
    getMock.mockResolvedValue(electricalBase);
    renderAt();
    // Ждём загрузки наряда
    await screen.findByText(/Замена выключателя/i);
    // Бейдж группы — текст «Группа: II» или просто «II» рядом с членом бригады
    expect(screen.getByText(/Группа:\s*II/i)).toBeInTheDocument();
  });

  it("показывает баннер готовности с ролью и недостаточной группой", async () => {
    getMock.mockResolvedValue(electricalBase);
    renderAt();
    await screen.findByText(/Замена выключателя/i);
    // Заголовок баннера — уникальный текст, должен быть ровно один такой элемент
    expect(screen.getByText(/Группы электробезопасности/i)).toBeInTheDocument();
    // Строка про производителя работ с указанием требуемой группы — ищем listitem
    const items = screen.getAllByRole("listitem");
    const hasInsufficient = items.some(
      (el) => /Производитель работ/i.test(el.textContent ?? "") && /требуется/i.test(el.textContent ?? ""),
    );
    expect(hasInsufficient).toBe(true);
  });

  it("не показывает баннер готовности при electrical_group_readiness: ok=true", async () => {
    getMock.mockResolvedValue({
      ...electricalBase,
      electrical_group_readiness: { ok: true, insufficient: [] },
    });
    renderAt();
    await screen.findByText(/Замена выключателя/i);
    // Баннер с «группа электробезопасности» или «требуется» не должен появляться
    expect(
      screen.queryByText(/требуется/i),
    ).not.toBeInTheDocument();
  });

  it("не показывает баннер готовности для не-электро наряда", async () => {
    getMock.mockResolvedValue({
      ...electricalBase,
      work_type: "height",
      electrical_group_readiness: null,
      members: [
        {
          id: "m1",
          person_id: "p1",
          role: "foreman",
          electrical_group: "II",
          created_at: "",
        },
      ],
    });
    renderAt();
    await screen.findByText(/Замена выключателя/i);
    expect(screen.queryByText(/Группа:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/требуется/i)).not.toBeInTheDocument();
  });
});
