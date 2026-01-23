import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePolling } from "@/hooks/usePolling";

describe("usePolling", () => {
  it("вызывает callback с заданным интервалом", () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 100));

    vi.advanceTimersByTime(350);
    expect(callback).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("останавливает интервал при отключении", () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    const { rerender } = renderHook(({ enabled }) => usePolling(callback, 100, enabled), {
      initialProps: { enabled: true }
    });

    vi.advanceTimersByTime(250);
    expect(callback).toHaveBeenCalledTimes(2);

    rerender({ enabled: false });
    vi.advanceTimersByTime(300);
    expect(callback).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
