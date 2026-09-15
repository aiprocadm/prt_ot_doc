import { useEffect, useState } from "react";
import { toast } from "sonner";

import { npaApi } from "@/api/npa";
import type { NpaResponsibleResponseDto } from "@/types/dto/npa";

/**
 * Кто ведёт этот акт в нашей организации (срез-203, B.18 разд. 19.1 «owner»).
 *
 * Ответственный АРЕНДАТОРСКИЙ: один и тот же приказ Минтруда ведут в разных
 * организациях разные люди, поэтому он не живёт у общей строки реестра.
 *
 * «Никто не ведёт» показывается словами, а не пустотой: пустое место человек
 * читает как «тут ничего не предусмотрено», а это состояние, которое надо
 * заметить и исправить — именно ему уходят задачи после новой редакции.
 */

interface NpaResponsibleProps {
  actId: string;
  /** Может ли пришедший назначать: у рядовой роли ручка ответит 403. */
  canEdit: boolean;
}

export const NpaResponsible = ({ actId, canEdit }: NpaResponsibleProps) => {
  const [state, setState] = useState<NpaResponsibleResponseDto | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    npaApi
      .responsible(actId)
      .then((data) => {
        if (alive) setState(data);
      })
      .catch(() => {
        if (alive) setState(null);
      });
    return () => {
      alive = false;
    };
  }, [actId]);

  if (!state) return null;

  const change = async (value: string) => {
    setSaving(true);
    try {
      const next = await npaApi.setResponsible(actId, value || null);
      setState({ ...state, responsible: next.responsible });
      toast.success(
        next.responsible
          ? `Ответственный: ${next.responsible.name}`
          : "Ответственный снят",
      );
    } catch {
      toast.error("Не удалось сохранить ответственного");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-2 text-sm" data-testid="npa-responsible">
      <span className="text-muted-foreground">Ответственный: </span>
      {canEdit ? (
        <select
          aria-label="Ответственный за акт"
          className="h-8 rounded border px-2 text-sm"
          value={state.responsible?.user_id ?? ""}
          disabled={saving}
          onChange={(event) => void change(event.target.value)}
        >
          <option value="">Никто не ведёт</option>
          {state.candidates.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {candidate.name}
            </option>
          ))}
        </select>
      ) : (
        <span>{state.responsible?.name ?? "никто не ведёт"}</span>
      )}
    </div>
  );
};
