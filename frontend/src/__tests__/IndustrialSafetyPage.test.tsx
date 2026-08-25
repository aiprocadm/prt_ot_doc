import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IndustrialSafetyPage from "@/pages/industrial-safety/IndustrialSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFacilitiesMock = vi.fn();
const listDevicesMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/industrialSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  industrialSafetyApi: {
    listFacilities: (...args: unknown[]) => listFacilitiesMock(...args),
    listDevices: (...args: unknown[]) => listDevicesMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

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

const populatedReadiness = {
  total_facilities: 2,
  by_class: { I: 0, II: 0, III: 1, IV: 1 },
  excluded_facilities: 1,
  total_devices: 2,
  epb_overdue: 1,
  epb_due_soon: 0,
  devices_past_lifetime_without_epb: 1,
  devices_without_work_record: 1,
};

describe("IndustrialSafetyPage", () => {
  beforeEach(() => {
    listFacilitiesMock.mockReset();
    listDevicesMock.mockReset();
    readinessMock.mockReset();
    listFacilitiesMock.mockResolvedValue(populatedFacilities);
    listDevicesMock.mockResolvedValue(populatedDevices);
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
});
