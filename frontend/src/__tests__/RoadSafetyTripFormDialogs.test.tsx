import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccidentFormDialog } from "@/features/road-safety/AccidentFormDialog";
import { ViolationFormDialog } from "@/features/road-safety/ViolationFormDialog";
import { WaybillFormDialog } from "@/features/road-safety/WaybillFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import {
  violationFormSchema,
  waybillFormSchema,
} from "@/types/forms/roadSafety";

const createWaybillMock = vi.fn();
const updateWaybillMock = vi.fn();
const createAccidentMock = vi.fn();
const updateAccidentMock = vi.fn();
const createViolationMock = vi.fn();
const updateViolationMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/roadSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  roadSafetyApi: {
    createWaybill: (...args: unknown[]) => createWaybillMock(...args),
    updateWaybill: (...args: unknown[]) => updateWaybillMock(...args),
    createAccident: (...args: unknown[]) => createAccidentMock(...args),
    updateAccident: (...args: unknown[]) => updateAccidentMock(...args),
    createViolation: (...args: unknown[]) => createViolationMock(...args),
    updateViolation: (...args: unknown[]) => updateViolationMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const vehicles = [
  {
    id: "v-1",
    plate_number: "А123ВС777",
    brand_model: "ГАЗ-3302",
  },
] as never;

const drivers = [{ id: "d-1", person_name: "Шофёров Пётр Иванович" }] as never;

const existingWaybill = {
  id: "wb-1",
  number: "000123",
  vehicle_id: "v-1",
  vehicle_plate: "А123ВС777",
  vehicle_brand_model: "ГАЗ-3302",
  driver_id: "d-1",
  driver_name: "Шофёров Пётр Иванович",
  driver_license_number: "9900 123456",
  issued_on: "2026-08-20",
  departure_at: "2026-08-20T08:00:00+00:00",
  return_at: null,
  trip_hours: null,
  pre_trip_medical: "passed",
  pre_trip_medical_label: "Пройден",
  post_trip_medical: "not_recorded",
  post_trip_medical_label: "Сведения не внесены",
  pre_trip_technical: "not_recorded",
  pre_trip_technical_label: "Сведения не внесены",
  release_status: "unconfirmed",
  release_status_label: "Контроль не подтверждён",
  status: "issued",
  status_label: "Выдан",
  notes: null,
};

const existingViolation = {
  id: "vio-1",
  vehicle_id: "v-1",
  vehicle_plate: "А123ВС777",
  driver_id: null,
  driver_name: null,
  driver_identified: false,
  occurred_at: "2026-08-02T12:00:00+00:00",
  source: "camera",
  source_label: "Автоматическая фиксация (камера)",
  article: "12.9 ч.2",
  resolution_number: "18810",
  place: null,
  fine_amount: "500.00",
  fine_paid_on: null,
  fine_status: "unpaid",
  fine_status_label: "Не оплачен",
  description: null,
};

describe("WaybillFormDialog — путевой лист (срез-108)", () => {
  beforeEach(() => {
    createWaybillMock.mockReset();
    updateWaybillMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createWaybillMock.mockResolvedValue({ ...existingWaybill, id: "wb-new" });
    updateWaybillMock.mockResolvedValue(existingWaybill);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <WaybillFormDialog
        vehicles={vehicles}
        drivers={drivers}
        trigger={<button>Выписать лист</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Выписать лист" }));
  };

  it("отметки по умолчанию — «сведения не внесены», а не «пройден»", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Номер листа"), "000999");
    await user.type(screen.getByLabelText("Выдан"), "2026-09-01");
    await user.selectOptions(screen.getByLabelText("Машина"), "v-1");
    await user.selectOptions(screen.getByLabelText("Водитель"), "d-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createWaybillMock).toHaveBeenCalled());
    expect(createWaybillMock.mock.calls[0][0]).toMatchObject({
      pre_trip_medical: "not_recorded",
      pre_trip_technical: "not_recorded",
      post_trip_medical: "not_recorded",
      departure_at: null,
      return_at: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Лист выписан");
  });

  it("возвращение раньше выезда не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Номер листа"), "000999");
    await user.type(screen.getByLabelText("Выдан"), "2026-09-01");
    await user.selectOptions(screen.getByLabelText("Машина"), "v-1");
    await user.selectOptions(screen.getByLabelText("Водитель"), "d-1");
    await user.click(
      screen.getByText("Отметки контроля, время рейса и заметки"),
    );
    await user.type(screen.getByLabelText("Выезд"), "2026-09-01T18:00");
    await user.type(screen.getByLabelText("Возвращение"), "2026-09-01T08:00");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "Возвращение раньше выезда: проверьте даты рейса",
      ),
    ).toBeInTheDocument();
    expect(createWaybillMock).not.toHaveBeenCalled();
  });

  it("правка: машина и водитель заперты, тело уходит без них", async () => {
    const user = userEvent.setup();
    render(
      <WaybillFormDialog
        vehicles={vehicles}
        drivers={drivers}
        initialData={existingWaybill}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Машина")).toBeDisabled();
    expect(screen.getByLabelText("Водитель")).toBeDisabled();

    await user.selectOptions(
      screen.getByLabelText("Состояние листа"),
      "closed",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateWaybillMock).toHaveBeenCalled());
    expect(updateWaybillMock.mock.calls[0][1]).toMatchObject({
      status: "closed",
      pre_trip_medical: "passed",
      // Дата-время приходит с зоной, а в поле уходит без секунд — проверяем,
      // что обратно сервер получает полную отметку времени.
      departure_at: "2026-08-20T08:00:00",
    });
    expect(updateWaybillMock.mock.calls[0][1]).not.toHaveProperty("vehicle_id");
    expect(updateWaybillMock.mock.calls[0][1]).not.toHaveProperty("driver_id");
  });

  it("на первом уровне пять полей: отметки и время рейса свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Номер листа");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Отметки контроля, время рейса и заметки"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/законное состояние, а не\s+нарушение/i),
    ).toBeInTheDocument();
  });
});

