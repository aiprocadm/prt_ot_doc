import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import GeneratePackWizardPage from "@/pages/packs/GeneratePackWizardPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

describe("GeneratePackWizardPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("shows safe summary and blocks run when json is invalid", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue({
      data: [{ id: "p-1", code: "P1", name: "Базовый", status: "active" }],
    });

    render(
      <MemoryRouter initialEntries={["/generate-pack"]}>
        <Routes>
          <Route path="/generate-pack" element={<GeneratePackWizardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: /Базовый/i }));
    await user.click(screen.getByRole("button", { name: "Далее" }));

    const json = screen.getByLabelText("Массив строк в формате JSON");
    await user.clear(json);
    await user.type(json, "{invalid}");

    await user.click(screen.getByRole("button", { name: "Далее" }));
    expect(await screen.findByText("Невалидный JSON")).toBeInTheDocument();

    fireEvent.change(json, { target: { value: "[]" } });
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(screen.getByRole("button", { name: "Далее" }));

    expect(await screen.findByText("Строк для генерации")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Запустить генерацию" }),
    ).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Назад" }));
    await user.clear(
      screen.getByLabelText("Ключ идемпотентности (уникальный запуск)"),
    );
    expect(screen.getByRole("button", { name: "Далее" })).toBeDisabled();
  });

  it("проверка без записи не запускает генерацию (срез-164)", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue({
      data: [{ id: "p-1", code: "P1", name: "Базовый", status: "active" }],
    });
    postMock.mockResolvedValue({
      data: {
        ready: false,
        score: 50,
        documents_total: 2,
        rows_total: 2,
        rows_selected: 2,
        rows_ready: 1,
        problems: [
          {
            code: "missing_column",
            message: "Нет колонки «Должность»",
            blocking: true,
            rows: [2],
            rows_total: 2,
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/generate-pack"]}>
        <Routes>
          <Route path="/generate-pack" element={<GeneratePackWizardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: /Базовый/i }));
    await user.click(screen.getByRole("button", { name: "Далее" }));
    fireEvent.change(screen.getByLabelText("Массив строк в формате JSON"), {
      target: { value: "[{}]" },
    });
    await user.click(screen.getByRole("button", { name: "Далее" }));

    // Шаг 3 — настройки: здесь живёт галочка «только проверить».
    await user.click(
      screen.getByLabelText("Только проверить, ничего не записывать"),
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));

    expect(await screen.findByText("Строк для генерации")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Проверить" }));

    // Ушёл запрос именно к проверке, и ни одного — к запуску генерации.
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock.mock.calls[0][0]).toBe("/pack-runs:preview");
    expect(
      await screen.findByText(/Проверка нашла помехи. Ничего не записано./),
    ).toBeInTheDocument();
    expect(screen.getByText(/Нет колонки «Должность»/)).toBeInTheDocument();
  });

  it("retries preset loading without forcing a full page reload", async () => {
    const user = userEvent.setup();
    getMock
      .mockRejectedValueOnce({
        message: "preset load failed",
        status: 400,
        code: "preset_load_failed",
      })
      .mockResolvedValueOnce({
        data: [{ id: "p-1", code: "P1", name: "Базовый", status: "active" }],
      });

    render(
      <MemoryRouter initialEntries={["/generate-pack"]}>
        <Routes>
          <Route path="/generate-pack" element={<GeneratePackWizardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("preset load failed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("button", { name: /Базовый/i }),
    ).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    getMock.mockResolvedValue({
      data: [{ id: "p-1", code: "P1", name: "Базовый", status: "active" }],
    });

    render(
      <MemoryRouter initialEntries={["/generate-pack"]}>
        <Routes>
          <Route path="/generate-pack" element={<GeneratePackWizardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole("button", { name: /Базовый/i });

    const budget = uxBudgetDelta(document.body, "GeneratePackWizardPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
