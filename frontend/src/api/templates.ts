import { apiClient } from "@/api/client";

export const templatesApi = {
  uploadVersion: async (templateId: string, file: File): Promise<void> => {
    const form = new FormData();
    form.append("file", file);
    await apiClient.post(`/templates/${templateId}/versions:upload`, form, {
      headers: { "Content-Type": "multipart/form-data", "Idempotency-Key": `${templateId}-${file.name}` }
    });
  },
  lintVersion: async (templateId: string, versionId: string): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.post<Record<string, unknown>>(`/templates/${templateId}/versions/${versionId}:lint`, {
      required_fields: []
    });
    return data;
  },
  previewVersion: async (templateId: string, versionId: string, payload: Record<string, unknown>): Promise<{ docx_url?: string }> => {
    const { data } = await apiClient.post<{ docx_url?: string }>(`/templates/${templateId}/versions/${versionId}:preview`, {
      data: payload,
      render_pdf: false
    });
    return data;
  }
};

