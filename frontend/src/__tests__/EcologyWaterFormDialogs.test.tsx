import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyWaterPointFormDialog } from "@/features/ecology/EcologyWaterPointFormDialog";
import { EcologyWaterRecordFormDialog } from "@/features/ecology/EcologyWaterRecordFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { ecologyWaterRecordFormSchema } from "@/types/forms/ecologyWater";

const createPointMock = vi.fn();
const updatePointMock = vi.fn();
const createRecordMock = vi.fn();
const updateRecordMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/ecology", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/ecology")>("@/api/ecology");
  return {
    ...actual,
    ecologyApi: {
      createWaterPoint: (...args: unknown[]) => createPointMock(...args),
      updateWaterPoint: (...args: unknown[]) => updatePointMock(...args),
      createWaterRecord: (...args: unknown[]) => createRecordMock(...args),
      updateWaterRecord: (...args: unknown[]) => updateRecordMock(...args),
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
] as never;

const points = [
  { id: "wp-1", point_number: "В-1", name: "Скважина №1" },
  { id: "wp-2", point_number: "С-1", name: "Выпуск сточных вод" },
] as never;

const existingPoint = {
  id: "wp-1",
  facility_id: "nvos-1",
  point_number: "В-1",
  name: "Скважина №1",
  kind: "intake",
  kind_label: "Водозабор",
  water_body: "подземный горизонт",
  permit_number: "ВП-7",
  permit_valid_until: "2028-01-01",
  annual_limit_cubic_meters: "15000.000",
  notes: null,
  volume_this_year: "1200.000",
  over_limit: false,
  permit_status: "ok",
  permit_status_label: "Действует",
};

const existingRecord = {
  id: "wr-1",
  point_id: "wp-1",
  period_year: 2026,
  period_month: 3,
  period_label: "март 2026",
  volume_cubic_meters: "1200.000",
  basis: "meter",
  basis_label: "Прибор учёта",
  meter_number: "СВК-15",
  notes: null,
};

describe("EcologyWaterPointFormDialog — точка водопользования (срез-101)", () => {
  beforeEach(() => {
    createPointMock.mockReset();
    updatePointMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createPointMock.mockResolvedValue({ ...existingPoint, id: "wp-new" });
    updatePointMock.mockResolvedValue(existingPoint);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyWaterPointFormDialog
        facilities={facilities}
        trigger={<button>Завести точку</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести точку" }));
  };

  it("отправляет объект, номер, название и вид; пустые поля — null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Объект НВОС"), "nvos-1");
    await user.selectOptions(screen.getByLabelText("Вид точки"), "discharge");
    await user.type(screen.getByLabelText("Номер точки"), "С-1");
    await user.type(screen.getByLabelText("Точка"), "Выпуск сточных вод");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createPointMock).toHaveBeenCalled());
    expect(createPointMock.mock.calls[0][0]).toEqual({
      facility_id: "nvos-1",
      point_number: "С-1",
      name: "Выпуск сточных вод",
      kind: "discharge",
      water_body: null,
      permit_number: null,
      permit_valid_until: null,
      annual_limit_cubic_meters: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Точка заведена");
  });

  it("лимит с запятой уходит числом", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Объект НВОС"), "nvos-1");
    await user.type(screen.getByLabelText("Номер точки"), "В-2");
    await user.type(screen.getByLabelText("Точка"), "Скважина №2");
    await user.type(screen.getByLabelText("Годовой лимит, м³"), "15000,5");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createPointMock).toHaveBeenCalled());
    expect(createPointMock.mock.calls[0][0].annual_limit_cubic_meters).toBe(
      "15000.5",
    );
  });

  it("правка: объект НВОС заперт, остальное уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyWaterPointFormDialog
        facilities={facilities}
        initialData={existingPoint}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Объект НВОС")).toBeDisabled();
    expect(screen.getByLabelText("Годовой лимит, м³")).toHaveValue("15000.000");

    await user.type(screen.getByLabelText("Точка"), " (основная)");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updatePointMock).toHaveBeenCalled());
    expect(updatePointMock.mock.calls[0][1]).toMatchObject({
      name: "Скважина №1 (основная)",
      permit_valid_until: "2028-01-01",
      water_body: "подземный горизонт",
    });
    expect(updatePointMock.mock.calls[0][1]).not.toHaveProperty("facility_id");
  });

  it("на первом уровне шесть полей; пустой срок — не просрочка", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Объект НВОС");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Водный объект, разрешение и заметки"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Пустой срок\s+разрешения не считается просрочкой/i),
    ).toBeInTheDocument();
  });
});

