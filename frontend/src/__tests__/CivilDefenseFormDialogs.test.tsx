import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CdDrillFormDialog } from "@/features/civil-defense/CdDrillFormDialog";
import { CdFormationFormDialog } from "@/features/civil-defense/CdFormationFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { cdDrillFormSchema } from "@/types/forms/civilDefense";

const createFormationMock = vi.fn();
const updateFormationMock = vi.fn();
const createDrillMock = vi.fn();
const updateDrillMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/civilDefense", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  civilDefenseApi: {
    createFormation: (...args: unknown[]) => createFormationMock(...args),
    updateFormation: (...args: unknown[]) => updateFormationMock(...args),
    createDrill: (...args: unknown[]) => createDrillMock(...args),
    updateDrill: (...args: unknown[]) => updateDrillMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const persons = [
  { id: "person-1", full_name: "Иванов Иван Иванович" },
] as never;

const existingFormation = {
  id: "cd-1",
  name: "Звено пожаротушения",
  kind: "nasf",
  kind_label: "НАСФ (аварийно-спасательное формирование)",
  purpose: "Тушение до прибытия подразделений",
  commander_person_id: "person-1",
  commander_name: "Иванов Иван Иванович",
  equipment_notes: null,
  notes: null,
  members_active: 4,
};

const formations = [existingFormation] as never;

const plannedDrill = {
  id: "drill-1",
  kind: "command_staff",
  kind_label: "Командно-штабное учение",
  title: "КШУ по ликвидации ЧС",
  planned_on: "2026-05-01",
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
};

describe("CdFormationFormDialog — формирование ГО (срез-109)", () => {
  beforeEach(() => {
    createFormationMock.mockReset();
    updateFormationMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createFormationMock.mockResolvedValue({
      ...existingFormation,
      id: "cd-new",
    });
    updateFormationMock.mockResolvedValue(existingFormation);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <CdFormationFormDialog
        persons={persons}
        trigger={<button>Завести формирование</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Завести формирование" }),
    );
  };

  it("командир необязателен: формирование заводят до приказа", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Формирование"), "Звено связи");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createFormationMock).toHaveBeenCalled());
    expect(createFormationMock.mock.calls[0][0]).toEqual({
      name: "Звено связи",
      kind: "nasf",
      purpose: null,
      commander_person_id: null,
      equipment_notes: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Формирование заведено");
  });

  it("без названия запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Назовите формирование"),
    ).toBeInTheDocument();
    expect(createFormationMock).not.toHaveBeenCalled();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <CdFormationFormDialog
        persons={persons}
        initialData={existingFormation}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Вид")).toHaveValue("nasf");
    expect(screen.getByLabelText("Командир")).toHaveValue("person-1");

    await user.selectOptions(screen.getByLabelText("Вид"), "nfgo");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateFormationMock).toHaveBeenCalled());
    expect(updateFormationMock.mock.calls[0][1]).toMatchObject({
      kind: "nfgo",
      purpose: "Тушение до прибытия подразделений",
      commander_person_id: "person-1",
    });
  });

  it("на первом уровне четыре поля; штат платформа не судит", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Формирование");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Оснащение и заметки")).toBeInTheDocument();
    expect(screen.getByText(/платформа этого не решает/i)).toBeInTheDocument();
  });
});

describe("CdDrillFormDialog — учение ГО (срез-109)", () => {
  beforeEach(() => {
    createDrillMock.mockReset();
    updateDrillMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createDrillMock.mockResolvedValue({ ...plannedDrill, id: "drill-new" });
    updateDrillMock.mockResolvedValue(plannedDrill);
  });

  const openProtocol = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(
      screen.getByText(
        "Протокол проведения: дата, результат, участники, анализ",
      ),
    );
  };

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <CdDrillFormDialog
        formations={formations}
        trigger={<button>Запланировать учение</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Запланировать учение" }),
    );
  };

  it("планирует учение; без формирования оно общеобъектовое", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Вид"), "complex");
    await user.type(screen.getByLabelText("Учение"), "Комплексное учение");
    await user.type(screen.getByLabelText("По плану"), "2026-11-05");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDrillMock).toHaveBeenCalled());
    expect(createDrillMock.mock.calls[0][0]).toEqual({
      kind: "complex",
      title: "Комплексное учение",
      planned_on: "2026-11-05",
      formation_id: null,
      participants: null,
      scenario: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Учение запланировано");
  });

  it("дата проведения без результата не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Учение"), "Тренировка");
    await user.type(screen.getByLabelText("По плану"), "2026-05-01");
    await openProtocol(user);
    await user.type(screen.getByLabelText("Проведено"), "2026-05-05");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("У проведённого учения обязателен результат"),
    ).toBeInTheDocument();
    expect(createDrillMock).not.toHaveBeenCalled();
  });

  it("результат без даты проведения не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Учение"), "Тренировка");
    await user.type(screen.getByLabelText("По плану"), "2026-05-01");
    await openProtocol(user);
    await user.selectOptions(screen.getByLabelText("Результат"), "passed");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Результат без даты проведения — выдумка о событии",
      ),
    ).toBeInTheDocument();
    expect(createDrillMock).not.toHaveBeenCalled();
  });

  it("протокол уходит в PATCH с датой, результатом и участниками", async () => {
    const user = userEvent.setup();
    render(
      <CdDrillFormDialog
        formations={formations}
        initialData={plannedDrill}
        trigger={<button>Протокол</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Протокол" }));
    await openProtocol(user);

    await user.type(screen.getByLabelText("Проведено"), "2026-05-05");
    await user.selectOptions(
      screen.getByLabelText("Результат"),
      "with_remarks",
    );
    await user.type(screen.getByLabelText("Участников"), "35");
    await user.selectOptions(screen.getByLabelText("Формирование"), "cd-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateDrillMock).toHaveBeenCalled());
    expect(updateDrillMock.mock.calls[0][0]).toBe("drill-1");
    expect(updateDrillMock.mock.calls[0][1]).toMatchObject({
      held_on: "2026-05-05",
      outcome: "with_remarks",
      participants: 35,
      formation_id: "cd-1",
    });
  });

  it("на первом уровне четыре поля; периодичность не назначается", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Вид");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(
        "Протокол проведения: дата, результат, участники, анализ",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/платформа её не назначает/i)).toBeInTheDocument();
  });
});

describe("cdDrillFormSchema (срез-109)", () => {
  it("принимает план без протокола", () => {
    expect(
      cdDrillFormSchema.safeParse({
        kind: "complex",
        title: "Учение",
        planned_on: "2026-11-05",
      }).success,
    ).toBe(true);
  });

  it("отклоняет дробное число участников", () => {
    expect(
      cdDrillFormSchema.safeParse({
        kind: "complex",
        title: "Учение",
        planned_on: "2026-11-05",
        held_on: "2026-11-06",
        outcome: "passed",
        participants: "12,5",
      }).success,
    ).toBe(false);
  });
});
