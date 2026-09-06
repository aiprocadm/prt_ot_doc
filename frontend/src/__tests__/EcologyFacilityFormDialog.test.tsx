import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyFacilityFormDialog } from "@/features/ecology/EcologyFacilityFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { ecologyFacilityFormSchema } from "@/types/forms/ecologyFacility";

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
      createFacility: (...args: unknown[]) => createMock(...args),
      updateFacility: (...args: unknown[]) => updateMock(...args),
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const sites = [
  { id: "site-1", name: "Площадка №1" },
  { id: "site-2", name: "Площадка №2" },
] as never;

const existing = {
  id: "nvos-1",
  name: "Производственная площадка №1",
  register_number: "12-0177-001234-П",
  category: "II",
  category_label: "II категория — умеренное негативное воздействие",
  site_id: "site-1",
  registered_on: "2019-04-10",
  actualized_on: "2026-02-01",
  excluded_on: null,
  status: "registered",
  status_label: "На государственном учёте",
  responsible: "Эколог Иванова",
  notes: null,
};

const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
  render(
    <EcologyFacilityFormDialog
      sites={sites}
      trigger={<button>Завести объект</button>}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Завести объект" }));
};

describe("EcologyFacilityFormDialog — объект НВОС (срез-99)", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMock.mockResolvedValue({ ...existing, id: "nvos-new" });
    updateMock.mockResolvedValue(existing);
  });

  it("отправляет сведения из свидетельства; незаполненное — null", async () => {
    const user = userEvent.setup();
    const onSubmitted = vi.fn();
    render(
      <EcologyFacilityFormDialog
        sites={sites}
        trigger={<button>Завести объект</button>}
        onSubmitted={onSubmitted}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести объект" }));

    await user.type(screen.getByLabelText("Объект"), "Котельная №3");
    await user.type(screen.getByLabelText("Код в реестре"), "12-0177-001234-П");
    await user.selectOptions(screen.getByLabelText("Категория"), "II");
    await user.selectOptions(screen.getByLabelText("Площадка"), "site-2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0]).toEqual({
      name: "Котельная №3",
      register_number: "12-0177-001234-П",
      category: "II",
      site_id: "site-2",
      status: "registered",
      registered_on: null,
      actualized_on: null,
      excluded_on: null,
      responsible: null,
      notes: null,
    });
    expect(onSubmitted).toHaveBeenCalledWith(
      expect.objectContaining({ id: "nvos-new" }),
    );
    expect(toastSuccess).toHaveBeenCalledWith("Объект заведён");
  });

  it("без названия, кода и категории запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Назовите объект")).toBeInTheDocument();
    expect(
      screen.getByText("Внесите код объекта из свидетельства об учёте"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Выберите категорию из свидетельства"),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("снятие с учёта без даты снятия не проходит: надзору нечего ответить", async () => {
    const user = userEvent.setup();
    render(
      <EcologyFacilityFormDialog
        sites={sites}
        initialData={existing}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    await user.selectOptions(screen.getByLabelText("Состояние"), "excluded");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("У снятого с учёта нужна дата снятия"),
    ).toBeInTheDocument();
    expect(updateMock).not.toHaveBeenCalled();
  });

  it("правка подставляет запись целиком и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyFacilityFormDialog
        sites={sites}
        initialData={existing}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Объект")).toHaveValue(existing.name);
    expect(screen.getByLabelText("Код в реестре")).toHaveValue(
      existing.register_number,
    );
    expect(screen.getByLabelText("Категория")).toHaveValue("II");
    expect(screen.getByLabelText("Площадка")).toHaveValue("site-1");

    await user.selectOptions(screen.getByLabelText("Категория"), "III");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock.mock.calls[0][0]).toBe("nvos-1");
    expect(updateMock.mock.calls[0][1]).toMatchObject({
      category: "III",
      registered_on: "2019-04-10",
      actualized_on: "2026-02-01",
      responsible: "Эколог Иванова",
    });
    expect(toastSuccess).toHaveBeenCalledWith("Объект обновлён");
  });

  it("дубль кода реестра: 422 словами, окно открыто", async () => {
    const user = userEvent.setup();
    createMock.mockRejectedValueOnce({
      status: 422,
      message: "Объект с кодом '12-0177-001234-П' уже заведён",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Объект"), "Котельная №3");
    await user.type(screen.getByLabelText("Код в реестре"), "12-0177-001234-П");
    await user.selectOptions(screen.getByLabelText("Категория"), "I");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже заведён");
    expect(
      screen.getByRole("heading", { name: "Завести объект НВОС" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне пять полей: даты, ответственный и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Объект");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Даты, ответственный и заметки"),
    ).toBeInTheDocument();
    // Категорию платформа не вычисляет — это названо в самой форме.
    expect(
      screen.getByText(/платформа её не вычисляет и не подсказывает/i),
    ).toBeInTheDocument();
  });
});

describe("ecologyFacilityFormSchema", () => {
  it("требует название, код и категорию", () => {
    expect(
      ecologyFacilityFormSchema.safeParse({
        name: "  ",
        register_number: "",
        category: "",
        status: "registered",
      }).success,
    ).toBe(false);
  });

  it("принимает объект на учёте без дат", () => {
    expect(
      ecologyFacilityFormSchema.safeParse({
        name: "Котельная №3",
        register_number: "12-0177-001234-П",
        category: "IV",
        status: "registered",
      }).success,
    ).toBe(true);
  });
});