describe("EcologyWaterRecordFormDialog — помесячный учёт (срез-101)", () => {
  beforeEach(() => {
    createRecordMock.mockReset();
    updateRecordMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createRecordMock.mockResolvedValue({ ...existingRecord, id: "wr-new" });
    updateRecordMock.mockResolvedValue(existingRecord);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyWaterRecordFormDialog
        points={points}
        trigger={<button>Записать объём</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Записать объём" }));
  };

  it("отправляет точку, период числами, объём и основание", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Точка водопользования"),
      "wp-1",
    );
    await user.clear(screen.getByLabelText("Год"));
    await user.type(screen.getByLabelText("Год"), "2026");
    await user.selectOptions(screen.getByLabelText("Месяц"), "3");
    await user.type(screen.getByLabelText("Объём, м³"), "1200,5");
    await user.selectOptions(
      screen.getByLabelText("Основание учёта"),
      "calculation",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createRecordMock).toHaveBeenCalled());
    expect(createRecordMock.mock.calls[0][0]).toEqual({
      point_id: "wp-1",
      period_year: 2026,
      period_month: 3,
      volume_cubic_meters: "1200.5",
      basis: "calculation",
      meter_number: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Объём записан");
  });

  it("повтор месяца: сервер отвечает словами, окно открыто", async () => {
    const user = userEvent.setup();
    createRecordMock.mockRejectedValueOnce({
      status: 422,
      message: "Учёт за март 2026 по этой точке уже внесён",
      field_errors: [],
    });
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Точка водопользования"),
      "wp-1",
    );
    await user.type(screen.getByLabelText("Объём, м³"), "10");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже внесён");
    expect(
      screen.getByRole("heading", { name: "Записать объём" }),
    ).toBeInTheDocument();
  });

  it("правка: точка и период заперты — это ключ записи, а не содержание", async () => {
    const user = userEvent.setup();
    render(
      <EcologyWaterRecordFormDialog
        points={points}
        initialData={existingRecord}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Точка водопользования")).toBeDisabled();
    expect(screen.getByLabelText("Год")).toBeDisabled();
    expect(screen.getByLabelText("Месяц")).toBeDisabled();

    await user.clear(screen.getByLabelText("Объём, м³"));
    await user.type(screen.getByLabelText("Объём, м³"), "1300");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateRecordMock).toHaveBeenCalled());
    expect(updateRecordMock.mock.calls[0][0]).toBe("wr-1");
    expect(updateRecordMock.mock.calls[0][1]).toEqual({
      volume_cubic_meters: "1300",
      basis: "meter",
      meter_number: "СВК-15",
      notes: null,
    });
  });

  it("на первом уровне пять полей: прибор и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Точка водопользования");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Прибор учёта и заметки")).toBeInTheDocument();
  });
});

describe("ecologyWaterRecordFormSchema", () => {
  it("принимает нулевой объём: месяц без водопользования — факт", () => {
    expect(
      ecologyWaterRecordFormSchema.safeParse({
        point_id: "wp-1",
        period_year: "2026",
        period_month: "3",
        volume_cubic_meters: "0",
        basis: "meter",
      }).success,
    ).toBe(true);
  });

  it("отклоняет год не из четырёх цифр", () => {
    expect(
      ecologyWaterRecordFormSchema.safeParse({
        point_id: "wp-1",
        period_year: "26",
        period_month: "3",
        volume_cubic_meters: "10",
        basis: "meter",
      }).success,
    ).toBe(false);
  });
});
