import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { buildBranchCreateBody, buildBranchUpdateBody } from "@/api/branchesApi";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useBranchesStore } from "@/stores/branches";
import type { BranchDto } from "@/types/dto/branches";
import type { CompanyDto } from "@/types/dto/companies";
import { branchSchema, type BranchFormValues } from "@/types/forms/branches";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyBranchForm: BranchFormValues = {
  company_id: "",
  name: "",
  code: "",
  address: "",
  contact_name: "",
  contact_phone: "",
  contact_email: "",
  status: "active"
};

const BRANCH_API_FIELD_MAP: Record<string, keyof BranchFormValues> = {
  company_id: "company_id",
  name: "name",
  code: "code",
  address: "address",
  contact_name: "contact_name",
  contact_phone: "contact_phone",
  contact_email: "contact_email",
  status: "status"
};

interface BranchFormDialogProps {
  trigger: ReactNode;
  companies: CompanyDto[];
  initialData?: BranchDto;
  defaultCompanyId?: string;
  onSubmitted?: (branch: BranchDto) => void;
}

export const BranchFormDialog = ({
  trigger,
  companies,
  initialData,
  defaultCompanyId,
  onSubmitted
}: BranchFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const form = useForm<BranchFormValues>({
    resolver: zodResolver(branchSchema),
    defaultValues: { ...emptyBranchForm, company_id: defaultCompanyId ?? "" }
  });

  const { create, update } = useBranchesStore();

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        company_id: initialData.company_id,
        name: initialData.name,
        code: initialData.code ?? "",
        address: initialData.address ?? "",
        contact_name: initialData.contact_name ?? "",
        contact_phone: initialData.contact_phone ?? "",
        contact_email: initialData.contact_email ?? "",
        status: initialData.status
      });
    } else {
      form.reset({ ...emptyBranchForm, company_id: defaultCompanyId ?? "" });
    }
  }, [open, initialData, defaultCompanyId, form]);

  const onSubmit = async (values: BranchFormValues) => {
    try {
      const result = initialData
        ? await update(initialData.id, buildBranchUpdateBody(values))
        : await create(buildBranchCreateBody(values));
      onSubmitted?.(result);
      toast.success(initialData ? "Филиал обновлён" : "Филиал создан");
      setOpen(false);
      if (!initialData) {
        form.reset({ ...emptyBranchForm, company_id: defaultCompanyId ?? "" });
      }
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, BRANCH_API_FIELD_MAP);
      }
      throw err;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать филиал" : "Новый филиал"}</DialogTitle>
          <DialogDescription>
            Филиал — уровень между компанией и объектами (площадками).
          </DialogDescription>
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
              <Label htmlFor="branch-company">Компания</Label>
              <select
                id="branch-company"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                disabled={Boolean(initialData)}
                {...form.register("company_id")}
              >
                <option value="">— выберите компанию —</option>
                {companies.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
                  </option>
                ))}
              </select>
              {initialData ? (
                <p className="text-xs text-muted-foreground">Компанию филиала изменить нельзя.</p>
              ) : null}
              {form.formState.errors.company_id && (
                <p className="text-xs text-destructive">{form.formState.errors.company_id.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="branch-status">Статус</Label>
              <select
                id="branch-status"
                className="h-10 w-full rounded-md border px-3"
                {...form.register("status")}
              >
                <option value="active">Активен</option>
                <option value="inactive">Неактивен</option>
                <option value="archived">Архив</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="branch-name">Название</Label>
              <Input id="branch-name" {...form.register("name")} required />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="branch-code">Код</Label>
              <Input id="branch-code" {...form.register("code")} placeholder="необязательно" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="branch-contact-name">Контактное лицо</Label>
              <Input id="branch-contact-name" {...form.register("contact_name")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="branch-contact-phone">Телефон</Label>
              <Input id="branch-contact-phone" {...form.register("contact_phone")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="branch-contact-email">Электронная почта</Label>
              <Input id="branch-contact-email" type="email" {...form.register("contact_email")} />
              {form.formState.errors.contact_email && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.contact_email.message}
                </p>
              )}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="branch-address">Адрес</Label>
            <Textarea id="branch-address" {...form.register("address")} rows={2} />
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