describe("AccidentFormDialog — ДТП (срез-108)", () => {
  beforeEach(() => {
    createAccidentMock.mockReset();
    updateAccidentMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createAccidentMock.mockResolvedValue({ id: "acc-new" });
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <AccidentFormDialog
        vehicles={vehicles}
        drivers={drivers}
        trigger={<button>Зарегистрировать ДТП</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Зарегистрировать ДТП" }),
    );
  };

  it("вина по умолчанию «не установлена», водитель необязателен", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("Дата и время"), "2026-08-01T09:30");
    await user.type(screen.getByLabelText("Место"), "ул. Заводская, 5");
    await user.selectOptions(screen.getByLabelText("Машина"), "v-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createAccidentMock).toHaveBeenCalled());
    expect(createAccidentMock.mock.calls[0][0]).toEqual({
      occurred_at: "2026-08-01T09:30:00",
      place: "ул. Заводская, 5",
      vehicle_id: "v-1",
      driver_id: null,
      kind: "collision",
      injured_count: 0,
      fatalities_count: 0,
      fault: "not_established",
      gibdd_reference: null,
      description: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("ДТП зарегистрировано");
  });

  it("ДТП в будущем: ответ сервера словами, окно открыто", async () => {
    const user = userEvent.setup();
    createAccidentMock.mockRejectedValueOnce({
      status: 422,
      message: "ДТП не может произойти в будущем: проверьте дату",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(screen.getByLabelText("Дата и время"), "2030-01-01T10:00");
    await user.type(screen.getByLabelText("Место"), "трасса");
    await user.selectOptions(screen.getByLabelText("Машина"), "v-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("в будущем");
    expect(
      screen.getByRole("heading", { name: "Зарегистрировать ДТП" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне пять полей; тяжесть форма не выводит", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Место");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.queryByLabelText(/Тяжесть/i)).toBeNull();
    expect(
      screen.getByText(/Вину устанавливают ГИБДД и суд/i),
    ).toBeInTheDocument();
  });
});

describe("ViolationFormDialog — нарушение ПДД (срез-108)", () => {
  beforeEach(() => {
    createViolationMock.mockReset();
    updateViolationMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createViolationMock.mockResolvedValue({ id: "vio-new" });
    updateViolationMock.mockResolvedValue(existingViolation);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <ViolationFormDialog
        vehicles={vehicles}
        drivers={drivers}
        trigger={<button>Внести нарушение</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Внести нарушение" }));
  };

  it("без водителя и штрафа: «не установлен» и «не наложен» уходят как null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Машина"), "v-1");
    await user.type(screen.getByLabelText("Дата и время"), "2026-08-02T12:00");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createViolationMock).toHaveBeenCalled());
    expect(createViolationMock.mock.calls[0][0]).toMatchObject({
      driver_id: null,
      fine_amount: null,
      source: "camera",
    });
  });

  it("дата оплаты без суммы штрафа не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Машина"), "v-1");
    await user.type(screen.getByLabelText("Дата и время"), "2026-08-02T12:00");
    await user.click(
      screen.getByText("Водитель, постановление, место и оплата"),
    );
    await user.type(screen.getByLabelText("Оплачен"), "2026-08-20");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Дата оплаты указана, а сумма штрафа не внесена"),
    ).toBeInTheDocument();
    expect(createViolationMock).not.toHaveBeenCalled();
  });

  it("правка: машина заперта, сумма с запятой уходит числом", async () => {
    const user = userEvent.setup();
    render(
      <ViolationFormDialog
        vehicles={vehicles}
        drivers={drivers}
        initialData={existingViolation}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Машина")).toBeDisabled();

    await user.clear(screen.getByLabelText("Штраф, ₽"));
    await user.type(screen.getByLabelText("Штраф, ₽"), "1500,50");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateViolationMock).toHaveBeenCalled());
    expect(updateViolationMock.mock.calls[0][1]).toMatchObject({
      fine_amount: "1500.50",
      article: "12.9 ч.2",
    });
    expect(updateViolationMock.mock.calls[0][1]).not.toHaveProperty(
      "vehicle_id",
    );
  });

  it("на первом уровне пять полей; статья — свободная строка", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Машина");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByLabelText("Статья КоАП")).toHaveAttribute(
      "placeholder",
      "напр. 12.9 ч.2",
    );
  });
});

describe("схемы второй половины БДД (срез-108)", () => {
  it("лист: одинаковое время выезда и возвращения допустимо", () => {
    expect(
      waybillFormSchema.safeParse({
        number: "1",
        vehicle_id: "v-1",
        driver_id: "d-1",
        issued_on: "2026-09-01",
        status: "issued",
        pre_trip_medical: "not_recorded",
        pre_trip_technical: "not_recorded",
        post_trip_medical: "not_recorded",
        departure_at: "2026-09-01T08:00",
        return_at: "2026-09-01T08:00",
      }).success,
    ).toBe(true);
  });

  it("нарушение: штраф с запятой допустим, буквы — нет", () => {
    const base = {
      vehicle_id: "v-1",
      occurred_at: "2026-08-02T12:00",
      source: "camera",
    };
    expect(
      violationFormSchema.safeParse({ ...base, fine_amount: "500,50" }).success,
    ).toBe(true);
    expect(
      violationFormSchema.safeParse({ ...base, fine_amount: "пятьсот" })
        .success,
    ).toBe(false);
  });
});
