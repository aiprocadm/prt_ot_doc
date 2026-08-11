import { apiClient } from "@/api/client";

export type UploadSessionResponse = {
  file_id: string;
  signed_put_url: string;
  expires_at: string;
};

export type FileRecordResponse = {
  id: string;
  status: string;
  size_bytes: number;
  metadata_json: Record<string, unknown>;
  content_index?: { status: string; attempts: number; last_error?: string | null } | null;
};

export const createUploadSession = async (payload: {
  filename: string;
  content_type: string;
  size_bytes: number;
  metadata_json?: Record<string, unknown>;
}) => {
  const { data } = await apiClient.post<UploadSessionResponse>("/files/presign-upload", payload);
  return data;
};

export const uploadToSignedUrl = async (signedPutUrl: string, file: File) => {
  await apiClient.put(signedPutUrl, file, {
    headers: { "Content-Type": file.type || "application/octet-stream" }
  });
};

export const finalizeUpload = async (fileId: string) => {
  const { data } = await apiClient.post<{ file_id: string; status: string }>(`/files/complete-upload`, { file_id: fileId });
  return data;
};

export const getFile = async (fileId: string) => {
  const { data } = await apiClient.get<FileRecordResponse>(`/files/records/${fileId}`);
  return data;
};

export const getDownloadUrl = async (fileId: string, purpose = "ui_download") => {
  const { data } = await apiClient.post<{ signed_get_url: string }>(`/files/${fileId}:download-url`, { purpose });
  return data.signed_get_url;
};

export const listEntityFiles = async (entityType: string, entityId: string) => {
  const { data } = await apiClient.get<Array<{ file_id: string; role: string; status: string; display_name: string; size: number }>>(
    `/files/entities/${entityType}/${entityId}/files`
  );
  return data;
};

export const fetchDownloadUrl = async (fileId: string, versionId: string) => {
  const { data } = await apiClient.get<{ url: string }>(`/files/${fileId}/versions/${versionId}:download-url`);
  return data.url;
};

export const fetchFileDownloadLink = async (fileId: string) => {
  const signed_get_url = await getDownloadUrl(fileId, "ui_download");
  return { url: signed_get_url, expires_in: 600 };
};


export const reindexFile = async (fileId: string) => {
  const { data } = await apiClient.post<{ file_id: string; status: string }>(`/files/${fileId}:reindex`);
  return data;
};
