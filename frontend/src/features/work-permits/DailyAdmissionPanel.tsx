import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { Input } from "@/components/ui/input";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkPermitDailyAdmissionDto, WorkPermitDto } from "@/types/dto/workPermits";

interface Props {
  wp: WorkPermitDto;
  onRefresh: () => void;
}

export const DailyAdmissionPanel = ({ wp, onRefresh }: Props) => {
  const [rows, setRows] = useState<WorkPermitDailyAdmissionDto[]>([]);
  const [day, setDay] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    workPermitsApi.listAdmissions(wp.id).then(setRows).catch(() => undefined);
  }, [wp.id]);

  useEffect(() => { load(); }, [load]);

  const canAdmit = wp.status === "issued";

  const handleAdd = async () => {
    if (!day) {
      toast.error("Укажите дату смены");
      return;
    }
    setSaving(true);
    try {
      await workPermitsApi.createAdmission(wp.id, {
        admission_date: day,
        start_at: new Date().toISOString(),
      });
      toast.success("Допуск на смену оформлен");
      setDay("");
      load();
      onRefresh();
    } catch {
      toast.error("Не удалось оформить допуск (наряд должен быть выдан)");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = async (a: WorkPermitDailyAdmissionDto) => {
    try {
      await workPermitsApi.updateAdmission(wp.id, a.id, { end_at: new Date().toISOString() });
      toast.success("Смена закрыта");
      load();
    } catch {
      toast.error("Не удалось закрыть смену");
    }
  };

  return (
    <div className="space-y-2">
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Допусков на смену нет</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {rows.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
              <span>
                {new Date(a.admission_date).toLocaleDateString("ru-RU")}
                {a.start_at ? ` · с ${new Date(a.start_at).toLocaleTimeString("ru-RU")}` : ""}
                {a.end_at ? ` · по ${new Date(a.end_at).toLocaleTimeString("ru-RU")}` : ""}
              </span>
              {!a.end_at && (
                <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
                  <Button size="sm" variant="ghost" onClick={() => void handleClose(a)}>
                    Закрыть смену
                  </Button>
                </Can>
              )}
            </li>
          ))}
        </ul>
      )}

      {canAdmit && (
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <Input type="date" className="w-44" value={day} onChange={(e) => setDay(e.target.value)} />
            <Button size="sm" disabled={saving || !day} onClick={() => void handleAdd()}>
              {saving ? "..." : "Допустить на смену"}
            </Button>
          </div>
        </Can>
      )}
    </div>
  );
};
