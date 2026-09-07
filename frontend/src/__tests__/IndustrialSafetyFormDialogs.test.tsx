import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpoDeviceFormDialog } from "@/features/industrial-safety/OpoDeviceFormDialog";
import { OpoDeviceWorkFormDialog } from "@/features/industrial-safety/OpoDeviceWorkFormDialog";
import { OpoFacilityFormDialog } from "@/features/industrial-safety/OpoFacilityFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { opoDeviceWorkFormSchema } from "@/types/forms/industrialSafety";

const createFacilityMock = vi.fn();
const updateFacilityMock = vi.fn();
const createDeviceMock = vi.fn();
const updateDeviceMock = vi.fn();
const recordWorkMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/industrialSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  industrialSafetyApi: {
    createFacility: (...args: unknown[]) => createFacilityMock(...args),
    updateFacility: (...args: unknown[]) => updateFacilityMock(...args),
    createDevice: (...args: unknown[]) => createDeviceMock(...args),
    updateDevice: (...args: unknown[]) => updateDeviceMock(...args),
    recordDeviceWork: (...args: unknown[]) => recordWorkMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const sites = [{ id: "site-1", name: "Площадка №1" }] as never;

const existingFacility = {
  id: "opo-1",
  name: "Площадка компрессорной",
  register_number: "А01-12345-0001",
  hazard_class: "III",
  hazard_class_label: "III класс — средняя опасность",
  site_id: "site-1",
  registered_on: "2015-04-01",
  excluded_on: null,
  status: "registered",
  status_label: "Зарегистрирован",
  responsible: "Иванов",
  notes: null,
};

const facilities = [existingFacility] as never;

const existingDevice = {
  id: "dev-1",
  facility_id: "opo-1",
  kind: "pressure_vessel",
  kind_label: "Сосуд, работающий под давлением",
  name: "Ресивер Р-1",
  serial_number: "12345",
  commissioned_on: "2009-05-20",
  lifetime_until: "2024-05-20",
  epb_conclusion_number: null,
  epb_registered_on: null,
  epb_valid_until: null,
  status: "in_operation",
  status_label: "В эксплуатации",
  notes: null,
  epb_status: "absent",
  epb_status_label: "Заключения нет",
  past_lifetime: true,
  last_work_on: null,
  last_work_result: null,
};

describe("OpoFacilityFormDialog — объект ОПО (срез-105)", () => {
  beforeEach(() => {
    createFacilityMock.mockReset();
    updateFacilityMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createFacilityMock.mockResolvedValue({
      ...existingFacility,
      id: "opo-new",
    });
    updateFacilityMock.mockResolvedValue(existingFacility);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <OpoFacilityFormDialog
        sites={sites}
        trigger={<button>Завести объект</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести объект" }));
  };

  it("отправляет наименование, номер и класс; пустые поля — null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Объект"), "Склад ГСМ");
    await user.type(screen.getByLabelText("Номер в реестре"), "А01-1-0001");
    await user.selectOptions(screen.getByLabelText("Класс опасности"), "II");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createFacilityMock).toHaveBeenCalled());
    expect(createFacilityMock.mock.calls[0][0]).toEqual({
      name: "Склад ГСМ",
      register_number: "А01-1-0001",
      hazard_class: "II",
      site_id: null,
      status: "registered",
      registered_on: null,
      excluded_on: null,
      responsible: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Объект зарегистрирован");
  });

  it("без номера в реестре и класса запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Объект"), "Склад");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Внесите номер из свидетельства о регистрации"),
    ).toBeInTheDocument();
    expect(screen.getByText("Выберите класс опасности")).toBeInTheDocument();
    expect(createFacilityMock).not.toHaveBeenCalled();
  });

  it("исключение из реестра без даты не проходит", async () => {
    const user = userEvent.setup();
    render(
      <OpoFacilityFormDialog
        sites={sites}
        initialData={existingFacility}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    await user.selectOptions(screen.getByLabelText("Состояние"), "excluded");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "У исключённого из реестра нужна дата исключения",
      ),
    ).toBeInTheDocument();
    expect(updateFacilityMock).not.toHaveBeenCalled();
  });

  it("на первом уровне пять полей; класс платформа не вычисляет", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Объект");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/платформа его не\s+вычисляет/i),
    ).toBeInTheDocument();
  });
});

