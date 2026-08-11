import { useState, type ReactNode } from "react";
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
import { Label } from "@/components/ui/label";
import { DOC_TYPE_LABELS, DOC_TYPE_OPTIONS, SCOPE_LABELS, SCOPE_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { DocScope, DocType } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  onSubmitted?: () => void;
}

export const DocumentRequirementFormDialog = ({ trigger, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [docType, setDocType] = useState<DocType>("license");
  const [scope, setScope] = useState<DocScope>("company");
  const [mandatory, setMandatory] = useState(true);

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      await contractorsApi.createRequirement({ doc_type: docType, scope, mandatory });
      toast.success("Требование добавлено");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      const e = err as { status?: number; code?: string; message?: string };
      if (e.status === 409 || e.code === "requirement_exists") {
        toast.error("Требование для этого типа документа и области уже существует");
      } else {
        toast.error(e.message ?? "Не удалось добавить требование");
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
          <DialogTitle>Новое требование к документу</DialogTitle>
          <DialogDescription>Тип документа и область применения обязательного требования.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="req-type">Тип документа</Label>
            <select
              id="req-type"
              className="h-10 w-full rounded-md border px-3"
              value={docType}
              onChange={(e) => setDocType(e.target.value as DocType)}
            >
              {DOC_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {DOC_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="req-scope">Область</Label>
            <select
              id="req-scope"
              className="h-10 w-full rounded-md border px-3"
              value={scope}
              onChange={(e) => setScope(e.target.value as DocScope)}
            >
              {SCOPE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {SCOPE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={mandatory} onChange={(e) => setMandatory(e.target.checked)} />
            Обязательный документ
          </label>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Добавить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
