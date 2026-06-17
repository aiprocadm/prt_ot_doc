import { useEffect, useState, type ReactNode } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { permitsApi } from "@/api/permits";
import type { PermitDto } from "@/types/dto/permits";

interface PermitExtendDialogProps {
  trigger: ReactNode;
  permit: PermitDto;
  onSubmitted?: (permit: PermitDto) => void;
}

export const PermitExtendDialog = ({ trigger, permit, onSubmitted }: PermitExtendDialogProps) => {
  const [open, setOpen] = useState(false);
  const [validUntil, setValidUntil] = useState(permit.valid_until ?? "");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setValidUntil(permit.valid_until ?? "");
  }, [open, permit.valid_until]);

  const submit = async () => {
    if (!validUntil) {
      toast.error("Укажите новую дату");
      return;
    }
    setSubmitting(true);
    try {
      const result = await permitsApi.extendPermit(permit.id, validUntil);
      onSubmitted?.(result);
      toast.success("Допуск продлён");
      setOpen(false);
    } catch (err: unknown) {
      const message = err && typeof err === "object" && "message" in err ? String(err.message) : "Не удалось продлить допуск";
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
          <DialogTitle>Продлить допуск</DialogTitle>
          <DialogDescription>Задайте новую дату «действует до».</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="extend_valid_until">Действует до</Label>
          <Input
            id="extend_valid_until"
            type="date"
            value={validUntil}
            onChange={(e) => setValidUntil(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => void submit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Продлить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
