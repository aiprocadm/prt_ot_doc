import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PackWizard } from "@/features/packs/PackWizard";

const listCompaniesMock = vi.fn();
const createMock = vi.fn();

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    items: [
      { id: "c-1", name: "СеверСтрой" },
      { id: "c-2", name: "ПромСервис" }
    ],
    list: listCompaniesMock
  })
}));

vi.mock("@/stores/packs", () => ({
  usePacksStore: () => ({
    create: createMock
  })
}));

describe("PackWizard", () => {
  beforeEach(() => {
    listCompaniesMock.mockReset();
    createMock.mockReset();
  });

  it("goes through steps and submits generation", async () => {
    createMock.mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<PackWizard />);

    expect(listCompaniesMock).toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText("Выберите компанию"), "c-1");
    await user.click(screen.getAllByRole("button", { name: "Далее" })[0]);

    const siteEntryCard = screen.getByText("Выход на объект").closest("button");
    expect(siteEntryCard).not.toBeNull();
    await user.click(siteEntryCard!);
    await user.click(screen.getAllByRole("button", { name: "Далее" })[0]);

    await user.type(screen.getByLabelText("Дополнительные параметры"), "Объект №42");
    await user.click(screen.getByRole("button", { name: "Запустить генерацию" }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith({
        company_id: "c-1",
        preset: "site_entry",
        parameters: { notes: "Объект №42" }
      });
    });

    expect(await screen.findByText(/Задача создана/, {}, { timeout: 10000 })).toBeInTheDocument();
  });

  it("shows api error and keeps wizard on submit step", async () => {
    createMock.mockRejectedValue(new Error("Сервис генерации недоступен"));
    const user = userEvent.setup();

    render(<PackWizard />);

    await user.selectOptions(screen.getByLabelText("Выберите компанию"), "c-1");
    await user.click(screen.getAllByRole("button", { name: "Далее" })[0]);

    const ecologyCard = screen.getByText("Экология").closest("button");
    expect(ecologyCard).not.toBeNull();
    await user.click(ecologyCard!);
    await user.click(screen.getAllByRole("button", { name: "Далее" })[0]);
    await user.click(screen.getByRole("button", { name: "Запустить генерацию" }));

    expect(await screen.findByText("Сервис генерации недоступен", {}, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByLabelText("Дополнительные параметры")).toBeInTheDocument();

    const content = within(screen.getByText("Сервис генерации недоступен").parentElement!);
    expect(content.getByText("Сервис генерации недоступен")).toBeInTheDocument();
  });
});
