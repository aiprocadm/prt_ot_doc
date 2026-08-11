import { useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { tenantsApi } from "@/api/tenants";
import { Badge } from "@/components/ui/badge";
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
import type { SubscriptionPlanDto, TenantFleetItem } from "@/types/dto/tenants";

interface TenantPlanDialogProps {
  trigger: ReactNode;
  item: TenantFleetItem;
  plans: SubscriptionPlanDto[];
  onSubmitted?: () => void;
}

const QUOTA_FIELDS: { key: string; label: string; hint: string }[] = [
  {
    key: "max_doc_generations_per_month",
    label: "Документов в месяц",
    hint: "Сколько документов тенант может сгенерировать за месяц",
  },
  {
    key: "max_storage_mb",
    label: "Хранилище, МБ",
    hint: "Лимит места под файлы",
  },
  {
    key: "max_parallel_jobs",
    label: "Параллельных задач",
    hint: "Сколько тяжёлых операций идут одновременно",
  },
  {
    key: "monthly_edo_outgoing",
    label: "Исходящих ЭДО в месяц",
    hint: "0 — без ограничения",
  },
];

/** Manage a tenant's subscription: pick a plan (features + preset limits) or fine-tune limits. */
export const TenantPlanDialog = ({
  trigger,
  item,
  plans,
  onSubmitted,
}: TenantPlanDialogProps) => {
  const [open, setOpen] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(item.plan ?? "");
  const [applying, setApplying] = useState(false);
  const [savingQuotas, setSavingQuotas] = useState(false);
  const [quotas, setQuotas] = useState<Record<string, number>>({});

  useEffect(() => {
    if (open) {
      setSelectedPlan(item.plan ?? "");
      setQuotas({
        max_doc_generations_per_month:
          item.quotas?.max_doc_generations_per_month ?? 0,
        max_storage_mb: item.quotas?.max_storage_mb ?? 0,
        max_parallel_jobs: item.quotas?.max_parallel_jobs ?? 1,
        monthly_edo_outgoing: item.quotas?.monthly_edo_outgoing ?? 0,
      });
    }
  }, [open, item]);

  const preview = useMemo(
    () => plans.find((plan) => plan.code === selectedPlan) ?? null,
    [plans, selectedPlan],
  );

  const applyPlan = async () => {
    if (!preview) return;
    setApplying(true);
    try {
      await tenantsApi.setPlan(item.tenant.id, preview.code);
      toast.success(
        `Тенанту «${item.tenant.name}» назначен тариф «${preview.title}»`,
      );
      onSubmitted?.();
      setOpen(false);
    } catch {
      /* toast is raised by the global error interceptor */
    } finally {
      setApplying(false);
    }
  };

  const saveQuotas = async () => {
    setSavingQuotas(true);
    try {
      await tenantsApi.updateQuotas(item.tenant.id, quotas);
      toast.success(`Лимиты для «${item.tenant.name}» сохранены`);
      onSubmitted?.();
      setOpen(false);
    } catch {
      /* toast is raised by the global error interceptor */
    } finally {
      setSavingQuotas(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Тариф и лимиты — {item.tenant.name}</DialogTitle>
          <DialogDescription>
            Тариф включает набор функций и заранее заданные лимиты. Ниже можно
            донастроить лимиты вручную.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <section className="space-y-2">
            <Label htmlFor="tenant-plan">Тариф</Label>
            <select
              id="tenant-plan"
              className="h-10 w-full rounded-md border px-3"
              value={selectedPlan}
              onChange={(event) => setSelectedPlan(event.target.value)}
            >
              <option value="" disabled>
                Выберите тариф
              </option>
              {plans.map((plan) => (
                <option key={plan.code} value={plan.code}>
                  {plan.title}
                </option>
              ))}
            </select>

            {preview ? (
              <div className="rounded-md border p-3 text-xs space-y-2">
                <p className="font-medium">Функции тарифа «{preview.title}»:</p>
                <div className="flex flex-wrap gap-1">
                  {item.features.map((feature) => {
                    const included = preview.feature_codes.includes(
                      feature.code,
                    );
                    return (
                      <Badge
                        key={feature.code}
                        variant={included ? "default" : "secondary"}
                        className={included ? "" : "opacity-50 line-through"}
                      >
                        {feature.title}
                      </Badge>
                    );
                  })}
                </div>
                <p className="text-muted-foreground">
                  Лимиты: {preview.quotas.max_doc_generations_per_month} док/мес
                  · {preview.quotas.max_storage_mb} МБ ·{" "}
                  {preview.quotas.max_parallel_jobs} задач
                </p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Сейчас у тенанта нестандартный набор функций («Свой набор»).
                Выберите тариф, чтобы привести к одному из наборов.
              </p>
            )}

            <Button
              type="button"
              onClick={() => void applyPlan()}
              disabled={!preview || applying}
            >
              {applying ? "Применение..." : "Применить тариф"}
            </Button>
          </section>

          <section className="space-y-3 border-t pt-4">
            <p className="text-sm font-medium">Точная настройка лимитов</p>
            {QUOTA_FIELDS.map((field) => (
              <div key={field.key} className="space-y-1">
                <Label htmlFor={`quota-${field.key}`}>{field.label}</Label>
                <Input
                  id={`quota-${field.key}`}
                  type="number"
                  min={0}
                  value={quotas[field.key] ?? 0}
                  onChange={(event) =>
                    setQuotas((prev) => ({
                      ...prev,
                      [field.key]: Number(event.target.value),
                    }))
                  }
                />
                <p className="text-xs text-muted-foreground">{field.hint}</p>
              </div>
            ))}
          </section>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => void saveQuotas()}
            disabled={savingQuotas}
          >
            {savingQuotas ? "Сохранение..." : "Сохранить лимиты"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
