import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import type { NpaClauseCreateDto, NpaScope } from "@/types/dto/npa";
import { isApiError } from "@/utils/apiFormErrors";

/**
 * Срез-141: точка входа в реестр НПА на витрине.
 *
 * Форма общего реестра показывается только владельцу платформы (`can_manage`
 * из `GET /npa`): реестр общий, и остальным ручка ответит 403 — кнопка,
 * которая всегда кончается отказом, хуже отсутствующей.
 *
 * Срез-201: та же форма заводит и СОБСТВЕННЫЙ акт организации — по `scope`.
 * Форма одна, потому что поля у акта одни и те же; разное здесь только одно —
 * куда он попадёт, и это сказано прямым текстом в заголовке и описании. Два
 * почти одинаковых окна разошлись бы уже на первой правке.
 */

/**
 * Пункты набираются строками «код текст»: первое слово — код пункта,
 * остальное — текст. Отдельная таблица полей для десятка строк была бы
 * тяжелее самого акта.
 */
export const parseClauses = (raw: string): NpaClauseCreateDto[] =>
  raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const gap = line.search(/\s/);
      if (gap < 0) return { code: line, text: line };
      return { code: line.slice(0, gap), text: line.slice(gap).trim() };
    });

const orNull = (value: string): string | null => (value ? value : null);

const failureMessage = (error: unknown, fallback: string): string => {
  if (isApiError(error) && error.status === 409) {
    return error.message;
  }
  return fallback;
};

interface NpaActFormDialogProps {
  trigger: ReactNode;
  onCreated: () => void;
  /** Срез-201: куда попадёт акт. По умолчанию — общий реестр, как было. */
  scope?: NpaScope;
}

export const NpaActFormDialog = ({
  trigger,
  onCreated,
  scope = "registry",
}: NpaActFormDialogProps) => {
  const own = scope === "own";
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [edition, setEdition] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [clauses, setClauses] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await npaApi.createAct({
        scope,
        code: code.trim(),
        title: title.trim(),
        edition: edition.trim(),
        valid_from: orNull(validFrom),
        valid_to: orNull(validTo),
        clauses: parseClauses(clauses),
      });
      toast.success(own ? "Акт организации добавлен" : "Акт добавлен в реестр");
      setOpen(false);
      setCode("");
      setTitle("");
      setEdition("");
      setValidFrom("");
      setValidTo("");
      setClauses("");
      onCreated();
    } catch (error) {
      toast.error(failureMessage(error, "Не удалось добавить акт"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {own ? "Новый акт организации" : "Новый нормативный акт"}
          </DialogTitle>
          <DialogDescription>
            {own
              ? "Акт увидит только ваша организация. Это ваш приказ или инструкция, а не общий документ платформы."
              : "Акт попадёт в общий реестр и станет виден всем арендаторам."}
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="npa-act-code">Номер</Label>
              <Input
                id="npa-act-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="npa-act-edition">Редакция</Label>
              <Input
                id="npa-act-edition"
                value={edition}
                onChange={(event) => setEdition(event.target.value)}
                placeholder="ред. от 01.03.2026"
                required
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="npa-act-title">Название</Label>
              <Input
                id="npa-act-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="npa-act-valid-from">Действует с</Label>
              <Input
                id="npa-act-valid-from"
                type="date"
                value={validFrom}
                onChange={(event) => setValidFrom(event.target.value)}
              />
            </div>
          </div>
          {/* Срок окончания и пункты нужны не каждому акту — под «Дополнительно»,
              чтобы форма укладывалась в UX-бюджет видимых полей (разд. 59.2). */}
          <details className="space-y-4">
            <summary className="cursor-pointer text-sm text-muted-foreground">
              Дополнительно
            </summary>
            <div className="space-y-2 pt-2">
              <Label htmlFor="npa-act-valid-to">Действует по</Label>
              <Input
                id="npa-act-valid-to"
                type="date"
                value={validTo}
                onChange={(event) => setValidTo(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="npa-act-clauses">Пункты</Label>
              <Textarea
                id="npa-act-clauses"
                rows={4}
                value={clauses}
                onChange={(event) => setClauses(event.target.value)}
                placeholder={
                  "По одному в строке: код и текст\n1 Общие положения"
                }
              />
            </div>
          </details>
          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving ? "Сохранение..." : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

interface NpaRevisionFormDialogProps {
  actId: string;
  trigger: ReactNode;
  onCreated: () => void;
}

export const NpaRevisionFormDialog = ({
  actId,
  trigger,
  onCreated,
}: NpaRevisionFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [revisionCode, setRevisionCode] = useState("");
  const [title, setTitle] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [summary, setSummary] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await npaApi.createRevision(actId, {
        revision_code: revisionCode.trim(),
        title: title.trim(),
        effective_from: orNull(effectiveFrom),
        effective_to: orNull(effectiveTo),
        change_summary: orNull(summary.trim()),
      });
      toast.success("Редакция добавлена");
      setOpen(false);
      setRevisionCode("");
      setTitle("");
      setEffectiveFrom("");
      setEffectiveTo("");
      setSummary("");
      onCreated();
    } catch (error) {
      toast.error(failureMessage(error, "Не удалось добавить редакцию"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новая редакция акта</DialogTitle>
          <DialogDescription>
            Действующей считается редакция, чей срок покрывает сегодняшний день.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="npa-rev-code">Код редакции</Label>
              <Input
                id="npa-rev-code"
                value={revisionCode}
                onChange={(event) => setRevisionCode(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="npa-rev-title">Название</Label>
              <Input
                id="npa-rev-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="npa-rev-from">Действует с</Label>
              <Input
                id="npa-rev-from"
                type="date"
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="npa-rev-to">Действует по</Label>
              <Input
                id="npa-rev-to"
                type="date"
                value={effectiveTo}
                onChange={(event) => setEffectiveTo(event.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="npa-rev-summary">Что изменилось</Label>
            <Textarea
              id="npa-rev-summary"
              rows={3}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving ? "Сохранение..." : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
