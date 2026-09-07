import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DriverFormDialog } from "@/features/road-safety/DriverFormDialog";
import { VehicleFormDialog } from "@/features/road-safety/VehicleFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { driverFormSchema, vehicleFormSchema } from "@/types/forms/roadSafety";

const createVehicleMock = vi.fn();
const updateVehicleMock = vi.fn();
const createDriverMock = vi.fn();
const updateDriverMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/roadSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  roadSafetyApi: {
    createVehicle: (...args: unknown[]) => createVehicleMock(...args),
    updateVehicle: (...args: unknown[]) => updateVehicleMock(...args),
    createDriver: (...args: unknown[]) => createDriverMock(...args),
    updateDriver: (...args: unknown[]) => updateDriverMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const sites = [{ id: "site-1", name: "Площадка №1" }] as never;
const persons = [
  { id: "p-1", full_name: "Шофёров Пётр Иванович" },
  { id: "p-2", full_name: "Петров Пётр Петрович" },
] as never;

const existingVehicle = {
  id: "v-1",
  plate_number: "А123ВС777",
  brand_model: "ГАЗ-3302",
  kind: "truck",
  kind_label: "Грузовой автомобиль",
  status: "in_service",
  status_label: "В эксплуатации",
  vin: "X9L",
  year_made: 2015,
  site_id: "site-1",
  inspection_due: "2026-10-01",
  insurance_due: null,
  license_number: null,
  license_due: null,
  tachograph_installed: true,
  tachograph_due: "2027-01-01",
  notes: null,
  inspection_status: "ok",
  inspection_status_label: "Действует",
  insurance_status: "missing",
  insurance_status_label: "Сведения не внесены",
  tachograph_status: "ok",
  tachograph_status_label: "Действует",
};

const existingDriver = {
  id: "d-1",
  person_id: "p-1",
  person_name: "Шофёров Пётр Иванович",
  personnel_number: "ТН-1",
  position_title: "Водитель",
  license_number: "9900 123456",
  categories: ["B", "C"],
  category_labels: ["B — легковые автомобили", "C — грузовые автомобили"],
  license_issued_at: "2018-05-01",
  license_due: "2028-05-01",
  experience_since: "2010-03-01",
  experience_years: 16,
  status: "admitted",
  status_label: "Допущен к управлению",
  license_status: "ok",
  license_status_label: "Действует",
  notes: null,
};

describe("VehicleFormDialog — транспортное средство (срез-107)", () => {
  beforeEach(() => {
    createVehicleMock.mockReset();
    updateVehicleMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createVehicleMock.mockResolvedValue({ ...existingVehicle, id: "v-new" });
    updateVehicleMock.mockResolvedValue(existingVehicle);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <VehicleFormDialog sites={sites} trigger={<button>Завести ТС</button>} />,
    );
    await user.click(screen.getByRole("button", { name: "Завести ТС" }));
  };

  it("отправляет госномер, марку и вид; пустые сроки — null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Госномер"), "В001АА99");
    await user.type(screen.getByLabelText("Марка и модель"), "УАЗ-390995");
    await user.selectOptions(screen.getByLabelText("Вид ТС"), "special");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createVehicleMock).toHaveBeenCalled());
    expect(createVehicleMock.mock.calls[0][0]).toEqual({
      plate_number: "В001АА99",
      brand_model: "УАЗ-390995",
      kind: "special",
      status: "in_service",
      vin: null,
      year_made: null,
      site_id: null,
      inspection_due: null,
      insurance_due: null,
      license_number: null,
      license_due: null,
      tachograph_installed: false,
      tachograph_due: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("ТС заведено");
  });

  it("срок поверки тахографа без самого тахографа не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Госномер"), "В001АА99");
    await user.type(screen.getByLabelText("Марка и модель"), "УАЗ");
    await user.click(screen.getByText("VIN, площадка, лицензия и тахограф"));
    await user.type(
      screen.getByLabelText("Поверка тахографа до"),
      "2027-01-01",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Срок поверки указан, а тахограф не отмечен как установленный",
      ),
    ).toBeInTheDocument();
    expect(createVehicleMock).not.toHaveBeenCalled();
  });

  it("дубль госномера: ответ сервера словами, окно открыто", async () => {
    const user = userEvent.setup();
    createVehicleMock.mockRejectedValueOnce({
      status: 422,
      message: "ТС с номером 'А123ВС777' уже заведено",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Госномер"), "А123ВС777");
    await user.type(screen.getByLabelText("Марка и модель"), "ГАЗ");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже заведено");
    expect(
      screen.getByRole("heading", { name: "Завести ТС" }),
    ).toBeInTheDocument();
  });

  it("правка подставляет запись целиком и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <VehicleFormDialog
        sites={sites}
        initialData={existingVehicle}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Госномер")).toHaveValue("А123ВС777");
    expect(screen.getByLabelText("Вид ТС")).toHaveValue("truck");

    await user.selectOptions(
      screen.getByLabelText("Состояние"),
      "decommissioned",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateVehicleMock).toHaveBeenCalled());
    expect(updateVehicleMock.mock.calls[0][1]).toMatchObject({
      status: "decommissioned",
      year_made: 2015,
      tachograph_installed: true,
      tachograph_due: "2027-01-01",
    });
  });

  it("на первом уровне шесть полей; границы дисциплины названы", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Госномер");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("VIN, площадка, лицензия и тахограф"),
    ).toBeInTheDocument();
    expect(screen.getByText(/платформа этого не решает/i)).toBeInTheDocument();
  });
});

