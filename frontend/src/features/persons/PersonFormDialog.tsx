import { useEffect, useRef, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCompaniesStore } from "@/stores/companies";
import { usePersonsStore } from "@/stores/persons";
import { mergeElectricalGroupQuals } from "@/api/personsApi";
import type { PersonDto } from "@/types/dto/persons";
import { personSchema, type PersonFormValues } from "@/types/forms/persons";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyPersonForm: PersonFormValues = {
  company_id: "",
  first_name: "",
  last_name: "",
  middle_name: "",
  position: "",
  email: "",
  phone: "",
  status: "active",
  electrical_group: "",
  electrical_group_valid_until: ""
};

interface PersonFormDialogProps {
  trigger: ReactNode;
  initialData?: PersonDto;
  onSubmitted?: (person: PersonDto) => void;
}

const PERSON_API_FIELD_MAP: Record<string, keyof PersonFormValues> = {
  company_id: "company_id",
  first_name: "first_name",
  last_name: "last_name",
  middle_name: "middle_name",
  email: "email",
  phone: "phone",
  employment_status: "status"
};

export const PersonFormDialog = ({ trigger, initialData, onSubmitted }: PersonFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const { list: listCompanies, items: companies } = useCompaniesStore();

  /**
   * Хранит квалификации персоны (кроме electrical_safety_group) — нужны для merge-safe патча.
   * При загрузке заполняется из initialData.qualifications.
   */
  const otherQualsRef = useRef<Array<Record<string, unknown>>>([]);

  const form = useForm<PersonFormValues>({
    resolver: zodResolver(personSchema),
    defaultValues: {
      company_id: initialData?.company_id ?? "",
      first_name: initialData?.first_name ?? "",
      last_name: initialData?.last_name ?? "",
      middle_name: initialData?.middle_name ?? "",
      position: initialData?.position ?? "",
      email: initialData?.email ?? "",
      phone: initialData?.phone ?? "",
      status: initialData?.status ?? "active",
      electrical_group: "",
      electrical_group_valid_until: ""
    }
  });

  const { create, update } = usePersonsStore();

  useEffect(() => {
    if (open) void listCompanies().catch(() => undefined);
  }, [open, listCompanies]);

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      const quals: Array<Record<string, unknown>> = Array.isArray(initialData.qualifications)
        ? (initialData.qualifications as Array<Record<string, unknown>>)
        : [];

      // Находим запись electrical_safety_group
      const elecEntry = quals.find((q) => q.kind === "electrical_safety_group") as
        | Record<string, unknown>
        | undefined;

      // Остальные квалификации сохраняем для merge
      otherQualsRef.current = quals.filter((q) => q.kind !== "electrical_safety_group");

      form.reset({
        company_id: initialData.company_id ?? "",
        first_name: initialData.first_name,
        last_name: initialData.last_name,
        middle_name: initialData.middle_name ?? "",
        position: initialData.position ?? "",
        email: initialData.email ?? "",
        phone: initialData.phone ?? "",
        status: initialData.status,
        electrical_group: elecEntry
          ? (String(elecEntry.level ?? "") as PersonFormValues["electrical_group"])
          : "",
        electrical_group_valid_until: elecEntry ? String(elecEntry.valid_until ?? "") : ""
      });
    } else {
      otherQualsRef.current = [];
      form.reset(emptyPersonForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: PersonFormValues) => {
    try {
      // Merge-safe: берём все прочие квалификации + новую/обновлённую electrical_safety_group
      const qualifications = mergeElectricalGroupQuals(otherQualsRef.current, values);

      const payload: PersonFormValues = { ...values, qualifications };

      const result = initialData ? await update(initialData.id, payload) : await create(payload);
      onSubmitted?.(result);
      const cid = result.company_id ?? values.company_id;
      if (cid) {
        const { item, getById } = useCompaniesStore.getState();
        if (item?.id === cid) {
          void getById(cid);
        }
      }
      toast.success(initialData ? "Сотрудник обновлён" : "Сотрудник добавлен");
      setOpen(false);
      if (!initialData) {
        form.reset(emptyPersonForm);
      }
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, PERSON_API_FIELD_MAP);
      }
      throw err;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать сотрудника" : "Новый сотрудник"}</DialogTitle>
          <DialogDescription>Добавьте или обновите данные сотрудника.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
            } catch {
              /* toast в onSubmit */
            }
          })}
        >
          <div className="space-y-2">
            <Label htmlFor="company_id">Компания</Label>
            <select id="company_id" className="h-10 w-full rounded-md border px-3" {...form.register("company_id")}>
              <option value="">— Выберите компанию —</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            {form.formState.errors.company_id && (
              <p className="text-xs text-destructive">{form.formState.errors.company_id.message}</p>
            )}
            {companies.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Сначала создайте компанию в разделе{" "}
                <Link to="/companies" className="underline underline-offset-2">
                  Компании
                </Link>
                .
              </p>
            ) : null}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="first_name">Имя</Label>
              <Input id="first_name" {...form.register("first_name")} />
              {form.formState.errors.first_name && (
                <p className="text-xs text-destructive">{form.formState.errors.first_name.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">Фамилия</Label>
              <Input id="last_name" {...form.register("last_name")} />
              {form.formState.errors.last_name && (
                <p className="text-xs text-destructive">{form.formState.errors.last_name.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="middle_name">Отчество</Label>
              <Input id="middle_name" {...form.register("middle_name")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="position">Должность</Label>
              <Input id="position" {...form.register("position")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Электронная почта</Label>
              <Input id="email" type="email" {...form.register("email")} />
              {form.formState.errors.email && <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">Телефон</Label>
              <Input id="phone" {...form.register("phone")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="status">Статус</Label>
              <select id="status" className="h-10 rounded-md border px-3" {...form.register("status")}>
                <option value="active">Активен</option>
                <option value="inactive">Неактивен</option>
                <option value="dismissed">Уволен</option>
              </select>
            </div>
          </div>

          {/* Группа по электробезопасности */}
          <div className="space-y-2 border-t pt-4">
            <Label className="text-sm font-medium">Группа по электробезопасности</Label>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="electrical_group">Группа по электробезопасности</Label>
                <select
                  id="electrical_group"
                  className="h-10 w-full rounded-md border px-3"
                  {...form.register("electrical_group")}
                >
                  <option value="">— Не установлена —</option>
                  <option value="I">I</option>
                  <option value="II">II</option>
                  <option value="III">III</option>
                  <option value="IV">IV</option>
                  <option value="V">V</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="electrical_group_valid_until">Действует до</Label>
                <Input
                  id="electrical_group_valid_until"
                  type="date"
                  {...form.register("electrical_group_valid_until")}
                />
              </div>
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
