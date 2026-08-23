import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FireSafetyPage from "@/pages/fire-safety/FireSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getFireSafetySnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getFireSafetySnapshot: (...args: unknown[]) =>
      getFireSafetySnapshotMock(...args),
  },
}));

const listEquipmentMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/fireSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fireSafetyApi: {
    listEquipment: (...args: unknown[]) => listEquipmentMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Средства ПБ: один срок просрочен, один истекает скоро (разд. 54.1). */
const populatedEquipment = [
  {
    id: "eq-1",
    kind: "extinguisher",
    label: "ОП-5 №1",
    location: "Цех 1",
    recharge_due: "2020-01-01",
    inspection_due: null,
    status: "active",
  },
  {
    id: "eq-2",
    kind: "alarm_system",
    label: "АУПС корпус А",
    location: null,
    recharge_due: null,
    inspection_due: "2099-01-01",
    status: "active",
  },
];

const populatedReadiness = {
  total_units: 2,
  overdue_recharge: 1,
  overdue_inspection: 0,
  due_soon: 1,
  due_soon_days: 30,
};

/** Наполненный снимок: статистика шапки и реестр площадок на экране. */
const populatedFireSafetySnapshot = {
  sites: [
    {
      id: "site-1",
      company_id: "comp-1",
      name: "Цех сборки №1",
      address: "г. Тверь, ул. Заводская, 5",
      hazard_class: "В2",
      contact_name: "Иванов И. И.",
    },
    {
      id: "site-2",
      company_id: "comp-1",
      name: "Склад ГСМ",
      address: null,
      hazard_class: null,
      contact_name: null,
    },
  ],
  inspections: [
    { id: "insp-1", site_id: "site-1", status: "scheduled" },
    { id: "insp-2", site_id: "site-1", status: "done" },
  ],
  tasks: [
    { id: "task-1", status: "open" },
    { id: "task-2", status: "done" },
  ],
};

describe("FireSafetyPage", () => {
  beforeEach(() => {
    getFireSafetySnapshotMock.mockReset();
    listEquipmentMock.mockReset();
    readinessMock.mockReset();
    listEquipmentMock.mockResolvedValue(populatedEquipment);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("рисует реестр объектов защиты по данным снимка", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    expect(screen.getByText(/пожарная безопасность/i)).toBeInTheDocument();
    expect(screen.getByText("Склад ГСМ")).toBeInTheDocument();
    // Связанные проверки посчитаны по site_id: у первой площадки их две.
    expect(screen.getByText("2 шт.")).toBeInTheDocument();
    expect(screen.getByText("Иванов И. И.")).toBeInTheDocument();
  });

  // Приёмка UX-бюджета (ТЗ разд. 59.2, BIZ-60): меряем ОТРИСОВАННЫЙ
  // наполненный экран — статистика шапки и таблица реестра видны.

  it("готовность к проверке МЧС видна в шапке (разд. 54.1)", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    // Просрочка — первое, что спрашивает инспектор: она в шапке, а не внутри
    // таблицы, куда надо долистать.
    expect(await screen.findByText(/просрочено сроков/i)).toBeInTheDocument();
    expect(screen.getByText(/истекает за 30 дн\./i)).toBeInTheDocument();
  });

  it("реестр средств открывается второй секцией и называет просроченный срок", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Средства и системы" }));

    expect(await screen.findByText("ОП-5 №1")).toBeInTheDocument();
    // Вид — словами, а не кодом; просроченный срок назван просроченным.
    expect(screen.getByText("Сигнализация (АУПС)")).toBeInTheDocument();
    // Не просто «дата в прошлом» — ячейка прямо называет срок просроченным
    // (в шапке слово тоже есть, поэтому матчим ячейку с датой).
    expect(screen.getByText(/·\s*просрочен$/i)).toBeInTheDocument();
  });

  it("FireSafetyPage в UX-бюджете в ОБЕИХ секциях", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    const sites = uxBudgetDelta(document.body, "FireSafetyPage");
    expect(sites.unexpected).toEqual([]);
    expect(sites.stale).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Средства и системы" }));
    expect(await screen.findByText("ОП-5 №1")).toBeInTheDocument();
    const equipment = uxBudgetDelta(document.body, "FireSafetyPage");
    expect(equipment.unexpected).toEqual([]);
    expect(equipment.stale).toEqual([]);
  });
});
