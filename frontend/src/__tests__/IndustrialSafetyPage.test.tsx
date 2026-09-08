import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

import IndustrialSafetyPage from "@/pages/industrial-safety/IndustrialSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFacilitiesMock = vi.fn();
const listDevicesMock = vi.fn();
const listAttestationsMock = vi.fn();
const listPcMeasuresMock = vi.fn();
const readinessMock = vi.fn();
const createFacilityMock = vi.fn();
const createDeviceMock = vi.fn();
const recordDeviceWorkMock = vi.fn();
const listSitesMock = vi.fn();
const listPcPlansMock = vi.fn();
const createPcPlanMock = vi.fn();
const createPcMeasureMock = vi.fn();
const createAttestationMock = vi.fn();
const fetchAllPersonsMock = vi.fn();

vi.mock("@/api/industrialSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  industrialSafetyApi: {
    listFacilities: (...args: unknown[]) => listFacilitiesMock(...args),
    listDevices: (...args: unknown[]) => listDevicesMock(...args),
    listAttestations: (...args: unknown[]) => listAttestationsMock(...args),
    listPcMeasures: (...args: unknown[]) => listPcMeasuresMock(...args),
    listPcPlans: (...args: unknown[]) => listPcPlansMock(...args),
    createPcPlan: (...args: unknown[]) => createPcPlanMock(...args),
    createPcMeasure: (...args: unknown[]) => createPcMeasureMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
    createFacility: (...args: unknown[]) => createFacilityMock(...args),
    createDevice: (...args: unknown[]) => createDeviceMock(...args),
    recordDeviceWork: (...args: unknown[]) => recordDeviceWorkMock(...args),
  },
}));

vi.mock("@/api/sites", () => ({
  sitesApi: { list: (...args: unknown[]) => listSitesMock(...args) },
}));

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: (...args: unknown[]) => fetchAllPersonsMock(...args),
}));

