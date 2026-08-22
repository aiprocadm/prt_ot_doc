import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ReportDatasetDto,
  ReportDefinitionDto,
  ReportPreviewDto,
} from "@/types/dto/reportBuilder";

const api = vi.hoisted(() => ({
  listDatasets: vi.fn(),
  listDefinitions: vi.fn(),
  createDefinition: vi.fn(),
  updateDefinition: vi.fn(),
  deleteDefinition: vi.fn(),
  preview: vi.fn(),
  runDefinition: vi.fn(),
  getExportJob: vi.fn(),
  downloadReportExport: vi.fn(),
}));

vi.mock("@/api/reportBuilder", () => ({ reportBuilderApi: api }));

import ReportBuilderPage from "@/pages/reports/ReportBuilderPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const DATASETS: ReportDatasetDto[] = [
  {
    code: "incidents",
    title: "Инциденты",
    columns: [
      {
        key: "title",
        label: "Название",
        kind: "string",
        aggregatable: false,
        enum_values: null,
        ops: ["eq", "neq", "contains"],
      },
      {
        key: "status",
        label: "Статус",
        kind: "enum",
        aggregatable: false,
        enum_values: ["reported", "closed"],
        ops: ["eq", "in"],
      },
      {
        key: "occurred_at",
        label: "Дата",
        kind: "datetime",
        aggregatable: false,
        enum_values: null,
        ops: ["eq", "gte", "lte"],
      },
    ],
  },
];

const SYSTEM_DEF: ReportDefinitionDto = {
  id: "sys-1",
  name: "Открытые инциденты",
  description: null,
  dataset_code: "incidents",
  config_json: { columns: ["title", "status"] },
  is_system: true,
  created_at: "2026-07-10T00:00:00Z",
  updated_at: "2026-07-10T00:00:00Z",
};

const PREVIEW: ReportPreviewDto = {
  columns: [
    { key: "title", label: "Название", kind: "string" },
    { key: "status", label: "Статус", kind: "enum" },
  ],
  rows: [{ title: "Падение с высоты", status: "reported" }],
  total: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ReportBuilderPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listDatasets.mockResolvedValue({ items: DATASETS, total: 1 });
  api.listDefinitions.mockResolvedValue({ items: [SYSTEM_DEF], total: 1 });
  api.preview.mockResolvedValue(PREVIEW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ReportBuilderPage", () => {
  it("renders saved definitions with system badge", async () => {
    renderPage();
    expect(await screen.findByText("Открытые инциденты")).toBeInTheDocument();
    expect(screen.getByText("Системный")).toBeInTheDocument();
  });

  it("builds a preview from the editor", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.click(screen.getByRole("button", { name: "Предпросмотр" }));
    expect(await screen.findByText("Падение с высоты")).toBeInTheDocument();
    expect(screen.getByText(/Всего: 1/)).toBeInTheDocument();
    expect(api.preview).toHaveBeenCalledWith({
      dataset_code: "incidents",
      config_json: expect.any(Object),
    });
  });

  it("adds a filter row that reaches the preview payload", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.click(screen.getByRole("button", { name: "Добавить фильтр" }));
    const filterRow = screen.getByTestId("filter-row-0");
    await user.selectOptions(
      within(filterRow).getByLabelText("Поле"),
      "status",
    );
    await user.selectOptions(
      within(filterRow).getByLabelText("Значение"),
      "reported",
    );
    await user.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() =>
      expect(api.preview).toHaveBeenCalledWith(
        expect.objectContaining({
          config_json: expect.objectContaining({
            filters: [{ field: "status", op: "eq", value: "reported" }],
          }),
        }),
      ),
    );
  });

  it("does not emit a filter row with empty value", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.click(screen.getByRole("button", { name: "Добавить фильтр" }));
    const filterRow = screen.getByTestId("filter-row-0");
    await user.selectOptions(
      within(filterRow).getByLabelText("Поле"),
      "status",
    );
    // значение намеренно не выбираем — пустой фильтр не должен попасть в config
    await user.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() => expect(api.preview).toHaveBeenCalled());
    const [payload] = api.preview.mock.calls[0];
    expect(payload.config_json.filters).toBeUndefined();
  });

  it("saves a new definition", async () => {
    api.createDefinition.mockResolvedValue({
      ...SYSTEM_DEF,
      id: "d2",
      is_system: false,
      name: "Мой отчёт",
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.type(screen.getByLabelText("Название отчёта"), "Мой отчёт");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(api.createDefinition).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Мой отчёт",
          dataset_code: "incidents",
        }),
      ),
    );
    expect(api.listDefinitions).toHaveBeenCalledTimes(2); // reload после сохранения
  });

  it("duplicates a system template into the editor", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.click(screen.getByRole("button", { name: "Дублировать" }));
    expect(screen.getByLabelText("Название отчёта")).toHaveValue(
      "Открытые инциденты (копия)",
    );
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    renderPage();
    await screen.findByText("Открытые инциденты");

    const budget = uxBudgetDelta(document.body, "ReportBuilderPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  // NOTE: vi.useFakeTimers() must NOT be active while we `await screen.findByText(...)`
  // for the initial async data load — under fake timers React's scheduler never gets a
  // macrotask tick to flush the pending update unless the fake clock is advanced, so the
  // wait deadlocks until the outer vitest test timeout. We enable fake timers only right
  // before triggering the export, and use `fireEvent` (not `userEvent`) for clicks issued
  // while fake timers are active, since userEvent's own internal async machinery has the
  // same deadlock issue with fake timers.
  //
  // Polling now runs through the house `usePolling` hook: the interval is created by a
  // useEffect after the "polling" state renders, so we flush that render/effect with an
  // empty act() before advancing the fake clock (otherwise the first advance fires zero ticks).
  it("exports: run → poll → download via dedicated route; uses job id", async () => {
    const user = userEvent.setup();
    api.runDefinition.mockResolvedValue({ job_id: "j1", status: "queued" });
    api.getExportJob
      .mockResolvedValueOnce({
        id: "j1",
        status: "running",
        file_id: null,
        row_count: null,
        error_payload: null,
      })
      .mockResolvedValueOnce({
        id: "j1",
        status: "done",
        file_id: "f1",
        row_count: 5,
        error_payload: null,
      });
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.click(screen.getByRole("button", { name: "Открыть" }));

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "XLSX" }));
    expect(api.runDefinition).toHaveBeenCalledWith("sys-1", "xlsx");
    await act(async () => {}); // flush: runDefinition → polling state → usePolling effect
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(screen.getByRole("button", { name: "Скачать" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Скачать" }));
    expect(api.downloadReportExport).toHaveBeenCalledWith(
      "j1",
      "Открытые инциденты.xlsx",
    );
  });

  it("shows a readable error when the export job fails", async () => {
    const user = userEvent.setup();
    api.runDefinition.mockResolvedValue({ job_id: "j1", status: "queued" });
    api.getExportJob.mockResolvedValue({
      id: "j1",
      status: "failed",
      file_id: null,
      row_count: null,
      error_payload: {
        code: "pdf_renderer_unavailable",
        message: "no soffice",
      },
    });
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.click(screen.getByRole("button", { name: "Открыть" }));

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "PDF" }));
    await act(async () => {}); // flush: runDefinition → polling state → usePolling effect
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(
      screen.getByText(/PDF-конвертер временно недоступен/),
    ).toBeInTheDocument();
  });
});