describe("DriverFormDialog — карточка водителя (срез-107)", () => {
  beforeEach(() => {
    createDriverMock.mockReset();
    updateDriverMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createDriverMock.mockResolvedValue({ ...existingDriver, id: "d-new" });
    updateDriverMock.mockResolvedValue(existingDriver);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <DriverFormDialog
        persons={persons}
        trigger={<button>Завести водителя</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести водителя" }));
  };

  it("без единой категории запрос не уходит: это не водитель", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Работник"), "p-2");
    await user.type(screen.getByLabelText("Номер удостоверения"), "77 77 1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Отметьте хотя бы одну категорию: без неё это не водитель",
      ),
    ).toBeInTheDocument();
    expect(createDriverMock).not.toHaveBeenCalled();
  });

  it("отправляет отмеченные категории списком", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Работник"), "p-2");
    await user.type(screen.getByLabelText("Номер удостоверения"), "77 77 1");
    await user.click(screen.getByRole("checkbox", { name: "B" }));
    await user.click(screen.getByRole("checkbox", { name: "D" }));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDriverMock).toHaveBeenCalled());
    expect(createDriverMock.mock.calls[0][0]).toMatchObject({
      person_id: "p-2",
      license_number: "77 77 1",
      categories: ["B", "D"],
      status: "admitted",
    });
    expect(toastSuccess).toHaveBeenCalledWith("Водитель заведён");
  });

  it("правка: работник заперт, тело уходит без person_id", async () => {
    const user = userEvent.setup();
    render(
      <DriverFormDialog
        persons={persons}
        initialData={existingDriver}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Работник")).toBeDisabled();
    expect(screen.getByLabelText("Номер удостоверения")).toHaveValue(
      "9900 123456",
    );

    await user.selectOptions(screen.getByLabelText("Допуск"), "suspended");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateDriverMock).toHaveBeenCalled());
    expect(updateDriverMock.mock.calls[0][1]).toMatchObject({
      status: "suspended",
      categories: ["B", "C"],
      experience_since: "2010-03-01",
    });
    expect(updateDriverMock.mock.calls[0][1]).not.toHaveProperty("person_id");
  });

  it("стаж в будущем: ответ сервера словами, окно открыто", async () => {
    const user = userEvent.setup();
    createDriverMock.mockRejectedValueOnce({
      status: 422,
      message: "Стаж не может начинаться в будущем",
      field_errors: [],
    });
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Работник"), "p-2");
    await user.type(screen.getByLabelText("Номер удостоверения"), "77 77 1");
    await user.click(screen.getByRole("checkbox", { name: "B" }));
    await user.click(screen.getByText("Выдача удостоверения, стаж и заметки"));
    await user.type(screen.getByLabelText("Стаж с"), "2030-01-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("в будущем");
    expect(
      screen.getByRole("heading", { name: "Завести водителя" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне пять полей; отметки категорий — один вопрос", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Работник");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Выдача удостоверения, стаж и заметки"),
    ).toBeInTheDocument();
  });
});

describe("схемы форм БДД (срез-107)", () => {
  it("ТС: год выпуска вне диапазона не проходит", () => {
    expect(
      vehicleFormSchema.safeParse({
        plate_number: "А1",
        brand_model: "ГАЗ",
        kind: "truck",
        status: "in_service",
        year_made: "1800",
      }).success,
    ).toBe(false);
  });

  it("водитель: одна категория достаточна", () => {
    expect(
      driverFormSchema.safeParse({
        person_id: "p-1",
        license_number: "77",
        categories: ["B"],
        status: "admitted",
      }).success,
    ).toBe(true);
  });
});
