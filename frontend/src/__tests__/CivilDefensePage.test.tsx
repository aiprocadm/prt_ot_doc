import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CivilDefensePage from "@/pages/civilDefense/CivilDefensePage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFormationsMock = vi.fn();
const listDrillsMock = vi.fn();
const listProfilesMock = vi.fn();
const listDocumentsMock = vi.fn();
const listProgramsMock = vi.fn();
const readinessMock = vi.fn();
const createFormationMock = vi.fn();
const createDrillMock = vi.fn();
const updateDrillMock = vi.fn();
const fetchAllPersonsMock = vi.fn();
const listSitesMock = vi.fn();
const createProfileMock = vi.fn();
const createDocumentMock = vi.fn();
const listMembersMock = vi.fn();
const addMemberMock = vi.fn();
const updateMemberMock = vi.fn();

vi.mock("@/api/civilDefense", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  civilDefenseApi: {
    createFormation: (...args: unknown[]) => createFormationMock(...args),
    createProfile: (...args: unknown[]) => createProfileMock(...args),
    updateProfile: vi.fn(),
    createDocument: (...args: unknown[]) => createDocumentMock(...args),
    updateDocument: vi.fn(),
    listFormationMembers: (...args: unknown[]) => listMembersMock(...args),
    addFormationMember: (...args: unknown[]) => addMemberMock(...args),
    updateFormationMember: (...args: unknown[]) => updateMemberMock(...args),
    updateFormation: vi.fn(),
    createDrill: (...args: unknown[]) => createDrillMock(...args),
    updateDrill: (...args: unknown[]) => updateDrillMock(...args),
    listFormations: (...args: unknown[]) => listFormationsMock(...args),
    listDrills: (...args: unknown[]) => listDrillsMock(...args),
    listProfiles: (...args: unknown[]) => listProfilesMock(...args),
    listDocuments: (...args: unknown[]) => listDocumentsMock(...args),
    listTrainingPrograms: (...args: unknown[]) => listProgramsMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: (...args: unknown[]) => fetchAllPersonsMock(...args),
}));

