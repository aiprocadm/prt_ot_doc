import type { DocumentBatchItem } from "@/api/documents";

export const parseCsvColumns = async (file: File) => {
  const text = await file.text();
  const [header] = text.split(/\r?\n/);
  return header
    .split(/[,;]/)
    .map((item) => item.trim())
    .filter(Boolean);
};

export const buildBatchErrors = (items: DocumentBatchItem[]) =>
  items
    .filter((item) => item.status === "failed")
    .map((item) => `Строка ${item.row_index}: ${item.error ?? "unknown_error"}`)
    .join("\n");

export const getArchiveStatusSummary = ({
  batchStatus,
  pipelineStatus,
}: {
  batchStatus?: string | null;
  pipelineStatus?: string | null;
}) => {
  if (pipelineStatus === "done" || batchStatus === "completed") {
    return {
      tone: "text-green-700",
      title: "Архив готов к публикации",
      description:
        "Артефакты сформированы, можно открыть архив, проверить документы и продолжить согласование/отправку.",
    };
  }
  if (
    pipelineStatus === "failed" ||
    pipelineStatus === "error" ||
    batchStatus === "failed"
  ) {
    return {
      tone: "text-destructive",
      title: "Есть ошибки перед архивированием",
      description:
        "Проверьте timeline pipeline или построчные ошибки batch перед передачей документов дальше.",
    };
  }
  return {
    tone: "text-muted-foreground",
    title: "Архив ожидает завершения фоновых задач",
    description:
      "Следите за статусом pipeline и batch: после завершения отсюда можно перейти в архив и на экран согласований без ручной перезагрузки.",
  };
};
