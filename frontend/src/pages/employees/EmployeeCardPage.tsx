import { ArrowLeft, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { employeesApi } from "@/api/employees";
import {
  INCIDENT_SEVERITY_LABELS,
  INCIDENT_TYPE_LABELS,
} from "@/api/incidents";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { lightLabel, lightVariant } from "@/lib/lights";
import type { ApiError } from "@/types/dto/common";
import type {
  EmployeeAuditItemDto,
  EmployeeBriefingItemDto,
  EmployeeCardDto,
  EmployeeComplianceDeadlineItemDto,
  EmployeeDisciplinesSectionDto,
  EmployeeDocumentItemDto,
  EmployeeIncidentItemDto,
  EmployeeInternshipItemDto,
  EmployeeMedicalItemDto,
  EmployeePermitItemDto,
  EmployeePPEIssueItemDto,
  EmployeeTrainingCertificateDto,
  EmployeeTrainingItemDto,
} from "@/types/dto/employee";

const EMPLOYMENT_STATUS_LABELS: Record<string, string> = {
  active: "Работает",
  on_leave: "В отпуске",
  suspended: "Отстранён",
  terminated: "Уволен",
};

const TRAINING_STATUS_LABELS: Record<string, string> = {
  scheduled: "Запланировано",
  in_progress: "В процессе",
  completed: "Пройдено",
  failed: "Провалено",
};

const PERMIT_STATUS_LABELS: Record<string, string> = {
  active: "Действует",
  expired: "Истёк",
  revoked: "Отозван",
};

// Срез-160: не хватало «Списано» и «Заменено» — карточка показывала их
// техническим кодом (`written_off`, `replaced`). Оба статуса живые: списание
// идёт ручкой снятия СИЗ, замена — при истечении срока носки. Состав словаря
// сверяется с перечислением сервера (tests/test_ppe_issue_status_vocab.py).
const PPE_ISSUE_STATUS_LABELS: Record<string, string> = {
  issued: "Выдано",
  returned: "Возвращено",
  written_off: "Списано",
  replaced: "Заменено",
  lost: "Утрачено",
};

// Срез-150: словарь видов происшествия один на продукт («@/api/incidents»);
// копия здесь и список на экране происшествий успели разойтись.

const INCIDENT_STATUS_LABELS: Record<string, string> = {
  reported: "Зарегистрирован",
  investigating: "Расследование",
  corrective_actions: "Меры",
  closed: "Закрыт",
  cancelled: "Отменён",
};

const INCIDENT_ROLE_LABELS: Record<string, string> = {
  victim: "Пострадавший",
  witness: "Свидетель",
  participant: "Участник",
};

const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  generated: "Сгенерирован",
  review: "На проверке",
  approved: "Утверждён",
  signed: "Подписан",
  archived: "В архиве",
  revoked: "Отозван",
};

/**
 * Подписи видов инструктажа. Список написан руками и УСПЕЛ РАЗОЙТИСЬ с ядром
 * (найдено срезом-5 контура БДД, разд. 56.2):
 *
 * - ключ `repeated` не существовал никогда — в ядре код `repeat`, и повторный
 *   инструктаж всё это время показывался сырым кодом;
 * - шести противопожарных видов, заведённых разд. 54.1, здесь не было вовсе.
 *
 * Подстраховки нет: `labelFor` печатает сырой ключ, и человек видел на
 * карточке `fire_ptm`. Соответствие ядру пинает сторож
 * `tests/test_road_safety_briefings.py`.
 */
const BRIEFING_TYPE_LABELS: Record<string, string> = {
  introductory: "Вводный",
  primary: "Первичный на рабочем месте",
  repeat: "Повторный",
  unscheduled: "Внеплановый",
  targeted: "Целевой",
  fire_introductory: "Противопожарный вводный",
  fire_primary: "Противопожарный первичный",
  fire_repeat: "Противопожарный повторный",
  fire_unscheduled: "Противопожарный внеплановый",
  fire_targeted: "Противопожарный целевой",
  fire_ptm: "Пожарно-технический минимум (ПТМ)",
  road_introductory: "Вводный инструктаж по БДД",
  road_pre_trip: "Предрейсовый инструктаж",
  road_seasonal: "Сезонный инструктаж по БДД",
  road_special: "Специальный инструктаж по БДД",
};

