import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { tenantsApi } from "@/api/tenants";
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
import type { IndustryDto, TenantProvisionResult } from "@/types/dto/tenants";
import {
  tenantProvisionSchema,
  type TenantProvisionFormValues,
} from "@/types/forms/tenants";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyTenantForm: TenantProvisionFormValues = {
  slug: "",
  name: "",
  owner_email: "",
  owner_password: "",
  kind: "customer",
  demo_data: false,
  industry: "general",
};

const TENANT_API_FIELD_MAP: Record<string, keyof TenantProvisionFormValues> = {
  slug: "slug",
  name: "name",
  owner_email: "owner_email",
  owner_password: "owner_password",
  kind: "kind",
};

interface TenantFormDialogProps {
  trigger: ReactNode;
  onSubmitted?: (result: TenantProvisionResult) => void;
}

export const TenantFormDialog = ({
  trigger,
  onSubmitted,
}: TenantFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const form = useForm<TenantProvisionFormValues>({
    resolver: zodResolver(tenantProvisionSchema),
    defaultValues: emptyTenantForm,
  });

  const [industries, setIndustries] = useState<IndustryDto[]>([]);

  useEffect(() => {
    if (open) {
      form.reset(emptyTenantForm);
    }
  }, [open, form]);

  useEffect(() => {
    if (!open) return;
    // Список берём у сервера: наборы эталонов живут там, и зашитая копия
    // разошлась бы с ними при первой же новой отрасли — человек выбрал бы
    // отрасль, для которой набора нет.
    void tenantsApi
      .industries()
      .then((data) => setIndustries(data.items))
      .catch(() => setIndustries([]));
  }, [open]);

  const onSubmit = async (values: TenantProvisionFormValues) => {
    try {
      const result = await tenantsApi.provision(values);
      onSubmitted?.(result);
      toast.success(`Тенант «${result.tenant.name}» создан`);
      setOpen(false);
      form.reset(emptyTenantForm);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, TENANT_API_FIELD_MAP);
      }
      throw err;
    }
  };

  const errors = form.formState.errors;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый тенант</DialogTitle>
          <DialogDescription>
            Создаётся сразу рабочим: схема БД, квоты, стартовый набор
            справочников и учётная запись владельца, под которой можно войти.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
            } catch {
              /* toast is raised by the global error interceptor */
            }
          })}
        >
          <div className="space-y-2">
            <Label htmlFor="tenant-slug">Слаг</Label>
            <Input
              id="tenant-slug"
              placeholder="acme"
              {...form.register("slug")}
            />
            <p className="text-xs text-muted-foreground">
              Короткий код латиницей — под ним вводят тенант на форме входа.
              Изменить позже нельзя.
            </p>
            {errors.slug ? (
              <p className="text-xs text-destructive">{errors.slug.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="tenant-name">Название</Label>
            <Input
              id="tenant-name"
              placeholder="ООО «Акме»"
              {...form.register("name")}
            />
            {errors.name ? (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="tenant-kind">Тип</Label>
            <select
              id="tenant-kind"
              className="h-10 w-full rounded-md border px-3"
              {...form.register("kind")}
            >
              <option value="customer">Заказчик</option>
              <option value="branch">Филиал</option>
              <option value="contractor">Подрядчик</option>
              <option value="reseller">Реселлер (партнёр)</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="tenant-owner-email">E-mail владельца</Label>
            <Input
              id="tenant-owner-email"
              type="email"
              autoComplete="off"
              placeholder="owner@acme.ru"
              {...form.register("owner_email")}
            />
            {errors.owner_email ? (
              <p className="text-xs text-destructive">
                {errors.owner_email.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="tenant-owner-password">Пароль владельца</Label>
            <Input
              id="tenant-owner-password"
              type="password"
              autoComplete="new-password"
              {...form.register("owner_password")}
            />
            <p className="text-xs text-muted-foreground">
              Передайте его владельцу — под этой парой он войдёт в свой тенант.
            </p>
            {errors.owner_password ? (
              <p className="text-xs text-destructive">
                {errors.owner_password.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="tenant-industry">Отрасль</Label>
            <select
              id="tenant-industry"
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              {...form.register("industry")}
            >
              {industries.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.title}
                </option>
              ))}
            </select>
            {/* Человек должен понимать, на что влияет выбор: иначе поле
                выглядит анкетным и его заполняют наугад. */}
            <p className="text-xs text-muted-foreground">
              Определяет, какие должности, опасности и меры получит новый
              клиент. Их можно изменить позже.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              id="tenant-demo-data"
              type="checkbox"
              className="h-4 w-4"
              {...form.register("demo_data")}
            />
            <Label htmlFor="tenant-demo-data" className="font-normal">
              Заполнить демонстрационными данными
            </Label>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Создание..." : "Создать тенант"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
