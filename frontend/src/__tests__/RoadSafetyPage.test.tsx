import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoadSafetyPage from "@/pages/roadSafety/RoadSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listVehiclesMock = vi.fn();
const listDriversMock = vi.fn();
const listWaybillsMock = vi.fn();
const listAccidentsMock = vi.fn();
const listViolationsMock = vi.fn();
const readinessMock = vi.fn();
const createVehicleMock = vi.fn();
const createDriverMock = vi.fn();
const createWaybillMock = vi.fn();
const createAccidentMock = vi.fn();
const createViolationMock = vi.fn();
const listSitesMock = vi.fn();
const fetchAllPersonsMock = vi.fn();

vi.mock("@/api/roadSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  roadSafetyApi: {
    createVehicle: (...args: unknown[]) => createVehicleMock(...args),
    createWaybill: (...args: unknown[]) => createWaybillMock(...args),
    createAccident: (...args: unknown[]) => createAccidentMock(...args),
    createViolation: (...args: unknown[]) => createViolationMock(...args),
    updateWaybill: vi.fn(),
    updateAccident: vi.fn(),
    updateViolation: vi.fn(),
    createDriver: (...args: unknown[]) => createDriverMock(...args),
    updateVehicle: vi.fn(),
    updateDriver: vi.fn(),
    listVehicles: (...args: unknown[]) => listVehiclesMock(...args),
    listDrivers: (...args: unknown[]) => listDriversMock(...args),
    listWaybills: (...args: unknown[]) => listWaybillsMock(...args),
    listAccidents: (...args: unknown[]) => listAccidentsMock(...args),
    listViolations: (...args: unknown[]) => listViolationsMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

vi.mock("@/api/sites", () => ({
  sitesApi: { list: (...args: unknown[]) => listSitesMock(...args) },
}));

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: (...args: unknown[]) => fetchAllPersonsMock(...args),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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

/**
 * ДТП: с пострадавшими и связанное с расследованием, без пострадавших и без
 * разбора, и наезд на стоящую машину без водителя за рулём.
 */
const populatedAccidents = [
  {
    id: "a-1",
    occurred_at: "2026-08-20T07:40:00+00:00",
    place: "45 км трассы М-4",
    vehicle_id: "v-1",
    vehicle_plate: "А123АА777",
    driver_id: "d-1",
    driver_name: "Шофёров Пётр Иванович",
    kind: "collision",
    kind_label: "Столкновение",
    injured_count: 2,
    fatalities_count: 0,
    consequences: "injured",
    consequences_label: "Есть пострадавшие",
    fault: "other_party",
    fault_label: "Другой участник",
    gibdd_reference: "МТ-12/345",
    incident_id: "inc-1",
    description: null,
    capa_total: 2,
    capa_open: 1,
    follow_up: "open",
    follow_up_label: "Есть незакрытые мероприятия",
  },
  {
    id: "a-2",
    occurred_at: "2026-08-10T12:00:00+00:00",
    place: "двор склада",
    vehicle_id: "v-2",
    vehicle_plate: "В456ВВ777",
    driver_id: null,
    driver_name: null,
    kind: "parked_vehicle",
    kind_label: "Наезд на стоящее ТС",
    injured_count: 0,
    fatalities_count: 0,
    consequences: "damage_only",
    consequences_label: "Только материальный ущерб",
    fault: "not_established",
    fault_label: "Не установлена",
    gibdd_reference: null,
    incident_id: null,
    description: null,
    capa_total: 0,
    capa_open: 0,
    follow_up: "not_started",
    follow_up_label: "Мероприятия не заведены",
  },
];

/** Нарушения: снятое камерой без водителя и остановка инспектором с оплатой. */
const populatedViolations = [
  {
    id: "vio-1",
    vehicle_id: "v-1",
    vehicle_plate: "А123АА777",
    driver_id: null,
    driver_name: null,
    driver_identified: false,
    occurred_at: "2026-08-25T09:15:00+00:00",
    source: "camera",
    source_label: "Автоматическая фиксация (камера)",
    article: "12.9 ч.2 КоАП",
    resolution_number: "18810177260825",
    place: "45 км трассы М-4",
    fine_amount: "500.00",
    fine_paid_on: null,
    fine_status: "unpaid",
    fine_status_label: "Не оплачен",
    description: null,
  },
  {
    id: "vio-2",
    vehicle_id: "v-2",
    vehicle_plate: "В456ВВ777",
    driver_id: "d-1",
    driver_name: "Шофёров Пётр Иванович",
    driver_identified: true,
    occurred_at: "2026-08-12T14:00:00+00:00",
    source: "officer",
    source_label: "Остановлен инспектором",
    article: "12.6 КоАП",
    resolution_number: null,
    place: null,
    fine_amount: "1000.00",
    fine_paid_on: "2026-08-20",
    fine_status: "paid",
    fine_status_label: "Оплачен",
    description: null,
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
  accident_window_days: 365,
  accidents_total: 2,
  accidents_by_consequences: { damage_only: 1, injured: 1, fatal: 0 },
  injured_total: 2,
  fatalities_total: 0,
  accidents_without_follow_up: 1,
  road_briefings_total: 4,
  road_briefings_overdue: 1,
  knowledge_checks_total: 3,
  knowledge_checks_overdue: 2,
  internships_total: 5,
  internships_in_progress: 2,
  internships_completed_short: 1,
  violation_window_days: 365,
  violations_total: 2,
  violations_without_driver: 1,
  fines_unpaid_count: 1,
  fines_unpaid_amount: 500,
  incidents_open: 3,
};

describe("RoadSafetyPage", () => {
  beforeEach(() => {
    listVehiclesMock.mockReset();
    createVehicleMock.mockReset();
    createDriverMock.mockReset();
    createWaybillMock.mockReset();
    createAccidentMock.mockReset();
    createViolationMock.mockReset();
    listSitesMock.mockReset();
    fetchAllPersonsMock.mockReset();
    listSitesMock.mockResolvedValue({
      items: [{ id: "site-1", name: "Площадка №1" }],
      total: 1,
    });
    fetchAllPersonsMock.mockResolvedValue([
      { id: "p-1", full_name: "Шофёров Пётр Иванович" },
    ]);
    listDriversMock.mockReset();
    listWaybillsMock.mockReset();
    listAccidentsMock.mockReset();
    listViolationsMock.mockReset();
    readinessMock.mockReset();
    listVehiclesMock.mockResolvedValue(populatedVehicles);
    listDriversMock.mockResolvedValue(populatedDrivers);
    listWaybillsMock.mockResolvedValue(populatedWaybills);
    listAccidentsMock.mockResolvedValue(populatedAccidents);
    listViolationsMock.mockResolvedValue(populatedViolations);
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

  it("путевой лист выписывается с экрана (срез-108)", async () => {
    const user = userEvent.setup();
    const added = { ...populatedWaybills[0], id: "wb-new", number: "000999" };
    createWaybillMock.mockResolvedValue(added);
    listWaybillsMock
      .mockResolvedValueOnce(populatedWaybills)
      .mockResolvedValue([...populatedWaybills, added]);

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Путевые листы" }),
    );

    await user.click(screen.getByRole("button", { name: "Выписать лист" }));
    await user.type(screen.getByLabelText("Номер листа"), "000999");
    await user.type(screen.getByLabelText("Выдан"), "2026-09-01");
    await user.selectOptions(
      screen.getByLabelText("Машина"),
      populatedVehicles[0].id,
    );
    await user.selectOptions(
      screen.getByLabelText("Водитель"),
      populatedDrivers[0].id,
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createWaybillMock).toHaveBeenCalled());
    expect(createWaybillMock.mock.calls[0][0]).toMatchObject({
      number: "000999",
      vehicle_id: populatedVehicles[0].id,
      driver_id: populatedDrivers[0].id,
      issued_on: "2026-09-01",
      status: "issued",
      // Свежий лист выписан до осмотра: это законное «сведений нет».
      pre_trip_medical: "not_recorded",
      pre_trip_technical: "not_recorded",
    });
  });

  it("ДТП и нарушение вносятся с экрана (срез-108)", async () => {
    const user = userEvent.setup();
    createAccidentMock.mockResolvedValue({ id: "acc-new" });
    createViolationMock.mockResolvedValue({ id: "vio-new" });

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("button", { name: "ДТП" }));

    await user.click(
      screen.getByRole("button", { name: "Зарегистрировать ДТП" }),
    );
    await user.type(screen.getByLabelText("Дата и время"), "2026-08-01T09:30");
    await user.type(screen.getByLabelText("Место"), "ул. Заводская, 5");
    await user.selectOptions(
      screen.getByLabelText("Машина"),
      populatedVehicles[0].id,
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createAccidentMock).toHaveBeenCalled());
    expect(createAccidentMock.mock.calls[0][0]).toMatchObject({
      occurred_at: "2026-08-01T09:30:00",
      place: "ул. Заводская, 5",
      vehicle_id: populatedVehicles[0].id,
      kind: "collision",
      // Вину устанавливают ГИБДД и суд: по умолчанию «не установлена».
      fault: "not_established",
      driver_id: null,
      injured_count: 0,
    });

    await user.click(screen.getByRole("button", { name: "Нарушения" }));
    await user.click(screen.getByRole("button", { name: "Внести нарушение" }));
    await user.selectOptions(
      screen.getByLabelText("Машина"),
      populatedVehicles[0].id,
    );
    await user.type(screen.getByLabelText("Дата и время"), "2026-08-02T12:00");
    await user.type(screen.getByLabelText("Статья КоАП"), "12.9 ч.2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createViolationMock).toHaveBeenCalled());
    expect(createViolationMock.mock.calls[0][0]).toMatchObject({
      vehicle_id: populatedVehicles[0].id,
      occurred_at: "2026-08-02T12:00:00",
      source: "camera",
      article: "12.9 ч.2",
      // Водитель не установлен, штраф не наложен — это факты, а не пустые поля.
      driver_id: null,
      fine_amount: null,
    });
  });

  it("ТС заводится с экрана, а не только через API (срез-107)", async () => {
    const user = userEvent.setup();
    const added = {
      ...populatedVehicles[0],
      id: "v-new",
      plate_number: "Х777ХХ777",
      brand_model: "КамАЗ-65115",
    };
    createVehicleMock.mockResolvedValue(added);
    listVehiclesMock
      .mockResolvedValueOnce(populatedVehicles)
      .mockResolvedValue([...populatedVehicles, added]);

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("button", { name: "Завести ТС" }),
    ).toBeInTheDocument();
    expect(uxBudgetDelta(document.body, "RoadSafetyPage").unexpected).toEqual(
      [],
    );

    await user.click(screen.getByRole("button", { name: "Завести ТС" }));
    await user.type(screen.getByLabelText("Госномер"), "Х777ХХ777");
    await user.type(screen.getByLabelText("Марка и модель"), "КамАЗ-65115");
    await user.selectOptions(screen.getByLabelText("Вид ТС"), "truck");
    await user.type(
      screen.getByLabelText("Диагностическая карта до"),
      "2027-04-01",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createVehicleMock).toHaveBeenCalled());
    expect(createVehicleMock.mock.calls[0][0]).toMatchObject({
      plate_number: "Х777ХХ777",
      brand_model: "КамАЗ-65115",
      kind: "truck",
      status: "in_service",
      inspection_due: "2027-04-01",
      // Полис не внесён — это «сведений нет», а не «бессрочно».
      insurance_due: null,
      tachograph_installed: false,
    });
    expect(await screen.findByText("Х777ХХ777")).toBeInTheDocument();
  });

  it("карточка водителя заводится с экрана (срез-107)", async () => {
    const user = userEvent.setup();
    const added = {
      ...populatedDrivers[0],
      id: "d-new",
      person_name: "Шофёров Пётр Иванович",
      license_number: "9900 654321",
    };
    createDriverMock.mockResolvedValue(added);
    listDriversMock
      .mockResolvedValueOnce(populatedDrivers)
      .mockResolvedValue([...populatedDrivers, added]);

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("button", { name: "Водители" }));

    await user.click(screen.getByRole("button", { name: "Завести водителя" }));
    await user.selectOptions(screen.getByLabelText("Работник"), "p-1");
    await user.type(
      screen.getByLabelText("Номер удостоверения"),
      "9900 654321",
    );
    await user.click(screen.getByRole("checkbox", { name: "C" }));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDriverMock).toHaveBeenCalled());
    expect(createDriverMock.mock.calls[0][0]).toMatchObject({
      person_id: "p-1",
      license_number: "9900 654321",
      categories: ["C"],
      status: "admitted",
      // Стаж задаётся датой; пусто — «сведения не внесены», а не «0 лет».
      experience_since: null,
    });
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
    // Срез-5: инструктажи БДД считаются, но своего журнала контур не заводит.
    expect(screen.getByText("Инструктаж БДД просрочен")).toBeInTheDocument();
    // Срез-6: проверки знаний ПДД — тоже без своего реестра.
    expect(screen.getByText("Проверка знаний просрочена")).toBeInTheDocument();
    // Срез-7: стажировки — тоже общим механизмом, без своего реестра.
    expect(screen.getByText("Стажировка с недобором смен")).toBeInTheDocument();
    expect(
      screen.getByText(/общим механизмом стажировок/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/в общем реестре аттестаций/i)).toBeInTheDocument();
    expect(
      screen.getByText(/ведутся в общем журнале инструктажей/i),
    ).toBeInTheDocument();
  });

  it("открывается на водителе по ссылке из карточки сотрудника (срез-67)", async () => {
    listDriversMock.mockResolvedValue([populatedDrivers[0]]);
    render(
      <MemoryRouter
        initialEntries={["/road-safety?section=drivers&person_id=p-1"]}
      >
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    // Секция из адреса — сразу «Водители», без клика; отбор — на сервере.
    // Имя встречается дважды: в строке таблицы и на плашке отбора.
    expect(
      await screen.findByRole("cell", { name: "Шофёров Пётр Иванович" }),
    ).toBeInTheDocument();
    expect(listDriversMock).toHaveBeenCalledWith({ person_id: "p-1" });
    // Плашка называет человека и ведёт обратно в карточку сотрудника.
    const chip = screen.getByTestId("road-safety-person-filter");
    expect(chip).toHaveTextContent("Водитель: Шофёров Пётр Иванович");
    expect(
      within(chip).getByRole("link", { name: "карточка" }),
    ).toHaveAttribute("href", "/employees/p-1");

    // «все» — снимает отбор: список перечитывается без person_id.
    listDriversMock.mockResolvedValue(populatedDrivers);
    await userEvent.click(
      screen.getByRole("button", { name: "Показать всех водителей" }),
    );
    await waitFor(() => expect(listDriversMock).toHaveBeenLastCalledWith({}));
    expect(
      screen.queryByTestId("road-safety-person-filter"),
    ).not.toBeInTheDocument();
  });

  it("у сотрудника без карточки водителя — честная пустота, а не весь состав (срез-67)", async () => {
    listDriversMock.mockResolvedValue([]);
    render(
      <MemoryRouter
        initialEntries={["/road-safety?section=drivers&person_id=p-9"]}
      >
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Карточки водителя нет"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("road-safety-person-filter")).toHaveTextContent(
      "p-9",
    );
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
    listAccidentsMock.mockResolvedValue([]);
    listViolationsMock.mockResolvedValue([]);
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
      accident_window_days: 365,
      accidents_total: 0,
      accidents_by_consequences: { damage_only: 0, injured: 0, fatal: 0 },
      injured_total: 0,
      fatalities_total: 0,
      accidents_without_follow_up: 0,
      road_briefings_total: 0,
      road_briefings_overdue: 0,
      knowledge_checks_total: 0,
      knowledge_checks_overdue: 0,
      internships_total: 0,
      internships_in_progress: 0,
      internships_completed_short: 0,
      violation_window_days: 365,
      violations_total: 0,
      violations_without_driver: 0,
      fines_unpaid_count: 0,
      fines_unpaid_amount: 0,
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
    await userEvent.click(
      screen.getByRole("button", { name: "Путевые листы" }),
    );

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
    await userEvent.click(
      screen.getByRole("button", { name: "Путевые листы" }),
    );

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
    await userEvent.click(
      screen.getByRole("button", { name: "Путевые листы" }),
    );
    expect(await screen.findByText("ПЛ-001")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "RoadSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("секция ДТП показывает последствия, разбор и границу", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ДТП" }));

    expect(await screen.findByText("45 км трассы М-4")).toBeInTheDocument();
    // Тяжесть считает сервер из чисел людей — экран печатает посчитанное.
    expect(screen.getByText("Есть пострадавшие")).toBeInTheDocument();
    expect(screen.getByText("Только материальный ущерб")).toBeInTheDocument();
    // Пустой водитель — это «за рулём никого не было», а не «неизвестно кто».
    expect(screen.getByText("За рулём никого не было")).toBeInTheDocument();
    // Разбор — следствие связей, а не галочка.
    expect(screen.getByText("Есть незакрытые мероприятия")).toBeInTheDocument();
    expect(screen.getByText("Мероприятия не заведены")).toBeInTheDocument();
    // Граница названа на экране.
    expect(screen.getByText(/не устанавливает вину/i)).toBeInTheDocument();
  });

  it("пустой учёт ДТП объясняет, что вносить", async () => {
    listAccidentsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      ...populatedReadiness,
      accidents_total: 0,
      accidents_by_consequences: { damage_only: 0, injured: 0, fatal: 0 },
      injured_total: 0,
      fatalities_total: 0,
      accidents_without_follow_up: 0,
    });

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ДТП" }));

    expect(
      await screen.findByText("ДТП не зарегистрированы"),
    ).toBeInTheDocument();
  });

  it("плитки шапки меняются вместе с секцией", async () => {
    /**
     * Общий набор дорос бы до пятнадцати чисел о четырёх разных задачах —
     * ровно то, что запрещает «одна задача — один экран» (разд. 59).
     * Проверяем, что чужие плитки НЕ показываются: без этого набор снова
     * начнёт расти и никто не заметит.
     */

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Транспортных средств")).toBeInTheDocument();
    expect(screen.queryByText("Погибло людей")).not.toBeInTheDocument();
    expect(screen.queryByText("Водителей")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "ДТП" }));

    expect(await screen.findByText("Погибло людей")).toBeInTheDocument();
    expect(screen.getByText("ДТП за 365 дн.")).toBeInTheDocument();
    expect(screen.queryByText("Транспортных средств")).not.toBeInTheDocument();
  });

  it("секция ДТП остаётся в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ДТП" }));
    expect(await screen.findByText("45 км трассы М-4")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "RoadSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("секция нарушений различает «не наложен» и «не оплачен»", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Нарушения" }));

    expect(
      await screen.findByText("Автоматическая фиксация (камера)"),
    ).toBeInTheDocument();
    // Пустой водитель — «не установлен», а не «неизвестно кто».
    expect(screen.getByText("Не установлен")).toBeInTheDocument();
    expect(screen.getByText("Не оплачен")).toBeInTheDocument();
    expect(screen.getByText("Оплачен")).toBeInTheDocument();
    // Граница названа на экране.
    expect(
      screen.getByText(/не устанавливает.{0,20}виновность/i),
    ).toBeInTheDocument();
  });

  it("пустой реестр нарушений объясняет, что вносить", async () => {
    listViolationsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      ...populatedReadiness,
      violations_total: 0,
      violations_without_driver: 0,
      fines_unpaid_count: 0,
      fines_unpaid_amount: 0,
    });

    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Нарушения" }));

    expect(
      await screen.findByText("Нарушения не зарегистрированы"),
    ).toBeInTheDocument();
  });

  it("секция нарушений остаётся в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Нарушения" }));
    expect(
      await screen.findByText("Автоматическая фиксация (камера)"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "RoadSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("открытые происшествия контура: число из сводки и ссылка в реестр (срез-49)", async () => {
    render(
      <MemoryRouter>
        <RoadSafetyPage />
      </MemoryRouter>,
    );

    // плитка живёт в секции ДТП: рядом с реестром ДТП, чтобы не путать одно
    // с другим — это ОБЩИЙ реестр происшествий, размеченных БДД
    expect(await screen.findByText("А123АА777")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ДТП" }));

    expect(
      await screen.findByText("Открытых происшествий"),
    ).toBeInTheDocument();
    // число — из сводки бэкенда (та же формула, что разрез у директора), а
    // ссылка ведёт в ОБЩИЙ реестр с уже выставленным фильтром дисциплины
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute(
      "href",
      "/incidents?discipline=road_safety&status=open",
    );
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
