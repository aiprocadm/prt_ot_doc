import { useState } from "react";
import { toast } from "sonner";

import { importsApi } from "@/api/imports";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBatchProgress } from "@/features/imports/useBatchProgress";
import type { ImportBatchDto, ImportBatchRowDto, ImportBatchStatus } from "@/types/dto/imports";

const STATUS_LABELS: Record<ImportBatchStatus, string> = {
  pending: "В очереди",
  running: "Выполняется",
  applied: "Применена",
  previewed: "Проверена",
  failed: "Оборвалась",
  rolled_back: "Откачена"
};

const STATUS_VARIANT: Record<ImportBatchStatus, "secondary" | "destructive" | "outline"> = {
  pending: "outline",
  running: "outline",
  applied: "secondary",
  previewed: "outline",
  failed: "destructive",
  rolled_back: "outline"
};

/** Итог проверки качества по записям партии (разд. 71.3). */
const QualityLine = ({ batch }: { batch: ImportBatchDto }) => {
  const quality = (batch.notes as { data_quality?: Record<string, unknown> } | null)?.data_quality;
  if (!quality) return null;
  if (typeof quality.error === "string") {
    return (
      <p className="text-sm text-muted-foreground">
        Проверка качества не выполнилась: {quality.error}
      </p>
    );
  }
  const total = Number(quality.issues_total ?? 0);
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">Проверка качества: замечаний нет</p>;
  }
  return (
    <p className="text-sm text-amber-700">
      Проверка качества: замечаний {total}
      {quality.sample_truncated ? " (показаны не все)" : ""}
    </p>
  );
};

interface BatchesPanelProps {
  batches: ImportBatchDto[];
  onChanged: () => void;
}

/**
 * История загрузок: отчёт по партии и её откат (ТЗ разд. 71.1).
 *
 * Откат подтверждается: он удаляет созданные записи и возвращает перезаписанные,
 * то есть меняет данные, а «нажал не туда» здесь стоит дорого.
 */
export const BatchesPanel = ({ batches, onChanged }: BatchesPanelProps) => {
  const [openBatchId, setOpenBatchId] = useState<string | null>(null);
  const [rows, setRows] = useState<ImportBatchRowDto[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Фоновые партии опрашиваются, пока не завершатся: прогресс, который надо
  // обновлять кнопкой «перезагрузить», прогрессом не выглядит.
  const liveBatches = useBatchProgress(batches, { onSettled: onChanged });

  const toggleRows = async (batch: ImportBatchDto) => {
    if (openBatchId === batch.id) {
      setOpenBatchId(null);
      setRows([]);
      return;
    }
    try {
      const failed = await importsApi.batchRows(batch.id, "failed");
      setRows(failed);
      setOpenBatchId(batch.id);
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const downloadReport = async (batchId: string) => {
    try {
      await importsApi.downloadReport(batchId);
    } catch {
      // Причину уже показал глобальный обработчик API.
    }
  };

  const checkQuality = async (batchId: string) => {
    setBusyId(batchId);
    try {
      await importsApi.qualityCheck(batchId);
      onChanged();
    } catch {
      // Причину уже показал глобальный обработчик API.
    } finally {
      setBusyId(null);
    }
  };

  const rollback = async (batch: ImportBatchDto) => {
    if (!window.confirm(`Откатить загрузку «${batch.source_filename}»? Созданные записи будут удалены.`)) {
      return;
    }
    setBusyId(batch.id);
    try {
      await importsApi.rollback(batch.id);
      toast.success("Партия откачена");
      onChanged();
    } catch {
      // Глобальный обработчик уже показал причину (например, 409 «на записи ссылаются»).
    } finally {
      setBusyId(null);
    }
  };

  if (liveBatches.length === 0) {
    return <p className="text-sm text-muted-foreground">Загрузок пока не было.</p>;
  }

  return (
    <div className="space-y-2">
      {liveBatches.map((batch) => (
        <div key={batch.id} className="rounded-md border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{batch.source_filename}</span>
                <Badge variant={STATUS_VARIANT[batch.status]}>{STATUS_LABELS[batch.status]}</Badge>
                {batch.mode === "preview" ? (
                  <Badge variant="outline">проверка без записи</Badge>
                ) : null}
              </div>
              {batch.status === "pending" || batch.status === "running" ? (
                <p className="text-sm text-muted-foreground" role="status">
                  обработано {batch.processed_rows}
                  {batch.total_rows > 0 ? ` из ${batch.total_rows}` : ""}
                  {batch.total_rows > 0
                    ? ` (${Math.floor((batch.processed_rows / batch.total_rows) * 100)}%)`
                    : ""}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {batch.mode === "preview" ? "будет создано " : "создано "}
                  {batch.created_count} · {batch.mode === "preview" ? "обновлено" : "обновлено"}{" "}
                  {batch.updated_count} · без изменений {batch.skipped_count} · ошибок{" "}
                  {batch.failed_count}
                </p>
              )}
              {batch.error_message ? (
                <p className="text-sm text-destructive">{batch.error_message}</p>
              ) : null}
              <QualityLine batch={batch} />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void downloadReport(batch.id)}
              >
                Отчёт
              </Button>
              {batch.mode !== "preview" && batch.status === "applied" ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === batch.id}
                  onClick={() => void checkQuality(batch.id)}
                >
                  Проверить качество
                </Button>
              ) : null}
              {batch.failed_count > 0 ? (
                <Button variant="outline" size="sm" onClick={() => void toggleRows(batch)}>
                  {openBatchId === batch.id ? "Скрыть ошибки" : "Показать ошибки"}
                </Button>
              ) : null}
              {batch.mode !== "preview" &&
              (batch.status === "applied" || batch.status === "failed") ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === batch.id}
                  onClick={() => void rollback(batch)}
                >
                  Откатить
                </Button>
              ) : null}
            </div>
          </div>

          {openBatchId === batch.id ? (
            <ul className="mt-2 space-y-1 text-sm">
              {rows.map((row) => (
                <li key={row.row_number} className="rounded border p-2">
                  <span className="font-medium">Строка {row.row_number}:</span> {row.message ?? "—"}
                </li>
              ))}
              {rows.length === 0 ? <li className="text-muted-foreground">Ошибок нет.</li> : null}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
};
