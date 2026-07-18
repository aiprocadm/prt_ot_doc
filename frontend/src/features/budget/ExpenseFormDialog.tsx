import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { analyticsApi } from "@/api/analyticsApi";
import { budgetApi } from "@/api/budget";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { BUDGET_DOMAIN_LABELS } from "@/pages/budget/budgetVocab";
import type { DirectoryItemDto } from "@/types/dto/analytics";
import type {
  BudgetArticlePageDto,
  BudgetDomain,
  BudgetExpenseCreateInput,
  BudgetExpenseDto,
  BudgetExpenseUpdateInput
} from "@/types/dto/budget";

const EXPENSE_DOMAINS: BudgetDomain[] = ["training", "medical", "events"];

/**
 * entity_type бэкенда для «Связать с записью» выводится из выбранного домена расхода —
 * пользователь задаёт только entity_id, тип не редактируется (см. §12.4 срез-1: оба поля
 * или ни одного, backend отклоняет 422 invalid_entity_link при несоответствии).
 */
const ENTITY_TYPE_BY_DOMAIN: Record<BudgetDomain, string> = {
  training: "training_session",
  medical: "medical_exam",
  events: "corrective_action"
};

interface Props {
  trigger: ReactNode;
  initialData?: BudgetExpenseDto;
  articles: BudgetArticlePageDto;
  onSubmitted?: () => void;
}

interface FormState {
  domain: BudgetDomain;
  article_id: string;
  title: string;
  occurred_on: string;
  amount: string;
  company_id: string;
  branch_id: string;
  site_id: string;
  notes: string;
  linkEntity: boolean;
  entity_id: string;
}

const emptyForm: FormState = {
  domain: "training",
  article_id: "",
  title: "",
  occurred_on: "",
  amount: "",
  company_id: "",
  branch_id: "",
  site_id: "",
  notes: "",
  linkEntity: false,
  entity_id: ""
};

