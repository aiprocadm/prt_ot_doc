import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import {
  civilDefenseApi,
  type FormationDto,
  type FormationMemberDto,
} from "@/api/civilDefense";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PersonDto } from "@/types/dto/persons";
import {
  cdFormationMemberFormSchema,
  type CdFormationMemberFormValues,
} from "@/types/forms/civilDefense";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";
import { formatDate } from "@/utils/datetime";

const emptyForm: CdFormationMemberFormValues = {
  person_id: "",
  role_in_formation: "",
  assigned_on: "",
  released_on: "",
  notes: "",
};

const API_FIELD_MAP: Record<string, keyof CdFormationMemberFormValues> = {
  person_id: "person_id",
  role_in_formation: "role_in_formation",
  assigned_on: "assigned_on",
  released_on: "released_on",
  notes: "notes",
};

const orNull = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim() : null;

interface CdFormationMembersDialogProps {
  trigger: ReactNode;
  formation: FormationDto;
  persons: PersonDto[];
  onChanged?: () => void;
}

/**
 * Состав нештатного формирования (разд. 56.1, срез-110).
 *
 * Список членов читается при открытии окна, а не грузится вместе со всем
 * экраном: составов столько же, сколько формирований, и тянуть их все ради
 * одной строки реестра — лишняя работа на каждой загрузке страницы.
 *
 * ГРАНИЦЫ: ФИО не хранится в составе — человек берётся из ядра. Вывод из
 * состава — ДАТА, а не удаление строки: история участия нужна и после того,
 * как человека вывели, а сводка считает только действующих. Повторное
 * включение выведенного человека сервер понимает как ВОЗВРАТ в состав (второй
 * строки не появится) — поэтому в списке для добавления остаются все.
 */
export const CdFormationMembersDialog = ({
  trigger,
  formation,
  persons,
  onChanged,
}: CdFormationMembersDialogProps) => {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<FormationMemberDto[]>([]);
  const [loading, setLoading] = useState(false);

  const form = useForm<CdFormationMemberFormValues>({
    resolver: zodResolver(cdFormationMemberFormSchema),
    defaultValues: emptyForm,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setMembers(await civilDefenseApi.listFormationMembers(formation.id));
    } catch {
      toast.error("Не удалось загрузить состав формирования");
    } finally {
      setLoading(false);
    }
  }, [formation.id]);

  useEffect(() => {
    if (!open) return;
    form.reset(emptyForm);
    void load();
  }, [open, load, form]);

  const onSubmit = async (values: CdFormationMemberFormValues) => {
    try {
      await civilDefenseApi.addFormationMember(formation.id, {
        person_id: values.person_id,
        role_in_formation: orNull(values.role_in_formation),
        assigned_on: orNull(values.assigned_on),
        notes: orNull(values.notes),
      });
      toast.success("Работник включён в состав");
      form.reset(emptyForm);
      await load();
      onChanged?.();
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось включить работника в состав");
      } else {
        toast.error("Не удалось включить работника в состав");
      }
      throw err;
    }
  };

  const release = async (member: FormationMemberDto) => {
    try {
      await civilDefenseApi.updateFormationMember(formation.id, member.id, {
        released_on: new Date().toISOString().slice(0, 10),
      });
      toast.success("Работник выведен из состава");
      await load();
      onChanged?.();
    } catch (err: unknown) {
      toast.error(
        isApiError(err)
          ? (err.message ?? "Не удалось вывести из состава")
          : "Не удалось вывести из состава",
      );
    }
  };

  const restore = async (member: FormationMemberDto) => {
    try {
      await civilDefenseApi.updateFormationMember(formation.id, member.id, {
        released_on: null,
      });
      toast.success("Работник возвращён в состав");
      await load();
      onChanged?.();
    } catch (err: unknown) {
      toast.error(
        isApiError(err)
          ? (err.message ?? "Не удалось вернуть в состав")
          : "Не удалось вернуть в состав",
      );
    }
  };

  const fieldError = (name: keyof CdFormationMemberFormValues) => {
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
          <DialogTitle>Состав: {formation.name}</DialogTitle>
          <DialogDescription>
            Вывод из состава — это дата, а не удаление: история участия
            остаётся, а в сводке считаются только действующие. ФИО берётся из
            справочника людей.
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
              <Label htmlFor="cd-member-person">Работник</Label>
              <select
                id="cd-member-person"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("person_id")}
              >
                <option value="">— Выберите работника —</option>
                {persons.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
              {fieldError("person_id")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="cd-member-role">Роль в формировании</Label>
              <Input
                id="cd-member-role"
                placeholder="напр. командир звена, спасатель"
                {...form.register("role_in_formation")}
              />
              {fieldError("role_in_formation")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="cd-member-assigned">Включён с</Label>
              <Input
                id="cd-member-assigned"
                type="date"
                {...form.register("assigned_on")}
              />
              {fieldError("assigned_on")}
            </div>
            <div className="flex items-end">
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting
                  ? "Сохранение..."
                  : "Включить в состав"}
              </Button>
            </div>
          </div>
        </form>
        <div className="space-y-2">
          {loading ? (
            <p className="text-sm text-muted-foreground">Загрузка состава…</p>
          ) : null}
          {!loading && members.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              В составе пока никого: включите работников из справочника.
            </p>
          ) : null}
          {members.map((member) => (
            <div
              key={member.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm"
            >
              <span>
                {member.person_name}
                {member.role_in_formation ? (
                  <span className="ml-1 text-muted-foreground">
                    · {member.role_in_formation}
                  </span>
                ) : null}
                <span className="ml-1 text-muted-foreground">
                  · {member.status_label}
                  {member.released_on
                    ? ` ${formatDate(member.released_on)}`
                    : ""}
                </span>
              </span>
              {member.status === "active" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void release(member)}
                >
                  Вывести
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void restore(member)}
                >
                  Вернуть
                </Button>
              )}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};
