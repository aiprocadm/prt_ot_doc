import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const docsMock = vi.hoisted(() => ({
  generateDocument: vi.fn(),
  getGenerationTaskStatus: vi.fn(),
  resolveTemplateForQuickGenerate: vi.fn(),
}));

vi.mock("@/api/documents", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  generateDocument: (...a: unknown[]) => docsMock.generateDocument(...a),
  getGenerationTaskStatus: (...a: unknown[]) =>
    docsMock.getGenerationTaskStatus(...a),
  resolveTemplateForQuickGenerate: (...a: unknown[]) =>
    docsMock.resolveTemplateForQuickGenerate(...a),
}));

vi.mock("@/pages/documents/wizard/useDocumentsWizardBootstrap", () => ({
  useDocumentsWizardBootstrap: () => ({
    tenant: { id: "t-1", slug: "test", name: "Тестовый арендатор" },
    companies: [{ id: "c-1", name: "ООО «Ромашка»" }],
    sites: [{ id: "s-1", name: "Площадка №1", company_id: "c-1" }],
    layoutPresets: [],
    brandingProfileScope: null,
  }),
}));

const personsState = vi.hoisted(() => ({
  items: [
    {
      id: "p-1",
      first_name: "Иван",
      last_name: "Иванов",
      middle_name: "Иванович",
      company_id: "c-1",
    },
  ],
  list: vi.fn(() => Promise.resolve()),
  setPageSize: vi.fn(),
}));

vi.mock("@/stores/persons", () => ({
  usePersonsStore: () => ({
    items: personsState.items,
    list: personsState.list,
    setPageSize: personsState.setPageSize,
  }),
}));

vi.mock("@/stores/documentsWizard", () => ({
  useDocumentsWizardStore: () => ({
    quickGenerationHistory: [],
    pushQuickGenerationHistory: vi.fn(),
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import QuickGeneratePage from "@/pages/documents/QuickGeneratePage";

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <QuickGeneratePage />
      </MemoryRouter>,
    );
  });
};

describe("QuickGeneratePage", () => {
  beforeEach(() => {
    docsMock.resolveTemplateForQuickGenerate.mockReset();
    docsMock.generateDocument.mockReset();
    docsMock.getGenerationTaskStatus.mockReset();
    personsState.list.mockReset();
    personsState.list.mockResolvedValue(undefined);
    docsMock.resolveTemplateForQuickGenerate.mockResolvedValue({
      template_id: "tpl-1",
      template_name: "Приказ о приёме",
      version: 3,
    });

    useAuthStore.setState({
      user: {
        id: "u-1",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "spec@example.com",
        full_name: "Специалист по ОТ",
        roles: ["ot_specialist"],
        permissions: [PERMISSIONS.DOCUMENT_CREATE, PERMISSIONS.DOCUMENT_VIEW],
        attributes: { tenant_id: "t-1" },
      },
      loading: false,
      error: null,
    } as never);
  });

  it("мастер открыт тому, кому разрешено создавать документы", async () => {
    await renderPage();

    expect(
      await screen.findByText("Быстрая генерация для сотрудника/случая"),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете", async () => {
    await renderPage();
    await screen.findByText("Быстрая генерация для сотрудника/случая");

    const budget = uxBudgetDelta(document.body, "QuickGeneratePage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
