import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { complianceRequirementsApi } from "@/api/complianceRequirements";
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
  ComplianceRequirementOptionsDto,
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
 *
 * Срез-147: ответственный, площадка и роль ВЫБИРАЮТСЯ из справочника формы
 * (`/compliance/requirements/options`), а не впечатываются кодом; та же форма
 * с `initialData` правит требование (PATCH) — код остаётся ключом и не меняется.
 */

export const SEVERITY_LABELS: Record<RequirementSeverity, string> = {
  low: "низкая",
  medium: "средняя",
  high: "высокая",
  critical: "критическая",
};

const selectClassName =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

const EMPTY_OPTIONS: ComplianceRequirementOptionsDto = {
  owners: [],
  sites: [],
  roles: [],
  processes: [],
};

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
  /** Есть — форма правит это требование; нет — заводит новое. */
  initialData?: ComplianceRequirementDto;
  onSaved: () => void;
}

export const RequirementFormDialog = ({
  trigger,
  acts,
  initialData,
  onSaved,
}: RequirementFormDialogProps) => {
  const isEdit = Boolean(initialData);
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
  const [siteId, setSiteId] = useState("");
  const [processCode, setProcessCode] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [options, setOptions] =
    useState<ComplianceRequirementOptionsDto>(EMPTY_OPTIONS);

  useEffect(() => {
    if (!open) return;
    // Справочник перечитывается при каждом открытии: людей и площадки заводят
    // между открытиями формы, а устаревший список — это «нет такого человека».
    void complianceRequirementsApi
      .options()
      .then(setOptions)
      .catch(() => setOptions(EMPTY_OPTIONS));
  }, [open]);

  // Поля берутся из требования при правке и пустые при создании; при каждом
  // открытии заново — чтобы брошенная на середине правка не переехала в
  // следующую строку.
  const fill = useCallback((data?: ComplianceRequirementDto) => {
    setCode(data?.code ?? "");
    setTitle(data?.title ?? "");
    setNpaId(data?.npa_id ?? "");
    setClauseId(data?.clause_id ?? "");
    setPeriodicity(
      data?.periodicity_days != null ? String(data.periodicity_days) : "",
    );
    setNextDueAt(data?.next_due_at ?? "");
    setSeverity(data?.severity ?? "medium");
    setDescription(data?.description ?? "");
    setRoleCode(data?.role_code ?? "");
    setSiteId(data?.site_id ?? "");
    setProcessCode(data?.process_code ?? "");
    setOwnerId(data?.owner_user_id ?? "");
  }, []);

  useEffect(() => {
    if (!open) return;
    fill(initialData);
  }, [open, initialData, fill]);

  const clauses = acts.find((act) => act.id === npaId)?.clauses ?? [];
  // Ответственный, роль или площадка, которых в справочнике уже нет (уволен,
  // снесена): показываем то, что записано, чтобы правка не стирала их молча.
  const ownerMissing =
    ownerId && !options.owners.some((owner) => owner.id === ownerId);
  const siteMissing =
    siteId && !options.sites.some((site) => site.id === siteId);
  const roleMissing =
    roleCode && !options.roles.some((role) => role.code === roleCode);
  // Срез-196: до него процесс был свободной строкой. У требований, заведённых
  // раньше, в поле лежит текст — показываем его, а не стираем молча.
  const processMissing =
    processCode && !options.processes.some((item) => item.code === processCode);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    const fields = {
      title: title.trim(),
      npa_id: orNull(npaId),
      clause_id: npaId ? orNull(clauseId) : null,
      periodicity_days: periodicity ? Number(periodicity) : null,
      next_due_at: orNull(nextDueAt),
      severity,
      description: orNull(description),
      role_code: orNull(roleCode),
      site_id: orNull(siteId),
      process_code: orNull(processCode),
      owner_user_id: orNull(ownerId),
    };
    try {
      if (initialData) {
        await complianceRequirementsApi.update(initialData.id, fields);
        toast.success("Требование обновлено");
      } else {
        await complianceRequirementsApi.create({
          code: code.trim(),
          ...fields,
        });
        toast.success("Требование добавлено в реестр");
      }
      setOpen(false);
      fill(undefined);
      onSaved();
    } catch (error) {
      toast.error(
        failureMessage(
          error,
          isEdit
            ? "Не удалось сохранить требование"
            : "Не удалось добавить требование",
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit
              ? `Изменить требование ${initialData?.code}`
              : "Новое требование"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Код не меняется — на него ссылаются доказательства и импорт. Статус меняют «Исполнено» и «Снять с контроля»."
              : "Что арендатор обязан делать по НПА: как часто, до какой даты и насколько серьёзно неисполнение."}
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
                readOnly={isEdit}
                aria-readonly={isEdit || undefined}
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
                  {ownerMissing ? (
                    <option value={ownerId}>
                      {initialData?.owner_name ?? "назначенный ранее"} (нет в
                      списке)
                    </option>
                  ) : null}
                  {options.owners.map((owner) => (
                    <option key={owner.id} value={owner.id}>
                      {owner.name} · {owner.role_label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirement-site">Площадка</Label>
                <select
                  id="requirement-site"
                  className={selectClassName}
                  value={siteId}
                  onChange={(event) => setSiteId(event.target.value)}
                >
                  <option value="">— весь арендатор —</option>
                  {siteMissing ? (
                    <option value={siteId}>
                      {initialData?.site_name ?? "выбранная ранее"} (нет в
                      списке)
                    </option>
                  ) : null}
                  {options.sites.map((site) => (
                    <option key={site.id} value={site.id}>
                      {site.name} · {site.company_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirement-role">Роль</Label>
                <select
                  id="requirement-role"
                  className={selectClassName}
                  value={roleCode}
                  onChange={(event) => setRoleCode(event.target.value)}
                >
                  <option value="">— любая роль —</option>
                  {roleMissing ? (
                    <option value={roleCode}>
                      {initialData?.role_label ?? roleCode}
                    </option>
                  ) : null}
                  {options.roles.map((role) => (
                    <option key={role.code} value={role.code}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirement-process">Процесс</Label>
                <select
                  id="requirement-process"
                  className={selectClassName}
                  value={processCode}
                  onChange={(event) => setProcessCode(event.target.value)}
                >
                  <option value="">— не указан —</option>
                  {processMissing ? (
                    <option value={processCode}>
                      {initialData?.process_label ?? processCode} (нет в списке)
                    </option>
                  ) : null}
                  {options.processes.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
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
              {saving ? "Сохранение..." : isEdit ? "Сохранить" : "Добавить"}
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
