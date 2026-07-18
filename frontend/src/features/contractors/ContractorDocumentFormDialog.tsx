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
import { DOC_TYPE_LABELS, DOC_TYPE_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { ContractorDocument, ContractorEmployee, DocType } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  contractorId: string;
  employees: ContractorEmployee[];
  initialData?: ContractorDocument;
  onSubmitted?: () => void;
}

export const ContractorDocumentFormDialog = ({ trigger, contractorId, employees, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(initialData);
  const [docType, setDocType] = useState<DocType>("license");
  const [title, setTitle] = useState("");
  const [number, setNumber] = useState("");
  const [issuingOrg, setIssuingOrg] = useState("");
  const [issuedAt, setIssuedAt] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [fileId, setFileId] = useState("");

  useEffect(() => {
    if (!open) return;
    setDocType(initialData?.doc_type ?? "license");
    setTitle(initialData?.title ?? "");
    setNumber(initialData?.number ?? "");
    setIssuingOrg(initialData?.issuing_org ?? "");
    setIssuedAt(initialData?.issued_at ?? "");
    setValidUntil(initialData?.valid_until ?? "");
    setEmployeeId(initialData?.employee_id ?? "");
    setFileId(initialData?.file_id ?? "");
  }, [open, initialData]);

  const onSubmit = async () => {
    if (!title.trim()) {
      toast.error("Укажите название документа");
      return;
    }
    setSubmitting(true);
    try {
      const common = {
        doc_type: docType,
        title: title.trim(),
        number: number || null,
        issuing_org: issuingOrg || null,
        issued_at: issuedAt || null,
        valid_until: validUntil || null,
        file_id: fileId || null
      };
      if (initialData) {
        await contractorsApi.updateDocument(initialData.id, common);
      } else {
        await contractorsApi.createDocument({ contractor_id: contractorId, employee_id: employeeId || null, ...common });
      }
      toast.success(isEdit ? "Документ обновлён" : "Документ добавлен");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      const e = err as { status?: number; message?: string };
      if (e.status === 422) {
        toast.error("Сотрудник не принадлежит выбранному подрядчику");
      } else {
        toast.error(e.message ?? "Не удалось сохранить документ");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать документ" : "Новый документ"}</DialogTitle>
          <DialogDescription>Сведения о документе подрядчика и сроки его действия.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc-type">Тип документа</Label>
              <select id="doc-type" className="h-10 w-full rounded-md border px-3" value={docType} onChange={(e) => setDocType(e.target.value as DocType)}>
                {DOC_TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {DOC_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="doc-employee">Сотрудник (необязательно)</Label>
              <select
                id="doc-employee"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                value={employeeId}
                disabled={isEdit}
                onChange={(e) => setEmployeeId(e.target.value)}
              >
                <option value="">— На компанию —</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.full_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-title">Название</Label>
            <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc-number">Номер</Label>
              <Input id="doc-number" value={number} onChange={(e) => setNumber(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="doc-org">Выдавший орган</Label>
              <Input id="doc-org" value={issuingOrg} onChange={(e) => setIssuingOrg(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc-issued">Выдан</Label>
              <Input id="doc-issued" type="date" value={issuedAt} onChange={(e) => setIssuedAt(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="doc-valid">Действует до</Label>
              <Input id="doc-valid" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-file">ID файла (необязательно)</Label>
            <Input id="doc-file" value={fileId} onChange={(e) => setFileId(e.target.value)} />
          </div>
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
