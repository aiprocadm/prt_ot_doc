import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import GeneratePackWizardPage from "@/pages/packs/GeneratePackWizardPage";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args)
  }
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn()
  }
}));

describe("GeneratePackWizardPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("shows safe summary and blocks run when json is invalid", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue({
      data: [{ id: "p-1", code: "P1", name: "Базовый", status: "active" }]
    });

    render(
      <MemoryRouter initialEntries={["/generate-pack"]}>
        <Routes>
          <Route path="/generate-pack" element={<GeneratePackWizardPage />} />
        </Routes>
      </MemoryRouter>
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
    expect(screen.getByRole("button", { name: "Запустить генерацию" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Назад" }));
    await user.clear(screen.getByLabelText("Ключ идемпотентности (уникальный запуск)"));
    expect(screen.getByRole("button", { name: "Далее" })).toBeDisabled();
  });

  it("retries preset loading without forcing a full page reload", async () => {
    const user = userEvent.setup();
    getMock
      .mockRejectedValueOnce({ message: "preset load failed", status: 400, code: "preset_load_failed" })
      .mockResolvedValueOnce({
        data: [{ id: "p-1", code: "P1", name: "Базовый", status: "active" }]
      });

    render(
      <MemoryRouter initialEntries={["/generate-pack"]}>
        <Routes>
          <Route path="/generate-pack" element={<GeneratePackWizardPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText("preset load failed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByRole("button", { name: /Базовый/i })).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledTimes(2);
  });
});
