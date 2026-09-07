import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyWasteMovementFormDialog } from "@/features/ecology/EcologyWasteMovementFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { ecologyWasteMovementFormSchema } from "@/types/forms/ecologyWasteMovement";

const createMock = vi.fn();
const updateMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/ecology", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/ecology")>("@/api/ecology");
  return {
    ...actual,
    ecologyApi: {
      createWasteMovement: (...args: unknown[]) => createMock(...args),
      updateWasteMovement: (...args: unknown[]) => updateMock(...args),
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const contracts = [
  {
    id: "ct-1",
    counterparty_name: "ООО «Оператор»",
    contract_number: "ОТХ-12",
    valid_until: "2027-01-01",
    status: "active",
  },
] as never;

const passports = [
  { id: "wp-1", name: "Отходы масел", fkko_code: "4 06 110 01 31 3" },
  { id: "wp-2", name: "Обтирочный материал", fkko_code: "9 19 204 01 60 4" },
] as never;

const existing = {
  id: "wm-1",
  passport_id: "wp-1",
  kind: "transferred",
  kind_label: "Передача оператору",
  happened_on: "2026-08-20",
  quantity_tons: "1.250",
  contract_id: null,
  counterparty: "ООО «Оператор»",
  notes: null,
};

const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
  render(
    <EcologyWasteMovementFormDialog
      passports={passports}
      contracts={contracts}
      trigger={<button>Записать движение</button>}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Записать движение" }));
};

describe("EcologyWasteMovementFormDialog — журнал учёта отходов (срез-100)", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMock.mockResolvedValue({ ...existing, id: "wm-new" });
    updateMock.mockResolvedValue(existing);
  });

  it("отправляет паспорт, вид, дату и массу; запятая уходит точкой", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Паспорт отхода"), "wp-1");
    await user.selectOptions(screen.getByLabelText("Движение"), "transferred");
    await user.type(screen.getByLabelText("Дата"), "2026-08-20");
    await user.type(screen.getByLabelText("Масса, т"), "1,250");
    await user.type(screen.getByLabelText("Контрагент"), "ООО «Оператор»");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0]).toEqual({
      passport_id: "wp-1",
      kind: "transferred",
      happened_on: "2026-08-20",
      quantity_tons: "1.250",
      counterparty: "ООО «Оператор»",
      // Договор не выбран — движение без договора (образование, накопление).
      contract_id: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Движение записано");
  });

  it("нулевая масса не проходит: пустая строка журнала ничего не учитывает", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Паспорт отхода"), "wp-1");
    await user.type(screen.getByLabelText("Дата"), "2026-08-20");
    await user.type(screen.getByLabelText("Масса, т"), "0");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Масса больше нуля: движение без массы ничего не учитывает",
      ),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("без паспорта и даты запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Масса, т"), "1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Выберите паспорт отхода"),
    ).toBeInTheDocument();
    expect(screen.getByText("Внесите дату движения")).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("дата в будущем: сервер отвечает словами, окно открыто", async () => {
    const user = userEvent.setup();
    createMock.mockRejectedValueOnce({
      status: 422,
      message:
        "Дата движения не может быть в будущем — журнал учёта фиксирует свершившееся",
      field_errors: [],
    });
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Паспорт отхода"), "wp-2");
    await user.type(screen.getByLabelText("Дата"), "2030-01-01");
    await user.type(screen.getByLabelText("Масса, т"), "2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("не может быть в будущем");
    expect(
      screen.getByRole("heading", { name: "Записать движение" }),
    ).toBeInTheDocument();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyWasteMovementFormDialog
        passports={passports}
        contracts={contracts}
        initialData={existing}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Паспорт отхода")).toHaveValue("wp-1");
    expect(screen.getByLabelText("Движение")).toHaveValue("transferred");
    expect(screen.getByLabelText("Масса, т")).toHaveValue("1.250");

    await user.selectOptions(screen.getByLabelText("Движение"), "utilized");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock.mock.calls[0][0]).toBe("wm-1");
    expect(updateMock.mock.calls[0][1]).toMatchObject({
      kind: "utilized",
      quantity_tons: "1.250",
      counterparty: "ООО «Оператор»",
    });
    expect(toastSuccess).toHaveBeenCalledWith("Запись обновлена");
  });

  it("договор с оператором выбирается из реестра (срез-112)", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Паспорт отхода"), "wp-1");
    await user.selectOptions(screen.getByLabelText("Движение"), "transferred");
    await user.type(screen.getByLabelText("Дата"), "2026-08-20");
    await user.type(screen.getByLabelText("Масса, т"), "1");
    await user.click(screen.getByText("Дополнительно"));
    // В списке договор назван контрагентом и номером — сумм в нём нет.
    await user.selectOptions(
      screen.getByLabelText("Договор с оператором"),
      "ct-1",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0].contract_id).toBe("ct-1");
  });

  it("на первом уровне пять полей; договор и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Паспорт отхода");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Дополнительно")).toBeInTheDocument();
    expect(screen.getByText(/без сумм и условий/i)).toBeInTheDocument();
  });
});

describe("ecologyWasteMovementFormSchema", () => {
  it("отклоняет массу не числом", () => {
    expect(
      ecologyWasteMovementFormSchema.safeParse({
        passport_id: "wp-1",
        kind: "generated",
        happened_on: "2026-08-20",
        quantity_tons: "много",
      }).success,
    ).toBe(false);
  });

  it("принимает массу с запятой", () => {
    expect(
      ecologyWasteMovementFormSchema.safeParse({
        passport_id: "wp-1",
        kind: "generated",
        happened_on: "2026-08-20",
        quantity_tons: "0,750",
      }).success,
    ).toBe(true);
  });
});
