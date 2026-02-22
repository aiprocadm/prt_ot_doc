import { apiClient } from "@/api/client";

export const fetchDownloadUrl = async (fileId: string, versionId: string) => {
  const { data } = await apiClient.get<{ url: string }>(`/files/${fileId}/versions/${versionId}:download-url`);
  return data.url;
};
