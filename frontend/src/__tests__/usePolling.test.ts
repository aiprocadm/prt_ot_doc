import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePolling } from "@/hooks/usePolling";

describe("usePolling", () => {
  it("вызывает callback с заданным интервалом", async () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 100));

    await vi.advanceTimersByTimeAsync(350);
    expect(callback).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("останавливает интервал при отключении", async () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    const { rerender } = renderHook(({ enabled }) => usePolling(callback, 100, enabled), {
      initialProps: { enabled: true }
    });

    await vi.advanceTimersByTimeAsync(250);
    expect(callback).toHaveBeenCalledTimes(2);

    rerender({ enabled: false });
    await vi.advanceTimersByTimeAsync(300);
    expect(callback).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("не запускает новый polling пока прошлый запрос не завершился", async () => {
    vi.useFakeTimers();
    let resolves = 0;
    const callback = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          setTimeout(() => {
            resolves += 1;
            resolve();
          }, 200);
        })
    );
    renderHook(() => usePolling(callback, 100));

    await vi.advanceTimersByTimeAsync(1000);
    expect(callback.mock.calls.length).toBeLessThanOrEqual(4);
    expect(resolves).toBeGreaterThanOrEqual(callback.mock.calls.length - 1);
    vi.useRealTimers();
  });
});
