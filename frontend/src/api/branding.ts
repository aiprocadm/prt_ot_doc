import { apiClient } from "@/api/client";

export interface BrandingContactDto {
  full_name?: string | null;
  position?: string | null;
  email?: string | null;
  phone?: string | null;
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
    footer_details: string[];
    service_notes: string[];
    branch_label?: string | null;
    passport_label?: string | null;
    preferred_letterhead_preset?: string | null;
    watermark_text?: string | null;
    watermark_enabled: boolean;
    contacts: BrandingContactDto[];
  };
  header_context: Record<string, unknown>;
  reproducibility: Record<string, unknown>;
}

export interface BrandingPreviewDto {
  profile: BrandingProfileDto;
  preset_code?: string | null;
  sections: Record<string, string | null>;
  unresolved_placeholders: string[];
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

export const previewBranding = async (payload: {
  company_id: string;
  site_id?: string | null;
  preset_code?: string | null;
  document_title?: string | null;
  document_number?: string | null;
}) => {
  const { data } = await apiClient.post<BrandingPreviewDto>("/branding/preview", payload);
  return data;
};