describe("OpoDeviceFormDialog — техническое устройство (срез-105)", () => {
  beforeEach(() => {
    createDeviceMock.mockReset();
    updateDeviceMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createDeviceMock.mockResolvedValue({ ...existingDevice, id: "dev-new" });
    updateDeviceMock.mockResolvedValue(existingDevice);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <OpoDeviceFormDialog
        facilities={facilities}
        trigger={<button>Завести устройство</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Завести устройство" }),
    );
  };

  it("отправляет объект, вид и наименование; поля ЭПБ пусты — это не просрочка", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Объект (ОПО)"), "opo-1");
    await user.selectOptions(
      screen.getByLabelText("Вид устройства"),
      "lifting",
    );
    await user.type(screen.getByLabelText("Устройство"), "Кран мостовой");
    await user.type(screen.getByLabelText("Заводской номер"), "77");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDeviceMock).toHaveBeenCalled());
    expect(createDeviceMock.mock.calls[0][0]).toEqual({
      facility_id: "opo-1",
      kind: "lifting",
      name: "Кран мостовой",
      serial_number: "77",
      status: "in_operation",
      lifetime_until: null,
      commissioned_on: null,
      epb_conclusion_number: null,
      epb_registered_on: null,
      epb_valid_until: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Устройство заведено");
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <OpoDeviceFormDialog
        facilities={facilities}
        initialData={existingDevice}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Объект (ОПО)")).toHaveValue("opo-1");
    expect(screen.getByLabelText("Срок службы до")).toHaveValue("2024-05-20");

    await user.selectOptions(screen.getByLabelText("Состояние"), "suspended");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateDeviceMock).toHaveBeenCalled());
    expect(updateDeviceMock.mock.calls[0][1]).toMatchObject({
      status: "suspended",
      serial_number: "12345",
      commissioned_on: "2009-05-20",
    });
  });

  it("на первом уровне шесть полей: заключение ЭПБ свёрнуто", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Объект (ОПО)");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Ввод в эксплуатацию и заключение экспертизы"),
    ).toBeInTheDocument();
    expect(screen.getByText(/платформа этого не решает/i)).toBeInTheDocument();
  });
});

describe("OpoDeviceWorkFormDialog — работа по устройству (срез-105)", () => {
  beforeEach(() => {
    recordWorkMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    recordWorkMock.mockResolvedValue({ id: "work-new" });
  });

  const openCreate = async (
    user: ReturnType<typeof userEvent.setup>,
    presetDeviceId?: string,
  ) => {
    render(
      <OpoDeviceWorkFormDialog
        devices={[existingDevice]}
        presetDeviceId={presetDeviceId}
        trigger={<button>Записать работу</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Записать работу" }));
  };

  it("экспертиза без номера заключения не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user, "dev-1");

    await user.selectOptions(screen.getByLabelText("Вид работы"), "epb");
    await user.type(screen.getByLabelText("Дата работы"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Для экспертизы обязателен номер заключения: он вносится в реестр Ростехнадзора",
      ),
    ).toBeInTheDocument();
    expect(recordWorkMock).not.toHaveBeenCalled();
  });

  it("экспертиза с номером уходит на сервер", async () => {
    const user = userEvent.setup();
    await openCreate(user, "dev-1");

    await user.selectOptions(screen.getByLabelText("Вид работы"), "epb");
    await user.type(screen.getByLabelText("Дата работы"), "2026-09-01");
    await user.type(screen.getByLabelText("Номер заключения"), "ЭПБ-77/2026");
    await user.selectOptions(
      screen.getByLabelText("Результат"),
      "with_remarks",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(recordWorkMock).toHaveBeenCalled());
    expect(recordWorkMock.mock.calls[0][0]).toEqual({
      device_id: "dev-1",
      kind: "epb",
      performed_on: "2026-09-01",
      result: "with_remarks",
      conclusion_number: "ЭПБ-77/2026",
      performer: null,
      next_due: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Работа записана");
  });

  it("обслуживание номера заключения не требует", async () => {
    const user = userEvent.setup();
    await openCreate(user, "dev-1");

    await user.selectOptions(
      screen.getByLabelText("Вид работы"),
      "maintenance",
    );
    await user.type(screen.getByLabelText("Дата работы"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(recordWorkMock).toHaveBeenCalled());
    expect(recordWorkMock.mock.calls[0][0].conclusion_number).toBeNull();
  });

  it("форма называет, что срок продлевает только экспертиза", async () => {
    const user = userEvent.setup();
    await openCreate(user, "dev-1");
    await screen.findByLabelText("Устройство");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/только положительная экспертиза/i),
    ).toBeInTheDocument();
  });
});

describe("opoDeviceWorkFormSchema", () => {
  it("требует номер заключения только у экспертизы", () => {
    expect(
      opoDeviceWorkFormSchema.safeParse({
        device_id: "dev-1",
        kind: "epb",
        performed_on: "2026-09-01",
        result: "passed",
      }).success,
    ).toBe(false);
    expect(
      opoDeviceWorkFormSchema.safeParse({
        device_id: "dev-1",
        kind: "repair",
        performed_on: "2026-09-01",
        result: "passed",
      }).success,
    ).toBe(true);
  });
});
