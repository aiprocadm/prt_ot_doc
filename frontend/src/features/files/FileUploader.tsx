import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import { createUploadSession, finalizeUpload, getFile } from "@/api/files";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export const FileUploader = () => {
  const [description, setDescription] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (!acceptedFiles.length) return;
    setIsUploading(true);
    try {
      for (const file of acceptedFiles) {
        const session = await createUploadSession({
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          size_bytes: file.size,
          metadata_json: { description }
        });
        await apiClient(session.signed_put_url, {
          method: "PUT",
          headers: { "Content-Type": file.type || "application/octet-stream" },
          body: file
        });
        await finalizeUpload(session.file_id);
        for (let i = 0; i < 20; i += 1) {
          const current = await getFile(session.file_id);
          if (current.status === "ready") break;
          if (current.status === "infected" || current.status === "quarantined") {
            throw new Error(`Файл ${file.name} не прошёл AV-проверку`);
          }
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      }
      toast.success("Файлы загружены");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Ошибка загрузки");
    } finally {
      setIsUploading(false);
    }
  }, [description]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

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
        </div>
        {isUploading && <p className="text-sm text-muted-foreground">Загрузка...</p>}
      </CardContent>
    </Card>
  );
};
