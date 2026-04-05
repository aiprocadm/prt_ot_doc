import { useEffect, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCompaniesStore } from "@/stores/companies";
import type { CompanyDto } from "@/types/dto/companies";
import { companySchema, type CompanyFormValues } from "@/types/forms/companies";

interface CompanyFormDialogProps {
  trigger: ReactNode;
  initialData?: CompanyDto;
  onSubmitted?: (company: CompanyDto) => void;
}

export const CompanyFormDialog = ({ trigger, initialData, onSubmitted }: CompanyFormDialogProps) => {
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: {
      name: initialData?.name ?? "",
      inn: initialData?.inn ?? "",
      kpp: initialData?.kpp ?? "",
      ogrn: initialData?.ogrn ?? "",
      address: initialData?.address ?? "",
      email: initialData?.email ?? "",
      phone: initialData?.phone ?? "",
      website: initialData?.website ?? "",
      status: initialData?.status ?? "draft",
      tags: initialData?.tags ?? []
    }
  });

  const { create, update } = useCompaniesStore();

  useEffect(() => {
    if (initialData) {
      form.reset({
        name: initialData.name,
        inn: initialData.inn,
        kpp: initialData.kpp ?? "",
        ogrn: initialData.ogrn ?? "",
        address: initialData.address ?? "",
        email: initialData.email ?? "",
        phone: initialData.phone ?? "",
        website: initialData.website ?? "",
        status: initialData.status,
        tags: initialData.tags ?? []
      });
    }
  }, [initialData, form]);

  const onSubmit = async (values: CompanyFormValues) => {
    const payload = {
      name: values.name.trim(),
      inn: values.inn.trim() || undefined,
      kpp: values.kpp?.trim() || undefined,
      ogrn: values.ogrn?.trim() || undefined,
      address: values.address?.trim() || undefined,
      email: values.email?.trim() || undefined,
      phone_numbers: values.phone?.trim() ? [values.phone.trim()] : undefined,
      website: values.website?.trim() || undefined,
      status: values.status,
      tags: values.tags
    };

    try {
      const result = initialData ? await update(initialData.id, payload) : await create(payload);
      onSubmitted?.(result);
      toast.success(initialData ? "Компания обновлена" : "Компания создана");
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err && typeof (err as { message: string }).message === "string"
          ? (err as { message: string }).message
          : "Не удалось сохранить компанию";
      toast.error(msg);
      throw err;
    }
  };

  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать компанию" : "Новая компания"}</DialogTitle>
          <DialogDescription>Введите реквизиты компании для генерации документов.</DialogDescription>
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
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Название</Label>
              <Input id="name" {...form.register("name")} required />
              {form.formState.errors.name && <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="status">Статус</Label>
              <select id="status" className="h-10 rounded-md border px-3" {...form.register("status")}> 
                <option value="draft">Черновик</option>
                <option value="active">Активна</option>
                <option value="archived">Архив</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="inn">ИНН</Label>
              <Input id="inn" {...form.register("inn")} placeholder="10 или 12 цифр (необязательно)" />
              {form.formState.errors.inn && <p className="text-xs text-destructive">{form.formState.errors.inn.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="kpp">КПП</Label>
              <Input id="kpp" {...form.register("kpp")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ogrn">ОГРН</Label>
              <Input id="ogrn" {...form.register("ogrn")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="website">Сайт</Label>
              <Input id="website" type="url" {...form.register("website")} placeholder="https://…" />
              {form.formState.errors.website && <p className="text-xs text-destructive">{form.formState.errors.website.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" {...form.register("email")} />
              {form.formState.errors.email && <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">Телефон</Label>
              <Input id="phone" {...form.register("phone")} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="address">Адрес</Label>
            <Textarea id="address" {...form.register("address")} rows={3} />
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
