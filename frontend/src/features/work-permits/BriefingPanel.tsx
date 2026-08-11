import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import {
  SignaturesPanel,
  type SignerRow,
} from "@/features/work-permits/SignaturesPanel";
import { MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type {
  WorkPermitBriefingDto,
  WorkPermitDto,
  WorkPermitSignatureDto,
} from "@/types/dto/workPermits";

const BRIEFING_ROLES = new Set(["member", "observer", "foreman"]);

interface Props {
  wp: WorkPermitDto;
  nameOf: (personId: string) => string;
  signatures: WorkPermitSignatureDto[];
  onRefresh: () => void;
}

export const BriefingPanel = ({ wp, nameOf, signatures, onRefresh }: Props) => {
  const [briefing, setBriefing] = useState<WorkPermitBriefingDto | null>(null);
  const [topics, setTopics] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    workPermitsApi
      .getBriefings(wp.id)
      .then((rows) => setBriefing(rows[0] ?? null))
      .catch(() => undefined);
  }, [wp.id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    setSaving(true);
    try {
      await workPermitsApi.createBriefing(wp.id, {
        topics_text: topics || null,
        conducted_at: new Date().toISOString(),
      });
      toast.success("Инструктаж проведён");
      setTopics("");
      load();
    } catch {
      toast.error("Не удалось сохранить инструктаж");
    } finally {
      setSaving(false);
    }
  };

  const briefingSigners: SignerRow[] = wp.members
    .filter((m) => BRIEFING_ROLES.has(m.role))
    .map((m) => ({
      personId: m.person_id,
      name: nameOf(m.person_id),
      roleLabel: labelOf(MEMBER_ROLE_LABELS, m.role),
    }));

  const briefingSignatures = signatures.filter((s) => s.stream === "briefing");

  const handleSign = async (personId: string, mode: "attested" | "code") => {
    if (!briefing) return;
    const res = await workPermitsApi.createBriefingSignature(
      wp.id,
      briefing.id,
      { person_id: personId, mode },
    );
    if (mode === "code" && res.confirm_code) {
      toast.success(`Код для подписанта: ${res.confirm_code}`);
    }
    onRefresh();
  };

  const handleConfirm = async (requestId: string, code: string) => {
    await workPermitsApi.confirmSignatureCode(requestId, code);
    toast.success("Подпись подтверждена");
    onRefresh();
  };

  return (
    <div className="space-y-3">
      {briefing ? (
        <div className="text-sm">
          <div className="text-muted-foreground text-xs">
            Целевой инструктаж проведён
          </div>
          {briefing.conducted_at && (
            <div>{new Date(briefing.conducted_at).toLocaleString("ru-RU")}</div>
          )}
          {briefing.topics_text && (
            <div className="whitespace-pre-wrap">{briefing.topics_text}</div>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Целевой инструктаж не проведён
        </p>
      )}

      {!briefing && (
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="space-y-2">
            <textarea
              className="min-h-[60px] w-full rounded-md border px-3 py-2 text-sm"
              placeholder="Темы инструктажа"
              value={topics}
              onChange={(e) => setTopics(e.target.value)}
            />
            <Button
              size="sm"
              disabled={saving}
              onClick={() => void handleCreate()}
            >
              {saving ? "Сохранение..." : "Провести инструктаж"}
            </Button>
          </div>
        </Can>
      )}

      {briefing && (
        <SignaturesPanel
          title="Ознакомление бригады"
          signers={briefingSigners}
          signatures={briefingSignatures}
          onSign={handleSign}
          onConfirm={handleConfirm}
        />
      )}
    </div>
  );
};
