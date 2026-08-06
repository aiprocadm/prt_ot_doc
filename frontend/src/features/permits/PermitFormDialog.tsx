import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

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
import { permitsApi } from "@/api/permits";
import type { PermitDto } from "@/types/dto/permits";
import type { PersonDto } from "@/types/dto/persons";
import { permitFormSchema, type PermitFormValues } from "@/types/forms/permits";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: PermitFormValues = {
  person_id: "",
  permit_type: "",
  issued_at: "",
  valid_until: "",
};

const PERMIT_API_FIELD_MAP: Record<string, keyof PermitFormValues> = {
  person_id: "person_id",
  permit_type: "permit_type",
  issued_at: "issued_at",
  valid_until: "valid_until",
};

interface PermitFormDialogProps {
  trigger: ReactNode;
  persons: PersonDto[];
  initialData?: PermitDto;
  onSubmitted?: (permit: PermitDto) => void;
}

export const PermitFormDialog = ({
  trigger,
  persons,
  initialData,
  onSubmitted,
}: PermitFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<PermitFormValues>({
    resolver: zodResolver(permitFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        person_id: initialData.person_id,
        permit_type: initialData.permit_type,
        issued_at: initialData.issued_at ?? "",
        valid_until: initialData.valid_until ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: PermitFormValues) => {
    try {
      const result = initialData
        ? await permitsApi.updatePermit(initialData.id, {
            permit_type: values.permit_type,
            valid_until: values.valid_until || undefined,
          })
        : await permitsApi.createPermit({
            person_id: values.person_id,
            permit_type: values.permit_type,
            issued_at: values.issued_at || undefined,
            valid_until: values.valid_until || undefined,
          });
      onSubmitted?.(result);
      toast.success(initialData ? "Допуск обновлён" : "Допуск создан");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, PERMIT_API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить допуск");
      } else {
        toast.error("Не удалось сохранить допуск");
      }
      throw err;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Редактировать допуск" : "Новый допуск"}
          </DialogTitle>
          <DialogDescription>
            Заполните данные личного допуска сотрудника.
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
            <Label htmlFor="person_id">Сотрудник</Label>
            <select
              id="person_id"
              className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
              disabled={isEdit}
              {...form.register("person_id")}
            >
              <option value="">— Выберите сотрудника —</option>
              {persons.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name}
                </option>
              ))}
            </select>
            {form.formState.errors.person_id && (
              <p className="text-xs text-destructive">
                {form.formState.errors.person_id.message}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="permit_type">Тип допуска</Label>
            <Input
              id="permit_type"
              placeholder="напр. Работа на высоте"
              {...form.register("permit_type")}
            />
            {form.formState.errors.permit_type && (
              <p className="text-xs text-destructive">
                {form.formState.errors.permit_type.message}
              </p>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="issued_at">Выдан</Label>
              <Input
                id="issued_at"
                type="date"
                disabled={isEdit}
                {...form.register("issued_at")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="valid_until">Действует до</Label>
              <Input
                id="valid_until"
                type="date"
                {...form.register("valid_until")}
              />
            </div>
          </div>
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
