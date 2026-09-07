import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  CD_FORMATION_KIND_TITLES,
  civilDefenseApi,
  type FormationDto,
} from "@/api/civilDefense";
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
import type { PersonDto } from "@/types/dto/persons";
import {
  cdFormationFormSchema,
  type CdFormationFormValues,
} from "@/types/forms/civilDefense";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: CdFormationFormValues = {
  name: "",
  kind: "nasf",
  purpose: "",
  commander_person_id: "",
  equipment_notes: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof CdFormationFormValues> = {
  name: "name",
  kind: "kind",
  purpose: "purpose",
  commander_person_id: "commander_person_id",
  equipment_notes: "equipment_notes",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface CdFormationFormDialogProps {
  trigger: ReactNode;
  persons: PersonDto[];
  initialData?: FormationDto;
  onSubmitted?: (formation: FormationDto) => void;
}

/**
 * Форма нештатного формирования ГО (разд. 56.1, срез-109).
 *
 * Четыре поля на первом уровне: название, вид, предназначение и командир;
 * оснащение и заметки — под «Дополнительно».
 *
 * ГРАНИЦА: платформа не решает, сколько формирований нужно организации и
 * достаточен ли их штат — это определяют категория по ГО и орган управления
 * ГОЧС. Командир необязателен: формирование заводят до приказа о назначении,
 * и «без командира» отдельно видно в сводке.
 */
export const CdFormationFormDialog = ({
  trigger,
  persons,
  initialData,
  onSubmitted,
}: CdFormationFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<CdFormationFormValues>({
    resolver: zodResolver(cdFormationFormSchema),
    defaultValues: emptyForm,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        name: initialData.name,
        kind: initialData.kind,
        purpose: initialData.purpose ?? "",
        commander_person_id: initialData.commander_person_id ?? "",
        equipment_notes: initialData.equipment_notes ?? "",
        notes: initialData.notes ?? "",
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: CdFormationFormValues) => {
    const body = {
      name: values.name.trim(),
      kind: values.kind,
      purpose: orNull(values.purpose),
      commander_person_id: orNull(values.commander_person_id),
      equipment_notes: orNull(values.equipment_notes),
      notes: orNull(values.notes),
    };
    try {
      const result = initialData
        ? await civilDefenseApi.updateFormation(initialData.id, body)
        : await civilDefenseApi.createFormation(body);
      onSubmitted?.(result);
      toast.success(
        isEdit ? "Формирование обновлено" : "Формирование заведено",
      );
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить формирование");
      } else {
        toast.error("Не удалось сохранить формирование");
      }
      throw err;
    }
  };

  const fieldError = (name: keyof CdFormationFormValues) => {
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
            {isEdit ? "Изменить формирование" : "Завести формирование"}
          </DialogTitle>
          <DialogDescription>
            Сколько формирований нужно организации и каков их штат, определяют
            категория по ГО и орган управления ГОЧС — платформа этого не решает.
            Командира можно назначить позже: приказ обычно выходит отдельно.
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
              <Label htmlFor="cd-formation-name">Формирование</Label>
              <Input
                id="cd-formation-name"
                placeholder="напр. Звено пожаротушения"
                {...form.register("name")}
              />
              {fieldError("name")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="cd-formation-kind">Вид</Label>
              <select
                id="cd-formation-kind"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("kind")}
              >
                {Object.entries(CD_FORMATION_KIND_TITLES).map(
                  ([code, title]) => (
                    <option key={code} value={code}>
                      {title}
                    </option>
                  ),
                )}
              </select>
              {fieldError("kind")}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cd-formation-purpose">Предназначение</Label>
            <Input
              id="cd-formation-purpose"
              placeholder="какие задачи выполняет"
              {...form.register("purpose")}
            />
            {fieldError("purpose")}
          </div>
          <div className="space-y-2">
            <Label htmlFor="cd-formation-commander">Командир</Label>
            <select
              id="cd-formation-commander"
              className="h-10 w-full rounded-md border px-3"
              title="Пусто — командир ещё не назначен приказом"
              {...form.register("commander_person_id")}
            >
              <option value="">— Не назначен —</option>
              {persons.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                </option>
              ))}
            </select>
            {fieldError("commander_person_id")}
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Оснащение и заметки
            </summary>
            <div className="mt-3 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="cd-formation-equipment">Оснащение</Label>
                <Textarea
                  id="cd-formation-equipment"
                  rows={3}
                  placeholder="средства защиты, техника, имущество"
                  {...form.register("equipment_notes")}
                />
                {fieldError("equipment_notes")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd-formation-notes">Заметки</Label>
                <Textarea
                  id="cd-formation-notes"
                  rows={3}
                  placeholder="реквизиты приказа, особенности"
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
