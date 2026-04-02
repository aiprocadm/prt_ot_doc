import { useEffect, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePersonsStore } from "@/stores/persons";
import type { PersonDto } from "@/types/dto/persons";
import { personSchema, type PersonFormValues } from "@/types/forms/persons";

interface PersonFormDialogProps {
  trigger: ReactNode;
  initialData?: PersonDto;
  onSubmitted?: (person: PersonDto) => void;
}

export const PersonFormDialog = ({ trigger, initialData, onSubmitted }: PersonFormDialogProps) => {
  const form = useForm<PersonFormValues>({
    resolver: zodResolver(personSchema),
    defaultValues: {
      first_name: initialData?.first_name ?? "",
      last_name: initialData?.last_name ?? "",
      middle_name: initialData?.middle_name ?? "",
      position: initialData?.position ?? "",
      email: initialData?.email ?? "",
      phone: initialData?.phone ?? "",
      status: initialData?.status ?? "active"
    }
  });

  const { create, update } = usePersonsStore();

  useEffect(() => {
    if (initialData) {
      form.reset({
        first_name: initialData.first_name,
        last_name: initialData.last_name,
        middle_name: initialData.middle_name ?? "",
        position: initialData.position ?? "",
        email: initialData.email ?? "",
        phone: initialData.phone ?? "",
        status: initialData.status
      });
    }
  }, [initialData, form]);

  const onSubmit = async (values: PersonFormValues) => {
    const payload = {
      ...values,
      middle_name: values.middle_name || undefined,
      position: values.position || undefined,
      email: values.email || undefined,
      phone: values.phone || undefined
    };
    const result = initialData ? await update(initialData.id, payload) : await create(payload);
    onSubmitted?.(result);
  };

  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать сотрудника" : "Новый сотрудник"}</DialogTitle>
          <DialogDescription>Добавьте или обновите данные сотрудника.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="first_name">Имя</Label>
              <Input id="first_name" {...form.register("first_name")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">Фамилия</Label>
              <Input id="last_name" {...form.register("last_name")} />
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
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" {...form.register("email")} />
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
