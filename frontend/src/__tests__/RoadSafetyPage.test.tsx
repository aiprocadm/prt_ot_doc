import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoadSafetyPage from "@/pages/roadSafety/RoadSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listVehiclesMock = vi.fn();
const listDriversMock = vi.fn();
const listWaybillsMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/roadSafety", () => ({
  roadSafetyApi: {
    listVehicles: (...args: unknown[]) => listVehiclesMock(...args),
    listDrivers: (...args: unknown[]) => listDriversMock(...args),
    listWaybills: (...args: unknown[]) => listWaybillsMock(...args),
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

/**
 * Путевые листы: подтверждённый выпуск, лист без отметок и лист с
 * проваленным осмотром. Три состояния вердикта на трёх строках — иначе
 * невозможно увидеть, что «не внесено» и «не пройден» показываются по-разному.
 */
const populatedWaybills = [
  {
    id: "w-1",
    number: "ПЛ-001",
    vehicle_id: "v-1",
    vehicle_plate: "А123АА777",
    vehicle_brand_model: "КамАЗ 5490",
    driver_id: "d-1",
    driver_name: "Шофёров Пётр Иванович",
    driver_license_number: "9900 123456",
    issued_on: "2026-08-30",
    departure_at: "2026-08-30T08:00:00+00:00",
    return_at: "2026-08-30T17:30:00+00:00",
    trip_hours: 9.5,
    pre_trip_medical: "passed",
    pre_trip_medical_label: "Пройден",
    post_trip_medical: "not_recorded",
    post_trip_medical_label: "Сведения не внесены",
    pre_trip_technical: "passed",
    pre_trip_technical_label: "Пройден",
    release_status: "confirmed",
    release_status_label: "Выпуск подтверждён",
    status: "issued",
    status_label: "Выдан",
    notes: null,
  },
  {
    id: "w-2",
    number: "ПЛ-002",
    vehicle_id: "v-2",
    vehicle_plate: "В456ВВ777",
    vehicle_brand_model: "ГАЗель Next",
    driver_id: "d-1",
    driver_name: "Шофёров Пётр Иванович",
    driver_license_number: "9900 123456",
    issued_on: "2026-08-29",
    departure_at: null,
    return_at: null,
    trip_hours: null,
    pre_trip_medical: "not_recorded",
    pre_trip_medical_label: "Сведения не внесены",
    post_trip_medical: "not_recorded",
    post_trip_medical_label: "Сведения не внесены",
    pre_trip_technical: "not_recorded",
    pre_trip_technical_label: "Сведения не внесены",
    release_status: "unconfirmed",
    release_status_label: "Контроль не подтверждён",
    status: "issued",
    status_label: "Выдан",
    notes: null,
  },
  {
    id: "w-3",
    number: "ПЛ-003",
    vehicle_id: "v-1",
    vehicle_plate: "А123АА777",
    vehicle_brand_model: "КамАЗ 5490",
    driver_id: "d-1",
    driver_name: "Шофёров Пётр Иванович",
    driver_license_number: "9900 123456",
    issued_on: "2026-08-28",
    departure_at: null,
    return_at: null,
    trip_hours: null,
    pre_trip_medical: "failed",
    pre_trip_medical_label: "Не пройден",
    post_trip_medical: "not_recorded",
    post_trip_medical_label: "Сведения не внесены",
    pre_trip_technical: "passed",
    pre_trip_technical_label: "Пройден",
    release_status: "blocked",
    release_status_label: "Контроль не пройден",
    status: "issued",
    status_label: "Выдан",
    notes: null,
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
  waybill_window_days: 30,
  waybills_total: 3,
  waybills_by_status: { issued: 3, closed: 0, cancelled: 0 },
  waybills_release_blocked: 1,
  waybills_release_unconfirmed: 1,
};

describe("RoadSafetyPage", () => {
  beforeEach(() => {
    listVehiclesMock.mockReset();
    listDriversMock.mockReset();
    listWaybillsMock.mockReset();
    readinessMock.mockReset();
    listVehiclesMock.mockResolvedValue(populatedVehicles);
    listDriversMock.mockResolvedValue(populatedDrivers);
    listWaybillsMock.mockResolvedValue(populatedWaybills);
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
    listWaybillsMock.mockResolvedValue([]);
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
      waybill_window_days: 30,
      waybills_total: 0,
      waybills_by_status: { issued: 0, closed: 0, cancelled: 0 },
      waybills_release_blocked: 0,
      waybills_release_unconfirmed: 0,
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

  it("секция листов различает «не внесено» и «не пройден»", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Путевые листы" }));

    expect(await screen.findByText("ПЛ-001")).toBeInTheDocument();
    // Три вердикта показаны РАЗНЫМИ словами: склей их — и дыра в учёте
    // стала бы неотличима от нарушения выпуска.
    expect(screen.getByText("Выпуск подтверждён")).toBeInTheDocument();
    expect(screen.getByText("Контроль не подтверждён")).toBeInTheDocument();
    expect(screen.getByText("Контроль не пройден")).toBeInTheDocument();
    // Время В РЕЙСЕ печатается посчитанным сервером; без дат его нет вовсе.
    expect(screen.getByText(/9\.5 ч в рейсе/)).toBeInTheDocument();
    // Граница названа на экране.
    expect(
      screen.getByText(/послерейсовый осмотр в вердикт не входит/i),
    ).toBeInTheDocument();
  });

  it("пустой журнал листов объясняет, что вносить", async () => {
    listWaybillsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      ...populatedReadiness,
      waybills_total: 0,
      waybills_by_status: { issued: 0, closed: 0, cancelled: 0 },
      waybills_release_blocked: 0,
      waybills_release_unconfirmed: 0,
    });

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Путевые листы" }));

    expect(
      await screen.findByText("Путевые листы не выписаны"),
    ).toBeInTheDocument();
  });

  it("секция листов остаётся в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Путевые листы" }));
    expect(await screen.findByText("ПЛ-001")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "RoadSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
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
