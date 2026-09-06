import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyMeasurementFormDialog } from "@/features/ecology/EcologyMeasurementFormDialog";
import { EcologyMonitoringPlanFormDialog } from "@/features/ecology/EcologyMonitoringPlanFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { ecologyMonitoringPlanFormSchema } from "@/types/forms/ecologyMonitoring";

const createPlanMock = vi.fn();
const updatePlanMock = vi.fn();
const createMeasurementMock = vi.fn();
const updateMeasurementMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/ecology", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/ecology")>("@/api/ecology");
  return {
    ...actual,
    ecologyApi: {
      createMonitoringPlanItem: (...args: unknown[]) => createPlanMock(...args),
      updateMonitoringPlanItem: (...args: unknown[]) => updatePlanMock(...args),
      createEmissionMeasurement: (...args: unknown[]) =>
        createMeasurementMock(...args),
      updateEmissionMeasurement: (...args: unknown[]) =>
        updateMeasurementMock(...args),
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const sources = [
  { id: "src-1", source_number: "0001", name: "Труба котельной" },
  { id: "src-2", source_number: "0002", name: "Сварочный пост" },
] as never;

const planItems = [
  {
    id: "plan-1",
    substance: "Азота диоксид",
    periodicity_label: "раз в квартал",
  },
] as never;

const existingPlan = {
  id: "plan-1",
  source_id: "src-1",
  substance: "Азота диоксид",
  periodicity_months: 3,
  periodicity_label: "раз в квартал",
  next_due_on: "2026-10-01",
  method: null,
  laboratory: "ИЛЦ «Эко»",
  notes: null,
  status: "ok",
  status_label: "В графике",
  last_measured_on: "2026-07-01",
};

const existingMeasurement = {
  id: "meas-1",
  plan_id: "plan-1",
  source_id: "src-1",
  substance: "Азота диоксид",
  measured_on: "2026-07-01",
  value_grams_per_second: "0.120000",
  protocol_number: "П-15",
  laboratory: "ИЛЦ «Эко»",
  notes: null,
  norm_grams_per_second: "0.150000",
  comparison: "within",
  comparison_label: "В пределах норматива",
};

describe("EcologyMonitoringPlanFormDialog — план-график ПЭК (срез-101)", () => {
  beforeEach(() => {
    createPlanMock.mockReset();
    updatePlanMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createPlanMock.mockResolvedValue({ ...existingPlan, id: "plan-new" });
    updatePlanMock.mockResolvedValue(existingPlan);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyMonitoringPlanFormDialog
        sources={sources}
        trigger={<button>Внести строку плана</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Внести строку плана" }),
    );
  };

  it("отправляет источник, вещество, периодичность числом и дату", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Источник выбросов"),
      "src-1",
    );
    await user.type(screen.getByLabelText("Вещество"), "Азота диоксид");
    await user.type(screen.getByLabelText("Периодичность, месяцев"), "3");
    await user.type(screen.getByLabelText("Ближайший замер"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createPlanMock).toHaveBeenCalled());
    expect(createPlanMock.mock.calls[0][0]).toEqual({
      source_id: "src-1",
      substance: "Азота диоксид",
      periodicity_months: 3,
      next_due_on: "2026-10-01",
      method: null,
      laboratory: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Строка плана внесена");
  });

  it("периодичность больше 60 месяцев не уходит на сервер: это уже не график", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Источник выбросов"),
      "src-1",
    );
    await user.type(screen.getByLabelText("Вещество"), "Пыль");
    await user.type(screen.getByLabelText("Периодичность, месяцев"), "72");
    await user.type(screen.getByLabelText("Ближайший замер"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    // Границу 1–60 держат сразу двое: браузер (min/max у поля) и схема формы
    // (проверка ниже). Сервер тот же предел проверяет третьим — запрос с 72
    // не уходит вовсе.
    expect(createPlanMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Периодичность, месяцев")).toHaveAttribute(
      "max",
      "60",
    );
    expect(
      ecologyMonitoringPlanFormSchema.safeParse({
        source_id: "src-1",
        substance: "Пыль",
        periodicity_months: "72",
        next_due_on: "2026-10-01",
      }).success,
    ).toBe(false);
  });

  it("правка: источник заперт, остальное уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyMonitoringPlanFormDialog
        sources={sources}
        initialData={existingPlan}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Источник выбросов")).toBeDisabled();
    expect(screen.getByLabelText("Периодичность, месяцев")).toHaveValue(3);

    await user.clear(screen.getByLabelText("Периодичность, месяцев"));
    await user.type(screen.getByLabelText("Периодичность, месяцев"), "6");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updatePlanMock).toHaveBeenCalled());
    expect(updatePlanMock.mock.calls[0][0]).toBe("plan-1");
    expect(updatePlanMock.mock.calls[0][1]).toEqual({
      substance: "Азота диоксид",
      periodicity_months: 6,
      next_due_on: "2026-10-01",
      method: null,
      laboratory: "ИЛЦ «Эко»",
      notes: null,
    });
    expect(updatePlanMock.mock.calls[0][1]).not.toHaveProperty("source_id");
  });

  it("на первом уровне четыре поля; периодичность платформа не назначает", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Источник выбросов");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Метод, лаборатория и заметки"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/платформа её не\s+назначает/i),
    ).toBeInTheDocument();
  });
});

