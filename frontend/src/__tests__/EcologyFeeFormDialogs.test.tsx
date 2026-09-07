import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyFeeLineFormDialog } from "@/features/ecology/EcologyFeeLineFormDialog";
import { EcologyFeeRateFormDialog } from "@/features/ecology/EcologyFeeRateFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { ecologyFeeLineFormSchema } from "@/types/forms/ecologyFee";

const createRateMock = vi.fn();
const updateRateMock = vi.fn();
const createLineMock = vi.fn();
const updateLineMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/ecology", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/ecology")>("@/api/ecology");
  return {
    ...actual,
    ecologyApi: {
      createFeeRate: (...args: unknown[]) => createRateMock(...args),
      updateFeeRate: (...args: unknown[]) => updateRateMock(...args),
      createFeeLine: (...args: unknown[]) => createLineMock(...args),
      updateFeeLine: (...args: unknown[]) => updateLineMock(...args),
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const existingRate = {
  id: "rate-1",
  year: 2026,
  impact_kind: "emission",
  impact_kind_label: "Выбросы в атмосферу",
  subject: "Азота диоксид",
  rate_per_ton: "138.80",
  source_document: "ПП РФ №913",
  notes: null,
};

const existingLine = {
  id: "line-1",
  year: 2026,
  quarter: 2,
  impact_kind: "emission",
  impact_kind_label: "Выбросы в атмосферу",
  subject: "Азота диоксид",
  mass_tons: "1.500",
  coefficient: "1.00",
  notes: null,
  rate_status: "found",
  rate_status_label: "Ставка внесена",
  rate_per_ton: "138.80",
  amount_rubles: "208.20",
};

describe("EcologyFeeRateFormDialog — ставка платы за НВОС (срез-102)", () => {
  beforeEach(() => {
    createRateMock.mockReset();
    updateRateMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createRateMock.mockResolvedValue({ ...existingRate, id: "rate-new" });
    updateRateMock.mockResolvedValue(existingRate);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyFeeRateFormDialog trigger={<button>Внести ставку</button>} />,
    );
    await user.click(screen.getByRole("button", { name: "Внести ставку" }));
  };

  it("отправляет год числом, вид, предмет и ставку с запятой", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.clear(screen.getByLabelText("Год"));
    await user.type(screen.getByLabelText("Год"), "2026");
    await user.selectOptions(screen.getByLabelText("Вид воздействия"), "waste");
    await user.type(screen.getByLabelText("Предмет платы"), "Отходы IV класса");
    await user.type(screen.getByLabelText("Ставка, ₽/т"), "663,2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createRateMock).toHaveBeenCalled());
    expect(createRateMock.mock.calls[0][0]).toEqual({
      year: 2026,
      impact_kind: "waste",
      subject: "Отходы IV класса",
      rate_per_ton: "663.2",
      source_document: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Ставка внесена");
  });

  it("без ставки и предмета запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Назовите предмет платы"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Внесите ставку из постановления"),
    ).toBeInTheDocument();
    expect(createRateMock).not.toHaveBeenCalled();
  });

  it("правка: год, вид и предмет заперты — иначе поехали бы суммы прошлых лет", async () => {
    const user = userEvent.setup();
    render(
      <EcologyFeeRateFormDialog
        initialData={existingRate}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Год")).toBeDisabled();
    expect(screen.getByLabelText("Вид воздействия")).toBeDisabled();
    expect(screen.getByLabelText("Предмет платы")).toBeDisabled();

    await user.clear(screen.getByLabelText("Ставка, ₽/т"));
    await user.type(screen.getByLabelText("Ставка, ₽/т"), "150,5");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateRateMock).toHaveBeenCalled());
    expect(updateRateMock.mock.calls[0][0]).toBe("rate-1");
    expect(updateRateMock.mock.calls[0][1]).toEqual({
      rate_per_ton: "150.5",
      source_document: "ПП РФ №913",
      notes: null,
    });
  });

  it("дубль ставки на год: 422 словами, окно открыто", async () => {
    const user = userEvent.setup();
    createRateMock.mockRejectedValueOnce({
      status: 422,
      message: "Ставка на 2026 год по 'Азота диоксид' уже внесена",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Предмет платы"), "Азота диоксид");
    await user.type(screen.getByLabelText("Ставка, ₽/т"), "138,8");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже внесена");
    expect(
      screen.getByRole("heading", { name: "Внести ставку" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне четыре поля; ставку платформа не подсказывает", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Год");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Откуда взята ставка и заметки"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/платформа её\s+не знает и не подсказывает/i),
    ).toBeInTheDocument();
  });
});

describe("EcologyFeeLineFormDialog — строка расчёта платы (срез-102)", () => {
  beforeEach(() => {
    createLineMock.mockReset();
    updateLineMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createLineMock.mockResolvedValue({ ...existingLine, id: "line-new" });
    updateLineMock.mockResolvedValue(existingLine);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyFeeLineFormDialog
        trigger={<button>Внести строку расчёта</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Внести строку расчёта" }),
    );
  };

  it("отправляет год и квартал числами, массу и коэффициент", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.clear(screen.getByLabelText("Год"));
    await user.type(screen.getByLabelText("Год"), "2026");
    await user.selectOptions(screen.getByLabelText("Квартал"), "2");
    await user.type(screen.getByLabelText("Предмет платы"), "Азота диоксид");
    await user.type(screen.getByLabelText("Масса, т"), "1,5");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createLineMock).toHaveBeenCalled());
    expect(createLineMock.mock.calls[0][0]).toEqual({
      year: 2026,
      quarter: 2,
      impact_kind: "emission",
      subject: "Азота диоксид",
      mass_tons: "1.5",
      // Коэффициент по умолчанию 1 — «без повышающего», а не ноль.
      coefficient: "1",
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Строка расчёта внесена");
  });

  it("нулевой коэффициент не проходит: он обнулил бы плату", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Предмет платы"), "Азота диоксид");
    await user.type(screen.getByLabelText("Масса, т"), "1");
    await user.clear(screen.getByLabelText("Коэффициент"));
    await user.type(screen.getByLabelText("Коэффициент"), "0");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Коэффициент больше нуля: нулевой обнулил бы плату",
      ),
    ).toBeInTheDocument();
    expect(createLineMock).not.toHaveBeenCalled();
  });

  it("правка: ключ строки заперт, меняются масса и коэффициент", async () => {
    const user = userEvent.setup();
    render(
      <EcologyFeeLineFormDialog
        initialData={existingLine}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Год")).toBeDisabled();
    expect(screen.getByLabelText("Квартал")).toBeDisabled();
    expect(screen.getByLabelText("Вид воздействия")).toBeDisabled();
    expect(screen.getByLabelText("Предмет платы")).toBeDisabled();

    await user.clear(screen.getByLabelText("Масса, т"));
    await user.type(screen.getByLabelText("Масса, т"), "2,25");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateLineMock).toHaveBeenCalled());
    expect(updateLineMock.mock.calls[0][1]).toEqual({
      mass_tons: "2.25",
      coefficient: "1.00",
      notes: null,
    });
  });

  it("форма сумму не считает: это делает сервер по ставке своего года", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Год");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/Если ставки за год нет, сумма не считается вовсе/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Сумма/i)).toBeNull();
  });
});

describe("ecologyFeeLineFormSchema", () => {
  it("отклоняет коэффициент больше 200", () => {
    expect(
      ecologyFeeLineFormSchema.safeParse({
        year: "2026",
        quarter: "1",
        impact_kind: "emission",
        subject: "Азота диоксид",
        mass_tons: "1",
        coefficient: "250",
      }).success,
    ).toBe(false);
  });

  it("принимает нулевую массу: квартал без воздействия — факт", () => {
    expect(
      ecologyFeeLineFormSchema.safeParse({
        year: "2026",
        quarter: "1",
        impact_kind: "emission",
        subject: "Азота диоксид",
        mass_tons: "0",
        coefficient: "1",
      }).success,
    ).toBe(true);
  });
});
