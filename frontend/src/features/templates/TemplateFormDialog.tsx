import { useEffect, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useTemplatesStore } from "@/stores/templates";
import type { TemplateDto } from "@/types/dto/templates";
import { templateSchema, type TemplateFormValues } from "@/types/forms/templates";

interface TemplateFormDialogProps {
  trigger: ReactNode;
  initialData?: TemplateDto;
  onSubmitted?: (template: TemplateDto) => void;
}

export const TemplateFormDialog = ({ trigger, initialData, onSubmitted }: TemplateFormDialogProps) => {
  const form = useForm<TemplateFormValues>({
    resolver: zodResolver(templateSchema),
    defaultValues: {
      code: initialData?.code ?? "",
      name: initialData?.name ?? "",
      description: initialData?.description ?? "",
      template_type: initialData?.template_type ?? "",
      status: initialData?.status === "archived" ? "archived" : initialData?.status === "active" ? "active" : "draft",
      scope: {
        type: initialData?.scope?.type === "site" ? "site" : initialData?.scope?.type === "organization" || initialData?.scope?.type === "legal_entity" ? "organization" : initialData?.scope?.type === "global" ? "global" : "tenant",
        company_id: initialData?.scope?.company_id ?? "",
        site_id: initialData?.scope?.site_id ?? ""
      }
    }
  });

  const { create, update } = useTemplatesStore();

  useEffect(() => {
    if (initialData) {
      form.reset({
        code: initialData.code ?? "",
        name: initialData.name,
        description: initialData.description ?? "",
        template_type: initialData.template_type ?? "",
        status: initialData.status === "archived" ? "archived" : initialData.status === "active" ? "active" : "draft",
        scope: {
          type: initialData.scope?.type === "site" ? "site" : initialData.scope?.type === "organization" || initialData.scope?.type === "legal_entity" ? "organization" : initialData.scope?.type === "global" ? "global" : "tenant",
          company_id: initialData.scope?.company_id ?? "",
          site_id: initialData.scope?.site_id ?? ""
        }
      });
    }
  }, [initialData, form]);

  const onSubmit = async (values: TemplateFormValues) => {
    const result = initialData ? await update(initialData.id, values) : await create(values);
    onSubmitted?.(result);
  };

  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать шаблон" : "Новый шаблон"}</DialogTitle>
          <DialogDescription>Опишите назначение шаблона и его метаданные.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="template-code">
              Код
            </label>
            <Input id="template-code" {...form.register("code")} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="template-name">
              Название
            </label>
            <Input id="template-name" {...form.register("name")} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="template-type">
              Тип шаблона
            </label>
            <Input id="template-type" placeholder="order / instruction / protocol" {...form.register("template_type")} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="template-status">Статус</label>
            <select id="template-status" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" {...form.register("status")}>
              <option value="draft">draft</option>
              <option value="active">published/active</option>
              <option value="archived">archived</option>
            </select>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="template-scope-type">Scope</label>
              <select id="template-scope-type" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" {...form.register("scope.type")}>
                <option value="tenant">Tenant</option>
                <option value="organization">Организация</option>
                <option value="site">Филиал / площадка</option>
                <option value="global">Global/System</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="template-company-id">Company ID</label>
              <Input id="template-company-id" {...form.register("scope.company_id")} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="template-site-id">Site ID</label>
              <Input id="template-site-id" {...form.register("scope.site_id")} />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="template-description">
              Описание
            </label>
            <Textarea id="template-description" rows={4} {...form.register("description")} />
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
