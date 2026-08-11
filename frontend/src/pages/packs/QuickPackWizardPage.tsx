import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listCompanies } from "@/api/companiesApi";
import {
  archiveKeyOf,
  generatePack,
  getPackScenarioFields,
  getPackTaskStatus,
  listCompanyPersons,
  listCompanySites,
  listPackScenarios,
  packDownloadUrl,
  previewPack,
  publishPackToPortal,
  type PackPreview,
  type PackScenario,
  type PackScenarioFields,
  type PackTaskStatus,
  type WizardPerson,
  type WizardSite,
} from "@/api/packWizard";
import { WizardStepper, type WizardStep } from "@/components/wizard/WizardStepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CompanyDto } from "@/types/dto/companies";

/**
 * Мастер разового комплекта (ТЗ разд. 50.2): «от выбора сценария до готового
 * ZIP — не более 4 шагов».
 *
 * Шесть ручек мастера были сделаны шестью срезами бэкенда и не вызывались НИ
 * ОДНОЙ строкой фронта: пользоваться мастером мог только тот, кто ходит в API
 * руками.
 */

const STEPS: readonly WizardStep[] = [
  { id: 1, title: "Сценарий и клиент", description: "Что оформляем и кому" },
  { id: 2, title: "Недостающие данные", description: "Только то, чего нет" },
  { id: 3, title: "Предпросмотр", description: "Что войдёт и чего не хватает" },
  { id: 4, title: "Готово", description: "Скачать или выдать клиенту" },
];

//: Как часто спрашиваем статус генерации. Реже — человек решит, что зависло;
//: чаще — лишняя нагрузка ради секунды.
const POLL_MS = 2000;

