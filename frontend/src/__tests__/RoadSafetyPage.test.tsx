import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoadSafetyPage from "@/pages/roadSafety/RoadSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listVehiclesMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/roadSafety", () => ({
  roadSafetyApi: {
    listVehicles: (...args: unknown[]) => listVehiclesMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Парк: машина со сроками, машина без сведений и списанная. */
const populatedVehicles = [
  {
    id: "v-1",
    plate_number: "А123АА777",
    brand_model: "КамАЗ 5490",
    kind: "truck",
    kind_label: "Грузовой автомобиль",
    status: "in_service",
    status_label: "В эксплуатации",
    vin: null,
    year_made: 2019,
    site_id: null,
    inspection_due: "2027-03-01",
    insurance_due: "2026-09-01",
    license_number: null,
    license_due: null,
    tachograph_installed: true,
    tachograph_due: "2027-01-01",
    notes: null,
    inspection_status: "ok",
    inspection_status_label: "Действует",
    insurance_status: "due_soon",
    insurance_status_label: "Скоро истекает",
    tachograph_status: "ok",
    tachograph_status_label: "Действует",
  },
  {
    id: "v-2",
    plate_number: "В456ВВ777",
    brand_model: "ГАЗель Next",
    kind: "passenger_car",
    kind_label: "Легковой автомобиль",
    status: "in_service",
    status_label: "В эксплуатации",
    vin: null,
    year_made: null,
    site_id: null,
    inspection_due: null,
    insurance_due: null,
    license_number: null,
    license_due: null,
    tachograph_installed: false,
    tachograph_due: null,
    notes: null,
    inspection_status: "missing",
    inspection_status_label: "Сведения не внесены",
    insurance_status: "missing",
    insurance_status_label: "Сведения не внесены",
    tachograph_status: "not_installed",
    tachograph_status_label: "Не установлен",
  },
];

const populatedReadiness = {
  total_vehicles: 2,
  by_status: { in_service: 2, suspended: 0, decommissioned: 0 },
  inspection_overdue: 0,
  insurance_overdue: 0,
  tachograph_overdue: 0,
  documents_missing: 1,
};

describe("RoadSafetyPage", () => {
  beforeEach(() => {
    listVehiclesMock.mockReset();
    readinessMock.mockReset();
    listVehiclesMock.mockResolvedValue(populatedVehicles);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("рендерит парк с видами и состояниями словами", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    // Вид ТС — словами из закрытого словаря.
    expect(screen.getByText("Грузовой автомобиль")).toBeInTheDocument();
    expect(screen.getByText("Легковой автомобиль")).toBeInTheDocument();
    // Пустой срок — «сведения не внесены», а НЕ прочерк и не «бессрочно».
    expect(screen.getAllByText("Сведения не внесены").length).toBeGreaterThan(
      0,
    );
    // Отсутствие прибора — отдельное состояние.
    expect(screen.getByText("Не установлен")).toBeInTheDocument();
    // Граница названа на экране.
    expect(
      screen.getByText(/не решает, нужен ли тахограф/i),
    ).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listVehiclesMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_vehicles: 0,
      by_status: { in_service: 0, suspended: 0, decommissioned: 0 },
      inspection_overdue: 0,
      insurance_overdue: 0,
      tachograph_overdue: 0,
      documents_missing: 0,
    });

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Транспортные средства не заведены"),
    ).toBeInTheDocument();
  });

  it("RoadSafetyPage в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "RoadSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
