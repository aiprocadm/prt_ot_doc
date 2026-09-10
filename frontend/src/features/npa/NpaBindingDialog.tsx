import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { listDocumentsForPicker } from "@/api/documents";
import { npaApi } from "@/api/npa";
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
import type { DocumentDto } from "@/types/dto/documents";
import { isApiError } from "@/utils/apiFormErrors";

/**
 * Срез-142: привязка документа арендатора к акту реестра.
 *
 * Именно эти связи читает «Анализ влияния»: до среза их заводить было нечем,
 * и «Связанные сущности» были пусты на любых данных. Список документов
 * берётся с той же ручки, что и экран «Документы», — имя документа здесь и
 * там одно и то же.
 */

interface NpaBindingDialogProps {
  actId: string;
  trigger: ReactNode;
  onCreated: () => void;
}

const failureMessage = (error: unknown): string => {
  if (isApiError(error) && (error.status === 409 || error.status === 404)) {
    return error.message;
  }
  return "Не удалось привязать документ";
};

export const NpaBindingDialog = ({
  actId,
  trigger,
  onCreated,
}: NpaBindingDialogProps) => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [documents, setDocuments] = useState<DocumentDto[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [ref, setRef] = useState("");

  useEffect(() => {
    if (!open) return;
    void listDocumentsForPicker()
      .then((items) => setDocuments(items))
      .catch(() => setDocuments([]));
  }, [open]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!documentId) return;
    setSaving(true);
    try {
      await npaApi.createBinding(actId, {
        entity_type: "document",
        entity_id: documentId,
        ref: ref.trim() ? ref.trim() : null,
      });
      toast.success("Документ привязан к акту");
      setOpen(false);
      setDocumentId("");
      setRef("");
      onCreated();
    } catch (error) {
      toast.error(failureMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Привязать документ к акту</DialogTitle>
          <DialogDescription>
            Связь попадёт в анализ влияния: при новой редакции акта по ней будет
            поставлена задача обновления.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="space-y-2">
            <Label htmlFor="npa-binding-document">Документ</Label>
            <select
              id="npa-binding-document"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={documentId}
              onChange={(event) => setDocumentId(event.target.value)}
              required
            >
              <option value="">— выберите документ —</option>
              {documents.map((document) => (
                <option key={document.id} value={document.id}>
                  {document.name}
                  {document.company?.name ? ` · ${document.company.name}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="npa-binding-ref">Пункт акта</Label>
            <Input
              id="npa-binding-ref"
              value={ref}
              onChange={(event) => setRef(event.target.value)}
              placeholder="п. 4 (необязательно)"
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving || !documentId}>
              {saving ? "Сохранение..." : "Привязать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
