import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { GAS_PARAMETER_CODES } from "@/types/forms/workPermits";
import { GAS_PARAMETER_LABELS } from "@/lib/workPermitVocab";

export interface GasRow {
  parameter: string;
  value: string;
  norm?: string;
  measured_at?: string;
}

interface Props {
  rows: GasRow[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onCell: (index: number, field: keyof GasRow, value: string) => void;
}

export const GasAnalysisEditor = ({ rows, onAdd, onRemove, onCell }: Props) => (
  <div className="space-y-2">
    {rows.map((row, i) => (
      <div key={i} className="flex flex-wrap items-end gap-2">
        <select
          aria-label="Параметр замера"
          className="h-9 rounded-md border px-2 text-sm"
          value={row.parameter}
          onChange={(e) => onCell(i, "parameter", e.target.value)}
        >
          {GAS_PARAMETER_CODES.map((c) => (
            <option key={c} value={c}>{GAS_PARAMETER_LABELS[c]}</option>
          ))}
        </select>
        <Input
          aria-label="Значение"
          className="w-24"
          value={row.value}
          onChange={(e) => onCell(i, "value", e.target.value)}
        />
        <Input
          aria-label="Норма"
          className="w-28"
          value={row.norm ?? ""}
          onChange={(e) => onCell(i, "norm", e.target.value)}
        />
        <Input
          aria-label="Время замера"
          className="w-36"
          value={row.measured_at ?? ""}
          onChange={(e) => onCell(i, "measured_at", e.target.value)}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Удалить замер"
          onClick={() => onRemove(i)}
        >
          ✕
        </Button>
      </div>
    ))}
    <Button type="button" variant="outline" size="sm" onClick={onAdd}>
      Добавить замер
    </Button>
  </div>
);