vi.mock("@/api/attestations", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  attestationsApi: {
    create: (...args: unknown[]) => createAttestationMock(...args),
    update: vi.fn(),
  },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

/** Устройства: одно отработало срок службы, у другого просрочено заключение. */
const populatedDevices = [
  {
    id: "dev-1",
    facility_id: "opo-1",
    kind: "pressure_vessel",
    kind_label: "Сосуд, работающий под давлением",
    name: "Ресивер воздушный Р-1",
    serial_number: "12345",
    commissioned_on: "2009-05-20",
    lifetime_until: "2024-05-20",
    epb_conclusion_number: null,
    epb_registered_on: null,
    epb_valid_until: null,
    status: "in_operation",
    status_label: "В эксплуатации",
    notes: null,
    epb_status: "absent",
    epb_status_label: "Заключения нет",
    past_lifetime: true,
    // Работ по устройству не было ни разу.
    last_work_on: null,
    last_work_result: null,
  },
  {
    id: "dev-2",
    facility_id: "opo-1",
    kind: "boiler",
    kind_label: "Котёл",
    name: "Котёл ДКВР-10",
    serial_number: null,
    commissioned_on: null,
    lifetime_until: null,
    epb_conclusion_number: "ДЭ-03-00001-2018",
    epb_registered_on: "2018-03-01",
    epb_valid_until: "2020-03-01",
    status: "in_operation",
    status_label: "В эксплуатации",
    notes: null,
    epb_status: "overdue",
    epb_status_label: "Заключение просрочено",
    past_lifetime: false,
    last_work_on: "2018-03-01",
    last_work_result: "with_remarks",
  },
];

/** Два ОПО на одной площадке — то, чего полями площадки не выразить. */
const populatedFacilities = [
  {
    id: "opo-1",
    name: "Сеть газопотребления котельной",
    register_number: "А01-12345-0001",
    hazard_class: "III",
    hazard_class_label: "III класс — средняя опасность",
    site_id: "site-1",
    registered_on: "2021-06-15",
    excluded_on: null,
    status: "registered",
    status_label: "Зарегистрирован",
    responsible: "Главный инженер Петров",
    notes: null,
  },
  {
    id: "opo-2",
    name: "Площадка кранов",
    register_number: "А01-12345-0002",
    hazard_class: "IV",
    hazard_class_label: "IV класс — низкая опасность",
    site_id: "site-1",
    registered_on: null,
    excluded_on: null,
    status: "registered",
    status_label: "Зарегистрирован",
    responsible: null,
    notes: null,
  },
];

/** Аттестация: одна действует, одна просрочена. */
const populatedAttestations = [
  {
    id: "att-1",
    person_id: "p-1",
    person_name: "Петров Пётр",
    name: "Аттестация по промышленной безопасности",
    area_code: "Б.9",
    area_label: "Б.9 — подъёмные сооружения",
    issued_at: "2024-02-01",
    expires_at: "2029-02-01",
    validity_status: "ok",
    validity_status_label: "Действует",
  },
  {
    id: "att-2",
    person_id: "p-2",
    person_name: "Сидоров Сидор",
    name: "Аттестация по промышленной безопасности",
    area_code: "Б.8",
    area_label: "Б.8 — оборудование, работающее под избыточным давлением",
    issued_at: "2015-05-05",
    expires_at: "2020-05-05",
    validity_status: "overdue",
    validity_status_label: "Просрочена",
  },
];

/** Мероприятия ПК: одно просрочено, одно выполнено. */
const populatedMeasures = [
  {
    id: "m-1",
    plan_id: "plan-1",
    section: "violations",
    section_label: "Устранение выявленных нарушений",
    title: "Устранение замечаний прошлой проверки",
    due_on: "2026-08-01",
    responsible: "Механик Сидоров",
    status: "overdue",
    status_label: "Просрочено",
    completed_on: null,
    result: null,
  },
  {
    id: "m-2",
    plan_id: "plan-1",
    section: "reporting",
    section_label: "Отчётность в надзорные органы",
    title: "Отчёт в Ростехнадзор",
    due_on: "2026-04-01",
    responsible: null,
    status: "done",
    status_label: "Выполнено",
    completed_on: "2026-03-30",
    result: "Отчёт направлен",
  },
];

const populatedReadiness = {
  total_facilities: 2,
  by_class: { I: 0, II: 0, III: 1, IV: 1 },
  excluded_facilities: 1,
  total_devices: 2,
  epb_overdue: 1,
  epb_due_soon: 0,
  devices_past_lifetime_without_epb: 1,
  devices_without_work_record: 1,
  attestations_total: 2,
  attestations_overdue: 1,
  attestations_due_soon: 0,
  current_year_plan_exists: true,
  pc_measures_overdue: 1,
  pc_measures_planned: 0,
  incidents_open: 3,
};

describe("IndustrialSafetyPage", () => {
  beforeEach(() => {
    // Срез-120: кнопки записи закрыты правом `<контур>.manage` — экран
    // рендерится от лица того, кому запись разрешена.
    useAuthStore.setState({
      user: {
        id: "discipline-writer",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "writer@example.com",
        full_name: "Discipline Writer",
        roles: ["ot_specialist"],
        permissions: [
          PERMISSIONS.INDUSTRIAL_SAFETY_VIEW,
          PERMISSIONS.INDUSTRIAL_SAFETY_MANAGE,
        ],
        attributes: { tenant_id: "tenant-1" },
      },
      loading: false,
      error: null,
    } as never);
    listFacilitiesMock.mockReset();
    listDevicesMock.mockReset();
    listAttestationsMock.mockReset();
    listPcMeasuresMock.mockReset();
    readinessMock.mockReset();
    createFacilityMock.mockReset();
    createDeviceMock.mockReset();
    recordDeviceWorkMock.mockReset();
    listSitesMock.mockReset();
    listSitesMock.mockResolvedValue({
      items: [{ id: "site-1", name: "Площадка №1" }],
      total: 1,
    });
    listPcPlansMock.mockReset();
    createPcPlanMock.mockReset();
    createPcMeasureMock.mockReset();
    createAttestationMock.mockReset();
    fetchAllPersonsMock.mockReset();
    listPcPlansMock.mockResolvedValue([
      {
        id: "plan-1",
        year: 2026,
        title: "План ПК на 2026 год",
        responsible: "Петров",
        approved_on: "2026-01-10",
        status: "approved",
        status_label: "Утверждён",
        notes: null,
        measures_total: 1,
        measures_overdue: 0,
      },
    ]);
    fetchAllPersonsMock.mockResolvedValue([
      { id: "person-1", full_name: "Иванов Иван Иванович" },
    ]);
    listFacilitiesMock.mockResolvedValue(populatedFacilities);
    listDevicesMock.mockResolvedValue(populatedDevices);
    listAttestationsMock.mockResolvedValue(populatedAttestations);
    listPcMeasuresMock.mockResolvedValue(populatedMeasures);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("рисует реестр ОПО с классом словами", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    // Класс — словами, а не кодом «III»: код человеку ничего не говорит.
    expect(
      screen.getByText("III класс — средняя опасность"),
    ).toBeInTheDocument();
    expect(screen.getByText("А01-12345-0001")).toBeInTheDocument();
    // Два объекта на ОДНОЙ площадке — ради этого реестр и заводился.
    expect(screen.getByText("Площадка кранов")).toBeInTheDocument();
  });

  it("разрез по классам виден в шапке", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    // От класса зависит режим надзора: I и II — постоянный госнадзор.
    expect(await screen.findByText("I класс")).toBeInTheDocument();
    expect(screen.getByText("II класс")).toBeInTheDocument();
    expect(screen.getByText(/действующих ОПО/i)).toBeInTheDocument();
    expect(screen.getByText(/исключено из реестра/i)).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listFacilitiesMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_facilities: 0,
      by_class: { I: 0, II: 0, III: 0, IV: 0 },
      excluded_facilities: 0,
    });

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/объекты не заведены/i)).toBeInTheDocument();
    // Подсказка называет и источник сведений, и то, что объектов бывает много.
    expect(
      screen.getByText(/свидетельства о регистрации/i),
    ).toBeInTheDocument();
  });

  // Доп. №1 разд. 54.2 срез-2: технические устройства и ЭПБ. Ядровые
  // Asset/Equipment — две и три колонки без ручек и без сроков, учитывать по
  // ним экспертизу нечем.
  it("объект ОПО заводится с экрана, а не только через API (срез-105)", async () => {
    const user = userEvent.setup();
    const added = {
      ...populatedFacilities[0],
      id: "opo-new",
      name: "Склад ГСМ",
      register_number: "А01-99999-0009",
    };
    createFacilityMock.mockResolvedValue(added);
    listFacilitiesMock
      .mockResolvedValueOnce(populatedFacilities)
      .mockResolvedValue([...populatedFacilities, added]);

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("button", { name: "Завести объект" }),
    ).toBeInTheDocument();
    expect(
      uxBudgetDelta(document.body, "IndustrialSafetyPage").unexpected,
    ).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Завести объект" }));
    await user.type(screen.getByLabelText("Объект"), "Склад ГСМ");
    await user.type(screen.getByLabelText("Номер в реестре"), "А01-99999-0009");
    await user.selectOptions(screen.getByLabelText("Класс опасности"), "III");
    await user.selectOptions(screen.getByLabelText("Площадка"), "site-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createFacilityMock).toHaveBeenCalled());
    expect(createFacilityMock.mock.calls[0][0]).toMatchObject({
      name: "Склад ГСМ",
      register_number: "А01-99999-0009",
      hazard_class: "III",
      site_id: "site-1",
      status: "registered",
    });
    expect(await screen.findByText("Склад ГСМ")).toBeInTheDocument();
  });

  it("устройство и работа по нему заводятся с экрана (срез-105)", async () => {
    const user = userEvent.setup();
    const added = {
      ...populatedDevices[0],
      id: "dev-new",
      name: "Котёл КВ-2",
    };
    createDeviceMock.mockResolvedValue(added);
    recordDeviceWorkMock.mockResolvedValue({ id: "work-new" });
    listDevicesMock
      .mockResolvedValueOnce(populatedDevices)
      .mockResolvedValue([...populatedDevices, added]);

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Технические устройства" }),
    );

    await user.click(
      screen.getByRole("button", { name: "Завести устройство" }),
    );
    await user.selectOptions(screen.getByLabelText("Объект (ОПО)"), "opo-1");
    await user.selectOptions(screen.getByLabelText("Вид устройства"), "boiler");
    await user.type(screen.getByLabelText("Устройство"), "Котёл КВ-2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDeviceMock).toHaveBeenCalled());
    expect(createDeviceMock.mock.calls[0][0]).toMatchObject({
      facility_id: "opo-1",
      kind: "boiler",
      name: "Котёл КВ-2",
      status: "in_operation",
      // Заключения ЭПБ нет — это отдельное состояние, а не пустая просрочка.
      epb_conclusion_number: null,
      epb_valid_until: null,
    });

    // Работа записывается прямо из строки: устройство подставлено.
    await user.click(screen.getAllByRole("button", { name: "Работа" })[0]);
    expect(screen.getByLabelText("Устройство")).toHaveValue(
      populatedDevices[0].id,
    );
    await user.type(screen.getByLabelText("Дата работы"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(recordDeviceWorkMock).toHaveBeenCalled());
    expect(recordDeviceWorkMock.mock.calls[0][0]).toMatchObject({
      device_id: populatedDevices[0].id,
      kind: "diagnostics",
      performed_on: "2026-09-01",
      result: "passed",
    });
  });

  it("устройства открываются второй секцией с состоянием экспертизы", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Технические устройства" }),
    );

    expect(
      await screen.findByText("Ресивер воздушный Р-1"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Сосуд, работающий под давлением"),
    ).toBeInTheDocument();
    // «Заключения нет» — отдельное состояние, а не «просрочено».
    expect(screen.getByText("Заключения нет")).toBeInTheDocument();
    expect(screen.getByText("Заключение просрочено")).toBeInTheDocument();
    // Истёкший срок службы назван истёкшим, а не просто датой в прошлом.
    expect(screen.getByText(/· истёк$/)).toBeInTheDocument();
  });

  // Доп. №1 разд. 54.2 срез-3: история работ. До неё отметить проведённую
  // экспертизу можно было единственным способом — затереть срок правкой поля.
  it("показывает последнюю работу и называет её отсутствие", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Технические устройства" }),
    );

    expect(
      await screen.findByText("Ресивер воздушный Р-1"),
    ).toBeInTheDocument();
    // Результат — словами, а не кодом «with_remarks».
    expect(screen.getByText(/Пригодно с условиями/)).toBeInTheDocument();
    // Отсутствие записей названо словами, а не пустой ячейкой.
    expect(screen.getByText("нет записей")).toBeInTheDocument();
    // И то же самое числом в шапке.
    expect(screen.getByText(/без записей о работах/i)).toBeInTheDocument();
  });

  it("экран не выдаёт требование ЭПБ за своё суждение", async () => {
    // ГРАНИЦА названа НА ЭКРАНЕ: нужна ли экспертиза конкретному устройству,
    // из данных не следует — это зависит от типа устройства и норм ФНП.
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Технические устройства" }),
    );

    expect(
      await screen.findByText(/определяет специалист/i),
    ).toBeInTheDocument();
  });

  // Доп. №1 разд. 54.2 срез-4: аттестация. Область жила в свободной строке
  // `name`, а экрана у ядровых аттестаций не было ни одного.
  it("аттестация открывается третьей секцией с областью словами", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Аттестация персонала" }),
    );

    expect(await screen.findByText("Петров Пётр")).toBeInTheDocument();
    // Область — словами, а не кодом «Б.9».
    expect(screen.getByText("Б.9 — подъёмные сооружения")).toBeInTheDocument();
    // Просроченная аттестация названа просроченной.
    expect(screen.getByText("Просрочена")).toBeInTheDocument();
    // И то же самое числом в шапке.
    expect(screen.getByText(/просрочено аттестаций/i)).toBeInTheDocument();
  });

  // Доп. №1 разд. 54.2 срез-5: производственный контроль. В коде не было
  // ничего — `production_control` встречался лишь подписью поля в
  // экологическом комплекте документов.
  it("производственный контроль открывается четвёртой секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Производственный контроль" }),
    );

    expect(
      await screen.findByText("Устранение замечаний прошлой проверки"),
    ).toBeInTheDocument();
    // Раздел плана и состояние — словами.
    expect(
      screen.getByText("Устранение выявленных нарушений"),
    ).toBeInTheDocument();
    expect(screen.getByText("Просрочено")).toBeInTheDocument();
    // «Выполнено» — и заголовок колонки, и состояние мероприятия: проверяем
    // именно состояние, поэтому смотрим на второе мероприятие целиком.
    expect(screen.getByText("Отчёт в Ростехнадзор")).toBeInTheDocument();
    expect(screen.getAllByText("Выполнено").length).toBeGreaterThan(1);
  });

  it("план ПК и мероприятие заводятся с экрана (срез-106)", async () => {
    const user = userEvent.setup();
    createPcPlanMock.mockResolvedValue({ id: "plan-new" });
    createPcMeasureMock.mockResolvedValue({ id: "measure-new" });

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Производственный контроль" }),
    );

    await user.click(screen.getByRole("button", { name: "Завести план ПК" }));
    await user.type(
      screen.getByLabelText("План"),
      "План производственного контроля на 2027 год",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createPcPlanMock).toHaveBeenCalled());
    expect(createPcPlanMock.mock.calls[0][0]).toMatchObject({
      title: "План производственного контроля на 2027 год",
      status: "draft",
      approved_on: null,
    });

    await user.click(
      screen.getByRole("button", { name: "Запланировать мероприятие" }),
    );
    await user.selectOptions(screen.getByLabelText("План ПК"), "plan-1");
    await user.selectOptions(screen.getByLabelText("Раздел плана"), "epb");
    await user.type(
      screen.getByLabelText("Мероприятие"),
      "Диагностирование сосудов",
    );
    await user.type(screen.getByLabelText("Срок"), "2027-03-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createPcMeasureMock).toHaveBeenCalled());
    expect(createPcMeasureMock.mock.calls[0][0]).toMatchObject({
      plan_id: "plan-1",
      section: "epb",
      title: "Диагностирование сосудов",
      due_on: "2027-03-01",
      status: "planned",
      completed_on: null,
    });
  });

  it("аттестация вносится с экрана, область — только промбезопасности (срез-106)", async () => {
    const user = userEvent.setup();
    createAttestationMock.mockResolvedValue({ id: "att-new" });

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Аттестация персонала" }),
    );

    await user.click(screen.getByRole("button", { name: "Внести аттестацию" }));
    // В списке областей нет «ПДД»: это область другой дисциплины, и запись по
    // ней в реестр ОПО не попала бы.
    const areaOptions = Array.from(
      screen.getByLabelText("Область аттестации").querySelectorAll("option"),
    ).map((option) => option.getAttribute("value"));
    expect(areaOptions).toContain("Б.9");
    expect(areaOptions).not.toContain("ПДД");

    await user.selectOptions(screen.getByLabelText("Работник"), "person-1");
    await user.selectOptions(
      screen.getByLabelText("Область аттестации"),
      "Б.9",
    );
    await user.type(
      screen.getByLabelText("Аттестация"),
      "Аттестация по промбезопасности Б.9",
    );
    await user.type(screen.getByLabelText("Действует до"), "2029-06-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createAttestationMock).toHaveBeenCalled());
    expect(createAttestationMock.mock.calls[0][0]).toMatchObject({
      person_id: "person-1",
      area_code: "Б.9",
      name: "Аттестация по промбезопасности Б.9",
      status: "active",
      expires_at: "2029-06-01",
    });
  });

  it("экран не объявляет отсутствие плана ПК нарушением", async () => {
    // ГРАНИЦА названа НА ЭКРАНЕ: обязанность вести производственный контроль
    // зависит от того, эксплуатирует ли организация ОПО.
    listPcMeasuresMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      ...populatedReadiness,
      current_year_plan_exists: false,
      pc_measures_overdue: 0,
    });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Производственный контроль" }),
    );

    expect(
      await screen.findByText(/применимость определяет специалист/i),
    ).toBeInTheDocument();
  });

  it("открытые происшествия контура: число из сводки и ссылка в реестр (срез-49)", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Открытых происшествий"),
    ).toBeInTheDocument();
    // число — из сводки бэкенда (та же формула, что разрез у директора), а
    // ссылка ведёт в ОБЩИЙ реестр с уже выставленным фильтром дисциплины
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute(
      "href",
      "/incidents?discipline=industrial_safety&status=open",
    );
  });

  it("IndustrialSafetyPage в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "IndustrialSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("без права на запись кнопки записи не показываются (срез-120)", async () => {
    // Читателю контура экран доступен целиком, а вести записи он не может:
    // сервер такой запрос отклонит, и предлагать форму — обманывать человека.
    useAuthStore.setState({
      user: {
        id: "discipline-reader",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "reader@example.com",
        full_name: "Discipline Reader",
        roles: ["line_manager"],
        permissions: [PERMISSIONS.INDUSTRIAL_SAFETY_VIEW],
        attributes: { tenant_id: "tenant-1" },
      },
      loading: false,
      error: null,
    } as never);

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Завести план ПК" }),
      ).not.toBeInTheDocument(),
    );
  });
});