const BRIEFING_STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  signed: "Подписан",
  cancelled: "Отменён",
};

const DEADLINE_ENTITY_LABELS: Record<string, string> = {
  medical_exam: "Медосмотр",
  training_session: "Обучение",
  training: "Обучение",
  ppe_issue: "Выдача СИЗ",
  permit: "Допуск",
  briefing: "Инструктаж",
  document: "Документ",
};

const DEADLINE_STATUS_LABELS: Record<string, string> = {
  upcoming: "Запланирован",
  due_soon: "Скоро срок",
  overdue: "Просрочен",
  closed: "Закрыт",
  completed: "Выполнен",
  cancelled: "Отменён",
};

const labelFor = (
  map: Record<string, string>,
  key: string | null | undefined,
) => (key && map[key]) || (key ?? "—");

const formatDate = (iso: string | null | undefined) => {
  if (!iso) return "—";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso ?? "—";
  }
};

const formatDateTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso ?? "—";
  }
};

const Info = ({ label, value }: { label: string; value?: string | null }) => (
  <div>
    <div className="text-xs uppercase text-muted-foreground">{label}</div>
    <div className="text-sm font-medium">
      {value && value !== "" ? value : "—"}
    </div>
  </div>
);

const TabBadge = ({ count, danger }: { count: number; danger?: boolean }) =>
  count > 0 ? (
    <Badge
      variant={danger ? "destructive" : "secondary"}
      className="ml-2 px-1.5 text-[11px]"
    >
      {count}
    </Badge>
  ) : null;

const EmptyTabContent = ({ message }: { message: string }) => (
  <p className="text-sm text-muted-foreground">{message}</p>
);

