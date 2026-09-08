import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const filesState = vi.hoisted(() => ({
  items: [] as unknown[],
  loading: false,
  error: null as unknown,
  list: vi.fn(),
}));

vi.mock("@/stores/files", () => ({
  useFilesStore: () => ({
    list: filesState.list,
    items: filesState.items,
    loading: filesState.loading,
    error: filesState.error,
    pagination: { page: 1, page_size: 10, total: filesState.items.length },
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    remove: vi.fn(),
  }),
}));

vi.mock("@/features/files/FileUploader", () => ({
  FileUploader: () => <div data-testid="file-uploader">Загрузка файла</div>,
}));

import FilesPage from "@/pages/files/FilesPage";

const files = [
  {
    id: "f-1",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    name: "Приказ о назначении.pdf",
    mime_type: "application/pdf",
    size: 24576,
    url: "/files/f-1",
  },
  {
    id: "f-2",
    created_at: "2026-09-02T10:00:00Z",
    updated_at: "2026-09-02T10:00:00Z",
    name: "Журнал инструктажей.docx",
    mime_type:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size: 51200,
    url: "/files/f-2",
  },
];

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <FilesPage />
      </MemoryRouter>,
    );
  });
};

describe("FilesPage", () => {
  beforeEach(() => {
    filesState.items = files;
    filesState.loading = false;
    filesState.error = null;
    filesState.list.mockReset();
  });

  it("показывает реестр файлов", async () => {
    await renderPage();

    expect(
      await screen.findByText("Приказ о назначении.pdf"),
    ).toBeInTheDocument();
    expect(screen.getByText("Журнал инструктажей.docx")).toBeInTheDocument();
    expect(filesState.list).toHaveBeenCalled();
  });

  it("пустой реестр ведёт к следующему шагу, а не в тупик", async () => {
    filesState.items = [];
    await renderPage();

    expect(await screen.findByText("Файлы не найдены")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Перейти к документам" }),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных", async () => {
    await renderPage();
    await screen.findByText("Приказ о назначении.pdf");

    const budget = uxBudgetDelta(document.body, "FilesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
