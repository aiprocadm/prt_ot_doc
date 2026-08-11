import { apiClient } from "@/api/client";

/** Backend: `normalize_idempotency_key` — макс. 128 символов. Ключ в ASCII, имя файла учитывается в SHA-256. */
const idempotencyKeyForTemplateUpload = async (templateId: string, file: File) => {
  const material = new TextEncoder().encode(
    `${templateId}\0${file.size}\0${file.lastModified}\0${file.name}`
  );
  const digest = await crypto.subtle.digest("SHA-256", material);
  const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  return `tplu-${hex}`;
};

export const templatesApi = {
  uploadVersion: async (templateId: string, file: File): Promise<void> => {
    const form = new FormData();
    form.append("file", file);
    const idempotencyKey = await idempotencyKeyForTemplateUpload(templateId, file);
    await apiClient.post(`/templates/${templateId}/versions:upload`, form, {
      headers: { "Idempotency-Key": idempotencyKey }
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