describe("EcologyMeasurementFormDialog — замер ПЭК (срез-101)", () => {
  beforeEach(() => {
    createMeasurementMock.mockReset();
    updateMeasurementMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMeasurementMock.mockResolvedValue({
      ...existingMeasurement,
      id: "meas-new",
    });
    updateMeasurementMock.mockResolvedValue(existingMeasurement);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyMeasurementFormDialog
        sources={sources}
        planItems={planItems}
        trigger={<button>Внести замер</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Внести замер" }));
  };

  it("внеплановый замер уходит без строки плана; запятая — точкой", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Источник выбросов"),
      "src-2",
    );
    await user.type(screen.getByLabelText("Вещество"), "Пыль неорганическая");
    await user.type(screen.getByLabelText("Дата замера"), "2026-08-15");
    await user.type(screen.getByLabelText("Результат, г/с"), "0,08");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMeasurementMock).toHaveBeenCalled());
    expect(createMeasurementMock.mock.calls[0][0]).toEqual({
      source_id: "src-2",
      substance: "Пыль неорганическая",
      plan_id: null,
      measured_on: "2026-08-15",
      value_grams_per_second: "0.08",
      protocol_number: null,
      laboratory: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Замер внесён");
  });

  it("без результата и даты запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Источник выбросов"),
      "src-1",
    );
    await user.type(screen.getByLabelText("Вещество"), "Пыль");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Внесите дату замера")).toBeInTheDocument();
    expect(
      screen.getByText("Внесите результат замера в г/с"),
    ).toBeInTheDocument();
    expect(createMeasurementMock).not.toHaveBeenCalled();
  });

  it("правка: источник, вещество и строка плана заперты — это другой замер", async () => {
    const user = userEvent.setup();
    render(
      <EcologyMeasurementFormDialog
        sources={sources}
        planItems={planItems}
        initialData={existingMeasurement}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Источник выбросов")).toBeDisabled();
    expect(screen.getByLabelText("Вещество")).toBeDisabled();

    await user.clear(screen.getByLabelText("Результат, г/с"));
    await user.type(screen.getByLabelText("Результат, г/с"), "0,2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMeasurementMock).toHaveBeenCalled());
    expect(updateMeasurementMock.mock.calls[0][1]).toEqual({
      measured_on: "2026-07-01",
      value_grams_per_second: "0.2",
      protocol_number: "П-15",
      laboratory: "ИЛЦ «Эко»",
      notes: null,
    });
  });

  it("форма итог не выводит: превышение считает сервер по внесённому нормативу", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Источник выбросов");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/платформа сама «допустимое»\s+значение не назначает/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/превышение норматива/i)).toBeNull();
  });
});

describe("ecologyMonitoringPlanFormSchema", () => {
  it("отклоняет нулевую периодичность", () => {
    expect(
      ecologyMonitoringPlanFormSchema.safeParse({
        source_id: "src-1",
        substance: "Пыль",
        periodicity_months: "0",
        next_due_on: "2026-10-01",
      }).success,
    ).toBe(false);
  });

  it("принимает типовой квартал", () => {
    expect(
      ecologyMonitoringPlanFormSchema.safeParse({
        source_id: "src-1",
        substance: "Пыль",
        periodicity_months: "3",
        next_due_on: "2026-10-01",
      }).success,
    ).toBe(true);
  });
});