vi.mock("@/api/sites", () => ({
  sitesApi: { list: (...args: unknown[]) => listSitesMock(...args) },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

/** Доп. №1 разд. 56.1 срез-1: формирования с командиром и без. */
const populatedFormations = [
  {
    id: "cd-1",
    name: "Звено пожаротушения",
    kind: "nasf",
    kind_label: "НАСФ (аварийно-спасательное формирование)",
    purpose: "Тушение возгораний до прибытия подразделений",
    commander_person_id: "p-1",
    commander_name: "Командиров Пётр Иванович",
    equipment_notes: null,
    notes: null,
    members_active: 3,
  },
  {
    id: "cd-2",
    name: "Эвакуационная группа",
    kind: "nfgo",
    kind_label: "НФГО (формирование по обеспечению ГО)",
    purpose: null,
    commander_person_id: null,
    commander_name: null,
    equipment_notes: null,
    notes: null,
    members_active: 0,
  },
];

/** Учения: просроченное общеобъектовое и проведённое силами звена. */
const populatedDrills = [
  {
    id: "d-1",
    kind: "facility_training",
    kind_label: "Объектовая тренировка",
    title: "Тренировка по сигналу «Внимание всем»",
    planned_on: "2026-08-01",
    held_on: null,
    formation_id: null,
    formation_name: null,
    site_id: null,
    scenario: null,
    participants: null,
    outcome: null,
    outcome_label: null,
    findings: null,
    status: "overdue",
    status_label: "Просрочено",
  },
  {
    id: "d-2",
    kind: "command_staff",
    kind_label: "Командно-штабное учение",
    title: "КШУ по ликвидации ЧС",
    planned_on: "2026-06-10",
    held_on: "2026-06-10",
    formation_id: "cd-1",
    formation_name: "Звено пожаротушения",
    site_id: null,
    scenario: null,
    participants: 24,
    outcome: "with_remarks",
    outcome_label: "Проведено с замечаниями",
    findings: null,
    status: "held",
    status_label: "Проведено",
  },
];

/** Сведения по ГО: объект второй категории и объект без категории. */
const populatedProfiles = [
  {
    id: "p-1",
    site_id: "s-1",
    site_name: "Производственная площадка",
    category: "second",
    category_label: "Вторая категория по ГО",
    decision_number: "Решение от 12.03.2025 №14",
    decision_date: "2025-03-12",
    responsible: "Петров П.П.",
    notes: null,
  },
  {
    id: "p-2",
    site_id: "s-2",
    site_name: "Склад",
    category: "none",
    category_label: "Категория не присвоена",
    decision_number: null,
    decision_date: null,
    responsible: null,
    notes: null,
  },
];

/** Документы планирования: бессрочный приказ и просроченный план. */
const populatedDocuments = [
  {
    id: "doc-1",
    kind: "order",
    kind_label: "Приказ",
    title: "Приказ о создании формирований",
    number: "12-ГО",
    site_id: null,
    approved_on: "2025-02-01",
    review_due: null,
    responsible: null,
    notes: null,
    review_status: "ok",
    review_status_label: "Действует",
  },
  {
    id: "doc-2",
    kind: "plan_go",
    kind_label: "План гражданской обороны",
    title: "План гражданской обороны организации",
    number: null,
    site_id: null,
    approved_on: "2020-05-05",
    review_due: "2026-01-01",
    responsible: null,
    notes: null,
    review_status: "overdue",
    review_status_label: "Просрочен пересмотр",
  },
];

/** Программы обучения ЯДРА, размеченные дисциплиной ГО. */
const populatedPrograms = [
  {
    id: "tc-1",
    title: "Курсовое обучение по ГО",
    code: "ГО-16",
    duration_hours: 16,
    valid_period_days: 365,
  },
  {
    id: "tc-2",
    title: "Вводный инструктаж по ГО",
    code: null,
    duration_hours: null,
    valid_period_days: null,
  },
];

const populatedReadiness = {
  total_formations: 2,
  by_kind: { nasf: 1, nfgo: 1 },
  without_commander: 1,
  members_active: 3,
  drills_total: 2,
  drills_overdue: 1,
  drills_held_this_year: 1,
  profiles_total: 2,
  profiles_by_category: { special: 0, first: 0, second: 1, none: 1 },
  planning_documents: 2,
  planning_review_overdue: 1,
  training_programs: 2,
  incidents_open: 3,
};

describe("CivilDefensePage", () => {
  beforeEach(() => {
    listFormationsMock.mockReset();
    listDrillsMock.mockReset();
    listProfilesMock.mockReset();
    listDocumentsMock.mockReset();
    listProgramsMock.mockReset();
    readinessMock.mockReset();
    createFormationMock.mockReset();
    createDrillMock.mockReset();
    updateDrillMock.mockReset();
    fetchAllPersonsMock.mockReset();
    fetchAllPersonsMock.mockResolvedValue([
      { id: "person-1", full_name: "Иванов Иван Иванович" },
    ]);
    listSitesMock.mockReset();
    createProfileMock.mockReset();
    createDocumentMock.mockReset();
    listMembersMock.mockReset();
    addMemberMock.mockReset();
    updateMemberMock.mockReset();
    listSitesMock.mockResolvedValue({
      items: [{ id: "site-1", name: "Площадка №1" }],
      total: 1,
    });
    listMembersMock.mockResolvedValue([]);
    listFormationsMock.mockResolvedValue(populatedFormations);
    listDrillsMock.mockResolvedValue(populatedDrills);
    listProfilesMock.mockResolvedValue(populatedProfiles);
    listDocumentsMock.mockResolvedValue(populatedDocuments);
    listProgramsMock.mockResolvedValue(populatedPrograms);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("состав формирования читается по кнопке и пополняется (срез-110)", async () => {
    const user = userEvent.setup();
    listMembersMock.mockResolvedValue([
      {
        id: "m-1",
        formation_id: populatedFormations[0].id,
        person_id: "person-1",
        person_name: "Иванов Иван Иванович",
        role_in_formation: "командир звена",
        assigned_on: "2026-01-10",
        released_on: null,
        notes: null,
        status: "active",
        status_label: "В составе",
      },
    ]);
    addMemberMock.mockResolvedValue({ id: "m-2" });

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );
    await screen.findByText("Звено пожаротушения");

    // Список членов не грузится вместе с экраном: только по кнопке.
    expect(listMembersMock).not.toHaveBeenCalled();
    await user.click(screen.getAllByRole("button", { name: "Состав" })[0]);

    expect(await screen.findByText(/командир звена/)).toBeInTheDocument();
    await waitFor(() => expect(listMembersMock).toHaveBeenCalled());

    await user.selectOptions(screen.getByLabelText("Работник"), "person-1");
    await user.type(screen.getByLabelText("Роль в формировании"), "спасатель");
    await user.click(screen.getByRole("button", { name: "Включить в состав" }));

    await waitFor(() => expect(addMemberMock).toHaveBeenCalled());
    expect(addMemberMock.mock.calls[0][0]).toBe(populatedFormations[0].id);
    expect(addMemberMock.mock.calls[0][1]).toMatchObject({
      person_id: "person-1",
      role_in_formation: "спасатель",
      assigned_on: null,
    });
  });

  it("сведения по ГО и документ планирования заводятся с экрана (срез-110)", async () => {
    const user = userEvent.setup();
    createProfileMock.mockResolvedValue({ id: "profile-new" });
    createDocumentMock.mockResolvedValue({ id: "doc-new" });

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Категорирование и планы" }),
    );

    await user.click(
      screen.getByRole("button", { name: "Внести сведения по ГО" }),
    );
    await user.selectOptions(screen.getByLabelText("Площадка"), "site-1");
    await user.selectOptions(
      screen.getByLabelText("Категория по ГО"),
      "second",
    );
    await user.type(screen.getByLabelText("Решение №"), "12-ГО");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createProfileMock).toHaveBeenCalled());
    expect(createProfileMock.mock.calls[0][0]).toMatchObject({
      site_id: "site-1",
      category: "second",
      decision_number: "12-ГО",
    });

    await user.click(screen.getByRole("button", { name: "Завести документ" }));
    await user.selectOptions(
      screen.getByLabelText("Вид документа"),
      "safety_passport",
    );
    await user.type(
      screen.getByLabelText("Документ"),
      "Паспорт безопасности объекта",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDocumentMock).toHaveBeenCalled());
    expect(createDocumentMock.mock.calls[0][0]).toMatchObject({
      kind: "safety_passport",
      title: "Паспорт безопасности объекта",
      // Пустой срок пересмотра — «бессрочный», а не «просрочен».
      review_due: null,
    });
  });

  it("формирование заводится с экрана, а не только через API (срез-109)", async () => {
    const user = userEvent.setup();
    const added = {
      ...populatedFormations[0],
      id: "cd-new",
      name: "Звено связи",
    };
    createFormationMock.mockResolvedValue(added);
    listFormationsMock
      .mockResolvedValueOnce(populatedFormations)
      .mockResolvedValue([...populatedFormations, added]);

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("button", { name: "Завести формирование" }),
    ).toBeInTheDocument();
    expect(uxBudgetDelta(document.body, "CivilDefensePage").unexpected).toEqual(
      [],
    );

    await user.click(
      screen.getByRole("button", { name: "Завести формирование" }),
    );
    await user.type(screen.getByLabelText("Формирование"), "Звено связи");
    await user.selectOptions(screen.getByLabelText("Вид"), "nfgo");
    await user.selectOptions(screen.getByLabelText("Командир"), "person-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createFormationMock).toHaveBeenCalled());
    expect(createFormationMock.mock.calls[0][0]).toMatchObject({
      name: "Звено связи",
      kind: "nfgo",
      commander_person_id: "person-1",
    });
    expect(await screen.findByText("Звено связи")).toBeInTheDocument();
  });

  it("учение планируется и получает протокол с экрана (срез-109)", async () => {
    const user = userEvent.setup();
    createDrillMock.mockResolvedValue({ id: "drill-new" });
    updateDrillMock.mockResolvedValue({ id: populatedDrills[0].id });

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Учения и тренировки" }),
    );

    await user.click(
      screen.getByRole("button", { name: "Запланировать учение" }),
    );
    await user.selectOptions(screen.getByLabelText("Вид"), "complex");
    await user.type(screen.getByLabelText("Учение"), "Комплексное учение");
    await user.type(screen.getByLabelText("По плану"), "2026-11-05");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDrillMock).toHaveBeenCalled());
    expect(createDrillMock.mock.calls[0][0]).toMatchObject({
      kind: "complex",
      title: "Комплексное учение",
      planned_on: "2026-11-05",
      // Протокола ещё нет: учение общеобъектовое, участники не внесены.
      formation_id: null,
      participants: null,
    });
  });

  it("рендерит реестр формирований с видами словами", async () => {
    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();
    // Вид — словами из закрытого словаря, а не кодом.
    expect(
      screen.getByText("НАСФ (аварийно-спасательное формирование)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("НФГО (формирование по обеспечению ГО)"),
    ).toBeInTheDocument();
    // Пустые клетки запрещены: состояние названо словами.
    expect(screen.getByText("не назначен")).toBeInTheDocument();
    expect(screen.getByText("состав не внесён")).toBeInTheDocument();
    // Граница названа на экране: платформа не выносит вердиктов.
    expect(screen.getByText(/не выносит вердиктов/i)).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listFormationsMock.mockResolvedValue([]);
    listDrillsMock.mockResolvedValue([]);
    listProfilesMock.mockResolvedValue([]);
    listDocumentsMock.mockResolvedValue([]);
    listProgramsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_formations: 0,
      by_kind: { nasf: 0, nfgo: 0 },
      without_commander: 0,
      members_active: 0,
      drills_total: 0,
      drills_overdue: 0,
      drills_held_this_year: 0,
      profiles_total: 0,
      profiles_by_category: {},
      planning_documents: 0,
      planning_review_overdue: 0,
      training_programs: 0,
    });

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Формирования не заведены"),
    ).toBeInTheDocument();
  });

  // Доп. №1 разд. 56.1 срез-2: учения. «Журнал» — реестр с фактическими
  // датами; периодичность платформа не назначает.
  it("учения открываются второй секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Учения и тренировки" }),
    );

    expect(await screen.findByText("КШУ по ликвидации ЧС")).toBeInTheDocument();
    // Вид и состояние — словами из закрытых словарей.
    expect(screen.getByText("Командно-штабное учение")).toBeInTheDocument();
    expect(screen.getByText("Просрочено")).toBeInTheDocument();
    // Срез-109: дата проведения ушла в колонку состояния (место под колонку
    // действий). У непроведённого учения в этой ячейке только состояние —
    // «протокола нет» видно без отдельной клетки.
    const statusCell = screen.getByText("Просрочено").closest("td");
    expect(statusCell?.textContent?.trim()).toBe("Просрочено");
    // Кнопка строки зовёт внести протокол, а не просто «изменить».
    expect(
      screen.getByRole("button", { name: "Протокол" }),
    ).toBeInTheDocument();
    // Учение без формирования — это весь персонал, а не прочерк.
    expect(screen.getByText("весь персонал")).toBeInTheDocument();
    // Граница названа на экране.
    expect(screen.getByText(/сроки не назначает/i)).toBeInTheDocument();
  });

  // Доп. №1 разд. 56.1 срез-4: категорирование и планирование. Категорию
  // присваивает орган — платформа хранит внесённое.
  it("категорирование открывается третьей секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Категорирование и планы" }),
    );

    expect(
      await screen.findByText("Вторая категория по ГО"),
    ).toBeInTheDocument();
    // «Категория не присвоена» — внесённое сведение, а не пустая клетка.
    expect(screen.getByText("Категория не присвоена")).toBeInTheDocument();
    // Пустые реквизиты и ответственный названы словами.
    expect(screen.getByText("реквизиты не внесены")).toBeInTheDocument();
    expect(screen.getByText("не назначен")).toBeInTheDocument();
    // Документы планирования: бессрочный и просроченный пересмотр.
    expect(screen.getByText("бессрочно")).toBeInTheDocument();
    expect(screen.getByText("Просрочен пересмотр")).toBeInTheDocument();
    // Граница названа на экране.
    expect(
      screen.getByText(/не предлагает категорию сама/i),
    ).toBeInTheDocument();
  });

  // Доп. №1 разд. 56.1: программы обучения ГО. Реестром контур НЕ владеет —
  // программы заводятся в разделе обучения, здесь только своя часть.
  it("программы обучения открываются четвёртой секцией и только на чтение", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Программы обучения" }),
    );

    expect(
      await screen.findByText("Курсовое обучение по ГО"),
    ).toBeInTheDocument();
    // Пустые клетки запрещены: причина названа словами.
    expect(screen.getByText("не указано")).toBeInTheDocument();
    expect(screen.getByText("бессрочно")).toBeInTheDocument();
    // На экране прямо сказано, где программы заводятся: реестр один.
    expect(screen.getByText(/два места правды/i)).toBeInTheDocument();
    // Кнопки «завести программу» здесь нет — это ядро.
    expect(
      screen.queryByRole("button", { name: /добавить программу/i }),
    ).toBeNull();
  });

  it("открытые происшествия контура: число из сводки и ссылка в реестр (срез-49)", async () => {
    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Открытых происшествий"),
    ).toBeInTheDocument();
    // число — из сводки бэкенда (та же формула, что разрез у директора), а
    // ссылка ведёт в ОБЩИЙ реестр с уже выставленным фильтром дисциплины
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute(
      "href",
      "/incidents?discipline=civil_defense&status=open",
    );
  });

  it("CivilDefensePage в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "CivilDefensePage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
