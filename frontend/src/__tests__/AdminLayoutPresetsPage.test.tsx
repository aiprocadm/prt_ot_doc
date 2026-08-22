import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const apiClientMock = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
}));

const brandingApiMock = vi.hoisted(() => ({
  listLayoutPresets: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => apiClientMock.post(...args),
    patch: (...args: unknown[]) => apiClientMock.patch(...args),
  },
}));

vi.mock("@/api/branding", () => ({
  listLayoutPresets: (...args: unknown[]) =>
    brandingApiMock.listLayoutPresets(...args),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import AdminLayoutPresetsPage from "@/pages/AdminLayoutPresets/AdminLayoutPresetsPage";

const presetList = [
  {
    id: "preset-1",
    tenant_id: "tenant-1",
    code: "company_brand",
    name: "Company brand",
    different_first: false,
    different_odd_even: false,
    header_first_xml: null,
    header_odd_xml: "{{company.name}}",
    header_even_xml: null,
    footer_first_xml: null,
    footer_odd_xml: "{{doc.title}}",
    footer_even_xml: null,
    watermark: { enabled: false },
  },
  {
    id: "preset-2",
    tenant_id: "tenant-1",
    code: "branch_brand",
    name: "Branch brand",
    different_first: true,
    different_odd_even: true,
    header_first_xml: "{{site.name}}",
    header_odd_xml: "{{company.name}}",
    header_even_xml: "{{company.name}}",
    footer_first_xml: null,
    footer_odd_xml: "{{doc.title}}",
    footer_even_xml: "{{doc.title}}",
    watermark: { enabled: true, text: "ЧЕРНОВИК" },
  },
];

describe("AdminLayoutPresetsPage", () => {
  beforeEach(() => {
    apiClientMock.post.mockReset();
    apiClientMock.patch.mockReset();
    brandingApiMock.listLayoutPresets.mockReset();

    brandingApiMock.listLayoutPresets.mockResolvedValue(presetList);
  });

  it("renders breadcrumb and preset editor with loaded presets", async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <AdminLayoutPresetsPage />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText("company_brand — Company brand"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("branch_brand — Branch brand"),
    ).toBeInTheDocument();
    expect(screen.getByText("Макеты/Колонтитулы")).toBeInTheDocument();
    // Первый пресет выбирается по умолчанию — его данные попали в форму.
    expect(screen.getByDisplayValue("company_brand")).toBeInTheDocument();
    expect(screen.getByDisplayValue("{{company.name}}")).toBeInTheDocument();
  });

  it("экран в UX-бюджете (BIZ-60 волна 5)", async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <AdminLayoutPresetsPage />
        </MemoryRouter>,
      );
    });
    expect(
      await screen.findByText("company_brand — Company brand"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "AdminLayoutPresetsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
