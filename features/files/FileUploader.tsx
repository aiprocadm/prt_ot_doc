import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useFilesStore } from "@/stores/files";

export const FileUploader = () => {
  const { upload } = useFilesStore();
  const [description, setDescription] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length) return;
      setIsUploading(true);
      try {
        await Promise.all(acceptedFiles.map((file) => upload(file, { description })));
        toast.success("Файлы загружены");
      } finally {
        setIsUploading(false);
      }
    },
    [description, upload]
  );

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
