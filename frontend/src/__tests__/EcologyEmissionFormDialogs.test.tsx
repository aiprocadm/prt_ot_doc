import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyEmissionNormFormDialog } from "@/features/ecology/EcologyEmissionNormFormDialog";
import { EcologyEmissionSourceFormDialog } from "@/features/ecology/EcologyEmissionSourceFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import {
  ecologyEmissionNormFormSchema,
  numberToPayload,
} from "@/types/forms/ecologyEmission";

const createSourceMock = vi.fn();
const updateSourceMock = vi.fn();
const createNormMock = vi.fn();
const updateNormMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/ecology", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/ecology")>("@/api/ecology");
  return {
    ...actual,
    ecologyApi: {
      createEmissionSource: (...args: unknown[]) => createSourceMock(...args),
      updateEmissionSource: (...args: unknown[]) => updateSourceMock(...args),
      createEmissionNorm: (...args: unknown[]) => createNormMock(...args),
      updateEmissionNorm: (...args: unknown[]) => updateNormMock(...args),
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

const sources = [
  { id: "src-1", source_number: "0001", name: "Труба котельной" },
  { id: "src-2", source_number: "0002", name: "Сварочный пост" },
] as never;

const existingSource = {
  id: "src-1",
  facility_id: "nvos-1",
  source_number: "0001",
  name: "Труба котельной",
  kind: "organized",
  kind_label: "Организованный источник",
  location: "Котельная",
  inventoried_on: "2026-03-01",
  notes: null,
  norms_count: 2,
};

const existingNorm = {
  id: "norm-1",
  source_id: "src-1",
  substance: "Азота диоксид",
  limit_grams_per_second: "0.150000",
  limit_tons_per_year: "1.200000",
  permit_number: "РВ-12/2025",
  valid_until: "2027-05-01",
  notes: null,
  validity_status: "ok",
  validity_status_label: "Действует",
};

describe("EcologyEmissionSourceFormDialog — источник выбросов (срез-100)", () => {
  beforeEach(() => {
    createSourceMock.mockReset();
    updateSourceMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createSourceMock.mockResolvedValue({ ...existingSource, id: "src-new" });
    updateSourceMock.mockResolvedValue(existingSource);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyEmissionSourceFormDialog
        facilities={facilities}
        trigger={<button>Завести источник</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести источник" }));
  };

  it("отправляет объект, номер, название и вид; пустое — null", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Объект НВОС"), "nvos-2");
    await user.type(screen.getByLabelText("Номер источника"), "0007");
    await user.type(screen.getByLabelText("Источник"), "Труба котельной");
    await user.selectOptions(
      screen.getByLabelText("Вид источника"),
      "unorganized",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createSourceMock).toHaveBeenCalled());
    expect(createSourceMock.mock.calls[0][0]).toEqual({
      facility_id: "nvos-2",
      source_number: "0007",
      name: "Труба котельной",
      kind: "unorganized",
      location: null,
      inventoried_on: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Источник заведён");
  });

  it("без объекта, номера и названия запрос не уходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Выберите объект НВОС")).toBeInTheDocument();
    expect(screen.getByText("Внесите номер источника")).toBeInTheDocument();
    expect(screen.getByText("Назовите источник")).toBeInTheDocument();
    expect(createSourceMock).not.toHaveBeenCalled();
  });

  it("дубль номера на объекте: 422 словами, окно открыто", async () => {
    const user = userEvent.setup();
    createSourceMock.mockRejectedValueOnce({
      status: 422,
      message: "Источник с номером '0001' на этом объекте уже заведён",
      field_errors: [],
    });
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Объект НВОС"), "nvos-1");
    await user.type(screen.getByLabelText("Номер источника"), "0001");
    await user.type(screen.getByLabelText("Источник"), "Труба");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже заведён");
    expect(
      screen.getByRole("heading", { name: "Завести источник выбросов" }),
    ).toBeInTheDocument();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyEmissionSourceFormDialog
        facilities={facilities}
        initialData={existingSource}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Объект НВОС")).toHaveValue("nvos-1");
    expect(screen.getByLabelText("Номер источника")).toHaveValue("0001");

    await user.type(screen.getByLabelText("Источник"), " (после ремонта)");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateSourceMock).toHaveBeenCalled());
    expect(updateSourceMock.mock.calls[0][0]).toBe("src-1");
    expect(updateSourceMock.mock.calls[0][1]).toMatchObject({
      name: "Труба котельной (после ремонта)",
      location: "Котельная",
      inventoried_on: "2026-03-01",
    });
  });

  it("на первом уровне четыре поля: место, инвентаризация и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Объект НВОС");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Место, инвентаризация и заметки"),
    ).toBeInTheDocument();
  });
});

