import { apiClient } from "@/api/client";

/** ASCII-only for HTTP headers: имя файла (в т.ч. кириллица) в заголовки попадать не может. */
const headerSafeFileToken = (name: string) => {
  try {
    return btoa(unescape(encodeURIComponent(name)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  } catch {
    return "file";
  }
};

export const templatesApi = {
  uploadVersion: async (templateId: string, file: File): Promise<void> => {
    const form = new FormData();
    form.append("file", file);
    const idem = `${templateId}-${file.size}-${file.lastModified}-${headerSafeFileToken(file.name)}`;
    await apiClient.post(`/templates/${templateId}/versions:upload`, form, {
      headers: { "Idempotency-Key": idem.slice(0, 200) }
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

