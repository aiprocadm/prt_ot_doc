import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyWastePassportFormDialog } from "@/features/ecology/EcologyWastePassportFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import {
  ecologyWastePassportFormSchema,
  tonsToPayload,
} from "@/types/forms/ecologyWastePassport";

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
      createWastePassport: (...args: unknown[]) => createMock(...args),
      updateWastePassport: (...args: unknown[]) => updateMock(...args),
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const facilities = [
  { id: "nvos-1", name: "Производственная площадка №1" },
  { id: "nvos-2", name: "Котельная №3" },
] as never;

const existing = {
  id: "wp-1",
  name: "Отходы минеральных масел моторных",
  fkko_code: "4 06 110 01 31 3",
  hazard_class: "III",
  hazard_class_label: "III класс — умеренно опасные",
  facility_id: "nvos-1",
  approved_on: "2025-06-01",
  annual_limit_tons: "12.500",
  notes: null,
  generated_this_year_tons: "3.200",
  over_limit: false,
};

const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
  render(
    <EcologyWastePassportFormDialog
      facilities={facilities}
      trigger={<button>Завести паспорт</button>}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Завести паспорт" }));
};

describe("EcologyWastePassportFormDialog — паспорт отхода (срез-99)", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMock.mockResolvedValue({ ...existing, id: "wp-new" });
    updateMock.mockResolvedValue(existing);
  });

  it("отправляет вид, код ФККО, класс и лимит; лимит с запятой — числом", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(
      screen.getByLabelText("Вид отхода"),
      "Отходы минеральных масел моторных",
    );
    await user.type(screen.getByLabelText("Код ФККО"), "4 06 110 01 31 3");
    await user.selectOptions(screen.getByLabelText("Класс опасности"), "III");
    await user.selectOptions(screen.getByLabelText("Объект НВОС"), "nvos-1");
    await user.type(screen.getByLabelText("Годовой лимит, т"), "12,5");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0]).toEqual({
      name: "Отходы минеральных масел моторных",
      fkko_code: "4 06 110 01 31 3",
      hazard_class: "III",
      facility_id: "nvos-1",
      annual_limit_tons: "12.5",
      approved_on: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Паспорт заведён");
  });

  it("пустой лимит уходит как null: «не установлен», а не ноль тонн", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Вид отхода"), "Обтирочный материал");
    await user.type(screen.getByLabelText("Код ФККО"), "9 19 204 01 60 4");
    await user.selectOptions(screen.getByLabelText("Класс опасности"), "IV");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0].annual_limit_tons).toBeNull();
    expect(createMock.mock.calls[0][0].facility_id).toBeNull();
  });

  it("пятого класса в списке нет: на отходы V класса паспорт не составляют", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    const options = Array.from(
      screen.getByLabelText("Класс опасности").querySelectorAll("option"),
    ).map((option) => option.getAttribute("value"));
    expect(options).toEqual(["", "I", "II", "III", "IV"]);
    expect(
      screen.getByText(/отходы V класса\s+паспортизации не подлежат/i),
    ).toBeInTheDocument();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyWastePassportFormDialog
        facilities={facilities}
        initialData={existing}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Вид отхода")).toHaveValue(existing.name);
    expect(screen.getByLabelText("Класс опасности")).toHaveValue("III");
    expect(screen.getByLabelText("Годовой лимит, т")).toHaveValue("12.500");

    await user.selectOptions(screen.getByLabelText("Класс опасности"), "II");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock.mock.calls[0][0]).toBe("wp-1");
    expect(updateMock.mock.calls[0][1]).toMatchObject({
      hazard_class: "II",
      annual_limit_tons: "12.500",
      approved_on: "2025-06-01",
    });
    expect(toastSuccess).toHaveBeenCalledWith("Паспорт обновлён");
  });

  it("дубль кода ФККО: 422 словами, окно открыто", async () => {
    const user = userEvent.setup();
    createMock.mockRejectedValueOnce({
      status: 422,
      message: "Паспорт на код ФККО '4 06 110 01 31 3' уже заведён",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Вид отхода"), "Отходы масел");
    await user.type(screen.getByLabelText("Код ФККО"), "4 06 110 01 31 3");
    await user.selectOptions(screen.getByLabelText("Класс опасности"), "III");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже заведён");
    expect(
      screen.getByRole("heading", { name: "Завести паспорт отхода" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне пять полей: дата утверждения и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Вид отхода");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Дата утверждения и заметки")).toBeInTheDocument();
    expect(
      screen.getByText(/платформа его не рассчитывает/i),
    ).toBeInTheDocument();
  });
});

describe("ecologyWastePassportFormSchema", () => {
  it("отклоняет пустые название, код и класс", () => {
    expect(
      ecologyWastePassportFormSchema.safeParse({
        name: " ",
        fkko_code: "",
        hazard_class: "",
      }).success,
    ).toBe(false);
  });

  it("отклоняет лимит, который не число тонн", () => {
    expect(
      ecologyWastePassportFormSchema.safeParse({
        name: "Отходы масел",
        fkko_code: "4 06 110 01 31 3",
        hazard_class: "III",
        annual_limit_tons: "много",
      }).success,
    ).toBe(false);
  });

  it("пустой лимит — «не установлен»", () => {
    expect(tonsToPayload("")).toBeNull();
    expect(tonsToPayload(undefined)).toBeNull();
    expect(tonsToPayload("0,750")).toBe("0.750");
  });
});
