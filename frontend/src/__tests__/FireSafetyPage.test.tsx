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
const listDocumentsMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/fireSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fireSafetyApi: {
    listEquipment: (...args: unknown[]) => listEquipmentMock(...args),
    listDocuments: (...args: unknown[]) => listDocumentsMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Документы ПБ: один с просроченным пересмотром, один бессрочный. */
const populatedDocuments = [
  {
    id: "doc-1",
    kind: "instruction_general",
    kind_label: "Инструкция о мерах ПБ (общеобъектовая)",
    title: "Инструкция о мерах пожарной безопасности",
    number: "12-ПБ",
    location: null,
    approved_on: "2019-01-01",
    review_due: "2020-01-01",
    responsible: "Смирнов",
    document_id: null,
    notes: null,
    status: "overdue",
    status_label: "Просрочен пересмотр",
  },
  {
    id: "doc-2",
    kind: "journal",
    kind_label: "Журнал",
    title: "Журнал эксплуатации систем ПБ",
    number: null,
    location: null,
    approved_on: null,
    review_due: null,
    responsible: null,
    document_id: null,
    notes: null,
    status: "ok",
    status_label: "Действует",
  },
];

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
    last_maintenance_on: "2026-08-01",
    last_maintenance_result: "with_remarks",
  },
  {
    id: "eq-2",
    kind: "alarm_system",
    label: "АУПС корпус А",
    location: null,
    recharge_due: null,
    inspection_due: "2099-01-01",
    status: "active",
    // Работ по этому средству не было ни разу — срок есть, подтверждения нет.
    last_maintenance_on: null,
    last_maintenance_result: null,
  },
];

const populatedReadiness = {
  total_units: 2,
  overdue_recharge: 1,
  overdue_inspection: 0,
  due_soon: 1,
  due_soon_days: 30,
  overdue_fire_briefings: 2,
  units_without_maintenance: 1,
  fire_documents: 2,
  overdue_documents: 1,
  incidents_open: 3,
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
    listDocumentsMock.mockReset();
    listEquipmentMock.mockResolvedValue(populatedEquipment);
    listDocumentsMock.mockResolvedValue(populatedDocuments);
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
    // Разд. 54.1: контроль сроков инструктажей ПБ — в той же сводке.
    expect(
      screen.getByText(/просроченных инструктажей пб/i),
    ).toBeInTheDocument();
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
    await user.click(
      screen.getByRole("button", { name: "Средства и системы" }),
    );

    expect(await screen.findByText("ОП-5 №1")).toBeInTheDocument();
    // Вид — словами, а не кодом; просроченный срок назван просроченным.
    expect(screen.getByText("Сигнализация (АУПС)")).toBeInTheDocument();
    // Не просто «дата в прошлом» — ячейка прямо называет срок просроченным
    // (в шапке слово тоже есть, поэтому матчим ячейку с датой).
    expect(screen.getByText(/·\s*просрочен$/i)).toBeInTheDocument();
  });

  // Доп. №1 разд. 54.1 «регламентные работы». До этого среза у средства был
  // только СЛЕДУЮЩИЙ срок: отметить выполненное ТО можно было единственным
  // способом — затереть срок, и от работы не оставалось следа.
  it("показывает последнее подтверждённое ТО и называет его отсутствие", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Средства и системы" }),
    );

    expect(await screen.findByText("ОП-5 №1")).toBeInTheDocument();
    // Результат — словами, а не кодом «with_remarks».
    expect(screen.getByText(/Исправно с замечаниями/)).toBeInTheDocument();
    // Отсутствие записей названо словами: пустая ячейка читалась бы как
    // «данные не подгрузились», а это другое.
    expect(screen.getByText("нет записей")).toBeInTheDocument();
  });

  it("средства без подтверждения ТО названы числом в шапке", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/без подтверждения ТО/i),
    ).toBeInTheDocument();
  });

  // Доп. №1 разд. 54.1 «Документы ПБ». Ядровой Document для этого не годится
  // по построению: template_id NOT NULL, поэтому документ, который платформа
  // не выпускала (декларация из МЧС, план эвакуации от подрядчика), в реестр
  // ядра не заводится вовсе.
  it("реестр документов ПБ открывается третьей секцией", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Документы ПБ" }));

    expect(
      await screen.findByText("Инструкция о мерах пожарной безопасности"),
    ).toBeInTheDocument();
    // Вид и состояние — словами, а не кодами.
    expect(
      screen.getByText("Инструкция о мерах ПБ (общеобъектовая)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Просрочен пересмотр")).toBeInTheDocument();
    // Пустой срок пересмотра назван «бессрочный», а не пустой ячейкой.
    expect(screen.getByText("бессрочный")).toBeInTheDocument();
  });

  it("экран не выдаёт перечень обязательных документов за свой", async () => {
    // ГРАНИЦА названа НА ЭКРАНЕ: применимость декларации и планов эвакуации
    // зависит от характеристик объекта, которых в данных нет.
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Документы ПБ" }));

    expect(
      await screen.findByText(/определяет специалист/i),
    ).toBeInTheDocument();
  });

  it("открытые происшествия контура: число из сводки и ссылка в реестр (срез-49)", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);
    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Открытых происшествий"),
    ).toBeInTheDocument();
    // число — из сводки бэкенда (та же формула, что разрез у директора), а
    // ссылка ведёт в ОБЩИЙ реестр с уже выставленным фильтром дисциплины
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute(
      "href",
      "/incidents?discipline=fire_safety&status=open",
    );
  });

  it("FireSafetyPage в UX-бюджете во ВСЕХ ТРЁХ секциях", async () => {
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

    await user.click(
      screen.getByRole("button", { name: "Средства и системы" }),
    );
    expect(await screen.findByText("ОП-5 №1")).toBeInTheDocument();
    const equipment = uxBudgetDelta(document.body, "FireSafetyPage");
    expect(equipment.stale).toEqual([]);
    expect(equipment.unexpected).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Документы ПБ" }));
    expect(
      await screen.findByText("Инструкция о мерах пожарной безопасности"),
    ).toBeInTheDocument();
    const documents = uxBudgetDelta(document.body, "FireSafetyPage");
    expect(documents.unexpected).toEqual([]);
    expect(documents.stale).toEqual([]);
    expect(equipment.stale).toEqual([]);
  });
});
