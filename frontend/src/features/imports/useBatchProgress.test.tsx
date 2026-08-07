import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { importsApi } from "@/api/imports";
import { useBatchProgress } from "@/features/imports/useBatchProgress";
import type { ImportBatchDto } from "@/types/dto/imports";

vi.mock("@/api/imports", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/imports")>();
  return { ...actual, importsApi: { ...actual.importsApi, batch: vi.fn() } };
});

const mocked = vi.mocked(importsApi);

const batch = (over: Partial<ImportBatchDto> = {}): ImportBatchDto => ({
  id: "b1",
  target: "persons",
  status: "running",
  mode: "apply",
  source_filename: "staff.csv",
  source_format: "csv",
  mapping: {},
  notes: {},
  total_rows: 10,
  processed_rows: 0,
  created_count: 0,
  updated_count: 0,
  skipped_count: 0,
  failed_count: 0,
  applied_at: "2026-07-30T10:00:00Z",
  applied_by: null,
  finished_at: null,
  error_message: null,
  rolled_back_at: null,
  rolled_back_by: null,
  ...over,
});

describe("useBatchProgress", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("опрашивает незавершённую партию и отдаёт свежий прогресс", async () => {
    mocked.batch.mockResolvedValue(batch({ processed_rows: 4 }));

    const { result } = renderHook(() =>
      useBatchProgress([batch()], { intervalMs: 1000 }),
    );
    expect(result.current[0].processed_rows).toBe(0);

    // waitFor здесь неприменим: он крутит СВОЙ таймер, а таймеры подменены —
    // ожидание никогда бы не сдвинулось. Состояние уже слито внутри act().
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current[0].processed_rows).toBe(4);
  });

  it("не опрашивает завершённые партии", async () => {
    renderHook(() =>
      useBatchProgress([batch({ status: "applied" })], { intervalMs: 1000 }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    // Таймер на странице, где всё давно загрузилось, — это фоновый трафик,
    // который никто не замечает, пока он не станет проблемой.
    expect(mocked.batch).not.toHaveBeenCalled();
  });

  it("останавливает опрос, когда партия дошла до терминала, и зовёт onSettled", async () => {
    mocked.batch.mockResolvedValue(
      batch({ status: "applied", processed_rows: 10 }),
    );
    const onSettled = vi.fn();

    renderHook(() =>
      useBatchProgress([batch()], { intervalMs: 1000, onSettled }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);

    const callsAfterSettle = mocked.batch.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(mocked.batch.mock.calls.length).toBe(callsAfterSettle);
  });

  it("ошибка опроса не роняет страницу и не стирает прежний прогресс", async () => {
    mocked.batch.mockResolvedValueOnce(batch({ processed_rows: 3 }));
    mocked.batch.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() =>
      useBatchProgress([batch()], { intervalMs: 1000 }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current[0].processed_rows).toBe(3);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current[0].processed_rows).toBe(3);
  });
});
