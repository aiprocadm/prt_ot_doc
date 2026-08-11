import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

const brandingApiMock = vi.hoisted(() => ({
  getBrandingHistory: vi.fn(),
  getBrandingProfile: vi.fn(),
  listLayoutPresets: vi.fn(),
  listSites: vi.fn(),
  previewBranding: vi.fn(),
  updateBrandingProfile: vi.fn(),
}));

vi.mock("@/api/branding", () => ({
  getBrandingHistory: (...args: unknown[]) => brandingApiMock.getBrandingHistory(...args),
  getBrandingProfile: (...args: unknown[]) => brandingApiMock.getBrandingProfile(...args),
  listLayoutPresets: (...args: unknown[]) => brandingApiMock.listLayoutPresets(...args),
  listSites: (...args: unknown[]) => brandingApiMock.listSites(...args),
  previewBranding: (...args: unknown[]) => brandingApiMock.previewBranding(...args),
  updateBrandingProfile: (...args: unknown[]) => brandingApiMock.updateBrandingProfile(...args),
}));

vi.mock("@/hooks/useUnsavedChanges", () => ({
  useUnsavedChanges: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import BrandingSettingsPage from "@/pages/branding/BrandingSettingsPage";
import { useCompaniesStore } from "@/stores/companies";
import { toast } from "sonner";

const listCompaniesMock = vi.fn(async () => undefined);

const baseProfile = {
  company_id: "company-1",
  site_id: null,
  scope: "company",
  preferred_header_preset_code: "company_brand",
  header_context: {},
  reproducibility: { generated_at: "2026-03-26T00:00:00Z" },
  resolution: {
    scope_chain: ["tenant", "company"],
    effective_preset_code: "company_brand",
    effective_preset_source: "company.branding.preferred_letterhead_preset",
  },
  branding: {
    legal_name: "АО Тест",
    short_name: "Тест",
    inn: "7701234567",
    kpp: "770101001",
    ogrn: "1027700000000",
    legal_address: "Москва",
    actual_address: "Москва",
    website: "https://example.test",
    email: "office@example.test",
    phones: ["+7 495 000-00-00"],
    header_details: ["АО Тест"],
    footer_details: ["ИНН 7701234567"],
    service_notes: ["draft"],
    branch_label: "Центральный офис",
    passport_label: "DOC-PASSPORT",
    preferred_letterhead_preset: "company_brand",
    watermark_text: "DRAFT",
    watermark_enabled: true,
    contacts: [],
    images: {
      logo_file_id: null,
      stamp_file_id: null,
      signature_file_id: null,
    },
    palette: {
      primary: "#0055AA",
      secondary: "#334455",
      accent: "#FFAA00",
    },
    metadata: { source: "erp" },
    signatories: [],
  },
};

const previewResponse = {
  preset_code: "company_brand",
  sections: {
    header_odd: "АО Тест / Main site",
    header_even: "Header even",
    header_first: "Header first",
    footer_odd: "ИНН 7701234567",
  },
  unresolved_placeholders: [],
  watermark: { text: "DRAFT" },
  apply_headers_payload: { preset_code: "company_brand" },
  wizard_defaults: {},
  profile: {
    ...baseProfile,
    scope: "site",
    reproducibility: { generated_at: "2026-03-26T01:00:00Z" },
  },
};

const getLabeledTextarea = (label: string) => {
  const labelNode = screen.getByText(label);
  const wrapper = labelNode.parentElement;
  if (!wrapper) {
    throw new Error(`Wrapper not found for ${label}`);
  }
  const textarea = wrapper.querySelector("textarea");
  if (!textarea) {
    throw new Error(`Textarea not found for ${label}`);
  }
  return textarea as HTMLTextAreaElement;
};

describe("BrandingSettingsPage", () => {
  beforeEach(() => {
    listCompaniesMock.mockClear();
    Object.values(brandingApiMock).forEach((mock) => mock.mockReset());
    vi.mocked(toast.error).mockReset();
    vi.mocked(toast.success).mockReset();

    useCompaniesStore.setState({
      items: [{ id: "company-1", name: "АО Тест" }],
      list: listCompaniesMock,
    } as never);

    brandingApiMock.listLayoutPresets.mockResolvedValue([
      { id: "preset-1", code: "company_brand", name: "Company brand" },
    ]);
    brandingApiMock.listSites.mockResolvedValue([
      { id: "site-1", company_id: "company-1", name: "Main site" },
    ]);
    brandingApiMock.getBrandingProfile.mockResolvedValue(baseProfile);
    brandingApiMock.getBrandingHistory.mockResolvedValue([]);
    brandingApiMock.previewBranding.mockResolvedValue(previewResponse);
    brandingApiMock.updateBrandingProfile.mockResolvedValue(baseProfile);
  });

  it("loads branding profile and renders current scope data", async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <BrandingSettingsPage />
        </MemoryRouter>
      );
    });

    expect((await screen.findAllByDisplayValue("АО Тест")).length).toBeGreaterThan(0);
    expect(screen.getByText("company")).toBeInTheDocument();
    expect(screen.getAllByText("company_brand").length).toBeGreaterThan(0);
    expect(screen.getAllByText("АО Тест").length).toBeGreaterThan(0);
    expect(listCompaniesMock).toHaveBeenCalled();
    expect(brandingApiMock.listSites).toHaveBeenCalledWith("company-1");
    expect(brandingApiMock.getBrandingProfile).toHaveBeenCalledWith("company-1", undefined);
  });

  it("builds branded preview and stores it in recent history", async () => {
    const user = userEvent.setup();

    await act(async () => {
      render(
        <MemoryRouter>
          <BrandingSettingsPage />
        </MemoryRouter>
      );
    });

    expect((await screen.findAllByDisplayValue("АО Тест")).length).toBeGreaterThan(0);
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /тестовая генерация превью с брендингом/i }));
    });

    expect((await screen.findAllByText(/АО Тест \/ Main site/i)).length).toBeGreaterThan(0);
    expect(screen.getByText(/все плейсхолдеры разрешены/i)).toBeInTheDocument();
    expect(screen.getAllByText(/2026-03-26T01:00:00Z/i).length).toBeGreaterThan(0);
    expect(brandingApiMock.previewBranding).toHaveBeenCalledWith(
      expect.objectContaining({
        company_id: "company-1",
        preset_code: "company_brand",
      })
    );
    expect(toast.success).toHaveBeenCalledWith("Предпросмотр обновлён");
  });

  it("rejects invalid metadata json before save and avoids API write", async () => {
    const user = userEvent.setup();

    await act(async () => {
      render(
        <MemoryRouter>
          <BrandingSettingsPage />
        </MemoryRouter>
      );
    });

    expect((await screen.findAllByDisplayValue("АО Тест")).length).toBeGreaterThan(0);

    const metadataTextarea = getLabeledTextarea("Метаданные (JSON)");
    await act(async () => {
      fireEvent.change(metadataTextarea, { target: { value: "{" } });
    });
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /сохранить профиль/i }));
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Некорректный JSON в метаданных или подписантах");
    });
    expect(brandingApiMock.updateBrandingProfile).not.toHaveBeenCalled();
  });
});