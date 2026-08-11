import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_UNSAVED_CHANGES_MESSAGE, useUnsavedChanges } from "@/hooks/useUnsavedChanges";

const Probe = ({ dirty }: { dirty: boolean }) => {
  useUnsavedChanges(dirty);
  return null;
};

describe("useUnsavedChanges", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("регистрирует beforeunload handler для dirty state", () => {
    const addSpy = vi.spyOn(window, "addEventListener").mockImplementation((() => {}) as typeof window.addEventListener);
    const removeSpy = vi.spyOn(window, "removeEventListener").mockImplementation((() => {}) as typeof window.removeEventListener);

    const { unmount } = render(<Probe dirty />);

    expect(addSpy.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);
    const handlerCall = addSpy.mock.calls.find(([type]) => type === "beforeunload")?.[1];
    if (typeof handlerCall !== "function") {
      throw new Error("beforeunload handler was not registered");
    }

    const event = {
      preventDefault: vi.fn(),
      returnValue: undefined,
    } as unknown as BeforeUnloadEvent;
    handlerCall(event);

    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(event.returnValue).toBe(DEFAULT_UNSAVED_CHANGES_MESSAGE);

    unmount();

    expect(removeSpy.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);
  });

  it("не регистрирует beforeunload handler для clean state", () => {
    const addSpy = vi.spyOn(window, "addEventListener");

    render(<Probe dirty={false} />);

    expect(addSpy.mock.calls.filter(([type]) => type === "beforeunload")).toHaveLength(0);
  });
});