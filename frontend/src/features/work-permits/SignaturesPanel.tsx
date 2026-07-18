import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { SIGN_STATUS_LABELS, labelOf } from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkPermitSignatureDto } from "@/types/dto/workPermits";

export interface SignerRow {
  personId: string;
  name: string;
  roleLabel: string;
}

interface Props {
  title: string;
  signers: SignerRow[];
  signatures: WorkPermitSignatureDto[];
  onSign: (personId: string, mode: "attested" | "code") => Promise<void>;
  onConfirm: (requestId: string, code: string) => Promise<void>;
}

export const SignaturesPanel = ({ title, signers, signatures, onSign, onConfirm }: Props) => {
  const [codeInput, setCodeInput] = useState<Record<string, string>>({});

  // latest signature per person
  const sigByPerson = new Map<string, WorkPermitSignatureDto>();
  for (const s of signatures) {
    if (s.signer_person_id) sigByPerson.set(s.signer_person_id, s);
  }

  const handleSign = async (personId: string, mode: "attested" | "code") => {
    try {
      await onSign(personId, mode);
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
      await onConfirm(sig.id, code);
      setCodeInput((m) => ({ ...m, [sig.id]: "" }));
    } catch {
      toast.error("Код неверный или истёк");
    }
  };

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{title}</div>
      {signers.length === 0 && <p className="text-sm text-muted-foreground">Подписанты не назначены</p>}
      <ul className="space-y-2 text-sm">
        {signers.map((row) => {
          const sig = sigByPerson.get(row.personId);
          const signed = sig?.status === "signed";
          const awaiting = sig?.status === "awaiting_code";
          return (
            <li key={row.personId} className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
              <span>
                {row.name} <span className="text-muted-foreground">· {row.roleLabel}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className={signed ? "text-green-600" : "text-muted-foreground"}>
                  {sig ? labelOf(SIGN_STATUS_LABELS, sig.status) : "Не подписан"}
                </span>
                {!signed && (
                  <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
                    {awaiting && sig ? (
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
                        <Button size="sm" variant="outline" onClick={() => void handleSign(row.personId, "attested")}>
                          Зафиксировать
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void handleSign(row.personId, "code")}>
                          Запросить код
                        </Button>
                      </>
                    )}
                  </Can>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
