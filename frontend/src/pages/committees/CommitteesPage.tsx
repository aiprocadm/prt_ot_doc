import { useCallback, useEffect, useMemo, useState } from "react";

import {
  committeesApi,
  type Attendance,
  type Committee,
  type MemberDetail,
  type Meeting,
  type Protocol,
  type ProtocolDecision,
  type ProtocolJournalItem,
  type VoteChoice,
} from "@/api/committees";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

// ── Label maps ──────────────────────────────────────────────────────────────

const KIND_LABELS: Record<string, string> = {
  osms: "Комитет по ОТ",
  pb: "Комитет по ПБ",
  commission_training: "Комиссия по обучению",
  commission_investigation: "Комиссия по расследованию",
  other: "Иное",
};

const ROLE_LABELS: Record<string, string> = {
  chair: "Председатель",
  secretary: "Секретарь",
  member: "Член",
};

const CHOICE_LABELS: Record<VoteChoice, string> = {
  for: "За",
  against: "Против",
  abstain: "Воздержался",
};

const OUTCOME_LABELS: Record<string, string> = {
  carried: "Принято",
  rejected: "Отклонено",
};

const STATUS_LABELS: Record<string, string> = {
  planned: "Запланировано",
  held: "Проведено",
  cancelled: "Отменено",
};

const KIND_OPTIONS = Object.entries(KIND_LABELS);
const ROLE_OPTIONS = Object.entries(ROLE_LABELS);
const CHOICE_OPTIONS = Object.keys(CHOICE_LABELS) as VoteChoice[];

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

const personLabel = (m: MemberDetail): string => m.person_fio?.trim() || m.person_id;

// ── Committee list panel + create form ──────────────────────────────────────

interface CommitteeListProps {
  selected: Committee | null;
  onSelect: (c: Committee) => void;
}

