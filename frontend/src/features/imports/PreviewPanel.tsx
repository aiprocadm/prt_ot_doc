import { Badge } from "@/components/ui/badge";
import type { ImportPreviewDto, ImportRowAction } from "@/types/dto/imports";

const ACTION_LABELS: Record<ImportRowAction, string> = {
  create: "Создать",
  update: "Обновить",
  skip: "Без изменений",
  error: "Ошибка"
};

const COUNT_ORDER: ImportRowAction[] = ["create", "update", "skip", "error"];

interface PreviewPanelProps {
  preview: ImportPreviewDto;
  /** Сколько ошибочных строк показывать: полный список на тысячах строк бесполезен. */
  errorLimit?: number;
}

/**
 * Результат сухого прогона: сводка и построчные ошибки (ТЗ разд. 71.1).
 *
 * Ошибки показываются С НОМЕРОМ СТРОКИ: «файл не загрузился» без указания места
 * заставляет искать проблему глазами по всей выгрузке.
 */
export const PreviewPanel = ({ preview, errorLimit = 50 }: PreviewPanelProps) => {
  const errorRows = preview.rows.filter((row) => row.action === "error");
  const shown = errorRows.slice(0, errorLimit);
  const unknownRefs = Object.entries(preview.unknown_references);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {COUNT_ORDER.map((action) => (
          <Badge key={action} variant={action === "error" ? "destructive" : "secondary"}>
            {ACTION_LABELS[action]}: {preview.counts[action] ?? 0}
          </Badge>
        ))}
        <Badge variant="outline">Всего строк: {preview.counts.total ?? 0}</Badge>
      </div>

      {unknownRefs.length > 0 ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
          <p className="font-medium">Значения, которых нет в справочниках</p>
          {unknownRefs.map(([lookup, values]) => (
            <p key={lookup} className="text-muted-foreground">
              {lookup}: {values.join(", ")}
            </p>
          ))}
          <p className="mt-1 text-muted-foreground">
            Создайте их заранее — строки с неизвестными значениями не будут загружены.
          </p>
        </div>
      ) : null}

      {shown.length > 0 ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">Строки на исправление</p>
          <ul className="space-y-1 text-sm">
            {shown.map((row) => (
              <li key={row.row_number} className="rounded border p-2">
                <span className="font-medium">Строка {row.row_number}:</span>{" "}
                {row.errors.map((error) => error.message).join("; ")}
              </li>
            ))}
          </ul>
          {errorRows.length > shown.length ? (
            <p className="text-sm text-muted-foreground">
              Показаны первые {shown.length} из {errorRows.length}. Полный список — в отчёте партии
              после применения.
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Ошибочных строк нет.</p>
      )}
    </div>
  );
};
