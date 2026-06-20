import { useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import {
  CLOSING_MISSING_LABELS,
  SIGN_STATUS_LABELS,
  labelOf,
} from "@/lib/workPermitVocab";
import type { WorkPermitClosingSummaryDto, WorkPermitSignatureDto } from "@/types/dto/workPermits";

interface Props {
  summary: WorkPermitClosingSummaryDto;
  canManage: boolean;
  onClose: () => void;
  onRefresh: () => void;
  nameOf: (personId: string) => string;
  workPermitId?: string;
}

export const ClosingPanel = ({
  summary,
  canManage,
  onClose,
  onRefresh,
  nameOf,
  workPermitId,
}: Props) => {
  const [completionText, setCompletionText] = useState(summary.completion_text ?? "");
  const [savingAct, setSavingAct] = useState(false);
  const [codeInput, setCodeInput] = useState<Record<string, string>>({});

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
      const res = await workPermitsApi.createClosingSignature(workPermitId, personId, mode);
      if (mode === "code" && res.confirm_code) {
        toast.success(`Код для подписанта: ${res.confirm_code}`);
      }
      onRefresh();
    } catch {
      toast.error("Не удалось инициировать подпись");
    }
  };

  const handleConfirm = async (sig: WorkPermitSignatureDto) => {
    const code = (codeInput[sig.id] ?? "").trim();
    if (!code) {
      toast.error("Введите код");
      return;
    }
    try {
      await workPermitsApi.confirmSignatureCode(sig.id, code);
      toast.success("Подпись подтверждена");
      setCodeInput((m) => ({ ...m, [sig.id]: "" }));
      onRefresh();
    } catch {
      toast.error("Код неверный или истёк");
    }
  };

  return (
    <div className="space-y-4">
      {/* Акт окончания работ */}
      <div className="space-y-2">
        <div className="text-sm font-medium">Акт окончания работ</div>
        {summary.completion_text ? (
          <div className="text-sm whitespace-pre-wrap">{summary.completion_text}</div>
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
            <Button size="sm" disabled={savingAct} onClick={() => void handleRecordAct()}>
              {savingAct ? "Сохранение..." : "Оформить акт"}
            </Button>
          </div>
        )}
      </div>

      {/* Подписи закрытия */}
      <div className="space-y-2">
        <div className="text-sm font-medium">Подписи закрытия</div>
        {summary.signatures.length === 0 && (
          <p className="text-sm text-muted-foreground">Подписи ещё не запрошены</p>
        )}
        <ul className="space-y-2 text-sm">
          {summary.signatures.map((sig) => {
            const signed = sig.status === "signed";
            const awaiting = sig.status === "awaiting_code";
            const personLabel = sig.signer_person_id ? nameOf(sig.signer_person_id) : (sig.signer_name ?? "—");
            return (
              <li key={sig.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
                <span className="text-sm">{personLabel}</span>
                <span className="flex items-center gap-2">
                  <span className={signed ? "text-green-600" : "text-muted-foreground"}>
                    {labelOf(SIGN_STATUS_LABELS, sig.status)}
                  </span>
                  {!signed && canManage && (
                    <>
                      {awaiting ? (
                        <>
                          <input
                            aria-label="Код подтверждения"
                            className="h-8 w-24 rounded-md border px-2 text-sm"
                            placeholder="код"
                            value={codeInput[sig.id] ?? ""}
                            onChange={(e) => setCodeInput((m) => ({ ...m, [sig.id]: e.target.value }))}
                          />
                          <Button size="sm" variant="outline" onClick={() => void handleConfirm(sig)}>
                            Подтвердить
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => sig.signer_person_id && void handleSign(sig.signer_person_id, "attested")}
                          >
                            Зафиксировать
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => sig.signer_person_id && void handleSign(sig.signer_person_id, "code")}
                          >
                            Запросить код
                          </Button>
                        </>
                      )}
                    </>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

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
