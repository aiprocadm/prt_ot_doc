import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FireDrillFormDialog } from "@/features/fire-safety/FireDrillFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { fireDrillFormSchema } from "@/types/forms/fireSafety";

const createMock = vi.fn();
const updateMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/fireSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fireSafetyApi: {
    createDrill: (...args: unknown[]) => createMock(...args),
    updateDrill: (...args: unknown[]) => updateMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const sites = [{ id: "site-1", name: "Площадка №1" }] as never;

const plannedDrill = {
  id: "drill-1",
  kind: "evacuation",
  kind_label: "Тренировка по эвакуации",
  title: "Тренировка по эвакуации, корпус А",
  planned_on: "2026-08-01",
  held_on: null,
  site_id: "site-1",
  scenario: "Возгорание в электрощитовой",
  participants: null,
  outcome: null,
  outcome_label: null,
  findings: null,
  status: "overdue",
};

const openProtocol = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(
    screen.getByText("Протокол проведения: дата, результат, участники, анализ"),
  );
};

describe("FireDrillFormDialog — тренировка по ПБ (срез-104)", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMock.mockResolvedValue({ ...plannedDrill, id: "drill-new" });
    updateMock.mockResolvedValue(plannedDrill);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <FireDrillFormDialog
        sites={sites}
        trigger={<button>Запланировать тренировку</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Запланировать тренировку" }),
    );
  };

  it("планирует тренировку: вид, название и дата плана; протокол пуст", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Вид"), "fire_fighting");
    await user.type(
      screen.getByLabelText("Тренировка"),
      "Применение огнетушителей",
    );
    await user.type(screen.getByLabelText("По плану"), "2026-12-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0]).toEqual({
      kind: "fire_fighting",
      title: "Применение огнетушителей",
      planned_on: "2026-12-01",
      site_id: null,
      held_on: null,
      outcome: null,
      participants: null,
      scenario: null,
      findings: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Тренировка запланирована");
  });

  it("без названия и даты плана запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Назовите тренировку")).toBeInTheDocument();
    expect(screen.getByText("Внесите дату по плану")).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("дата проведения без результата не проходит: протокол обязан быть цельным", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Тренировка"), "Эвакуация");
    await user.type(screen.getByLabelText("По плану"), "2026-08-01");
    await openProtocol(user);
    await user.type(screen.getByLabelText("Проведена"), "2026-08-05");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("У проведённой тренировки обязателен результат"),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("результат без даты проведения не проходит: это выдумка о событии", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Тренировка"), "Эвакуация");
    await user.type(screen.getByLabelText("По плану"), "2026-08-01");
    await openProtocol(user);
    await user.selectOptions(screen.getByLabelText("Результат"), "passed");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Результат без даты проведения — выдумка о событии",
      ),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("протокол уходит в PATCH: дата, результат и число участников", async () => {
    const user = userEvent.setup();
    render(
      <FireDrillFormDialog
        sites={sites}
        initialData={plannedDrill}
        trigger={<button>Протокол</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Протокол" }));
    await openProtocol(user);

    await user.type(screen.getByLabelText("Проведена"), "2026-08-05");
    await user.selectOptions(screen.getByLabelText("Результат"), "failed");
    await user.type(screen.getByLabelText("Участников"), "17");
    await user.type(
      screen.getByLabelText("Анализ и замечания"),
      "Не сработала система оповещения",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock.mock.calls[0][0]).toBe("drill-1");
    expect(updateMock.mock.calls[0][1]).toMatchObject({
      held_on: "2026-08-05",
      outcome: "failed",
      participants: 17,
      findings: "Не сработала система оповещения",
      scenario: "Возгорание в электрощитовой",
    });
    expect(toastSuccess).toHaveBeenCalledWith("Тренировка обновлена");
  });

  it("дата проведения в будущем: ответ сервера словами, окно открыто", async () => {
    const user = userEvent.setup();
    createMock.mockRejectedValueOnce({
      status: 422,
      message:
        "Дата проведения не может быть в будущем — это план, а не протокол",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Тренировка"), "Эвакуация");
    await user.type(screen.getByLabelText("По плану"), "2030-01-01");
    await openProtocol(user);
    await user.type(screen.getByLabelText("Проведена"), "2030-01-02");
    await user.selectOptions(screen.getByLabelText("Результат"), "passed");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("не может быть в будущем");
    expect(
      screen.getByRole("heading", { name: "Запланировать тренировку" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне четыре поля: протокол свёрнут, интервал не судится", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Вид");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(
        "Протокол проведения: дата, результат, участники, анализ",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Периодичность определяет\s+специалист/i),
    ).toBeInTheDocument();
  });
});

describe("fireDrillFormSchema", () => {
  it("принимает план без протокола", () => {
    expect(
      fireDrillFormSchema.safeParse({
        kind: "evacuation",
        title: "Эвакуация",
        planned_on: "2026-08-01",
      }).success,
    ).toBe(true);
  });

  it("отклоняет дробное число участников", () => {
    expect(
      fireDrillFormSchema.safeParse({
        kind: "evacuation",
        title: "Эвакуация",
        planned_on: "2026-08-01",
        held_on: "2026-08-05",
        outcome: "passed",
        participants: "12.5",
      }).success,
    ).toBe(false);
  });
});