export const QuickPackWizardPage = () => {
  const [step, setStep] = useState(1);
  const [scenarios, setScenarios] = useState<PackScenario[]>([]);
  const [companies, setCompanies] = useState<CompanyDto[]>([]);
  const [scenarioCode, setScenarioCode] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [sites, setSites] = useState<WizardSite[]>([]);
  const [siteId, setSiteId] = useState("");
  const [persons, setPersons] = useState<WizardPerson[]>([]);
  const [personIds, setPersonIds] = useState<string[]>([]);
  const [fields, setFields] = useState<PackScenarioFields | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<PackPreview | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<PackTaskStatus | null>(null);
  const [published, setPublished] = useState(false);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    void listPackScenarios().then(setScenarios).catch(() => undefined);
    void listCompanies().then(setCompanies).catch(() => undefined);
  }, []);

  // Смена организации обнуляет объект и состав: они принадлежат прежней, и
  // генерация отвергла бы их (сотрудник другой организации — отказ).
  useEffect(() => {
    setSiteId("");
    setPersonIds([]);
    setPersons([]);
    setSites([]);
    if (!companyId) return;
    void listCompanySites(companyId).then(setSites).catch(() => undefined);
    void listCompanyPersons(companyId).then(setPersons).catch(() => undefined);
  }, [companyId]);

  const selection = useMemo(
    () => ({
      pack_code: scenarioCode,
      company_id: companyId,
      site_id: siteId || null,
      person_ids: personIds,
      data: answers,
    }),
    [scenarioCode, companyId, siteId, personIds, answers],
  );

  const archiveKey = archiveKeyOf(taskStatus);

  // Опрос останавливается, как только появился архив: продолжать спрашивать
  // готовое — тратить запросы и держать экран «в работе» после того, как всё
  // готово.
  useEffect(() => {
    if (!taskId || archiveKey) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRef.current = window.setInterval(() => {
      void getPackTaskStatus(taskId).then(setTaskStatus).catch(() => undefined);
    }, POLL_MS);
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [taskId, archiveKey]);

  const goToQuestions = useCallback(async () => {
    setBusy(true);
    try {
      setFields(await getPackScenarioFields(scenarioCode));
      setStep(2);
    } finally {
      setBusy(false);
    }
  }, [scenarioCode]);

  const goToPreview = useCallback(async () => {
    setBusy(true);
    try {
      setPreview(await previewPack(selection));
      setStep(3);
    } finally {
      setBusy(false);
    }
  }, [selection]);

  const startGeneration = useCallback(async () => {
    setBusy(true);
    try {
      const accepted = await generatePack(selection);
      setTaskId(accepted.task_id);
      setTaskStatus(null);
      setPublished(false);
      setStep(4);
    } finally {
      setBusy(false);
    }
  }, [selection]);

  const publish = useCallback(async () => {
    if (!archiveKey) return;
    setBusy(true);
    try {
      await publishPackToPortal({
        preset_code: scenarioCode,
        zip_storage_key: archiveKey,
        client_company_id: companyId || null,
      });
      setPublished(true);
    } finally {
      setBusy(false);
    }
  }, [archiveKey, scenarioCode, companyId]);

  const scenario = scenarios.find((item) => item.code === scenarioCode);
  const blocking = (preview?.problems ?? []).filter((item) => item.blocking);
  const warnings = (preview?.problems ?? []).filter((item) => !item.blocking);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Разовый комплект</h1>
        <p className="text-sm text-muted-foreground">
          Готовый набор документов по сценарию — за четыре шага.
        </p>
      </div>

      <WizardStepper steps={STEPS} currentStep={step} onStepClick={setStep} />

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Сценарий и клиент</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="scenario">Сценарий</Label>
              <select
                id="scenario"
                aria-label="Сценарий"
                className="w-full rounded border p-2"
                value={scenarioCode}
                onChange={(event) => setScenarioCode(event.target.value)}
              >
                <option value="">— выберите —</option>
                {scenarios.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.discipline ? `${item.discipline} · ${item.name}` : item.name}
                  </option>
                ))}
              </select>
              {scenario && (
                <p className="text-sm text-muted-foreground">{scenario.description}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="company">Организация клиента</Label>
              <select
                id="company"
                aria-label="Организация клиента"
                className="w-full rounded border p-2"
                value={companyId}
                onChange={(event) => setCompanyId(event.target.value)}
              >
                <option value="">— выберите —</option>
                {companies.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>

            {companyId && sites.length > 0 && (
              <div className="space-y-2">
                <Label htmlFor="site">Объект (если нужен)</Label>
                <select
                  id="site"
                  aria-label="Объект"
                  className="w-full rounded border p-2"
                  value={siteId}
                  onChange={(event) => setSiteId(event.target.value)}
                >
                  <option value="">— без объекта —</option>
                  {sites.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {companyId && (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">
                  Состав: на кого оформляем
                </legend>
                {persons.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    У этой организации нет сотрудников. Комплект будет оформлен на
                    организацию целиком.
                  </p>
                )}
                {/* Один сценарий на несколько человек — это и есть «комплект на
                    50 человек одним запуском» из ТЗ: генерация уже умеет список,
                    интерфейс его просто не предлагал. */}
                <div className="max-h-56 space-y-1 overflow-y-auto rounded border p-2">
                  {persons.map((person) => (
                    <label key={person.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={personIds.includes(person.id)}
                        onChange={(event) =>
                          setPersonIds((prev) =>
                            event.target.checked
                              ? [...prev, person.id]
                              : prev.filter((id) => id !== person.id),
                          )
                        }
                      />
                      {person.label}
                    </label>
                  ))}
                </div>
                {personIds.length > 0 && (
                  <p className="text-sm text-muted-foreground">
                    Выбрано: {personIds.length}
                  </p>
                )}
              </fieldset>
            )}

            <Button
              onClick={() => void goToQuestions()}
              disabled={!scenarioCode || !companyId || busy}
            >
              Дальше
            </Button>
          </CardContent>
        </Card>
      )}

      {step === 2 && fields && (
        <Card>
          <CardHeader>
            <CardTitle>Что нужно дозаполнить</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {fields.known_from_client.length > 0 && (
              <div className="rounded border bg-muted/40 p-3 text-sm">
                <div className="font-medium">Платформа подставит сама:</div>
                <ul className="list-inside list-disc text-muted-foreground">
                  {fields.known_from_client.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {fields.fields.map((field) => (
              <div key={field.name} className="space-y-1">
                <Label htmlFor={`f-${field.name}`}>
                  {field.label}
                  {field.required && <span className="text-destructive"> *</span>}
                </Label>
                <Input
                  id={`f-${field.name}`}
                  value={answers[field.name] ?? ""}
                  onChange={(event) =>
                    setAnswers((prev) => ({ ...prev, [field.name]: event.target.value }))
                  }
                />
              </div>
            ))}

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                Назад
              </Button>
              <Button onClick={() => void goToPreview()} disabled={busy}>
                Показать, что получится
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && preview && (
        <Card>
          <CardHeader>
            <CardTitle>Предпросмотр комплекта</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-sm">
              Готовность: <strong>{preview.score}%</strong> · документов:{" "}
              <strong>{preview.documents_total}</strong>
            </div>

            {blocking.length > 0 && (
              <div className="rounded border border-destructive/40 bg-destructive/5 p-3">
                <div className="font-medium">Пока сгенерировать нельзя:</div>
                <ul className="list-inside list-disc text-sm">
                  {blocking.map((item) => (
                    <li key={item.code}>{item.message}</li>
                  ))}
                </ul>
              </div>
            )}

            {warnings.length > 0 && (
              <div className="rounded border border-amber-400/50 bg-amber-50 p-3">
                <div className="font-medium">Выйдет, но с пробелами:</div>
                <ul className="list-inside list-disc text-sm">
                  {warnings.map((item) => (
                    <li key={item.code}>{item.message}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <div className="font-medium">Войдут документы:</div>
              <ul className="list-inside list-disc text-sm text-muted-foreground">
                {preview.documents.map((item, index) => (
                  <li key={`${item.template_name}-${item.person_name ?? "org"}-${index}`}>
                    {item.template_name}
                    {item.person_name ? ` — ${item.person_name}` : ""}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)}>
                Назад
              </Button>
              <Button
                onClick={() => void startGeneration()}
                // Кнопка выключена ровно по ответу сервера: гадать на фронте,
                // «хватит ли данных», значило бы завести вторую правду.
                disabled={!preview.ready || busy}
              >
                Сгенерировать
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 4 && (
        <Card>
          <CardHeader>
            <CardTitle>Комплект</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!archiveKey && (
              <p className="text-sm text-muted-foreground">
                Готовим комплект. Это занимает до нескольких минут — страницу можно не
                держать открытой, задача не потеряется.
              </p>
            )}

            {archiveKey && (
              <div className="space-y-3">
                <p className="text-sm">Комплект готов.</p>
                <div className="flex flex-wrap gap-2">
                  <Button asChild>
                    <a href={packDownloadUrl(archiveKey)}>Скачать архив</a>
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => void publish()}
                    disabled={busy || published}
                  >
                    {published ? "Выдан клиенту" : "Выдать в кабинет клиента"}
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};