const CommitteeList = ({ selected, onSelect }: CommitteeListProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [items, setItems] = useState<Committee[]>([]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("osms");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await committeesApi.list();
      setItems(page.items);
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить комитеты"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      await committeesApi.createCommittee({ kind, name: name.trim() });
      setName("");
      await load();
    } catch (err) {
      setFormError(asApiError(err, "Не удалось создать комитет"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Комитеты</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreate}>
          <div className="flex-1 min-w-[200px] space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="cmt-name">
              Название
            </label>
            <Input
              id="cmt-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Новый комитет"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="cmt-kind">
              Вид
            </label>
            <select
              id="cmt-kind"
              className={selectClass}
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {KIND_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={saving || !name.trim()}>
            Создать комитет
          </Button>
        </form>
        <ErrorState error={formError ?? undefined} />
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка комитетов" /> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="Нет данных" description="Комитеты ещё не созданы." />
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Название</TableHead>
                <TableHead>Вид</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((c) => (
                <TableRow
                  key={c.id}
                  className={`cursor-pointer ${selected?.id === c.id ? "bg-muted" : ""}`}
                  onClick={() => onSelect(c)}
                >
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="text-muted-foreground">{KIND_LABELS[c.kind] ?? c.kind}</TableCell>
                  <TableCell>
                    <Badge variant={c.is_active ? "default" : "secondary"}>
                      {c.is_active ? "Активен" : "Неактивен"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Members panel ───────────────────────────────────────────────────────────

interface MembersPanelProps {
  committee: Committee;
}

const MembersPanel = ({ committee }: MembersPanelProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [personId, setPersonId] = useState("");
  const [role, setRole] = useState("member");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMembers(await committeesApi.listMembers(committee.id));
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить состав"));
    } finally {
      setLoading(false);
    }
  }, [committee.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!personId.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      await committeesApi.addMember(committee.id, { person_id: personId.trim(), role });
      setPersonId("");
      await load();
    } catch (err) {
      setFormError(asApiError(err, "Не удалось добавить члена"));
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (memberId: string) => {
    setFormError(null);
    try {
      await committeesApi.removeMember(committee.id, memberId);
      await load();
    } catch (err) {
      setFormError(asApiError(err, "Не удалось удалить члена"));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Состав — {committee.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="flex flex-wrap items-end gap-2" onSubmit={handleAdd}>
          <div className="flex-1 min-w-[200px] space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="member-person">
              ID сотрудника
            </label>
            <Input
              id="member-person"
              value={personId}
              onChange={(e) => setPersonId(e.target.value)}
              placeholder="person_id"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="member-role">
              Роль
            </label>
            <select
              id="member-role"
              className={selectClass}
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ROLE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={saving || !personId.trim()}>
            Добавить
          </Button>
        </form>
        <ErrorState error={formError ?? undefined} />
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка состава" /> : null}
        {!loading && !error && members.length === 0 ? (
          <EmptyState title="Нет данных" description="В комитет ещё не добавлены члены." />
        ) : null}
        {!loading && !error && members.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Сотрудник</TableHead>
                <TableHead>Роль</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{personLabel(m)}</TableCell>
                  <TableCell className="text-muted-foreground">{ROLE_LABELS[m.role] ?? m.role}</TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemove(m.id)}
                    >
                      Удалить
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Meeting list panel + create form ────────────────────────────────────────

interface MeetingListProps {
  committee: Committee;
  selected: Meeting | null;
  onSelect: (m: Meeting) => void;
}

const MeetingList = ({ committee, selected, onSelect }: MeetingListProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [items, setItems] = useState<Meeting[]>([]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [location, setLocation] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await committeesApi.listMeetings(committee.id);
      setItems(page.items);
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить заседания"));
    } finally {
      setLoading(false);
    }
  }, [committee.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scheduledAt) return;
    setSaving(true);
    setFormError(null);
    try {
      await committeesApi.createMeeting(committee.id, {
        scheduled_at: new Date(scheduledAt).toISOString(),
        location: location.trim() || null,
      });
      setScheduledAt("");
      setLocation("");
      await load();
    } catch (err) {
      setFormError(asApiError(err, "Не удалось создать заседание"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Заседания — {committee.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreate}>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="meeting-date">
              Дата и время
            </label>
            <Input
              id="meeting-date"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
          </div>
          <div className="flex-1 min-w-[160px] space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="meeting-location">
              Место
            </label>
            <Input
              id="meeting-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Место проведения"
            />
          </div>
          <Button type="submit" disabled={saving || !scheduledAt}>
            Создать заседание
          </Button>
        </form>
        <ErrorState error={formError ?? undefined} />
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка заседаний" /> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="Нет данных" description="Заседания ещё не проводились." />
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата</TableHead>
                <TableHead>Место</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((m) => (
                <TableRow
                  key={m.id}
                  className={`cursor-pointer ${selected?.id === m.id ? "bg-muted" : ""}`}
                  onClick={() => onSelect(m)}
                >
                  <TableCell className="font-medium">{formatDate(m.scheduled_at)}</TableCell>
                  <TableCell className="text-muted-foreground">{m.location ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{STATUS_LABELS[m.status] ?? m.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Attendance panel (planned meeting only) ─────────────────────────────────

interface AttendancePanelProps {
  meeting: Meeting;
  onHeld: (updated: Meeting) => void;
}

const AttendancePanel = ({ meeting, onHeld }: AttendancePanelProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [present, setPresent] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [holding, setHolding] = useState(false);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mem, att] = await Promise.all([
        committeesApi.listMembers(meeting.committee_id),
        committeesApi.getAttendance(meeting.id),
      ]);
      setMembers(mem);
      const byPerson = new Map<string, Attendance>(att.map((a) => [a.person_id, a]));
      const map: Record<string, boolean> = {};
      mem.forEach((m) => {
        map[m.person_id] = byPerson.get(m.person_id)?.present ?? false;
      });
      setPresent(map);
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить присутствие"));
    } finally {
      setLoading(false);
    }
  }, [meeting.committee_id, meeting.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const presentCount = useMemo(
    () => members.filter((m) => present[m.person_id]).length,
    [members, present],
  );
  const total = members.length;
  const hasQuorum = presentCount * 2 > total;

  const toggle = (personId: string) => {
    setSavedNote(null);
    setPresent((prev) => ({ ...prev, [personId]: !prev[personId] }));
  };

  const handleSave = async () => {
    setSaving(true);
    setActionError(null);
    setSavedNote(null);
    try {
      await committeesApi.putAttendance(
        meeting.id,
        members.map((m) => ({ person_id: m.person_id, present: Boolean(present[m.person_id]) })),
      );
      setSavedNote("Присутствие сохранено");
    } catch (err) {
      setActionError(asApiError(err, "Не удалось сохранить присутствие"));
    } finally {
      setSaving(false);
    }
  };

  const handleHold = async () => {
    setHolding(true);
    setActionError(null);
    try {
      const updated = await committeesApi.holdMeeting(meeting.id);
      onHeld(updated);
    } catch (err) {
      setActionError(asApiError(err, "Не удалось провести заседание"));
    } finally {
      setHolding(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Присутствие — {formatDate(meeting.scheduled_at)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorState error={actionError ?? undefined} />
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка присутствия" /> : null}
        {!loading && !error && members.length === 0 ? (
          <EmptyState title="Нет состава" description="Сначала добавьте членов комитета." />
        ) : null}
        {!loading && !error && members.length > 0 ? (
          <>
            <ul className="space-y-1">
              {members.map((m) => (
                <li key={m.person_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`present-${m.person_id}`}
                    checked={Boolean(present[m.person_id])}
                    onChange={() => toggle(m.person_id)}
                    className="h-4 w-4"
                  />
                  <label htmlFor={`present-${m.person_id}`} className="text-sm">
                    {personLabel(m)}{" "}
                    <span className="text-muted-foreground">({ROLE_LABELS[m.role] ?? m.role})</span>
                  </label>
                </li>
              ))}
            </ul>
            <p className="text-sm" data-testid="quorum-indicator">
              Присутствует {presentCount} из {total} —{" "}
              <span className={hasQuorum ? "text-emerald-600" : "text-destructive"}>
                {hasQuorum ? "кворум есть" : "кворум нет"}
              </span>
            </p>
            {savedNote ? <p className="text-xs text-emerald-600">{savedNote}</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={handleSave} disabled={saving}>
                Сохранить присутствие
              </Button>
              <Button type="button" onClick={handleHold} disabled={holding}>
                Провести заседание
              </Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Voting control for a single decision ────────────────────────────────────

interface DecisionVotingProps {
  decision: ProtocolDecision;
  presentMembers: MemberDetail[];
  onVoted: () => void;
}

const DecisionVoting = ({ decision, presentMembers, onVoted }: DecisionVotingProps) => {
  const [voteError, setVoteError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const outcome = decision.outcome ?? null;

  const cast = async (personId: string, choice: VoteChoice) => {
    setPending(true);
    setVoteError(null);
    try {
      await committeesApi.castVote(decision.decision.id, personId, choice);
      onVoted();
    } catch (err) {
      setVoteError(asApiError(err, "Не удалось учесть голос"));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          За: {decision.votes_for ?? 0} · Против: {decision.votes_against ?? 0} · Воздержались:{" "}
          {decision.votes_abstain ?? 0}
        </span>
        {outcome ? (
          <Badge variant={outcome === "carried" ? "default" : "destructive"}>
            {OUTCOME_LABELS[outcome] ?? outcome}
          </Badge>
        ) : null}
      </div>
      <ErrorState error={voteError ?? undefined} />
      {presentMembers.length === 0 ? (
        <p className="text-xs text-muted-foreground">Нет присутствующих для голосования.</p>
      ) : (
        <ul className="space-y-1">
          {presentMembers.map((m) => (
            <li key={m.person_id} className="flex flex-wrap items-center gap-2">
              <span className="text-sm min-w-[160px]">{personLabel(m)}</span>
              {CHOICE_OPTIONS.map((choice) => (
                <Button
                  key={choice}
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={pending}
                  onClick={() => cast(m.person_id, choice)}
                >
                  {CHOICE_LABELS[choice]}
                </Button>
              ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

// ── Create-task form for a decision ─────────────────────────────────────────

interface DecisionTaskFormProps {
  decisionId: string;
  members: MemberDetail[];
  onCreated: () => void;
}

const DecisionTaskForm = ({ decisionId, members, onCreated }: DecisionTaskFormProps) => {
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await committeesApi.createTask(decisionId, {
        assignee_person_id: assignee || null,
        due_date: dueDate || null,
        evidence_note: note.trim() || null,
      });
      setAssignee("");
      setDueDate("");
      setNote("");
      onCreated();
    } catch (err) {
      setError(asApiError(err, "Не удалось создать задачу"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={handleSubmit}>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Ответственный</label>
        <select className={selectClass} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          <option value="">— не назначен —</option>
          {members.map((m) => (
            <option key={m.person_id} value={m.person_id}>
              {personLabel(m)}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Срок</label>
        <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
      </div>
      <div className="flex-1 min-w-[160px] space-y-1">
        <label className="text-xs text-muted-foreground">Примечание</label>
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Примечание" />
      </div>
      <Button type="submit" size="sm" variant="outline" disabled={saving}>
        Добавить задачу
      </Button>
      <ErrorState error={error ?? undefined} />
    </form>
  );
};

// ── Protocol panel (proceedings, voting, decisions) ─────────────────────────

interface ProtocolPanelProps {
  meeting: Meeting;
}

const ProtocolPanel = ({ meeting }: ProtocolPanelProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [protocol, setProtocol] = useState<Protocol | null>(null);
  const [members, setMembers] = useState<MemberDetail[]>([]);
  const [presentIds, setPresentIds] = useState<Set<string>>(new Set());
  const [decisionText, setDecisionText] = useState("");
  const [savingDecision, setSavingDecision] = useState(false);
  const [decisionError, setDecisionError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [proto, mem, att] = await Promise.all([
        committeesApi.getProtocol(meeting.id),
        committeesApi.listMembers(meeting.committee_id),
        committeesApi.getAttendance(meeting.id),
      ]);
      setProtocol(proto);
      setMembers(mem);
      setPresentIds(new Set(att.filter((a) => a.present).map((a) => a.person_id)));
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить протокол"));
    } finally {
      setLoading(false);
    }
  }, [meeting.committee_id, meeting.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const presentMembers = useMemo(
    () => members.filter((m) => presentIds.has(m.person_id)),
    [members, presentIds],
  );

  const isHeld = meeting.status === "held";
  const snapshotMeeting = protocol?.meeting ?? meeting;
  const protocolNo = snapshotMeeting.protocol_no ?? meeting.protocol_no ?? null;

  const handleCreateDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!decisionText.trim()) return;
    setSavingDecision(true);
    setDecisionError(null);
    try {
      await committeesApi.createDecision(meeting.id, { text: decisionText.trim() });
      setDecisionText("");
      await load();
    } catch (err) {
      setDecisionError(asApiError(err, "Не удалось создать решение"));
    } finally {
      setSavingDecision(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Протокол{protocolNo ? ` № ${protocolNo}` : ""} — {formatDate(meeting.scheduled_at)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isHeld ? (
          <p className="text-sm text-muted-foreground">
            Присутствовало {snapshotMeeting.present_count ?? "—"} из{" "}
            {snapshotMeeting.members_total ?? "—"}
          </p>
        ) : null}
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка протокола" /> : null}

        {!loading && !error && isHeld ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreateDecision}>
            <div className="flex-1 min-w-[220px] space-y-1">
              <label className="text-xs text-muted-foreground" htmlFor="decision-text">
                Новое решение
              </label>
              <Input
                id="decision-text"
                value={decisionText}
                onChange={(e) => setDecisionText(e.target.value)}
                placeholder="Формулировка решения"
              />
            </div>
            <Button type="submit" disabled={savingDecision || !decisionText.trim()}>
              Добавить решение
            </Button>
            <ErrorState error={decisionError ?? undefined} />
          </form>
        ) : null}

        {!loading && !error && !isHeld ? (
          <p className="text-sm text-muted-foreground">
            Решения и голосование доступны после проведения заседания.
          </p>
        ) : null}

        {!loading && !error && protocol !== null && protocol.decisions.length === 0 && isHeld ? (
          <EmptyState title="Нет решений" description="Решения по заседанию ещё не внесены." />
        ) : null}

        {!loading && !error && protocol !== null && protocol.decisions.length > 0 ? (
          <div className="space-y-4">
            {protocol.decisions.map((pd) => (
              <div key={pd.decision.id} className="rounded-md border border-border p-4 space-y-3">
                <p className="text-sm font-medium">{pd.decision.text}</p>
                {pd.decision.decided_at ? (
                  <p className="text-xs text-muted-foreground">
                    Внесено: {formatDate(pd.decision.decided_at)}
                  </p>
                ) : null}

                <DecisionVoting decision={pd} presentMembers={presentMembers} onVoted={load} />

                {pd.tasks.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Срок</TableHead>
                        <TableHead>Статус</TableHead>
                        <TableHead>Примечание</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pd.tasks.map((task) => (
                        <TableRow key={task.id}>
                          <TableCell>
                            <span className="flex items-center gap-2">
                              {formatDate(task.due_date)}
                              {task.is_overdue ? (
                                <Badge variant="destructive" className="text-xs">
                                  Просрочено
                                </Badge>
                              ) : null}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{task.status}</Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {task.evidence_note ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-xs text-muted-foreground">Задачи не назначены.</p>
                )}

                <DecisionTaskForm decisionId={pd.decision.id} members={members} onCreated={load} />
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Protocol journal panel ──────────────────────────────────────────────────

interface ProtocolJournalPanelProps {
  onSelect: (item: ProtocolJournalItem) => void;
}

const ProtocolJournalPanel = ({ onSelect }: ProtocolJournalPanelProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [items, setItems] = useState<ProtocolJournalItem[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await committeesApi.listProtocols();
      setItems(page.items);
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить журнал протоколов"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Журнал протоколов</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка журнала" /> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="Нет данных" description="Проведённых заседаний пока нет." />
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Протокол №</TableHead>
                <TableHead>Комитет</TableHead>
                <TableHead>Дата</TableHead>
                <TableHead>Решений</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow
                  key={item.meeting_id}
                  className="cursor-pointer"
                  onClick={() => onSelect(item)}
                >
                  <TableCell className="font-medium">{item.protocol_no}</TableCell>
                  <TableCell>{item.committee_name}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(item.held_at)}</TableCell>
                  <TableCell>{item.decisions_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Page ────────────────────────────────────────────────────────────────────

const journalItemToMeeting = (item: ProtocolJournalItem): Meeting => ({
  id: item.meeting_id,
  committee_id: item.committee_id,
  scheduled_at: item.held_at,
  location: null,
  status: "held",
  held_at: item.held_at,
  members_total: item.members_total,
  present_count: item.present_count,
  protocol_no: item.protocol_no,
});

const CommitteesPage = () => {
  const [selectedCommittee, setSelectedCommittee] = useState<Committee | null>(null);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);

  const handleSelectCommittee = (c: Committee) => {
    setSelectedCommittee(c);
    setSelectedMeeting(null);
  };

  const handleSelectProtocol = (item: ProtocolJournalItem) => {
    setSelectedMeeting(journalItemToMeeting(item));
  };

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Комитеты"
        description="Комитеты по охране труда: состав, заседания, присутствие, голосование и протоколы решений."
      />
      <CommitteeList selected={selectedCommittee} onSelect={handleSelectCommittee} />
      {selectedCommittee !== null ? (
        <>
          <MembersPanel committee={selectedCommittee} />
          <MeetingList
            committee={selectedCommittee}
            selected={selectedMeeting}
            onSelect={setSelectedMeeting}
          />
        </>
      ) : null}
      {selectedMeeting !== null && selectedMeeting.status === "planned" ? (
        <AttendancePanel meeting={selectedMeeting} onHeld={setSelectedMeeting} />
      ) : null}
      {selectedMeeting !== null ? <ProtocolPanel meeting={selectedMeeting} /> : null}
      <ProtocolJournalPanel onSelect={handleSelectProtocol} />
    </div>
  );
};

export default CommitteesPage;
