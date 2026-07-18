import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

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
import { BUDGET_DOMAIN_LABELS } from "@/pages/budget/budgetVocab";
import type { BudgetArticleCreateInput, BudgetArticleDto, BudgetArticleUpdateInput, BudgetDomain } from "@/types/dto/budget";

const ARTICLE_DOMAINS: BudgetDomain[] = ["training", "medical", "events"];

interface Props {
  trigger: ReactNode;
  initialData?: BudgetArticleDto;
  onSubmitted?: () => void;
}

interface FormState {
  code: string;
  name: string;
  domain: BudgetDomain | "";
  is_active: boolean;
}

const emptyForm: FormState = {
  code: "",
  name: "",
  domain: "",
  is_active: true
};

export const ArticleFormDialog = ({ trigger, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const isEdit = Boolean(initialData);

  useEffect(() => {
    if (!open) return;
    setForm(
      initialData
        ? {
            code: initialData.code,
            name: initialData.name,
            domain: initialData.domain ?? "",
            is_active: initialData.is_active
          }
        : emptyForm
    );
  }, [open, initialData]);

  const onSubmit = async () => {
    // code иммутабелен при редактировании — бэкенд не принимает его в BudgetArticleUpdate,
    // валидируем только при создании.
    if (!isEdit && !form.code.trim()) {
      toast.error("Укажите код статьи");
      return;
    }
    if (!form.name.trim()) {
      toast.error("Укажите название статьи");
      return;
    }
    setSubmitting(true);
    try {
      if (isEdit && initialData) {
        // Только изменённые поля.
        const payload: BudgetArticleUpdateInput = {};
        const trimmedName = form.name.trim();
        if (trimmedName !== initialData.name) payload.name = trimmedName;
        const normalizedDomain = form.domain || null;
        if (normalizedDomain !== initialData.domain) payload.domain = normalizedDomain;
        if (form.is_active !== initialData.is_active) payload.is_active = form.is_active;
        await budgetApi.updateArticle(initialData.id, payload);
        toast.success("Статья обновлена");
      } else {
        const payload: BudgetArticleCreateInput = {
          code: form.code.trim(),
          name: form.name.trim(),
          domain: form.domain || null,
          is_active: form.is_active
        };
        await budgetApi.createArticle(payload);
        toast.success("Статья создана");
      }
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить статью");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать статью" : "Новая статья"}</DialogTitle>
          <DialogDescription>Статья расходов бюджета безопасности — код, название и домен.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="a-code">Код</Label>
            <Input
              id="a-code"
              value={form.code}
              disabled={isEdit}
              onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="a-name">Название</Label>
            <Input
              id="a-name"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="a-domain">Домен</Label>
            <select
              id="a-domain"
              className="h-10 w-full rounded-md border px-3"
              value={form.domain}
              onChange={(e) => setForm((prev) => ({ ...prev, domain: e.target.value as BudgetDomain | "" }))}
            >
              <option value="">Универсальная</option>
              {ARTICLE_DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {BUDGET_DOMAIN_LABELS[d]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input
              id="a-active"
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.checked }))}
            />
            <Label htmlFor="a-active">Активна</Label>
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
