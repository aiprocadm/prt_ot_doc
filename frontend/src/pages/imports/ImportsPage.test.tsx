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
      applyAsync: vi.fn(),
      dryRunAsync: vi.fn(),
      batch: vi.fn(),
      batches: vi.fn(),
      batchRows: vi.fn(),
      downloadReport: vi.fn(),
      qualityCheck: vi.fn(),
      profiles: vi.fn(),
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
      lookup: "company",
      lookup_creatable: false
    },
    {
      field: "last_name",
      title: "Фамилия",
      kind: "str",
      required: true,
      aliases: [],
      enum_values: [],
      lookup: null,
      lookup_creatable: false
    },
    {
      field: "personnel_number",
      title: "Табельный номер",
      kind: "str",
      required: false,
      aliases: [],
      enum_values: [],
      lookup: null,
      lookup_creatable: false
    },
    {
      field: "position_id",
      title: "Должность",
      kind: "str" as const,
      required: false,
      aliases: [],
      enum_values: [],
      lookup: "position",
      lookup_creatable: true
    }
  ]
};

const PREVIEW: ImportPreviewDto = {
  target: "persons",
  detected_profile: null,
  applied_profile: null,
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
  mode: "apply",
  source_filename: "staff.csv",
  source_format: "csv",
  mapping: {},
  notes: {},
  total_rows: 4,
  processed_rows: 4,
  created_count: 2,
  updated_count: 1,
  skipped_count: 0,
  failed_count: 1,
  applied_at: "2026-07-30T10:00:00Z",
  applied_by: null,
  finished_at: "2026-07-30T10:00:05Z",
  error_message: null,
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
    mocked.profiles.mockResolvedValue([
      {
        code: "1c_zup_persons",
        title: "1С:ЗУП — список сотрудников",
        target: "persons",
        source: "1c",
        description: "",
        mapping: {},
        split_columns: ["ФИО"]
      }
    ]);
    mocked.batches.mockResolvedValue([BATCH]);
    mocked.dryRun.mockResolvedValue(PREVIEW);
    mocked.apply.mockResolvedValue({ batch: BATCH, preview: PREVIEW });
    mocked.batchRows.mockResolvedValue([]);
    mocked.rollback.mockResolvedValue({ ...BATCH, status: "rolled_back" });
    mocked.downloadReport.mockResolvedValue(undefined);
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
  it("на слишком большом файле предлагает фоновую загрузку вместо тупика", async () => {
    mocked.dryRun.mockRejectedValueOnce({
      status: 422,
      code: "IMPORT_FILE_TOO_MANY_ROWS",
      message: "File has 6000 data rows, the limit is 5000."
    });
    renderPage();
    await selectTargetAndFile();

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() =>
      expect(screen.getByText(/слишком большой для предварительной проверки/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "Загрузить в фоне" })).toBeInTheDocument();
  });

  it("фоновая загрузка спрашивает подтверждение и называет откат страховкой", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mocked.dryRun.mockRejectedValueOnce({
      status: 422,
      code: "IMPORT_FILE_TOO_MANY_ROWS",
      message: "too many rows"
    });
    mocked.applyAsync.mockResolvedValue({ ...BATCH, status: "pending", processed_rows: 0 });

    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Загрузить в фоне" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Загрузить в фоне" }));

    await waitFor(() => expect(mocked.applyAsync).toHaveBeenCalledTimes(1));
    // Пользователю прямо сказано, что предпросмотра не будет, а страховка — откат.
    expect(confirmSpy.mock.calls[0][0]).toMatch(/откатить/i);
    confirmSpy.mockRestore();
  });

  it("прочая ошибка проверки не превращается в предложение фоновой загрузки", async () => {
    mocked.dryRun.mockRejectedValueOnce({ status: 422, code: "IMPORT_REQUIRED_COLUMNS_MISSING", message: "нет колонки" });
    renderPage();
    await selectTargetAndFile();

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() => expect(mocked.dryRun).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Загрузить в фоне" })).toBeNull();
  });

  it("показывает прогресс незавершённой партии вместо счётчиков", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, status: "running", processed_rows: 3, total_rows: 10, failed_count: 0 }
    ]);
    mocked.batch.mockResolvedValue({
      ...BATCH,
      status: "running",
      processed_rows: 3,
      total_rows: 10,
      failed_count: 0
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/обработано 3 из 10/)).toBeInTheDocument());
    expect(screen.getByText(/30%/)).toBeInTheDocument();
    // У незавершённой партии откатывать нечего — кнопки нет.
    expect(screen.queryByRole("button", { name: "Откатить" })).toBeNull();
  });

  it("причина обрыва видна прямо в истории", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, status: "failed", error_message: "import_source_unavailable: нет файла" }
    ]);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/import_source_unavailable/)).toBeInTheDocument()
    );
  });
  it("для большого файла предлагает сперва проверку, а не только загрузку", async () => {
    mocked.dryRun.mockRejectedValueOnce({
      status: 422,
      code: "IMPORT_FILE_TOO_MANY_ROWS",
      message: "too many rows"
    });
    renderPage();
    await selectTargetAndFile();

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Проверить в фоне" })).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "Загрузить в фоне" })).toBeInTheDocument();
  });

  it("фоновая проверка не спрашивает подтверждения — она ничего не пишет", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mocked.dryRun.mockRejectedValueOnce({
      status: 422,
      code: "IMPORT_FILE_TOO_MANY_ROWS",
      message: "too many rows"
    });
    mocked.dryRunAsync.mockResolvedValue({ ...BATCH, mode: "preview", status: "pending" });

    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Проверить в фоне" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Проверить в фоне" }));

    await waitFor(() => expect(mocked.dryRunAsync).toHaveBeenCalledTimes(1));
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("партию-проверку помечает и не даёт откатить", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, mode: "preview", status: "previewed", failed_count: 0 }
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText("проверка без записи")).toBeInTheDocument());
    expect(screen.getByText("Проверена")).toBeInTheDocument();
    // Откатывать нечего: в целевые таблицы ничего не писали.
    expect(screen.queryByRole("button", { name: "Откатить" })).toBeNull();
  });

  it("счётчики проверки читаются как «будет создано»", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, mode: "preview", status: "previewed", created_count: 7, failed_count: 0 }
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText(/будет создано 7/)).toBeInTheDocument());
  });
  it("предлагает дозавести только те справочники, которым это разрешено", async () => {
    mocked.dryRun.mockResolvedValue({
      ...PREVIEW,
      unknown_references: { position: ["Слесарь"], company: ["НЕТ ТАКОЙ"] }
    });
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() => expect(screen.getByText(/Создать недостающие значения: должности/)).toBeInTheDocument());
    // Организация несёт реквизиты — её из импорта заводить нельзя.
    expect(screen.queryByText(/Создать недостающие значения: организации/)).toBeNull();
  });

  it("отмеченный справочник уходит в применение", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mocked.dryRun.mockResolvedValue({ ...PREVIEW, unknown_references: { position: ["Слесарь"] } });
    renderPage();
    await selectTargetAndFile();
    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Применить импорт" }));

    await waitFor(() => expect(mocked.apply).toHaveBeenCalledTimes(1));
    expect(mocked.apply.mock.calls[0][3]).toEqual(["position"]);
    confirmSpy.mockRestore();
  });

  it("отчёт по партии скачивается из истории", async () => {
    renderPage();
    await screen.findByText("staff.csv");

    fireEvent.click(screen.getByRole("button", { name: "Отчёт" }));

    await waitFor(() => expect(mocked.downloadReport).toHaveBeenCalledWith("batch-1"));
  });
  it("показывает итог проверки качества по загрузке", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, notes: { data_quality: { issues_total: 3, by_severity: { high: 3 } } } }
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText(/Проверка качества: замечаний 3/)).toBeInTheDocument());
  });

  it("чистую загрузку помечает отдельно, а не молчанием", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, notes: { data_quality: { issues_total: 0, by_severity: {} } } }
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText(/замечаний нет/)).toBeInTheDocument());
  });

  it("несработавшую проверку показывает причиной, а не тишиной", async () => {
    mocked.batches.mockResolvedValue([
      { ...BATCH, notes: { data_quality: { error: "rule engine exploded" } } }
    ]);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Проверка качества не выполнилась/)).toBeInTheDocument()
    );
  });

  it("проверку качества можно запустить из истории", async () => {
    mocked.qualityCheck.mockResolvedValue(BATCH);
    renderPage();
    await screen.findByText("staff.csv");

    fireEvent.click(screen.getByRole("button", { name: "Проверить качество" }));

    await waitFor(() => expect(mocked.qualityCheck).toHaveBeenCalledWith("batch-1"));
  });
  it("предлагает профиль источника для выбранной цели", async () => {
    renderPage();
    await screen.findByText("Импорт данных");
    fireEvent.change(screen.getByLabelText("Тип данных"), { target: { value: "persons" } });

    await waitFor(() => expect(screen.getByLabelText("Откуда файл")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "1С:ЗУП — список сотрудников" })).toBeInTheDocument();
  });

  it("выбранный профиль уходит в проверку и в применение", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await selectTargetAndFile();
    fireEvent.change(screen.getByLabelText("Откуда файл"), { target: { value: "1c_zup_persons" } });

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));
    await waitFor(() => expect(mocked.dryRun).toHaveBeenCalled());
    expect(mocked.dryRun.mock.calls[0][3]).toBe("1c_zup_persons");

    fireEvent.click(screen.getByRole("button", { name: "Применить импорт" }));
    await waitFor(() => expect(mocked.apply).toHaveBeenCalled());
    expect(mocked.apply.mock.calls[0][4]).toBe("1c_zup_persons");
    confirmSpy.mockRestore();
  });

  it("опознанный источник показывается подсказкой, пока его не выбрали", async () => {
    mocked.dryRun.mockResolvedValue({ ...PREVIEW, detected_profile: "1c_zup_persons" });
    renderPage();
    await selectTargetAndFile();

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() =>
      expect(screen.getByText(/Похоже на выгрузку: 1С:ЗУП/)).toBeInTheDocument()
    );
  });

  it("применённый профиль подсказку не показывает", async () => {
    mocked.dryRun.mockResolvedValue({
      ...PREVIEW,
      detected_profile: "1c_zup_persons",
      applied_profile: "1c_zup_persons"
    });
    renderPage();
    await selectTargetAndFile();

    fireEvent.click(screen.getByRole("button", { name: "Проверить без записи" }));

    await waitFor(() => expect(screen.getByText("Создать: 2")).toBeInTheDocument());
    expect(screen.queryByText(/Похоже на выгрузку/)).toBeNull();
  });
});
