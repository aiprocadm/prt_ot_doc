import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoadSafetyPage from "@/pages/roadSafety/RoadSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listVehiclesMock = vi.fn();
const listDriversMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/roadSafety", () => ({
  roadSafetyApi: {
    listVehicles: (...args: unknown[]) => listVehiclesMock(...args),
    listDrivers: (...args: unknown[]) => listDriversMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/**
 * Водительский состав: допущенный с внесённым стажем и отстранённый без
 * сведений о сроке удостоверения.
 */
const populatedDrivers = [
  {
    id: "d-1",
    person_id: "p-1",
    person_name: "Шофёров Пётр Иванович",
    personnel_number: "ТН-1",
    position_title: "Водитель",
    license_number: "9900 123456",
    categories: ["B", "C"],
    category_labels: ["B — легковые автомобили", "C — грузовые автомобили"],
    license_issued_at: "2020-05-01",
    license_due: "2030-05-01",
    experience_since: "2015-05-01",
    experience_years: 11,
    status: "admitted",
    status_label: "Допущен к управлению",
    license_status: "ok",
    license_status_label: "Действует",
    notes: null,
  },
  {
    id: "d-2",
    person_id: "p-2",
    person_name: "Отстранённов Иван Петрович",
    personnel_number: "ТН-2",
    position_title: "Водитель",
    license_number: "9900 654321",
    categories: ["D"],
    category_labels: ["D — автобусы"],
    license_issued_at: null,
    license_due: null,
    experience_since: null,
    experience_years: null,
    status: "suspended",
    status_label: "Отстранён",
    license_status: "missing",
    license_status_label: "Сведения не внесены",
    notes: null,
  },
];

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
  total_drivers: 2,
  drivers_by_status: { admitted: 1, suspended: 1, dismissed: 0 },
  driver_license_overdue: 0,
  driver_license_missing: 0,
};

describe("RoadSafetyPage", () => {
  beforeEach(() => {
    listVehiclesMock.mockReset();
    listDriversMock.mockReset();
    readinessMock.mockReset();
    listVehiclesMock.mockResolvedValue(populatedVehicles);
    listDriversMock.mockResolvedValue(populatedDrivers);
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

  it("секция водителей показывает состав, стаж и границу", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Водители" }));

    // ФИО приходит из ядрового справочника людей, карточка его не хранит.
    expect(
      await screen.findByText("Шофёров Пётр Иванович"),
    ).toBeInTheDocument();
    // Стаж считает сервер от даты начала — экран печатает посчитанное.
    expect(screen.getByText("11 л.")).toBeInTheDocument();
    // «Не знаем» — это не «ноль лет» и не «просрочено».
    expect(screen.getAllByText("Сведения не внесены").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("Отстранён")).toBeInTheDocument();
    // Граница названа на экране.
    expect(
      screen.getByText(/не решает, какая категория нужна/i),
    ).toBeInTheDocument();
  });

  it("пустой состав водителей объясняет, что вносить", async () => {
    listDriversMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      ...populatedReadiness,
      total_drivers: 0,
      drivers_by_status: { admitted: 0, suspended: 0, dismissed: 0 },
    });

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Водители" }));

    expect(await screen.findByText("Водители не заведены")).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listVehiclesMock.mockResolvedValue([]);
    listDriversMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_vehicles: 0,
      by_status: { in_service: 0, suspended: 0, decommissioned: 0 },
      inspection_overdue: 0,
      insurance_overdue: 0,
      tachograph_overdue: 0,
      documents_missing: 0,
      total_drivers: 0,
      drivers_by_status: { admitted: 0, suspended: 0, dismissed: 0 },
      driver_license_overdue: 0,
      driver_license_missing: 0,
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
