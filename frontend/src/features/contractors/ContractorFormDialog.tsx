import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
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
import type { ContractorRegistry } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  initialData?: ContractorRegistry;
  onSubmitted?: (contractor: ContractorRegistry) => void;
}

const emptyForm = { name: "", legal_name: "", inn: "", contact_person: "", contact_phone: "", status: "active" };

export const ContractorFormDialog = ({ trigger, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const isEdit = Boolean(initialData);

  useEffect(() => {
    if (!open) return;
    setForm(
      initialData
        ? {
            name: initialData.name,
            legal_name: initialData.legal_name ?? "",
            inn: initialData.inn ?? "",
            contact_person: initialData.contact_person ?? "",
            contact_phone: initialData.contact_phone ?? "",
            status: initialData.status ?? "active"
          }
        : emptyForm
    );
  }, [open, initialData]);

  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = async () => {
    if (!form.name.trim()) {
      toast.error("Укажите название контрагента");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        legal_name: form.legal_name || null,
        inn: form.inn || null,
        contact_person: form.contact_person || null,
        contact_phone: form.contact_phone || null
      };
      const result = initialData
        ? await contractorsApi.updateRegistry(initialData.id, { ...payload, status: form.status })
        : await contractorsApi.createRegistry(payload);
      toast.success(isEdit ? "Контрагент обновлён" : "Контрагент создан");
      onSubmitted?.(result);
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить контрагента");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать контрагента" : "Новый контрагент"}</DialogTitle>
          <DialogDescription>Реквизиты контрагента и контактные данные.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="c-name">Название</Label>
            <Input id="c-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="c-legal">Юр. наименование</Label>
              <Input id="c-legal" value={form.legal_name} onChange={(e) => set("legal_name", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-inn">ИНН</Label>
              <Input id="c-inn" value={form.inn} onChange={(e) => set("inn", e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="c-contact">Контактное лицо</Label>
              <Input id="c-contact" value={form.contact_person} onChange={(e) => set("contact_person", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-phone">Телефон</Label>
              <Input id="c-phone" value={form.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} />
            </div>
          </div>
          {isEdit ? (
            <div className="space-y-2">
              <Label htmlFor="c-status">Статус</Label>
              <select
                id="c-status"
                className="h-10 w-full rounded-md border px-3"
                value={form.status}
                onChange={(e) => set("status", e.target.value)}
              >
                <option value="active">Активен</option>
                <option value="suspended">Приостановлен</option>
                <option value="blocked">Заблокирован</option>
              </select>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
