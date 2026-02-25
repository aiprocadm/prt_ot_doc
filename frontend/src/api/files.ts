import { apiClient } from "@/api/client";

export const fetchDownloadUrl = async (fileId: string, versionId: string) => {
  const { data } = await apiClient.get<{ url: string }>(`/files/${fileId}/versions/${versionId}:download-url`);
  return data.url;
};

export const fetchFileDownloadLink = async (fileId: string) => {
  const { data } = await apiClient.get<{ url: string; expires_in: number }>(`/v1/files/${fileId}/download`);
  return data;
};