const PersonalTab = ({ card }: { card: EmployeeCardDto }) => {
  const { personal } = card;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Info label="Компания" value={personal.company_name} />
      <Info label="Должность" value={personal.position_name} />
      <Info label="Рабочее место" value={personal.workplace_name} />
      <Info
        label="Статус занятости"
        value={labelFor(EMPLOYMENT_STATUS_LABELS, personal.employment_status)}
      />
      <Info label="Дата приёма" value={formatDate(personal.hired_at)} />
      <Info label="Дата рождения" value={formatDate(personal.birth_date)} />
      <Info label="Email" value={personal.email} />
      <Info label="Телефон" value={personal.phone} />
      <Info label="Табельный номер" value={personal.personnel_number} />
      <Info label="СНИЛС" value={personal.snils} />
      <Info
        label="Класс условий труда"
        value={personal.working_conditions_class}
      />
      {personal.hazardous_factors.length > 0 ? (
        <div className="md:col-span-2">
          <div className="text-xs uppercase text-muted-foreground">
            Вредные факторы
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {personal.hazardous_factors.map((factor) => (
              <Badge key={factor} variant="outline" className="text-xs">
                {factor}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const RolesTab = ({ card }: { card: EmployeeCardDto }) => {
  const { roles_and_assignments: roles } = card;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <Info label="Компания" value={roles.company_name} />
        <Info label="Должность" value={roles.position_name} />
        <Info label="Рабочее место" value={roles.workplace_name} />
        <Info
          label="Статус занятости"
          value={labelFor(EMPLOYMENT_STATUS_LABELS, roles.employment_status)}
        />
      </div>
      <div className="rounded-md border p-3">
        <div className="text-xs uppercase text-muted-foreground">
          Системный аккаунт
        </div>
        {roles.user_account ? (
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <Info label="Email" value={roles.user_account.email} />
            <Info label="Основная роль" value={roles.user_account.role} />
            <Info
              label="Активен"
              value={roles.user_account.is_active ? "да" : "нет"}
            />
            <Info
              label="Последний вход"
              value={formatDateTime(roles.user_account.last_login_at)}
            />
            {roles.user_account.additional_roles.length > 0 ? (
              <div className="md:col-span-2">
                <div className="text-xs uppercase text-muted-foreground">
                  Дополнительные роли
                </div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {roles.user_account.additional_roles.map((role) => (
                    <Badge key={role} variant="outline" className="text-xs">
                      {role}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            Нет связанной учётной записи.
          </p>
        )}
      </div>
    </div>
  );
};

const TrainingTab = ({ card }: { card: EmployeeCardDto }) => {
  const { training } = card;
  const internships = training.internships ?? [];
  if (
    training.sessions.length === 0 &&
    training.certificates.length === 0 &&
    internships.length === 0
  ) {
    return <EmptyTabContent message="Нет записей об обучении." />;
  }
  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-sm font-semibold">
          Курсы и сессии · {training.sessions_count}
        </h3>
        {training.sessions.length === 0 ? (
          <EmptyTabContent message="Сессии обучения не зафиксированы." />
        ) : (
          <Card className="mt-2">
            <CardContent className="px-0 pb-0 pt-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Курс</TableHead>
                    <TableHead className="w-[140px]">Статус</TableHead>
                    <TableHead className="w-[140px]">Начало</TableHead>
                    <TableHead className="w-[140px]">Завершение</TableHead>
                    <TableHead className="w-[100px] text-right">Балл</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {training.sessions.map((session: EmployeeTrainingItemDto) => (
                    <TableRow key={session.id}>
                      <TableCell className="text-sm font-medium">
                        {session.course_title ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {labelFor(
                          TRAINING_STATUS_LABELS,
                          String(session.status),
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {formatDate(session.started_at)}
                      </TableCell>
                      <TableCell className="text-sm">
                        {formatDate(session.completed_at)}
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {session.score ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </section>
      <section>
        <h3 className="text-sm font-semibold">
          Удостоверения · {training.certificates_count}
        </h3>
        {training.certificates.length === 0 ? (
          <EmptyTabContent message="Удостоверения не зарегистрированы." />
        ) : (
          <Card className="mt-2">
            <CardContent className="px-0 pb-0 pt-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Курс</TableHead>
                    <TableHead className="w-[160px]">Номер</TableHead>
                    <TableHead className="w-[140px]">Выдано</TableHead>
                    <TableHead className="w-[140px]">Действует до</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {training.certificates.map(
                    (cert: EmployeeTrainingCertificateDto) => (
                      <TableRow key={cert.id}>
                        <TableCell className="text-sm font-medium">
                          {cert.course_title ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm font-mono">
                          {cert.code ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {formatDate(cert.issued_at)}
                        </TableCell>
                        <TableCell className="text-sm">
                          {formatDate(cert.valid_until)}
                        </TableCell>
                      </TableRow>
                    ),
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </section>
      <section>
        <h3 className="text-sm font-semibold">
          Стажировки · {training.internships_count ?? 0}
          <Link
            to={`/internships?person_id=${encodeURIComponent(card.person_id)}`}
            className="ml-3 text-xs font-normal text-primary underline"
          >
            открыть в реестре
          </Link>
        </h3>
        {/* Та же запись, что в общем реестре /internships: недобор — факт
            расхождения плана и факта, а не вердикт о допуске к работе. */}
        {internships.length === 0 ? (
          <EmptyTabContent message="Стажировки не назначались." />
        ) : (
          <Card className="mt-2">
            <CardContent className="px-0 pb-0 pt-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Предмет</TableHead>
                    <TableHead className="w-[200px]">Наставник</TableHead>
                    <TableHead className="w-[120px] text-right">
                      Смены
                    </TableHead>
                    <TableHead className="w-[140px]">Состояние</TableHead>
                    <TableHead className="w-[200px]">Период</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {internships.map((item: EmployeeInternshipItemDto) => (
                    <TableRow key={item.id}>
                      <TableCell className="text-sm font-medium">
                        {item.subject ?? "—"}
                        {item.discipline_label ? (
                          <div className="text-xs text-muted-foreground">
                            {item.discipline_label}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm">
                        {item.mentor_name ?? "Не назначен"}
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {item.completed_shifts} / {item.planned_shifts}
                      </TableCell>
                      <TableCell className="text-sm">
                        {item.status_label}
                        {item.completed_short ? (
                          <Badge variant="destructive" className="ml-2">
                            недобор
                          </Badge>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm">
                        {formatDate(item.started_on)} —{" "}
                        {formatDate(item.finished_on)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
};

const MedicalsTab = ({ card }: { card: EmployeeCardDto }) => {
  const { medicals } = card;
  if (medicals.items.length === 0) {
    return <EmptyTabContent message="Медосмотры не найдены." />;
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Тип</TableHead>
              <TableHead className="w-[140px]">Дата</TableHead>
              <TableHead className="w-[160px]">Действителен до</TableHead>
              <TableHead>Заключение</TableHead>
              <TableHead className="w-[100px]">Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {medicals.items.map((exam: EmployeeMedicalItemDto) => (
              <TableRow key={exam.id}>
                <TableCell className="text-sm font-medium">
                  {exam.exam_type}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDate(exam.exam_date)}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDate(exam.valid_until)}
                </TableCell>
                <TableCell className="text-sm">
                  {exam.conclusion ?? "—"}
                </TableCell>
                <TableCell>
                  {exam.is_expired ? (
                    <Badge variant="destructive">Просрочен</Badge>
                  ) : (
                    <Badge variant="secondary">Актуален</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const PPETab = ({ card }: { card: EmployeeCardDto }) => {
  const { ppe } = card;
  if (ppe.items.length === 0) {
    return <EmptyTabContent message="Выдач СИЗ нет." />;
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Номенклатура</TableHead>
              <TableHead className="w-[80px] text-right">Кол-во</TableHead>
              <TableHead className="w-[160px]">Выдано</TableHead>
              <TableHead className="w-[160px]">Действует до</TableHead>
              <TableHead className="w-[120px]">Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ppe.items.map((issue: EmployeePPEIssueItemDto) => (
              <TableRow key={issue.id}>
                <TableCell className="text-sm font-medium">
                  {issue.item_name}
                </TableCell>
                <TableCell className="text-right text-sm">
                  {issue.quantity}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDateTime(issue.issued_at)}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDateTime(issue.expires_at)}
                </TableCell>
                <TableCell>
                  {issue.is_expired ? (
                    <Badge variant="destructive">Просрочено</Badge>
                  ) : (
                    <Badge variant="secondary">
                      {labelFor(PPE_ISSUE_STATUS_LABELS, String(issue.status))}
                    </Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const PermitsTab = ({ card }: { card: EmployeeCardDto }) => {
  const { permits } = card;
  if (permits.items.length === 0) {
    return <EmptyTabContent message="Допусков и нарядов нет." />;
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Тип допуска</TableHead>
              <TableHead className="w-[140px]">Выдан</TableHead>
              <TableHead className="w-[160px]">Действует до</TableHead>
              <TableHead className="w-[120px]">Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {permits.items.map((permit: EmployeePermitItemDto) => (
              <TableRow key={permit.id}>
                <TableCell className="text-sm font-medium">
                  {permit.permit_type}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDate(permit.issued_at)}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDate(permit.valid_until)}
                </TableCell>
                <TableCell>
                  {permit.is_expired ? (
                    <Badge variant="destructive">Просрочен</Badge>
                  ) : (
                    <Badge variant="secondary">
                      {labelFor(PERMIT_STATUS_LABELS, String(permit.status))}
                    </Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const IncidentsTab = ({ card }: { card: EmployeeCardDto }) => {
  const { incidents } = card;
  if (incidents.items.length === 0) {
    return (
      <EmptyTabContent message="Происшествий с участием сотрудника не зарегистрировано." />
    );
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Заголовок</TableHead>
              <TableHead className="w-[160px]">Тип</TableHead>
              <TableHead className="w-[100px]">Тяжесть</TableHead>
              <TableHead className="w-[160px]">Дата</TableHead>
              <TableHead className="w-[140px]">Роль</TableHead>
              <TableHead className="w-[140px]">Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {incidents.items.map((incident: EmployeeIncidentItemDto) => (
              <TableRow key={incident.id}>
                <TableCell className="text-sm font-medium">
                  <Link
                    to={`/incidents?focus=${encodeURIComponent(incident.id)}`}
                    className="text-primary hover:underline"
                  >
                    {incident.title}
                  </Link>
                </TableCell>
                <TableCell className="text-sm">
                  {labelFor(
                    INCIDENT_TYPE_LABELS,
                    String(incident.incident_type),
                  )}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      String(incident.severity) === "high"
                        ? "destructive"
                        : "secondary"
                    }
                  >
                    {labelFor(
                      INCIDENT_SEVERITY_LABELS,
                      String(incident.severity),
                    )}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm">
                  {formatDateTime(incident.occurred_at)}
                </TableCell>
                <TableCell className="text-sm">
                  {labelFor(INCIDENT_ROLE_LABELS, String(incident.role))}
                </TableCell>
                <TableCell className="text-sm">
                  {labelFor(INCIDENT_STATUS_LABELS, String(incident.status))}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const DocumentsTab = ({ card }: { card: EmployeeCardDto }) => {
  const { documents } = card;
  if (documents.items.length === 0) {
    return <EmptyTabContent message="Документов по сотруднику не найдено." />;
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Шаблон</TableHead>
              <TableHead className="w-[160px]">Создан</TableHead>
              <TableHead className="w-[140px]">Статус</TableHead>
              <TableHead className="w-[120px]">Подпись</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.items.map((doc: EmployeeDocumentItemDto) => (
              <TableRow key={doc.id}>
                <TableCell className="text-sm font-medium">
                  <Link
                    to={`/documents?focus=${encodeURIComponent(doc.id)}`}
                    className="text-primary hover:underline"
                  >
                    {doc.template_name ?? "Без названия"}
                  </Link>
                </TableCell>
                <TableCell className="text-sm">
                  {formatDateTime(doc.created_at)}
                </TableCell>
                <TableCell className="text-sm">
                  {labelFor(DOCUMENT_STATUS_LABELS, String(doc.status))}
                </TableCell>
                <TableCell>
                  {doc.is_signed ? (
                    <Badge variant="secondary">Подписан</Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const BriefingsTab = ({ card }: { card: EmployeeCardDto }) => {
  const { briefings } = card;
  if (briefings.items.length === 0) {
    return <EmptyTabContent message="Инструктажей не зарегистрировано." />;
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Программа</TableHead>
              <TableHead className="w-[140px]">Тип</TableHead>
              <TableHead className="w-[160px]">Дата</TableHead>
              <TableHead className="w-[160px]">Действует до</TableHead>
              <TableHead className="w-[140px]">Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {briefings.items.map((entry: EmployeeBriefingItemDto) => (
              <TableRow key={entry.id}>
                <TableCell className="text-sm font-medium">
                  {entry.briefing_template_title ?? "Без программы"}
                </TableCell>
                <TableCell className="text-sm">
                  {labelFor(BRIEFING_TYPE_LABELS, String(entry.briefing_type))}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDateTime(entry.briefing_date)}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDateTime(entry.valid_until)}
                </TableCell>
                <TableCell>
                  {entry.is_superseded ? (
                    // перекрыта свежей записью того же вида: история, не просрочка (срез-85)
                    <Badge variant="outline">Перекрыт</Badge>
                  ) : entry.is_expired ? (
                    <Badge variant="destructive">Просрочен</Badge>
                  ) : (
                    <Badge variant="secondary">
                      {labelFor(BRIEFING_STATUS_LABELS, String(entry.status))}
                    </Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const ComplianceDeadlinesTab = ({ card }: { card: EmployeeCardDto }) => {
  const { compliance_deadlines: deadlines } = card;
  if (deadlines.items.length === 0) {
    return <EmptyTabContent message="Контрольных сроков нет." />;
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Объект</TableHead>
              <TableHead className="w-[160px]">Срок</TableHead>
              <TableHead className="w-[140px]">Статус</TableHead>
              <TableHead>Политика напоминаний</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {deadlines.items.map(
              (deadline: EmployeeComplianceDeadlineItemDto) => (
                <TableRow key={deadline.id}>
                  <TableCell className="text-sm font-medium">
                    {labelFor(
                      DEADLINE_ENTITY_LABELS,
                      String(deadline.entity_type),
                    )}
                    <div className="text-xs font-mono text-muted-foreground">
                      {deadline.entity_id}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {formatDateTime(deadline.due_at)}
                  </TableCell>
                  <TableCell>
                    {deadline.is_overdue ? (
                      <Badge variant="destructive">Просрочен</Badge>
                    ) : (
                      <Badge variant="secondary">
                        {labelFor(
                          DEADLINE_STATUS_LABELS,
                          String(deadline.status),
                        )}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {deadline.reminder_policy ?? "—"}
                  </TableCell>
                </TableRow>
              ),
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

const AuditTab = ({ card }: { card: EmployeeCardDto }) => {
  const { audit } = card;
  if (audit.items.length === 0) {
    return (
      <EmptyTabContent message="Изменений по карточке не зафиксировано." />
    );
  }
  return (
    <Card>
      <CardContent className="px-0 pb-0 pt-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[180px]">Когда</TableHead>
              <TableHead className="w-[200px]">Действие</TableHead>
              <TableHead className="w-[220px]">Кто</TableHead>
              <TableHead>Изменения</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {audit.items.map((entry: EmployeeAuditItemDto) => (
              <TableRow key={entry.id}>
                <TableCell className="text-sm">
                  {formatDateTime(entry.when)}
                </TableCell>
                <TableCell className="text-sm font-mono">
                  {entry.action}
                </TableCell>
                <TableCell className="text-sm">
                  {entry.actor_email ?? "—"}
                </TableCell>
                <TableCell className="text-xs">
                  {Object.keys(entry.changed_fields ?? {}).length > 0 ? (
                    <code className="rounded bg-muted px-1.5 py-0.5">
                      {Object.keys(entry.changed_fields).join(", ")}
                    </code>
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

/**
 * Светофор дисциплин (BIZ-54-57 срез-53, Доп. №1 разд. 57.1).
 *
 * Вкладки ниже показывают записи; этот блок отвечает на вопрос «всё ли
 * положенное у человека действует» — по каждой дисциплине словаря, теми же
 * словами и цветами, что карточка площадки 360°. Стоит НАД вкладками:
 * ответ читают первым, а записи — когда ответ красный.
 *
 * Срез-67: строка «БДД» с водителем ведёт на его карточку в контуре
 * (`/road-safety?section=drivers&person_id=`) — расшифровка называет срок
 * удостоверения, а править его можно только там. Без карточки водителя
 * (`required` = 0) ссылки нет: вести некуда.
 */
const DisciplinesCard = ({
  section,
  personId,
}: {
  section: EmployeeDisciplinesSectionDto;
  personId: string;
}) => (
  <section data-ux-block>
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">
          Дисциплины
          <Badge
            className="ml-2"
            variant={lightVariant(section.overall)}
            data-testid="employee-disciplines-overall"
          >
            {lightLabel(section.overall)}
          </Badge>
        </CardTitle>
        <CardDescription>
          {section.note ??
            "Всё ли положенное действует — по нормам должности; «Не измеряется» значит, что эталона в системе нет, а не что всё в порядке."}
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="employee-disciplines">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-1 pr-4 font-medium">Дисциплина</th>
              <th className="py-1 pr-4 font-medium">Состояние</th>
              <th className="py-1 font-medium">Расшифровка</th>
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row) => (
              <tr key={row.discipline} className="border-t align-top">
                <td className="py-2 pr-4">{row.title}</td>
                <td className="py-2 pr-4">
                  <Badge variant={lightVariant(row.light)}>
                    {lightLabel(row.light)}
                  </Badge>
                </td>
                <td className="py-2 text-muted-foreground">
                  {row.reason}
                  {row.discipline === "road_safety" && row.required > 0 ? (
                    <Link
                      to={`/road-safety?section=drivers&person_id=${encodeURIComponent(personId)}`}
                      className="ml-2 text-xs text-primary underline"
                      data-testid="employee-discipline-driver-link"
                    >
                      карточка водителя
                    </Link>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {section.not_applicable ? (
          // Скрытое по редакции не молчит: иначе пять строк вместо восьми
          // читались бы как недоделка (срез-54).
          <p
            className="mt-3 text-xs text-muted-foreground"
            data-testid="employee-disciplines-not-applicable"
          >
            {section.not_applicable}
          </p>
        ) : null}
      </CardContent>
    </Card>
  </section>
);

export default function EmployeeCardPage() {
  const { personId = "" } = useParams<{ personId: string }>();
  const navigate = useNavigate();
  const [card, setCard] = useState<EmployeeCardDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    if (!personId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await employeesApi.getCard(personId);
      setCard(data);
    } catch (err) {
      setError(
        (err as ApiError) ?? {
          status: 0,
          message: "Не удалось загрузить карточку",
          field_errors: [],
        },
      );
    } finally {
      setLoading(false);
    }
  }, [personId]);

  useEffect(() => {
    void load();
  }, [load]);

  const headerName = card
    ? card.personal.fio ||
      `${card.personal.last_name} ${card.personal.first_name}`.trim()
    : "Сотрудник";

  return (
    <div className="space-y-6 p-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Сотрудники", to: "/persons" },
          { label: headerName },
        ]}
      />

      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {headerName}
          </h1>
          {card ? (
            <p className="text-muted-foreground mt-1 text-sm">
              {card.personal.position_name ?? "Без должности"}
              {card.personal.company_name
                ? ` · ${card.personal.company_name}`
                : ""}
              {card.personal.workplace_name
                ? ` · ${card.personal.workplace_name}`
                : ""}
            </p>
          ) : null}
          {card ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Карточка собрана: {formatDateTime(card.generated_at)}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
            Назад
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={load}
            disabled={loading}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            Обновить
          </Button>
        </div>
      </div>

      <ErrorState error={error ?? undefined} onRetry={load} />

      {loading && !card ? (
        <LoadingScreen label="Загрузка карточки сотрудника" />
      ) : null}

      {!loading && !error && card ? (
        <DisciplinesCard section={card.disciplines} personId={card.person_id} />
      ) : null}

      {!loading && !error && card ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Полные данные сотрудника</CardTitle>
            <CardDescription>
              Источник — единый агрегат <code>/api/v1/employees/{"{id}"}</code>:
              персональные данные, роли, обучение, медосмотры, СИЗ, допуски,
              документы, инструктажи, контрольные сроки, происшествия и аудит.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="personal">
              <TabsList className="flex h-auto flex-wrap gap-1">
                <TabsTrigger value="personal">Персональные данные</TabsTrigger>
                <TabsTrigger value="roles">
                  Роли и назначения
                  {card.roles_and_assignments.user_account ? (
                    <Badge
                      variant="secondary"
                      className="ml-2 px-1.5 text-[11px]"
                    >
                      аккаунт
                    </Badge>
                  ) : null}
                </TabsTrigger>
                <TabsTrigger value="training">
                  Обучение
                  <TabBadge
                    count={
                      card.training.sessions_count +
                      card.training.certificates_count +
                      (card.training.internships_count ?? 0)
                    }
                  />
                </TabsTrigger>
                <TabsTrigger value="medicals">
                  Медосмотры
                  <TabBadge count={card.medicals.count} />
                  <TabBadge count={card.medicals.expired_count} danger />
                </TabsTrigger>
                <TabsTrigger value="ppe">
                  СИЗ
                  <TabBadge count={card.ppe.active_count} />
                  <TabBadge count={card.ppe.expired_count} danger />
                </TabsTrigger>
                <TabsTrigger value="permits">
                  Допуски
                  <TabBadge count={card.permits.active_count} />
                  <TabBadge count={card.permits.expired_count} danger />
                </TabsTrigger>
                <TabsTrigger value="documents">
                  Документы
                  <TabBadge count={card.documents.count} />
                  <TabBadge count={card.documents.signed_count} />
                </TabsTrigger>
                <TabsTrigger value="briefings">
                  Инструктажи
                  <TabBadge count={card.briefings.count} />
                  <TabBadge count={card.briefings.expired_count} danger />
                </TabsTrigger>
                <TabsTrigger value="deadlines">
                  Сроки
                  <TabBadge count={card.compliance_deadlines.upcoming_count} />
                  <TabBadge
                    count={card.compliance_deadlines.overdue_count}
                    danger
                  />
                </TabsTrigger>
                <TabsTrigger value="incidents">
                  Происшествия
                  <TabBadge count={card.incidents.count} />
                  <TabBadge count={card.incidents.open_count} danger />
                </TabsTrigger>
                <TabsTrigger value="audit">
                  Аудит
                  <TabBadge count={card.audit.count} />
                </TabsTrigger>
              </TabsList>

              <TabsContent value="personal">
                <PersonalTab card={card} />
              </TabsContent>
              <TabsContent value="roles">
                <RolesTab card={card} />
              </TabsContent>
              <TabsContent value="training">
                <TrainingTab card={card} />
              </TabsContent>
              <TabsContent value="medicals">
                <MedicalsTab card={card} />
              </TabsContent>
              <TabsContent value="ppe">
                <PPETab card={card} />
              </TabsContent>
              <TabsContent value="permits">
                <PermitsTab card={card} />
              </TabsContent>
              <TabsContent value="documents">
                <DocumentsTab card={card} />
              </TabsContent>
              <TabsContent value="briefings">
                <BriefingsTab card={card} />
              </TabsContent>
              <TabsContent value="deadlines">
                <ComplianceDeadlinesTab card={card} />
              </TabsContent>
              <TabsContent value="incidents">
                <IncidentsTab card={card} />
              </TabsContent>
              <TabsContent value="audit">
                <AuditTab card={card} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
