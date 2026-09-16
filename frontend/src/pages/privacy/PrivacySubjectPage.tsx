import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  privacySubjectApi,
  type PdnAccessLogPageDto,
  type PdnConsentPageDto,
  type PdnErasureResultDto,
  type PdnSubjectExportDto,
} from "@/api/privacy";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePersonsStore } from "@/stores/persons";
import { downloadBlob } from "@/utils/download";

/**
 * Права человека на его персональные данные (152-ФЗ разд. 66.2, срез-209).
 *
 * ЗАЧЕМ. Срез-208 завёл первый экран контура (реестр утечек) и назвал остаток:
 * четыре права субъекта жили только ручками. Право, которым нельзя
 * воспользоваться через продукт, не работает: человек пишет заявление, а
 * кадровик не может его исполнить, не позвав программиста.
 *
 * ЧЕТЫРЕ ПРАВА ИЗ ТАБЛИЦЫ 66.2 — четыре раздела экрана:
 * доступ (выгрузка), журнал доступа, отзыв согласия, удаление (обезличивание).
 * Уточнение и исправление — это обычное редактирование карточки сотрудника с
 * аудитом, отдельного места ему не нужно, и выдумывать его здесь не стали.
 *
 * ДВА РЕШЕНИЯ, КОТОРЫЕ ВАЖНЕЕ ВЁРСТКИ:
 *
 * 1. **«Оснований обработки не осталось» показывается КРУПНО.** Сервер уже
 *    считает `remaining_legal_bases`; пустой список означает, что обрабатывать
 *    человека больше не на чем и обезличивание стало ОБЯЗАННОСТЬЮ. Спрятать
 *    это значило бы оставить организацию нарушать закон молча.
 * 2. **Признак `truncated` у выгрузки не скрывается.** Иначе человек получит
 *    неполные данные, считая их полными, — и это хуже отказа.
 */

/**
 * Основания обработки и состояния согласия — СЛОВАМИ.
 *
 * Сторож `tests/test_frontend_raw_status_prints.py` поймал на этом экране
 * печать служебного кода: человек видел бы «consent» и «active» латиницей.
 * Состав словарей повторяет серверные `PDN_LEGAL_BASES` и
 * `PDN_CONSENT_STATUSES` — расходиться им нельзя, иначе экран однажды покажет
 * код вместо слова снова.
 */
const LEGAL_BASIS_TITLES: Record<string, string> = {
  consent: "согласие человека",
  contract: "трудовой договор",
  legal_obligation: "требование закона",
  vital_interests: "защита жизни и здоровья",
};

const CONSENT_STATUS_TITLES: Record<string, string> = {
  active: "действует",
  withdrawn: "отозвано",
  superseded: "заменено новой версией",
};

const ACTION_TITLES: Record<string, string> = {
  view_card: "Просмотр карточки",
  export: "Выгрузка данных",
  rectify: "Изменение данных",
  consent_grant: "Оформлено согласие",
  consent_withdraw: "Отозвано согласие",
  anonymize: "Обезличивание",
};

const formatMoment = (value: string | null): string => {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("ru-RU");
};

