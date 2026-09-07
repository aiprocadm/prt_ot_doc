import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FireDocumentFormDialog } from "@/features/fire-safety/FireDocumentFormDialog";
import { FireEquipmentFormDialog } from "@/features/fire-safety/FireEquipmentFormDialog";
import { FireMaintenanceFormDialog } from "@/features/fire-safety/FireMaintenanceFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { fireMaintenanceFormSchema } from "@/types/forms/fireSafety";

const createEquipmentMock = vi.fn();
const updateEquipmentMock = vi.fn();
const createDocumentMock = vi.fn();
const updateDocumentMock = vi.fn();
const recordMaintenanceMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/fireSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fireSafetyApi: {
    createEquipment: (...args: unknown[]) => createEquipmentMock(...args),
    updateEquipment: (...args: unknown[]) => updateEquipmentMock(...args),
    createDocument: (...args: unknown[]) => createDocumentMock(...args),
    updateDocument: (...args: unknown[]) => updateDocumentMock(...args),
    recordMaintenance: (...args: unknown[]) => recordMaintenanceMock(...args),
  },
}));

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

const existingUnit = {
  id: "unit-1",
  kind: "hydrant",
  label: "ПК-3",
  site_id: "site-1",
  location: "Цех №2",
  recharge_due: null,
  inspection_due: "2026-11-01",
  status: "active",
  last_maintenance_on: "2026-05-01",
  last_maintenance_result: "passed",
};

const existingDocument = {
  id: "doc-1",
  kind: "instruction_general",
  kind_label: "Инструкция о мерах ПБ (общеобъектовая)",
  title: "Инструкция о мерах пожарной безопасности",
  site_id: "site-1",
  number: "12-ПБ",
  location: null,
  approved_on: "2019-01-01",
  review_due: "2027-01-01",
  responsible: "Смирнов",
  document_id: null,
  notes: null,
  status: "ok",
  status_label: "Действует",
};

describe("FireEquipmentFormDialog — средство защиты (срез-103)", () => {
  beforeEach(() => {
    createEquipmentMock.mockReset();
    updateEquipmentMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createEquipmentMock.mockResolvedValue({ ...existingUnit, id: "unit-new" });
    updateEquipmentMock.mockResolvedValue(existingUnit);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <FireEquipmentFormDialog
        sites={sites}
        trigger={<button>Завести средство</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести средство" }));
  };

  it("отправляет вид, наименование и сроки; пустой срок — null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Вид средства"), "hydrant");
    await user.type(screen.getByLabelText("Наименование или номер"), "ПК-3");
    await user.type(screen.getByLabelText("Место установки"), "Цех №2");
    await user.type(screen.getByLabelText("Поверка / ТО до"), "2026-11-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createEquipmentMock).toHaveBeenCalled());
    expect(createEquipmentMock.mock.calls[0][0]).toEqual({
      kind: "hydrant",
      label: "ПК-3",
      site_id: null,
      location: "Цех №2",
      recharge_due: null,
      inspection_due: "2026-11-01",
      // Срез-111: состояние из закрытого словаря; по умолчанию «в эксплуатации».
      status: "active",
    });
    expect(toastSuccess).toHaveBeenCalledWith("Средство заведено");
  });

  it("без наименования запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Внесите наименование или инвентарный номер"),
    ).toBeInTheDocument();
    expect(createEquipmentMock).not.toHaveBeenCalled();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <FireEquipmentFormDialog
        sites={sites}
        initialData={existingUnit}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Вид средства")).toHaveValue("hydrant");
    expect(screen.getByLabelText("Площадка")).toHaveValue("site-1");

    await user.type(screen.getByLabelText("Место установки"), ", у входа");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateEquipmentMock).toHaveBeenCalled());
    expect(updateEquipmentMock.mock.calls[0][0]).toBe("unit-1");
    expect(updateEquipmentMock.mock.calls[0][1]).toMatchObject({
      location: "Цех №2, у входа",
      inspection_due: "2026-11-01",
    });
  });

  it("средство списывается с экрана: состояние из закрытого словаря (срез-111)", async () => {
    const user = userEvent.setup();
    render(
      <FireEquipmentFormDialog
        sites={sites}
        initialData={existingUnit}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    // Состояние подставлено из записи, а список — ровно три значения словаря.
    expect(screen.getByLabelText("Состояние")).toHaveValue("active");
    const statuses = Array.from(
      screen.getByLabelText("Состояние").querySelectorAll("option"),
    ).map((option) => option.getAttribute("value"));
    expect(statuses).toEqual(["active", "suspended", "decommissioned"]);

    await user.selectOptions(
      screen.getByLabelText("Состояние"),
      "decommissioned",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateEquipmentMock).toHaveBeenCalled());
    expect(updateEquipmentMock.mock.calls[0][1]).toMatchObject({
      status: "decommissioned",
    });
  });

  it("на первом уровне поля в бюджете; граница сроков названа", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Вид средства");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/Пустой срок означает «не\s+применимо»/i),
    ).toBeInTheDocument();
  });
});

