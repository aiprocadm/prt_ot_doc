import { useEffect, useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { CLOSING_MISSING_LABELS } from "@/lib/workPermitVocab";
import type { WorkPermitClosingSummaryDto } from "@/types/dto/workPermits";
import { SignaturesPanel, type SignerRow } from "./SignaturesPanel";

interface Props {
  summary: WorkPermitClosingSummaryDto;
  signers: SignerRow[];
  canManage: boolean;
  onClose: () => void;
  onRefresh: () => void;
  nameOf: (personId: string) => string;
  workPermitId?: string;
}

export const ClosingPanel = ({
  summary,
  signers,
  canManage,
  onClose,
  onRefresh,
  workPermitId,
}: Props) => {
  const [completionText, setCompletionText] = useState(
    summary.completion_text ?? "",
  );
  const [savingAct, setSavingAct] = useState(false);

  // Текст акта приходит из summary; после onRefresh (или правки другим пользователем) поле
  // должно отражать актуальное значение, иначе редактор показывает устаревший снимок.
  useEffect(() => {
    setCompletionText(summary.completion_text ?? "");
  }, [summary.completion_text]);

  const handleRecordAct = async () => {
    if (!workPermitId) return;
    if (!completionText.trim()) {
      toast.error("Введите текст акта окончания работ");
      return;
    }
    setSavingAct(true);
    try {
      await workPermitsApi.recordCompletion(workPermitId, completionText);
      toast.success("Акт окончания оформлен");
      onRefresh();
    } catch {
      toast.error("Не удалось оформить акт");
    } finally {
      setSavingAct(false);
    }
  };

  const handleSign = async (personId: string, mode: "attested" | "code") => {
    if (!workPermitId) return;
    try {
      const res = await workPermitsApi.createClosingSignature(
        workPermitId,
        personId,
        mode,
      );
      if (mode === "code" && res.confirm_code) {
        toast.success(`Код для подписанта: ${res.confirm_code}`);
      }
      onRefresh();
    } catch {
      toast.error("Не удалось инициировать подпись");
    }
  };

  const handleConfirm = async (requestId: string, code: string) => {
    await workPermitsApi.confirmSignatureCode(requestId, code);
    toast.success("Подпись подтверждена");
    onRefresh();
  };

  return (
    <div className="space-y-4">
      {/* Акт окончания работ */}
      <div className="space-y-2">
        <div className="text-sm font-medium">Акт окончания работ</div>
        {summary.completion_text ? (
          <div className="text-sm whitespace-pre-wrap">
            {summary.completion_text}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Акт не оформлен</p>
        )}
        {canManage && (
          <div className="space-y-2">
            <textarea
              className="min-h-[72px] w-full rounded-md border px-3 py-2 text-sm"
              placeholder="Опишите выполненные работы и состояние рабочего места"
              value={completionText}
              onChange={(e) => setCompletionText(e.target.value)}
            />
            <Button
              size="sm"
              disabled={savingAct}
              onClick={() => void handleRecordAct()}
            >
              {savingAct ? "Сохранение..." : "Оформить акт"}
            </Button>
          </div>
        )}
      </div>

      {/* Подписи закрытия */}
      <SignaturesPanel
        title="Подписи закрытия (сдал / принял)"
        signers={signers}
        signatures={summary.signatures}
        onSign={handleSign}
        onConfirm={handleConfirm}
      />

      {/* Кнопка закрытия + пояснение */}
      <div className="space-y-2 pt-1">
        <Button disabled={!summary.can_close} onClick={onClose}>
          Закрыть наряд
        </Button>
        {!summary.can_close && summary.missing.length > 0 && (
          <ul className="text-sm text-muted-foreground list-disc list-inside space-y-0.5">
            {summary.missing.map((key) => (
              <li key={key}>{CLOSING_MISSING_LABELS[key] ?? key}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};