const PrivacySubjectPage = () => {
  const { items: persons, list: listPersons } = usePersonsStore();
  const [personId, setPersonId] = useState("");
  const [exported, setExported] = useState<PdnSubjectExportDto | null>(null);
  const [accessLog, setAccessLog] = useState<PdnAccessLogPageDto | null>(null);
  const [consents, setConsents] = useState<PdnConsentPageDto | null>(null);
  const [erasure, setErasure] = useState<PdnErasureResultDto | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void listPersons();
  }, [listPersons]);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const [log, consent] = await Promise.all([
        privacySubjectApi.accessLog(id),
        privacySubjectApi.consents(id),
      ]);
      setAccessLog(log);
      setConsents(consent);
    } catch {
      toast.error("Не удалось загрузить данные субъекта");
    }
  }, []);

  useEffect(() => {
    setExported(null);
    setErasure(null);
    void load(personId);
  }, [personId, load]);

  const doExport = async () => {
    setBusy(true);
    try {
      const data = await privacySubjectApi.exportSubject(personId);
      setExported(data);
      // Выгрузка по запросу человека — это файл, который ему отдают на руки.
      downloadBlob(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
        `pdn-${personId}.json`,
      );
      await load(personId);
    } catch {
      toast.error("Не удалось выгрузить данные");
    } finally {
      setBusy(false);
    }
  };

  const withdraw = async (purpose: string) => {
    setBusy(true);
    try {
      await privacySubjectApi.withdrawConsent(personId, purpose, reason);
      toast.success("Согласие отозвано");
      await load(personId);
    } catch {
      toast.error("Не удалось отозвать согласие");
    } finally {
      setBusy(false);
    }
  };

  const anonymize = async () => {
    // Обезличивание НЕОБРАТИМО — спрашиваем прямо, без «вы уверены?» вообще
    // было бы неверно, а с одним лишь «уверены?» человек не поймёт, что
    // именно исчезнет.
    if (
      !window.confirm(
        "Обезличивание необратимо: личные данные будут вычищены, а записи, " +
          "которые закон велит хранить, останутся под псевдонимом. Продолжить?",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      setErasure(await privacySubjectApi.anonymize(personId, reason));
      toast.success("Субъект обезличен");
      await load(personId);
    } catch {
      toast.error("Не удалось обезличить субъекта");
    } finally {
      setBusy(false);
    }
  };

  const noLegalBasis =
    consents !== null && consents.remaining_legal_bases.length === 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Персональные данные человека</h1>
        <p className="text-sm text-muted-foreground">
          Права субъекта по 152-ФЗ: получить свои данные, увидеть, кто к ним
          обращался, отозвать согласие, потребовать удаления.
        </p>
      </div>

      <Card>
        <CardContent className="space-y-2 pt-6">
          <Label htmlFor="pdn-person">Человек</Label>
          <select
            id="pdn-person"
            className="block h-9 w-full max-w-md rounded border px-2 text-sm"
            value={personId}
            onChange={(event) => setPersonId(event.target.value)}
          >
            <option value="">— выберите —</option>
            {persons.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      {!personId ? (
        <EmptyState
          title="Выберите человека"
          description="Здесь появятся его данные, журнал обращений и согласия."
        />
      ) : null}

      {personId ? (
        <>
          {/* ГЛАВНОЕ НА ЭКРАНЕ: оснований не осталось — обезличивание стало
              обязанностью, и молчать об этом нельзя. */}
          {noLegalBasis ? (
            <p
              className="rounded border border-rose-300 bg-rose-50 p-3 text-sm"
              data-testid="pdn-no-legal-basis"
            >
              Законных оснований обрабатывать данные этого человека не осталось.
              Обработку нужно прекратить: обезличьте субъекта.
            </p>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Право на доступ: выгрузка данных</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button onClick={() => void doExport()} disabled={busy}>
                {busy ? "Подготовка..." : "Выгрузить данные"}
              </Button>
              {exported ? (
                <div className="text-sm" data-testid="pdn-export-result">
                  <div>
                    Выгружено: {formatMoment(exported.generated_at)} ·
                    категории: {exported.data_categories.join(", ") || "—"}
                  </div>
                  {/* Признак неполноты НЕ прячем: неполная выгрузка, принятая
                      за полную, хуже отказа. */}
                  {exported.truncated ? (
                    <p
                      className="mt-2 rounded bg-amber-50 p-2"
                      data-testid="pdn-export-truncated"
                    >
                      Выгрузка неполная: часть разделов обрезана до{" "}
                      {exported.max_items_per_section} записей. Полные счётчики
                      остались внутри файла — сверьте их перед выдачей.
                    </p>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>
                Журнал доступа: кто обращался к данным
                {accessLog ? ` (${accessLog.total})` : ""}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {accessLog && accessLog.items.length > 0 ? (
                accessLog.items.map((entry) => (
                  <div
                    key={entry.id}
                    className="rounded border p-2 text-sm"
                    data-testid="pdn-access-entry"
                  >
                    <span className="font-medium">
                      {ACTION_TITLES[entry.action] ?? entry.action}
                    </span>{" "}
                    · {entry.actor_email ?? "—"} ·{" "}
                    {formatMoment(entry.occurred_at)}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  Обращений к данным этого человека пока не было.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Согласия и основания обработки</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="pdn-reason">
                  Причина (для отзыва или обезличивания)
                </Label>
                <Input
                  id="pdn-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Заявление сотрудника от 15.09.2026"
                />
              </div>
              {consents?.items.length ? (
                consents.items.map((entry) => (
                  <div
                    key={entry.id}
                    className="rounded border p-2 text-sm"
                    data-testid="pdn-consent"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{entry.purpose}</span>
                      <span className="text-xs uppercase">
                        {CONSENT_STATUS_TITLES[entry.status] ?? entry.status}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        основание:{" "}
                        {LEGAL_BASIS_TITLES[entry.legal_basis] ?? entry.legal_basis} ·
                        версия {entry.version}
                      </span>
                    </div>
                    {entry.withdrawn_at ? (
                      <div className="text-xs text-muted-foreground">
                        Отозвано: {formatMoment(entry.withdrawn_at)}
                      </div>
                    ) : (
                      <Button
                        className="mt-2"
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => void withdraw(entry.purpose)}
                      >
                        Отозвать согласие
                      </Button>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  Согласий не зафиксировано.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Право на удаление: обезличивание</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Личные данные вычищаются, а записи, которые закон велит хранить,
                остаются под псевдонимом — это и есть доказательство исполнения.
              </p>
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => void anonymize()}
              >
                Обезличить субъекта
              </Button>
              {erasure ? (
                <div className="text-sm" data-testid="pdn-erasure-result">
                  <div>Псевдоним: {erasure.pseudonym}</div>
                  <div>
                    Вычищено полей:{" "}
                    {
                      Object.values(erasure.scrubbed_fields).filter(Boolean)
                        .length
                    }
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
};

export default PrivacySubjectPage;