describe("FireDocumentFormDialog — документ ПБ (срез-103)", () => {
  beforeEach(() => {
    createDocumentMock.mockReset();
    updateDocumentMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createDocumentMock.mockResolvedValue({
      ...existingDocument,
      id: "doc-new",
    });
    updateDocumentMock.mockResolvedValue(existingDocument);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <FireDocumentFormDialog
        sites={sites}
        trigger={<button>Завести документ</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести документ" }));
  };

  it("отправляет вид, название и срок пересмотра", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Вид документа"),
      "evacuation_plan",
    );
    await user.type(screen.getByLabelText("Документ"), "План эвакуации 2 этаж");
    await user.selectOptions(screen.getByLabelText("Площадка"), "site-2");
    await user.type(screen.getByLabelText("Пересмотр до"), "2028-03-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDocumentMock).toHaveBeenCalled());
    expect(createDocumentMock.mock.calls[0][0]).toEqual({
      kind: "evacuation_plan",
      title: "План эвакуации 2 этаж",
      site_id: "site-2",
      number: null,
      review_due: "2028-03-01",
      approved_on: null,
      location: null,
      responsible: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Документ заведён");
  });

  it("неизвестный вид: ответ сервера словами, окно открыто", async () => {
    const user = userEvent.setup();
    createDocumentMock.mockRejectedValueOnce({
      status: 422,
      message: "Неизвестный вид документа 'plan'; допустимые: order, ...",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Документ"), "Приказ");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("Неизвестный вид документа");
    expect(
      screen.getByRole("heading", { name: "Завести документ ПБ" }),
    ).toBeInTheDocument();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <FireDocumentFormDialog
        sites={sites}
        initialData={existingDocument}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Номер")).toHaveValue("12-ПБ");

    await user.clear(screen.getByLabelText("Пересмотр до"));
    await user.type(screen.getByLabelText("Пересмотр до"), "2029-01-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateDocumentMock).toHaveBeenCalled());
    expect(updateDocumentMock.mock.calls[0][1]).toMatchObject({
      review_due: "2029-01-01",
      responsible: "Смирнов",
      approved_on: "2019-01-01",
    });
  });

  it("экран не выдаёт перечень обязательного за свой; поля второго уровня свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Вид документа");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Утверждение, помещение и ответственный"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/определяет специалист — платформа этого не решает/i),
    ).toBeInTheDocument();
  });
});

describe("FireMaintenanceFormDialog — запись о работе (срез-103)", () => {
  beforeEach(() => {
    recordMaintenanceMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    recordMaintenanceMock.mockResolvedValue({ id: "maint-new" });
  });

  const openCreate = async (
    user: ReturnType<typeof userEvent.setup>,
    presetEquipmentId?: string,
  ) => {
    render(
      <FireMaintenanceFormDialog
        equipment={[existingUnit]}
        presetEquipmentId={presetEquipmentId}
        trigger={<button>Записать работу</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Записать работу" }));
  };

  it("отправляет средство, вид, дату и результат; пустой срок — null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Средство"), "unit-1");
    await user.selectOptions(screen.getByLabelText("Вид работы"), "recharge");
    await user.type(screen.getByLabelText("Дата работы"), "2026-09-01");
    await user.selectOptions(screen.getByLabelText("Результат"), "passed");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(recordMaintenanceMock).toHaveBeenCalled());
    expect(recordMaintenanceMock.mock.calls[0][0]).toEqual({
      equipment_id: "unit-1",
      kind: "recharge",
      performed_on: "2026-09-01",
      result: "passed",
      performer: null,
      next_due: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Работа записана");
  });

  it("средство подставляется из строки реестра", async () => {
    const user = userEvent.setup();
    await openCreate(user, "unit-1");

    expect(screen.getByLabelText("Средство")).toHaveValue("unit-1");
  });

  it("без даты запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user, "unit-1");

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Внесите дату работы")).toBeInTheDocument();
    expect(recordMaintenanceMock).not.toHaveBeenCalled();
  });

  it("форма не обещает переносить срок сама: это делает сервер по результату", async () => {
    const user = userEvent.setup();
    await openCreate(user, "unit-1");
    await screen.findByLabelText("Средство");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/«неисправно» срок не двигает/i),
    ).toBeInTheDocument();
  });
});

describe("fireMaintenanceFormSchema", () => {
  it("требует средство, дату и результат", () => {
    expect(
      fireMaintenanceFormSchema.safeParse({
        equipment_id: "",
        kind: "inspection",
        performed_on: "",
        result: "",
      }).success,
    ).toBe(false);
  });

  it("принимает работу без исполнителя и следующего срока", () => {
    expect(
      fireMaintenanceFormSchema.safeParse({
        equipment_id: "unit-1",
        kind: "inspection",
        performed_on: "2026-09-01",
        result: "passed",
      }).success,
    ).toBe(true);
  });
});
