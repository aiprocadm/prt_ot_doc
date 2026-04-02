import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useTheme } from "@/hooks/useTheme";

describe("useTheme", () => {
  beforeEach(() => {
    document.documentElement.className = "";
    window.localStorage.clear();
  });

  it("переключает темы", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("light");

    act(() => result.current[2]());

    expect(result.current[0]).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("prt-theme")).toBe("dark");
  });

  it("устанавливает тему напрямую", () => {
    const { result } = renderHook(() => useTheme());

    act(() => result.current[1]("dark"));
    expect(result.current[0]).toBe("dark");

    act(() => result.current[1]("light"));
    expect(result.current[0]).toBe("light");
  });
});
