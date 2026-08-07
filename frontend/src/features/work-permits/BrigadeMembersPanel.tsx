import { useState } from "react";
import { toast } from "sonner";

import { workPermitsApi, type PersonOption } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkPermitDto } from "@/types/dto/workPermits";

interface Props {
  wp: WorkPermitDto;
  persons: PersonOption[];
  nameOf: (personId: string) => string;
  onRefresh: () => void;
}

export const BrigadeMembersPanel = ({
  wp,
  persons,
  nameOf,
  onRefresh,
}: Props) => {
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [selectedRole, setSelectedRole] = useState("member");
  const [adding, setAdding] = useState(false);

  // Ф3a: состав бригады редактируется и в работе (issued/suspended), не только в черновике
  const canEdit =
    wp.status === "draft" ||
    wp.status === "issued" ||
    wp.status === "suspended";

  const handleAdd = async () => {
    if (!selectedPersonId) {
      toast.error("Выберите сотрудника");
      return;
    }
    setAdding(true);
    try {
      await workPermitsApi.addMember(wp.id, {
        person_id: selectedPersonId,
        role: selectedRole,
      });
      toast.success("Участник добавлен");
      setSelectedPersonId("");
      setSelectedRole("member");
      onRefresh();
    } catch {
      toast.error("Не удалось добавить участника");
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (memberId: string) => {
    try {
      await workPermitsApi.removeMember(wp.id, memberId);
      toast.success("Участник удалён");
      onRefresh();
    } catch {
      toast.error("Не удалось удалить участника");
    }
  };

  return (
    <div className="space-y-2">
      <ul className="space-y-1 text-sm">
        {wp.members.map((m) => (
          <li key={m.id} className="flex items-center justify-between gap-2">
            <span>{nameOf(m.person_id)}</span>
            <span className="text-muted-foreground">
              {labelOf(MEMBER_ROLE_LABELS, m.role)}
            </span>
            {wp.work_type === "electrical" && (
              <span className="text-xs text-muted-foreground">
                Группа: {m.electrical_group ?? "—"}
              </span>
            )}
            {canEdit && (
              <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
                <button
                  type="button"
                  className="text-xs text-destructive hover:underline"
                  onClick={() => void handleRemove(m.id)}
                >
                  Удалить
                </button>
              </Can>
            )}
          </li>
        ))}
        {wp.members.length === 0 && (
          <li className="text-muted-foreground">Бригада не набрана</li>
        )}
      </ul>

      {canEdit && (
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <div className="flex flex-col gap-1">
              <label
                htmlFor="bm-person"
                className="text-xs text-muted-foreground"
              >
                Сотрудник
              </label>
              <select
                id="bm-person"
                className="h-9 rounded-md border px-2 text-sm min-w-[180px]"
                value={selectedPersonId}
                onChange={(e) => setSelectedPersonId(e.target.value)}
              >
                <option value="">— выберите —</option>
                {persons.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label
                htmlFor="bm-role"
                className="text-xs text-muted-foreground"
              >
                Роль
              </label>
              <select
                id="bm-role"
                className="h-9 rounded-md border px-2 text-sm"
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value)}
              >
                {Object.entries(MEMBER_ROLE_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <Button
              type="button"
              size="sm"
              disabled={adding || !selectedPersonId}
              onClick={() => void handleAdd()}
            >
              {adding ? "Добавление..." : "Добавить"}
            </Button>
          </div>
        </Can>
      )}
    </div>
  );
};
