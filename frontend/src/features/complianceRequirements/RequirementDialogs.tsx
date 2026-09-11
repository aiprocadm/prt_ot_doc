import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import {
  complianceRequirementsApi,
  listOwnerOptions,
  type OwnerOptionDto,
} from "@/api/complianceRequirements";
import { listDocumentsForPicker } from "@/api/documents";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type {
  ComplianceRequirementDto,
  RequirementSeverity,
} from "@/types/dto/complianceRequirements";
import type { DocumentDto } from "@/types/dto/documents";
import type { NpaDto } from "@/types/dto/npa";
import { isApiError } from "@/utils/apiFormErrors";

/**
 * Срез-145 (B.18 разд. 19.2): формы реестра требований.
 *
 * Обе формы показываются только ролям записи (`can_manage` из списка):
 * остальным ручка ответит 403, а кнопка, всегда кончающаяся отказом, хуже
 * отсутствующей.
 */

export const SEVERITY_LABELS: Record<RequirementSeverity, string> = {
  low: "низкая",
  medium: "средняя",
  high: "высокая",
  critical: "критическая",
};

const selectClassName =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

const orNull = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

const failureMessage = (error: unknown, fallback: string): string => {
  if (
    isApiError(error) &&
    (error.status === 409 || error.status === 404 || error.status === 422)
  ) {
    return error.message;
  }
  return fallback;
};

interface RequirementFormDialogProps {
  trigger: ReactNode;
  acts: NpaDto[];
  onCreated: () => void;
}

