import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  PC_MEASURE_SECTION_TITLES,
  PC_MEASURE_WRITABLE_STATUS_TITLES,
  industrialSafetyApi,
  type PcMeasureDto,
  type PcPlanDto,
} from "@/api/industrialSafety";
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
import {
  pcMeasureFormSchema,
  type PcMeasureFormValues,
} from "@/types/forms/industrialSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: PcMeasureFormValues = {
  plan_id: "",
  section: "inspections",
  title: "",
  due_on: "",
  status: "planned",
  responsible: "",
  completed_on: "",
  result: "",
};

const API_FIELD_MAP: Record<string, keyof PcMeasureFormValues> = {
  plan_id: "plan_id",
  section: "section",
  title: "title",
  due_on: "due_on",
  status: "status",
  responsible: "responsible",
  completed_on: "completed_on",
  result: "result",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface PcMeasureFormDialogProps {
  trigger: ReactNode;
  plans: PcPlanDto[];
  initialData?: PcMeasureDto;
  onSubmitted?: (measure: PcMeasureDto) => void;
}

/**
 * Форма мероприятия плана ПК (разд. 54.2, срез-106).
 *
 * Пять полей на первом уровне: план, раздел, мероприятие, срок и состояние;
 * ответственный, дата выполнения и результат — под «Дополнительно».
 *
 * ГРАНИЦЫ: «Просрочено» в списке состояний НЕТ — это вычисляемое состояние,
 * срок наступает сам, без решения человека (словарь формы копирует
 * `PC_MEASURE_WRITABLE_STATUSES`). У выполненного мероприятия обязательна дата
 * выполнения: именно она предъявляется надзору как доказательство исполнения
 * плана (правило сервера, форма показывает его до запроса).
 */
export const PcMeasureFormDialog = ({
  trigger,
  plans,
  initialData,
  onSubmitted,
}: PcMeasureFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<PcMeasureFormValues>({
    resolver: zodResolver(pcMeasureFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        plan_id: initialData.plan_id,
        section: initialData.section,
        title: initialData.title,
        due_on: initialData.due_on,
        // «Просрочено» руками не ставится: для правки показываем «запланировано».
        status:
          initialData.status === "overdue" ? "planned" : initialData.status,
        responsible: initialData.responsible ?? "",
        completed_on: initialData.completed_on ?? "",
        result: initialData.result ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: PcMeasureFormValues) => {
    const body = {
      plan_id: values.plan_id,
      section: values.section,
      title: values.title.trim(),
      due_on: values.due_on,
      status: values.status,
      responsible: orNull(values.responsible),
      completed_on: orNull(values.completed_on),
      result: orNull(values.result),
    };
    try {
      const result = initialData
        ? await industrialSafetyApi.updatePcMeasure(initialData.id, body)
        : await industrialSafetyApi.createPcMeasure(body);
      onSubmitted?.(result);
      toast.success(
        isEdit ? "Мероприятие обновлено" : "Мероприятие запланировано",
      );
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить мероприятие");
      } else {
        toast.error("Не удалось сохранить мероприятие");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof PcMeasureFormValues) => {
    const message = form.formState.errors[name]?.message;
    return message ? (
      <p className="text-xs text-destructive">{message}</p>
    ) : null;
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Изменить мероприятие" : "Запланировать мероприятие"}
          </DialogTitle>
          <DialogDescription>
            Мероприятие живёт в разделе плана ПК. «Просрочено» не выбирается:
            срок наступает сам. У выполненного нужна дата выполнения — именно
            она предъявляется надзору.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
            } catch {
              /* toast уже показан в onSubmit */
            }
          })}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="pc-measure-plan">План ПК</Label>
              <select
                id="pc-measure-plan"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("plan_id")}
              >
                <option value="">— Выберите план —</option>
                {plans.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.year} · {plan.title}
                  </option>
                ))}
              </select>
              {fieldError("plan_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="pc-measure-section">Раздел плана</Label>
              <select
                id="pc-measure-section"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("section")}
              >
                {Object.entries(PC_MEASURE_SECTION_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("section")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="pc-measure-title">Мероприятие</Label>
            <Input
              id="pc-measure-title"
              placeholder="напр. Обследование состояния зданий и сооружений"
              {...form.register("title")}
            />
            {fieldError("title")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="pc-measure-due">Срок</Label>
              <Input
                id="pc-measure-due"
                type="date"
                {...form.register("due_on")}
              />
              {fieldError("due_on")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="pc-measure-status">Состояние</Label>
              <select
                id="pc-measure-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                {Object.entries(PC_MEASURE_WRITABLE_STATUS_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("status")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Ответственный, выполнение и результат
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="pc-measure-responsible">Ответственный</Label>
                  <Input
                    id="pc-measure-responsible"
                    placeholder="кто выполняет"
                    {...form.register("responsible")}
                  />
                  {fieldError("responsible")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pc-measure-completed">Выполнено</Label>
                  <Input
                    id="pc-measure-completed"
                    type="date"
                    {...form.register("completed_on")}
                  />
                  {fieldError("completed_on")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="pc-measure-result">Результат</Label>
                <Textarea
                  id="pc-measure-result"
                  rows={3}
                  placeholder="что сделано, какие выявлены отклонения"
                  {...form.register("result")}
                />
                {fieldError("result")}
              </div>
            </div>
          </details>
          <DialogFooter>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
