import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { vi } from "vitest";
import { afterEach } from "vitest";
import { beforeAll } from "vitest";

afterEach(() => {
  cleanup();
});

if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  });
}

const originalWarn = console.warn;
const originalError = console.error;

beforeAll(() => {
  vi.spyOn(console, "warn").mockImplementation((...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (
      text.includes("React Router Future Flag Warning")
    ) {
      return;
    }
    originalWarn(...args);
  });

  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (text.includes("not wrapped in act")) {
      return;
    }
    originalError(...args);
  });
});
