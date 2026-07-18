import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { briefingsApi, type BriefingEntryDto, type BriefingJournalDto, type BriefingTemplateDto } from "@/api/briefings";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import type { ApiError } from "@/types/dto/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAbility } from "@/permissions/useAbility";
import { PERMISSIONS } from "@/permissions/permissions";
import { fetchAllPersons } from "@/api/personsApi";
import type { PersonDto } from "@/types/dto/persons";
import { formatDate } from "@/utils/datetime";

const BriefingsPage = () => {
  const [templates, setTemplates] = useState<BriefingTemplateDto[]>([]);
  const [journals, setJournals] = useState<BriefingJournalDto[]>([]);
  const [entries, setEntries] = useState<BriefingEntryDto[]>([]);
  const [overdue, setOverdue] = useState<BriefingEntryDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [persons, setPersons] = useState<PersonDto[]>([]);
  const [templateForm, setTemplateForm] = useState({ code: "", title: "", briefing_type: "introductory", status: "active", description: "", validity_days: 365 });
  const [journalForm, setJournalForm] = useState({ code: "", title: "", journal_type: "ot", status: "active", site_id: null as string | null, department_id: null as string | null });
  const [entryForm, setEntryForm] = useState({ briefing_journal_id: "", briefing_template_id: "", person_id: "", instructor_user_id: "", briefing_type: "introductory", briefing_date: new Date().toISOString().slice(0, 16), valid_until: "", reason: "", status: "draft", notes: "" });
  const ability = useAbility();
  const canManageBriefings = ability.can(PERMISSIONS.TRAINING_ASSIGN);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [templateItems, journalItems, entryItems, overdueItems] = await Promise.all([
        briefingsApi.listTemplates(),
        briefingsApi.listJournals(),
        briefingsApi.listEntries(),
        briefingsApi.listOverdue()
      ]);
      setTemplates(templateItems);
      setJournals(journalItems);
      setEntries(entryItems);
      setOverdue(overdueItems);
    } catch (err) {
      setLoadError((err as ApiError) ?? { status: 0, message: "Не удалось загрузить данные по инструктажам" });
      toast.error("Не удалось загрузить данные по инструктажам");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    fetchAllPersons().then(setPersons).catch(() => undefined);
  }, []);

  const personOptions = useMemo(
    () => persons.map((person) => ({ value: person.id, label: person.full_name || person.id })),
    [persons],
  );

  return (
    <div className="space-y-6">
      <ErrorState error={loadError ?? undefined} onRetry={() => void load()} />
      {loading && templates.length === 0 && journals.length === 0 ? <LoadingScreen label="Загрузка инструктажей" /> : null}
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Инструктажи" }]} />
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
          <Button
            variant="secondary"
            disabled={!canManageBriefings}
            title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
            onClick={() => void briefingsApi.remindOverdue().then((result) => { toast.success(`Отправлено напоминаний: ${result.count}`); return load(); }).catch(() => toast.error("Не удалось отправить напоминания"))}
          >
            Напомнить о просрочке
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Контроль сроков</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border p-3"><div className="text-sm text-muted-foreground">Шаблоны</div><div className="text-2xl font-semibold">{templates.length}</div></div>
          <div className="rounded-lg border p-3"><div className="text-sm text-muted-foreground">Журналы</div><div className="text-2xl font-semibold">{journals.length}</div></div>
          <div className="rounded-lg border p-3"><div className="text-sm text-muted-foreground">Записи</div><div className="text-2xl font-semibold">{entries.length}</div></div>
          <div className="rounded-lg border p-3"><div className="text-sm text-muted-foreground">Просрочено</div><div className="text-2xl font-semibold text-destructive">{overdue.length}</div></div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Новый шаблон</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Код" value={templateForm.code} onChange={(e) => setTemplateForm((p) => ({ ...p, code: e.target.value }))} />
            <Input placeholder="Название" value={templateForm.title} onChange={(e) => setTemplateForm((p) => ({ ...p, title: e.target.value }))} />
            <Input placeholder="Тип инструктажа" value={templateForm.briefing_type} onChange={(e) => setTemplateForm((p) => ({ ...p, briefing_type: e.target.value }))} />
            <Input type="number" placeholder="Срок действия, дни" value={templateForm.validity_days} onChange={(e) => setTemplateForm((p) => ({ ...p, validity_days: Number(e.target.value) }))} />
            <Button
              className="w-full"
              disabled={!canManageBriefings}
              title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
              onClick={() => void briefingsApi.createTemplate(templateForm).then(() => { toast.success("Шаблон создан"); setTemplateForm({ code: "", title: "", briefing_type: "introductory", status: "active", description: "", validity_days: 365 }); return load(); }).catch(() => toast.error("Не удалось создать шаблон"))}
            >
              Создать шаблон
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Новый журнал</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Код" value={journalForm.code} onChange={(e) => setJournalForm((p) => ({ ...p, code: e.target.value }))} />
            <Input placeholder="Название" value={journalForm.title} onChange={(e) => setJournalForm((p) => ({ ...p, title: e.target.value }))} />
            <Input placeholder="Тип журнала" value={journalForm.journal_type} onChange={(e) => setJournalForm((p) => ({ ...p, journal_type: e.target.value }))} />
            <Button
              className="w-full"
              disabled={!canManageBriefings}
              title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
              onClick={() => void briefingsApi.createJournal(journalForm).then(() => { toast.success("Журнал создан"); setJournalForm({ code: "", title: "", journal_type: "ot", status: "active", site_id: null, department_id: null }); return load(); }).catch(() => toast.error("Не удалось создать журнал"))}
            >
              Создать журнал
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Назначить инструктаж</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label>Журнал</Label>
              <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={entryForm.briefing_journal_id} onChange={(e) => setEntryForm((p) => ({ ...p, briefing_journal_id: e.target.value }))}>
                <option value="">Выберите журнал</option>
                {journals.map((journal) => <option key={journal.id} value={journal.id}>{journal.title}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <Label>Шаблон</Label>
              <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={entryForm.briefing_template_id} onChange={(e) => setEntryForm((p) => ({ ...p, briefing_template_id: e.target.value }))}>
                <option value="">Выберите шаблон</option>
                {templates.map((template) => <option key={template.id} value={template.id}>{template.title}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="entry-person">Сотрудник</Label>
              <select id="entry-person" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={entryForm.person_id} onChange={(e) => setEntryForm((p) => ({ ...p, person_id: e.target.value }))}>
                <option value="">Выберите сотрудника</option>
                {personOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </div>
            <Input type="datetime-local" value={entryForm.briefing_date} onChange={(e) => setEntryForm((p) => ({ ...p, briefing_date: e.target.value }))} />
            <Button
              className="w-full"
              disabled={!canManageBriefings}
              title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
              onClick={() => void briefingsApi.createEntry({ ...entryForm, briefing_template_id: entryForm.briefing_template_id || null, person_id: entryForm.person_id || null, instructor_user_id: entryForm.instructor_user_id || null, valid_until: entryForm.valid_until || null }).then(() => { toast.success("Инструктаж назначен"); return load(); }).catch(() => toast.error("Не удалось назначить инструктаж"))}
            >
              Назначить
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Журнал инструктажей</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {entries.map((entry) => (
            <div key={entry.id} className="rounded-lg border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-medium">{entry.briefing_type}</div>
                  <div className="text-sm text-muted-foreground">Дата: {formatDate(entry.briefing_date)} · Срок: {entry.valid_until ? formatDate(entry.valid_until) : "не задан"}</div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={entry.status} />
                  {entry.is_overdue ? <StatusBadge status="overdue" /> : null}
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!canManageBriefings}
                  title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
                  onClick={() => void briefingsApi.sign(entry.id, "employee").then(() => load()).catch(() => toast.error("Не удалось зафиксировать подпись сотрудника"))}
                >
                  Подпись сотрудника
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!canManageBriefings}
                  title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
                  onClick={() => void briefingsApi.sign(entry.id, "instructor").then(() => load()).catch(() => toast.error("Не удалось зафиксировать подпись инструктора"))}
                >
                  Подпись инструктора
                </Button>
                <Button
                  size="sm"
                  disabled={!canManageBriefings}
                  title={canManageBriefings ? undefined : "Недостаточно прав для управления инструктажами"}
                  onClick={() => void briefingsApi.complete(entry.id).then(() => { toast.success("Инструктаж завершен"); return load(); }).catch((err) => toast.error((err as { message?: string })?.message || "Не удалось завершить инструктаж (нужны обе подписи)"))}
                >
                  Завершить
                </Button>
              </div>
              <div className="mt-3 text-sm text-muted-foreground">Подписей: {entry.signatures.length}</div>
            </div>
          ))}
          {!entries.length ? <div className="text-sm text-muted-foreground">Записей пока нет.</div> : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default BriefingsPage;