export const ExpenseFormDialog = ({ trigger, initialData, articles, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const isEdit = Boolean(initialData);

  // Справочники — опциональные пикеры, деградируют молча при 403/ошибке (как у
  // ManagementDashboardPage): компании/объекты уже есть в analyticsApi, филиалы — через
  // budgetApi.listBranchesLite (см. комментарий в api/budget.ts).
  const [companies, setCompanies] = useState<DirectoryItemDto[]>([]);
  const [companiesAvailable, setCompaniesAvailable] = useState(true);
  const [branches, setBranches] = useState<DirectoryItemDto[]>([]);
  const [branchesAvailable, setBranchesAvailable] = useState(true);
  const [sites, setSites] = useState<DirectoryItemDto[]>([]);
  const [sitesAvailable, setSitesAvailable] = useState(true);

  useEffect(() => {
    if (!open) return;
    setForm(
      initialData
        ? {
            domain: initialData.domain,
            article_id: initialData.article_id ?? "",
            title: initialData.title,
            occurred_on: initialData.occurred_on,
            amount: String(initialData.amount),
            company_id: initialData.company_id ?? "",
            branch_id: initialData.branch_id ?? "",
            site_id: initialData.site_id ?? "",
            notes: initialData.notes ?? "",
            linkEntity: Boolean(initialData.entity_type && initialData.entity_id),
            entity_id: initialData.entity_id ?? ""
          }
        : emptyForm
    );
  }, [open, initialData]);

  useEffect(() => {
    if (!open) return;
    analyticsApi
      .getCompanies()
      .then((page) => setCompanies(page.items ?? []))
      .catch(() => setCompaniesAvailable(false));
    analyticsApi
      .getSites()
      .then((page) => setSites(page.items ?? []))
      .catch(() => setSitesAvailable(false));
    budgetApi
      .listBranchesLite()
      .then((page) => setBranches(page.items ?? []))
      .catch(() => setBranchesAvailable(false));
  }, [open]);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  // Статья должна соответствовать домену и быть активной — иначе бэкенд отклонит 422
  // article_domain_mismatch/article_inactive. Универсальные статьи (domain=null) подходят
  // любому домену.
  const availableArticles = articles.items.filter(
    (a) => a.is_active && (a.domain === null || a.domain === form.domain)
  );

  const onDomainChange = (nextDomain: BudgetDomain) => {
    setForm((prev) => {
      const articleStillValid = articles.items.some(
        (a) => a.id === prev.article_id && a.is_active && (a.domain === null || a.domain === nextDomain)
      );
      return { ...prev, domain: nextDomain, article_id: articleStillValid ? prev.article_id : "" };
    });
  };

  const onSubmit = async () => {
    if (!form.title.trim()) {
      toast.error("Укажите название расхода");
      return;
    }
    if (!form.occurred_on) {
      toast.error("Укажите дату расхода");
      return;
    }
    if (!isEdit && form.amount.trim() === "") {
      toast.error("Укажите сумму расхода");
      return;
    }
    if (form.amount.trim() !== "" && Number(form.amount) <= 0) {
      toast.error("Сумма должна быть больше нуля");
      return;
    }
    if (form.linkEntity && !form.entity_id.trim()) {
      toast.error("Укажите идентификатор связанной записи");
      return;
    }
    setSubmitting(true);
    try {
      if (isEdit && initialData) {
        // Только изменённые поля: domain иммутабелен при редактировании (не отправляем).
        const payload: BudgetExpenseUpdateInput = {};
        const trimmedTitle = form.title.trim();
        if (trimmedTitle !== initialData.title) payload.title = trimmedTitle;
        if (form.occurred_on !== initialData.occurred_on) payload.occurred_on = form.occurred_on;
        if (form.amount.trim() !== "" && Number(form.amount) !== initialData.amount) {
          payload.amount = Number(form.amount);
        }
        const normalizedArticle = form.article_id || null;
        if (normalizedArticle !== initialData.article_id) payload.article_id = normalizedArticle;
        const normalizedCompany = form.company_id || null;
        if (normalizedCompany !== initialData.company_id) payload.company_id = normalizedCompany;
        const normalizedBranch = form.branch_id || null;
        if (normalizedBranch !== initialData.branch_id) payload.branch_id = normalizedBranch;
        const normalizedSite = form.site_id || null;
        if (normalizedSite !== initialData.site_id) payload.site_id = normalizedSite;
        const normalizedNotes = form.notes.trim() || null;
        if (normalizedNotes !== initialData.notes) payload.notes = normalizedNotes;

        const nextEntityType = form.linkEntity ? ENTITY_TYPE_BY_DOMAIN[form.domain] : null;
        const nextEntityId = form.linkEntity ? form.entity_id.trim() : null;
        if (nextEntityType !== initialData.entity_type) payload.entity_type = nextEntityType;
        if (nextEntityId !== initialData.entity_id) payload.entity_id = nextEntityId;

        await budgetApi.updateExpense(initialData.id, payload);
        toast.success("Расход обновлён");
      } else {
        const payload: BudgetExpenseCreateInput = {
          domain: form.domain,
          title: form.title.trim(),
          occurred_on: form.occurred_on,
          amount: Number(form.amount),
          article_id: form.article_id || null,
          company_id: form.company_id || null,
          branch_id: form.branch_id || null,
          site_id: form.site_id || null,
          notes: form.notes.trim() || null
        };
        // Both-or-neither: entity_type/entity_id либо оба, либо ни одного — иначе бэкенд
        // отклонит 422 invalid_entity_link.
        if (form.linkEntity) {
          payload.entity_type = ENTITY_TYPE_BY_DOMAIN[form.domain];
          payload.entity_id = form.entity_id.trim();
        }
        await budgetApi.createExpense(payload);
        toast.success("Расход создан");
      }
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить расход");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать расход" : "Новый расход"}</DialogTitle>
          <DialogDescription>Расход по бюджету безопасности — сумма, дата и привязка к статье.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="e-domain">Домен</Label>
            <select
              id="e-domain"
              className="h-10 w-full rounded-md border px-3"
              value={form.domain}
              disabled={isEdit}
              onChange={(e) => onDomainChange(e.target.value as BudgetDomain)}
            >
              {EXPENSE_DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {BUDGET_DOMAIN_LABELS[d]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="e-article">Статья</Label>
            <select
              id="e-article"
              className="h-10 w-full rounded-md border px-3"
              value={form.article_id}
              onChange={(e) => setField("article_id", e.target.value)}
            >
              <option value="">— без статьи —</option>
              {availableArticles.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="e-title">Название</Label>
            <Input id="e-title" value={form.title} onChange={(e) => setField("title", e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="e-date">Дата</Label>
              <Input
                id="e-date"
                type="date"
                value={form.occurred_on}
                onChange={(e) => setField("occurred_on", e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="e-amount">Сумма</Label>
              <Input
                id="e-amount"
                type="number"
                value={form.amount}
                onChange={(e) => setField("amount", e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {companiesAvailable ? (
              <div className="space-y-2">
                <Label htmlFor="e-company">Компания</Label>
                <select
                  id="e-company"
                  className="h-10 w-full rounded-md border px-3"
                  value={form.company_id}
                  onChange={(e) => setField("company_id", e.target.value)}
                >
                  <option value="">— не указана —</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            {branchesAvailable ? (
              <div className="space-y-2">
                <Label htmlFor="e-branch">Филиал</Label>
                <select
                  id="e-branch"
                  className="h-10 w-full rounded-md border px-3"
                  value={form.branch_id}
                  onChange={(e) => setField("branch_id", e.target.value)}
                >
                  <option value="">— не указан —</option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            {sitesAvailable ? (
              <div className="space-y-2">
                <Label htmlFor="e-site">Объект</Label>
                <select
                  id="e-site"
                  className="h-10 w-full rounded-md border px-3"
                  value={form.site_id}
                  onChange={(e) => setField("site_id", e.target.value)}
                >
                  <option value="">— не указан —</option>
                  {sites.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="e-notes">Заметки</Label>
            <Textarea id="e-notes" value={form.notes} onChange={(e) => setField("notes", e.target.value)} />
          </div>

          <div className="space-y-3 rounded-md border p-3">
            <div className="flex items-center gap-2">
              <input
                id="e-link-entity"
                type="checkbox"
                checked={form.linkEntity}
                onChange={(e) => setField("linkEntity", e.target.checked)}
              />
              <Label htmlFor="e-link-entity">Связать с записью</Label>
            </div>
            {form.linkEntity ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="e-entity-type">Тип записи</Label>
                  <Input id="e-entity-type" value={ENTITY_TYPE_BY_DOMAIN[form.domain]} readOnly disabled />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="e-entity-id">ID записи</Label>
                  <Input
                    id="e-entity-id"
                    value={form.entity_id}
                    onChange={(e) => setField("entity_id", e.target.value)}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