describe("EcologyEmissionNormFormDialog — норматив выброса (срез-100)", () => {
  beforeEach(() => {
    createNormMock.mockReset();
    updateNormMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createNormMock.mockResolvedValue({ ...existingNorm, id: "norm-new" });
    updateNormMock.mockResolvedValue(existingNorm);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <EcologyEmissionNormFormDialog
        sources={sources}
        trigger={<button>Внести норматив</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Внести норматив" }));
  };

  it("отправляет источник, вещество и пределы; пустой срок — бессрочно", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Источник выбросов"),
      "src-1",
    );
    await user.type(screen.getByLabelText("Вещество"), "Азота диоксид");
    await user.type(screen.getByLabelText("Предел, г/с"), "0,15");
    await user.type(screen.getByLabelText("Номер разрешения"), "РВ-12/2025");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createNormMock).toHaveBeenCalled());
    expect(createNormMock.mock.calls[0][0]).toEqual({
      source_id: "src-1",
      substance: "Азота диоксид",
      limit_grams_per_second: "0.15",
      limit_tons_per_year: null,
      permit_number: "РВ-12/2025",
      valid_until: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Норматив внесён");
  });

  it("норматив без единого предела не проходит: ограничивать нечем", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(
      screen.getByLabelText("Источник выбросов"),
      "src-2",
    );
    await user.type(screen.getByLabelText("Вещество"), "Взвешенные вещества");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Внесите хотя бы один предел: г/с или т/год"),
    ).toBeInTheDocument();
    expect(createNormMock).not.toHaveBeenCalled();
  });

  it("правка подставляет запись и уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyEmissionNormFormDialog
        sources={sources}
        initialData={existingNorm}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(screen.getByLabelText("Источник выбросов")).toHaveValue("src-1");
    expect(screen.getByLabelText("Предел, г/с")).toHaveValue("0.150000");
    expect(screen.getByLabelText("Разрешение действует до")).toHaveValue(
      "2027-05-01",
    );

    await user.type(screen.getByLabelText("Вещество"), " (пересчёт)");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateNormMock).toHaveBeenCalled());
    expect(updateNormMock.mock.calls[0][0]).toBe("norm-1");
    expect(updateNormMock.mock.calls[0][1]).toMatchObject({
      substance: "Азота диоксид (пересчёт)",
      limit_tons_per_year: "1.200000",
      valid_until: "2027-05-01",
    });
  });

  it("на первом уровне шесть полей: заметки свёрнуты, границы названы", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Источник выбросов");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Дополнительно")).toBeInTheDocument();
    expect(
      screen.getByText(/платформа их не\s+рассчитывает/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/означает «бессрочно»/i)).toBeInTheDocument();
  });
});

describe("ecologyEmissionNormFormSchema", () => {
  it("принимает норматив с одним пределом", () => {
    expect(
      ecologyEmissionNormFormSchema.safeParse({
        source_id: "src-1",
        substance: "Азота диоксид",
        limit_tons_per_year: "1,2",
      }).success,
    ).toBe(true);
  });

  it("пустое числовое поле — «не задано»", () => {
    expect(numberToPayload("")).toBeNull();
    expect(numberToPayload("0,15")).toBe("0.15");
  });
});
