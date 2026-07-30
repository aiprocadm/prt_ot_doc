import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { importsApi } from "@/api/imports";
import type { ImportBatchDto, ImportPreviewDto, ImportTargetDto } from "@/types/dto/imports";

import ImportsPage from "./ImportsPage";

vi.mock("@/api/imports", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/imports")>();
  return {
    ...actual,
    importsApi: {
      targets: vi.fn(),
      downloadTemplate: vi.fn(),
      dryRun: vi.fn(),
      apply: vi.fn(),
      batches: vi.fn(),
      batchRows: vi.fn(),
      rollback: vi.fn()
    }
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() }
}));

const TARGET: ImportTargetDto = {
  code: "persons",
  title: "Сотрудники",
  description: "Списки сотрудников.",
  natural_keys: ["организация + табельный номер", "организация + ФИО + дата рождения"],
  columns: [
    {
      field: "company_id",
      title: "Организация",
      kind: "str",
      required: true,
      aliases: [],
      enum_values: [],
      lookup: "company"
    },
    {
      field: "last_name",
      title: "Фамилия",
      kind: "str",
      required: true,
      aliases: [],
      enum_values: [],
      lookup: null
    },
    {
      field: "personnel_number",
      title: "Табельный номер",
      kind: "str",
      required: false,
      aliases: [],
      enum_values: [],
      lookup: null
    }
  ]
};

const PREVIEW: ImportPreviewDto = {
  target: "persons",
  counts: { create: 2, update: 1, skip: 0, error: 1, total: 4 },
  mapping: { company_id: "Организация", last_name: "Фамилия" },
  unmapped_headers: ["Оклад"],
  unknown_references: { company: ["НЕТ ТАКОЙ"] },
  rows: [
    { row_number: 2, action: "create", natural_key: "k1", changed_fields: [], errors: [] },
    { row_number: 3, action: "create", natural_key: "k2", changed_fields: [], errors: [] },
    { row_number: 4, action: "update", natural_key: "k3", changed_fields: ["last_name"], errors: [] },
    {
      row_number: 5,
      action: "error",
      natural_key: null,
      changed_fields: [],
      errors: [{ code: "required", field: "last_name", message: "Фамилия: value is required" }]
    }
  ]
};

const BATCH: ImportBatchDto = {
  id: "batch-1",
  target: "persons",
  status: "applied",
  source_filename: "staff.csv",
  source_format: "csv",
  mapping: {},
  notes: {},
  total_rows: 4,
  created_count: 2,
  updated_count: 1,
  skipped_count: 0,
  failed_count: 1,
  applied_at: "2026-07-30T10:00:00Z",
  applied_by: null,
  rolled_back_at: null,
  rolled_back_by: null
};

const mocked = vi.mocked(importsApi);

const renderPage = () =>
  render(
    <MemoryRouter>
      <ImportsPage />
    </MemoryRouter>
  );

const selectTargetAndFile = async () => {
  await screen.findByText("Импорт данных");
  fireEvent.change(screen.getByLabelText("Тип данных"), { target: { value: "persons" } });
  const file = new File(["Организация,Фамилия\nАКМЕ,Иванов\n"], "staff.csv", { type: "text/csv" });
  fireEvent.change(screen.getByLabelText("Файл импорта"), { target: { files: [file] } });
  return file;
};

describe("ImportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.targets.mockResolvedValue([TARGET]);
    mocked.batches.mockResolvedValue([BATCH]);
    mocked.dryRun.mockResolvedValue(PREVIEW);
    mocked.apply.mockResolvedValue({ batch: BATCH, preview: PREVIEW });
    mocked.batchRows.mockResolvedValue([]);
    mocked.rollback.mockResolvedValue({ ...BATCH, status: "rolled_back" });
  });

  it("не даёт применить импорт до сухого прогона", async () => {
    renderPage();
    await selectTargetAndFile();

    // Кнопка применения появляется только вместе с результатом проверки —
    // «загрузил и сразу применил» это ровно тот сценарий, ради которого в ТЗ есть dry-run.
    expect(screen.queryByRole("button", { name: "Применить импорт" })).toBeNull();
  });

  it("показывает сводку, неизвестные справочники и строки на исправление", async () => {
    renderPage();
    await selectTargetAndFile();

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() => expect(screen.getByText("Создать: 2")).toBeInTheDocument());
    expect(screen.getByText("Обновить: 1")).toBeInTheDocument();
    expect(screen.getByText("Ошибка: 1")).toBeInTheDocument();
    // Неизвестное значение справочника видно списком, а не теряется в ошибках строк.
    expect(screen.getByText(/НЕТ ТАКОЙ/)).toBeInTheDocument();
    // У ошибки обязателен номер строки: иначе её ищут глазами по всему файлу.
    expect(screen.getByText(/Строка 5:/)).toBeInTheDocument();
  });

  it("предупреждает о колонках файла без пары", async () => {
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() => expect(screen.getByText(/Колонки файла без пары: Оклад/)).toBeInTheDocument());
  });

  it("ручное сопоставление уходит в повторный прогон", async () => {
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByLabelText("Табельный номер")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Табельный номер"), { target: { value: "Оклад" } });
    fireEvent.click(screen.getByRole("button", { name: "Пересчитать с новым сопоставлением" }));

    await waitFor(() => expect(mocked.dryRun).toHaveBeenCalledTimes(2));
    const [, , mapping] = mocked.dryRun.mock.calls[1];
    expect(mapping).toMatchObject({ personnel_number: "Оклад", company_id: "Организация" });
  });

  it("применение спрашивает подтверждение и передаёт итоговое сопоставление", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Применить импорт" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Применить импорт" }));

    await waitFor(() => expect(mocked.apply).toHaveBeenCalledTimes(1));
    expect(confirmSpy).toHaveBeenCalled();
    const [target, , mapping] = mocked.apply.mock.calls[0];
    expect(target).toBe("persons");
    expect(mapping).toMatchObject({ company_id: "Организация", last_name: "Фамилия" });
    confirmSpy.mockRestore();
  });

  it("отказ в подтверждении отменяет применение", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Применить импорт" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Применить импорт" }));

    expect(mocked.apply).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("история загрузок позволяет откатить партию с подтверждением", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await screen.findByText("staff.csv");

    fireEvent.click(screen.getByRole("button", { name: "Откатить" }));

    await waitFor(() => expect(mocked.rollback).toHaveBeenCalledWith("batch-1"));
    confirmSpy.mockRestore();
  });

  it("смена файла обесценивает прежний предпросмотр", async () => {
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByText("Создать: 2")).toBeInTheDocument());

    const other = new File(["Организация\nБЕТА\n"], "other.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Файл импорта"), { target: { files: [other] } });

    // План, посчитанный для другого файла, — это приглашение применить не то.
    expect(screen.queryByText("Создать: 2")).toBeNull();
    expect(screen.queryByRole("button", { name: "Применить импорт" })).toBeNull();
  });
});
