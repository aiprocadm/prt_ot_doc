import { useCallback, useMemo, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import { createUploadSession, finalizeUpload, getFile } from "@/api/files";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type UploadStatus = "pending" | "uploading" | "processing" | "ready" | "error";

interface UploadItem {
  id: string;
  name: string;
  status: UploadStatus;
  progress: number;
  error?: string;
}

const ACCEPTED_FILE_TYPES = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"]
};

const sleep = (timeout: number) => new Promise((resolve) => setTimeout(resolve, timeout));

const statusLabel: Record<UploadStatus, string> = {
  pending: "В очереди",
  uploading: "Загрузка",
  processing: "Проверка",
  ready: "Готово",
  error: "Ошибка"
};

interface FileUploaderProps {
  pollAttempts?: number;
  pollIntervalMs?: number;
}

export const FileUploader = ({ pollAttempts = 20, pollIntervalMs = 500 }: FileUploaderProps) => {
  const [description, setDescription] = useState("");
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const updateUpload = useCallback((id: string, patch: Partial<UploadItem>) => {
    setUploads((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const uploadSingleFile = useCallback(
    async (file: File) => {
      const localId = `${file.name}-${file.size}-${Date.now()}`;
      setUploads((current) => [
        ...current,
        { id: localId, name: file.name, status: "pending", progress: 0 }
      ]);

      try {
        updateUpload(localId, { status: "uploading", progress: 20 });
        const session = await createUploadSession({
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          size_bytes: file.size,
          metadata_json: { description }
        });

        updateUpload(localId, { progress: 45 });
        await apiClient.put(session.signed_put_url, file, {
          headers: { "Content-Type": file.type || "application/octet-stream" }
        });

        updateUpload(localId, { progress: 70, status: "processing" });
        await finalizeUpload(session.file_id);

        let fileReady = false;
        for (let i = 0; i < pollAttempts; i += 1) {
          const current = await getFile(session.file_id);
          if (current.status === "ready") {
            fileReady = true;
            break;
          }
          if (current.status === "infected" || current.status === "quarantined") {
            throw new Error(`Файл ${file.name} не прошёл AV-проверку`);
          }
          await sleep(pollIntervalMs);
        }

        if (!fileReady) {
          throw new Error(`Файл ${file.name}: превышено ожидание обработки`);
        }

        updateUpload(localId, { progress: 100, status: "ready", error: undefined });
        return true;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Ошибка загрузки";
        updateUpload(localId, { status: "error", progress: 100, error: message });
        return false;
      }
    },
    [description, pollAttempts, pollIntervalMs, updateUpload]
  );

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length) return;
      setIsUploading(true);
      try {
        const results = await Promise.all(acceptedFiles.map(uploadSingleFile));
        const failed = results.filter((status) => !status).length;
        if (!failed) {
          toast.success("Файлы загружены");
        } else if (failed === acceptedFiles.length) {
          toast.error("Не удалось загрузить выбранные файлы");
        } else {
          toast.warning(`Частичная загрузка: ошибок ${failed} из ${acceptedFiles.length}`);
        }
      } finally {
        setIsUploading(false);
      }
    },
    [uploadSingleFile]
  );

  const onDropRejected = useCallback((rejections: FileRejection[]) => {
    if (!rejections.length) return;
    const first = rejections[0];
    const reason = first.errors[0]?.message || "Неподдерживаемый формат";
    toast.error(`Файл ${first.file.name}: ${reason}`);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    accept: ACCEPTED_FILE_TYPES,
    maxSize: 50 * 1024 * 1024
  });

  const hasErrors = useMemo(() => uploads.some((upload) => upload.status === "error"), [uploads]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl font-semibold">Загрузка файлов</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input
          placeholder="Описание"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          aria-label="Описание файла"
        />
        <div
          {...getRootProps({
            className: `flex h-40 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed text-sm ${
              isDragActive ? "border-primary bg-primary/10" : "border-muted-foreground/40"
            }`
          })}
        >
          <input {...getInputProps()} />
          <p>Перетащите файлы сюда или нажмите для выбора</p>
          <p className="mt-1 text-xs text-muted-foreground">Допустимо: PDF, DOCX, XLSX до 50MB</p>
        </div>
        {isUploading && <p className="text-sm text-muted-foreground">Загрузка выполняется, не закрывайте страницу.</p>}
        {uploads.length > 0 && (
          <div className="space-y-2 rounded-md border p-3" aria-live="polite">
            {uploads.map((upload) => (
              <div key={upload.id} className="space-y-1 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate">{upload.name}</span>
                  <span className="text-xs text-muted-foreground">{statusLabel[upload.status]} · {upload.progress}%</span>
                </div>
                <div className="h-2 rounded bg-muted">
                  <div className="h-2 rounded bg-primary transition-all" style={{ width: `${upload.progress}%` }} />
                </div>
                {upload.error && <p className="text-xs text-destructive">{upload.error}</p>}
              </div>
            ))}
            {hasErrors && (
              <Button type="button" variant="outline" size="sm" onClick={() => setUploads((current) => current.filter((item) => item.status !== "error"))}>
                Очистить ошибки
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
