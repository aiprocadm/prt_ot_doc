import { useState, type ReactNode } from "react";
import { toast } from "sonner";

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
import { permitsApi } from "@/api/permits";
import type { PermitDto } from "@/types/dto/permits";

interface RevokePermitDialogProps {
  trigger: ReactNode;
  permit: PermitDto;
  onSubmitted?: (permit: PermitDto) => void;
}

export const RevokePermitDialog = ({ trigger, permit, onSubmitted }: RevokePermitDialogProps) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      const result = await permitsApi.revokePermit(permit.id);
      onSubmitted?.(result);
      toast.success("Допуск отозван");
      setOpen(false);
    } catch (err: unknown) {
      const message = err && typeof err === "object" && "message" in err ? String(err.message) : "Не удалось отозвать допуск";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Отозвать допуск?</DialogTitle>
          <DialogDescription>
            Допуск «{permit.permit_type}» будет отозван без возможности восстановления.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="destructive" onClick={() => void submit()} disabled={submitting}>
            {submitting ? "Отзыв..." : "Отозвать"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
