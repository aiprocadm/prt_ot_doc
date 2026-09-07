import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  OPO_WORK_KIND_TITLES,
  OPO_WORK_RESULT_TITLES,
  industrialSafetyApi,
  type DeviceWorkDto,
  type TechnicalDeviceDto,
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
  opoDeviceWorkFormSchema,
  type OpoDeviceWorkFormValues,
} from "@/types/forms/industrialSafety";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: OpoDeviceWorkFormValues = {
  device_id: "",
  kind: "diagnostics",
  performed_on: "",
  result: "passed",
  conclusion_number: "",
  performer: "",
  next_due: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof OpoDeviceWorkFormValues> = {
  device_id: "device_id",
  kind: "kind",
  performed_on: "performed_on",
  result: "result",
  conclusion_number: "conclusion_number",
  performer: "performer",
  next_due: "next_due",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface OpoDeviceWorkFormDialogProps {
  trigger: ReactNode;
  devices: TechnicalDeviceDto[];
  presetDeviceId?: string;
  onSubmitted?: (record: DeviceWorkDto) => void;
}

/**
 * Форма работы по техническому устройству (разд. 54.2, срез-105).
 *
 * Пять полей на первом уровне: устройство, вид работы, дата, результат и номер
 * заключения; исполнитель, следующий срок и заметки — под «Дополнительно».
 *
 * ГРАНИЦЫ: срок эксплуатации продлевает ТОЛЬКО положительная экспертиза — если
 * бы его двигала любая работа, «протёрли и записали ТО» продлевало бы жизнь
 * устройству на бумаге. У экспертизы обязателен номер заключения: именно он
 * вносится в реестр Ростехнадзора (правило сервера, форма показывает его до
 * запроса). Записи только добавляются: работа — свидетельство, а не черновик.
 */
export const OpoDeviceWorkFormDialog = ({
  trigger,
  devices,
  presetDeviceId,
  onSubmitted,
}: OpoDeviceWorkFormDialogProps) => {
  const [open, setOpen] = useState(false);

  const form = useForm<OpoDeviceWorkFormValues>({
    resolver: zodResolver(opoDeviceWorkFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    form.reset({ ...emptyForm, device_id: presetDeviceId ?? "" });
  }, [open, presetDeviceId, form]);

  const onSubmit = async (values: OpoDeviceWorkFormValues) => {
    try {
      const result = await industrialSafetyApi.recordDeviceWork({
        device_id: values.device_id,
        kind: values.kind,
        performed_on: values.performed_on,
        result: values.result,
        conclusion_number: orNull(values.conclusion_number),
        performer: orNull(values.performer),
        next_due: orNull(values.next_due),
        notes: orNull(values.notes),
      });
      onSubmitted?.(result);
      toast.success("Работа записана");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось записать работу");
      } else {
        toast.error("Не удалось записать работу");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof OpoDeviceWorkFormValues) => {
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
          <DialogTitle>Записать работу по устройству</DialogTitle>
          <DialogDescription>
            Срок эксплуатации продлевает только положительная экспертиза
            промышленной безопасности: техническое обслуживание и ремонт срок не
            двигают. Для экспертизы обязателен номер заключения.
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
          <div className="space-y-2">
            <Label htmlFor="opo-work-device">Устройство</Label>
            <select
              id="opo-work-device"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("device_id")}
            >
              <option value="">— Выберите устройство —</option>
              {devices.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                  {device.serial_number ? ` · ${device.serial_number}` : ""}
                </option>
              ))}
            </select>
            {fieldError("device_id")}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="opo-work-kind">Вид работы</Label>
              <select
                id="opo-work-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(OPO_WORK_KIND_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("kind")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-work-date">Дата работы</Label>
              <Input
                id="opo-work-date"
                type="date"
                title="Дата в будущем — это план, а не свидетельство"
                {...form.register("performed_on")}
              />
              {fieldError("performed_on")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="opo-work-result">Результат</Label>
              <select
                id="opo-work-result"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("result")}
              >
                {Object.entries(OPO_WORK_RESULT_TITLES).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </select>
              {fieldError("result")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="opo-work-conclusion">Номер заключения</Label>
              <Input
                id="opo-work-conclusion"
                placeholder="обязателен для экспертизы"
                {...form.register("conclusion_number")}
              />
              {fieldError("conclusion_number")}
            </div>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Исполнитель, следующий срок и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="opo-work-performer">Исполнитель</Label>
                  <Input
                    id="opo-work-performer"
                    placeholder="экспертная организация, подрядчик"
                    {...form.register("performer")}
                  />
                  {fieldError("performer")}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="opo-work-next">Следующий срок</Label>
                  <Input
                    id="opo-work-next"
                    type="date"
                    title="Пусто — срок перенесёт система, но только по положительной экспертизе"
                    {...form.register("next_due")}
                  />
                  {fieldError("next_due")}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="opo-work-notes">Заметки</Label>
                <Textarea
                  id="opo-work-notes"
                  rows={3}
                  placeholder="условия заключения, выявленные замечания"
                  {...form.register("notes")}
                />
                {fieldError("notes")}
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