export const RequirementFormDialog = ({
  trigger,
  acts,
  onCreated,
}: RequirementFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [npaId, setNpaId] = useState("");
  const [clauseId, setClauseId] = useState("");
  const [periodicity, setPeriodicity] = useState("");
  const [nextDueAt, setNextDueAt] = useState("");
  const [severity, setSeverity] = useState<RequirementSeverity>("medium");
  const [description, setDescription] = useState("");
  const [roleCode, setRoleCode] = useState("");
  const [processCode, setProcessCode] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [users, setUsers] = useState<OwnerOptionDto[]>([]);

  useEffect(() => {
    if (!open) return;
    void listOwnerOptions().then(setUsers);
  }, [open]);

  const clauses = acts.find((act) => act.id === npaId)?.clauses ?? [];

  const reset = () => {
    setCode("");
    setTitle("");
    setNpaId("");
    setClauseId("");
    setPeriodicity("");
    setNextDueAt("");
    setSeverity("medium");
    setDescription("");
    setRoleCode("");
    setProcessCode("");
    setOwnerId("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await complianceRequirementsApi.create({
        code: code.trim(),
        title: title.trim(),
        npa_id: orNull(npaId),
        clause_id: npaId ? orNull(clauseId) : null,
        periodicity_days: periodicity ? Number(periodicity) : null,
        next_due_at: orNull(nextDueAt),
        severity,
        description: orNull(description),
        role_code: orNull(roleCode),
        process_code: orNull(processCode),
        owner_user_id: orNull(ownerId),
      });
      toast.success("Требование добавлено в реестр");
      setOpen(false);
      reset();
      onCreated();
    } catch (error) {
      toast.error(failureMessage(error, "Не удалось добавить требование"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новое требование</DialogTitle>
          <DialogDescription>
            Что арендатор обязан делать по НПА: как часто, до какой даты и
            насколько серьёзно неисполнение.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="requirement-code">Код</Label>
              <Input
                id="requirement-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="ОТ-12"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="requirement-severity">Серьёзность</Label>
              <select
                id="requirement-severity"
                className={selectClassName}
                value={severity}
                onChange={(event) =>
                  setSeverity(event.target.value as RequirementSeverity)
                }
              >
                {(Object.keys(SEVERITY_LABELS) as RequirementSeverity[]).map(
                  (value) => (
                    <option key={value} value={value}>
                      {SEVERITY_LABELS[value]}
                    </option>
                  ),
                )}
              </select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="requirement-title">Требование</Label>
              <Input
                id="requirement-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Проводить обучение по охране труда"
                required
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="requirement-npa">Нормативный акт</Label>
              <select
                id="requirement-npa"
                className={selectClassName}
                value={npaId}
                onChange={(event) => {
                  setNpaId(event.target.value);
                  setClauseId("");
                }}
              >
                <option value="">— без привязки к акту —</option>
                {acts.map((act) => (
                  <option key={act.id} value={act.id}>
                    {act.code} · {act.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="requirement-periodicity">
                Периодичность, дней
              </Label>
              <Input
                id="requirement-periodicity"
                type="number"
                min={1}
                value={periodicity}
                onChange={(event) => setPeriodicity(event.target.value)}
                placeholder="365 (пусто — разовое)"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="requirement-due">Контрольная дата</Label>
              <Input
                id="requirement-due"
                type="date"
                value={nextDueAt}
                onChange={(event) => setNextDueAt(event.target.value)}
              />
            </div>
          </div>
          <details className="rounded border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Дополнительно
            </summary>
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              {clauses.length > 0 ? (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="requirement-clause">Пункт акта</Label>
                  <select
                    id="requirement-clause"
                    className={selectClassName}
                    value={clauseId}
                    onChange={(event) => setClauseId(event.target.value)}
                  >
                    <option value="">— весь акт —</option>
                    {clauses.map((clause) => (
                      <option key={clause.id} value={clause.id}>
                        {clause.code}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="requirement-owner">Ответственный</Label>
                <select
                  id="requirement-owner"
                  className={selectClassName}
                  value={ownerId}
                  onChange={(event) => setOwnerId(event.target.value)}
                >
                  <option value="">— не назначен —</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.email}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirement-role">Роль</Label>
                <Input
                  id="requirement-role"
                  value={roleCode}
                  onChange={(event) => setRoleCode(event.target.value)}
                  placeholder="ot_specialist"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirement-process">Процесс</Label>
                <Input
                  id="requirement-process"
                  value={processCode}
                  onChange={(event) => setProcessCode(event.target.value)}
                  placeholder="training"
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="requirement-description">Описание</Label>
                <Textarea
                  id="requirement-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                />
              </div>
            </div>
          </details>
          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving ? "Сохранение..." : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

interface RequirementEvidenceDialogProps {
  requirement: ComplianceRequirementDto;
  trigger: ReactNode;
  onConfirmed: () => void;
}

/**
 * «Исполнено»: документ и/или заметка — чем доказано. Сервер сдвинет
 * контрольную дату на период от дня подтверждения, разовое — закроет.
 */
export const RequirementEvidenceDialog = ({
  requirement,
  trigger,
  onConfirmed,
}: RequirementEvidenceDialogProps) => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [documents, setDocuments] = useState<DocumentDto[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [note, setNote] = useState("");
  const [confirmedAt, setConfirmedAt] = useState("");

  useEffect(() => {
    if (!open) return;
    void listDocumentsForPicker()
      .then((items) => setDocuments(items))
      .catch(() => setDocuments([]));
  }, [open]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!documentId && !note.trim()) return;
    setSaving(true);
    try {
      await complianceRequirementsApi.confirm(requirement.id, {
        document_id: orNull(documentId),
        note: orNull(note),
        confirmed_at: orNull(confirmedAt),
      });
      toast.success("Исполнение подтверждено");
      setOpen(false);
      setDocumentId("");
      setNote("");
      setConfirmedAt("");
      onConfirmed();
    } catch (error) {
      toast.error(failureMessage(error, "Не удалось подтвердить исполнение"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Исполнено: {requirement.code}</DialogTitle>
          <DialogDescription>
            {requirement.periodicity_days
              ? `Следующий срок сдвинется на ${requirement.periodicity_days} дн. от дня подтверждения.`
              : "Разовое требование будет закрыто."}
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="space-y-2">
            <Label htmlFor="evidence-document">Документ-доказательство</Label>
            <select
              id="evidence-document"
              className={selectClassName}
              value={documentId}
              onChange={(event) => setDocumentId(event.target.value)}
            >
              <option value="">— без документа —</option>
              {documents.map((document) => (
                <option key={document.id} value={document.id}>
                  {document.name}
                  {document.company?.name ? ` · ${document.company.name}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="evidence-note">Заметка</Label>
            <Textarea
              id="evidence-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Протокол № 7 от 01.03.2026"
              rows={3}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="evidence-date">Дата исполнения</Label>
            <Input
              id="evidence-date"
              type="date"
              value={confirmedAt}
              onChange={(event) => setConfirmedAt(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              type="submit"
              disabled={saving || (!documentId && !note.trim())}
            >
              {saving ? "Сохранение..." : "Подтвердить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
