import { Label } from "@/components/ui/label";
import type { ImportColumnDto, ImportPreviewDto } from "@/types/dto/imports";

interface MappingEditorProps {
  columns: ImportColumnDto[];
  preview: ImportPreviewDto;
  overrides: Record<string, string>;
  onChange: (field: string, header: string) => void;
}

/**
 * Визуальный маппинг «колонка файла → поле системы» (ТЗ разд. 71.1).
 *
 * Показываются ВСЕ колонки цели, а не только распознанные: пользователь должен
 * видеть, что осталось несопоставленным, — иначе пропущенное поле обнаружится
 * уже после импорта, когда данные записаны.
 *
 * Варианты выбора — заголовки ИЗ ФАЙЛА (сопоставленные и «ничьи»), потому что
 * выбирать можно только из того, что в файле действительно есть.
 */
export const MappingEditor = ({
  columns,
  preview,
  overrides,
  onChange,
}: MappingEditorProps) => {
  const fileHeaders = Array.from(
    new Set([...Object.values(preview.mapping), ...preview.unmapped_headers]),
  ).sort((a, b) => a.localeCompare(b, "ru"));

  const effective = (field: string): string =>
    overrides[field] ?? preview.mapping[field] ?? "";

  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">
        Сопоставление подобрано автоматически по заголовкам. Если колонка
        распознана неверно, выберите нужную вручную — ручной выбор всегда
        сильнее автоопределения.
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {columns.map((column) => {
          const value = effective(column.field);
          const missingRequired = column.required && !value;
          return (
            <div key={column.field} className="space-y-1">
              <Label htmlFor={`map-${column.field}`}>
                {column.title}
                {column.required ? (
                  <span className="text-destructive"> *</span>
                ) : null}
              </Label>
              <select
                id={`map-${column.field}`}
                aria-label={column.title}
                className={`h-9 w-full rounded-md border px-3 text-sm ${
                  missingRequired ? "border-destructive" : ""
                }`}
                value={value}
                onChange={(event) => onChange(column.field, event.target.value)}
              >
                <option value="">— не сопоставлено —</option>
                {fileHeaders.map((header) => (
                  <option key={header} value={header}>
                    {header}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>

      {preview.unmapped_headers.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Колонки файла без пары: {preview.unmapped_headers.join(", ")}. Они не
          будут загружены.
        </p>
      ) : null}
    </div>
  );
};
