import { apiClient } from "@/api/client";

export interface BrandingContactDto {
  full_name?: string | null;
  position?: string | null;
  email?: string | null;
  phone?: string | null;
}

export interface BrandingImageSetDto {
  logo_file_id?: string | null;
  stamp_file_id?: string | null;
  signature_file_id?: string | null;
}

export interface BrandingPaletteDto {
  primary?: string | null;
  secondary?: string | null;
  accent?: string | null;
  watermark?: string | null;
}

export interface BrandingProfileDto {
  company_id: string;
  site_id?: string | null;
  scope: string;
  preferred_header_preset_code?: string | null;
  branding: {
    legal_name?: string | null;
    short_name?: string | null;
    inn?: string | null;
    kpp?: string | null;
    ogrn?: string | null;
    legal_address?: string | null;
    actual_address?: string | null;
    website?: string | null;
    email?: string | null;
    phones: string[];
    header_details: string[];
    footer_details: string[];
    service_notes: string[];
    branch_label?: string | null;
    passport_label?: string | null;
    preferred_letterhead_preset?: string | null;
    watermark_text?: string | null;
    watermark_enabled: boolean;
    contacts: BrandingContactDto[];
    images?: BrandingImageSetDto;
    palette?: BrandingPaletteDto;
    signatories?: Array<Record<string, unknown>>;
    metadata?: Record<string, unknown>;
  };
  header_context: Record<string, unknown>;
  reproducibility: Record<string, unknown>;
  resolution?: {
    scope_chain?: string[];
    company_has_branding?: boolean;
    site_has_branding?: boolean;
    site_branding_applied?: boolean;
    effective_preset_code?: string | null;
    effective_preset_source?: string | null;
  };
}

export interface BrandingPreviewDto {
  profile: BrandingProfileDto;
  preset_code?: string | null;
  sections: Record<string, string | null>;
  unresolved_placeholders: string[];
  watermark: Record<string, unknown>;
  apply_headers_payload: Record<string, unknown>;
  wizard_defaults: Record<string, unknown>;
}


export interface BrandingGenerationHistoryItemDto {
  pipeline_run_id: string;
  company_id: string;
  site_id?: string | null;
  template_id?: string | null;
  template_version_id?: string | null;
  status: string;
  generated_at?: string | null;
  preset_code?: string | null;
  document_title?: string | null;
  document_number?: string | null;
  output_name?: string | null;
  reproducibility: Record<string, unknown>;
}

export interface BrandingPreviewRequestDto {
  company_id: string;
  site_id?: string | null;
  preset_code?: string | null;
  document_title?: string | null;
  document_number?: string | null;
  generated_at?: string | null;
  watermark_override?: Record<string, unknown> | null;
}

export const getBrandingProfile = async (companyId: string, siteId?: string) => {
  const { data } = await apiClient.get<BrandingProfileDto>("/branding/profile", {
    params: { company_id: companyId, site_id: siteId }
  });
  return data;
};

export const updateBrandingProfile = async (
  companyId: string,
  payload: {
    preferred_header_preset_code?: string | null;
    site_id?: string | null;
    branding: BrandingProfileDto["branding"];
  }
) => {
  const { data } = await apiClient.patch<BrandingProfileDto>(`/branding/profile/${companyId}`, payload);
  return data;
};

export const previewBranding = async (payload: BrandingPreviewRequestDto) => {
  const { data } = await apiClient.post<BrandingPreviewDto>("/branding/preview", payload);
  return data;
};

export interface LayoutPresetDto {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  different_first: boolean;
  different_odd_even: boolean;
  header_first_xml?: string | null;
  header_odd_xml?: string | null;
  header_even_xml?: string | null;
  footer_first_xml?: string | null;
  footer_odd_xml?: string | null;
  footer_even_xml?: string | null;
  watermark: Record<string, unknown>;
}

export const listLayoutPresets = async () => {
  const { data } = await apiClient.get<{ items: LayoutPresetDto[] }>("/layout-presets");
  return data.items;
};

export interface SiteDto {
  id: string;
  company_id: string;
  name: string;
  address?: string | null;
  branding_payload?: Record<string, unknown>;
}

export const listSites = async (companyId: string) => {
  const { data } = await apiClient.get<{ items: SiteDto[] }>("/sites", {
    params: { company_id: companyId, limit: 200, offset: 0 }
  });
  return data.items;
};

export const getBrandingHistory = async (companyId: string, siteId?: string, limit = 10) => {
  const { data } = await apiClient.get<{ items: BrandingGenerationHistoryItemDto[] }>("/branding/history", {
    params: { company_id: companyId, site_id: siteId, limit }
  });
  return data.items;
};
