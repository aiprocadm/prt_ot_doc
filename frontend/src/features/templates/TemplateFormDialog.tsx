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
      category: initialData?.category ?? "",
      tags: initialData?.tags ?? []
    }
  });

  const { create, update } = useTemplatesStore();

  useEffect(() => {
    if (initialData) {
      form.reset({
        code: initialData.code ?? "",
        name: initialData.name,
        description: initialData.description ?? "",
        category: initialData.category ?? "",
        tags: initialData.tags ?? []
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
            <label className="text-sm font-medium" htmlFor="template-category">
              Категория
            </label>
            <Input id="template-category" {...form.register("category")} />
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
