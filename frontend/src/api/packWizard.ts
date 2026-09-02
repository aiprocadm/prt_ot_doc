import { apiClient } from "@/api/client";

/**
 * Мастер разового комплекта (BIZ-50, ТЗ разд. 50.2).
 *
 * Шесть ручек мастера были сделаны на бэкенде шестью срезами и до сих пор не
 * вызывались НИ ОДНОЙ строкой фронта — то есть мастером мог пользоваться
 * только тот, кто ходит в API руками.
 */

export type PackScenario = {
  code: string;
  name: string;
  description: string;
  /** Дисциплина человеческим языком — по ней сценарий и ищут в каталоге. */
  discipline: string | null;
  templates: { code: string; name: string; category: string }[];
};

export type PackScenarioField = {
  name: string;
  label: string;
  required: boolean;
  /**
   * ПОДСКАЗКА ИЗ РЕЕСТРА, а НЕ ответ. Не подставляется в поле сама: отчёт
   * подписывает специалист, и он отвечает за каждое число в нём.
   */
  suggested?: string | null;
  /** Откуда взята подсказка — без источника её нельзя проверить. */
  suggested_source?: string | null;
};

export type PackScenarioFields = {
  scenario_code: string;
  scenario_name: string;
  fields: PackScenarioField[];
  /** Что платформа подставит сама — мастер это не спрашивает, но показывает. */
  known_from_client: string[];
  /** Пояснение про подсказки словами; пусто — подсказок нет. */
  suggestions_note?: string | null;
};

export type PackPreviewProblem = {
  code: string;
  message: string;
  blocking: boolean;
  rows_total: number;
};

export type PackPreview = {
  ready: boolean;
  score: number;
  documents_total: number;
  persons_total: number;
  persons_ready: number;
  documents: { template_name: string; person_name: string | null }[];
  problems: PackPreviewProblem[];
};

export type PackGenerateAccepted = {
  task_id: string;
  status_url: string;
};

export type PackTaskStatus = {
  task_id: string;
  status: string;
  metadata?: Record<string, unknown> | null;
};

export const listPackScenarios = async () => {
  const { data } = await apiClient.get<{ data: PackScenario[] }>(
    "/packs/scenarios",
  );
  return data.data;
};

export const getPackScenarioFields = async (code: string) => {
  const { data } = await apiClient.get<PackScenarioFields>(
    `/packs/scenarios/${encodeURIComponent(code)}/fields`,
  );
  return data;
};


/** Люди и объекты выбранной организации — для первого шага мастера. */
export type WizardPerson = { id: string; label: string };
export type WizardSite = { id: string; name: string };

export const listCompanyPersons = async (companyId: string) => {
  const { data } = await apiClient.get<{ items: Record<string, unknown>[] }>(
    "/persons",
    // Фильтр по организации делает СЕРВЕР: список постраничный, и отбор на
    // стороне интерфейса молча терял бы людей за пределами страницы.
    { params: { company_id: companyId, limit: 200 } },
  );
  return (data.items ?? []).map((row) => {
    const parts = [row["last_name"], row["first_name"], row["middle_name"]]
      .filter((part): part is string => typeof part === "string" && part.length > 0)
      .join(" ");
    return {
      id: String(row["id"]),
      label: parts || String(row["id"]),
    } satisfies WizardPerson;
  });
};

export const listCompanySites = async (companyId: string) => {
  const { data } = await apiClient.get<{ items: { id: string; name: string }[] }>(
    "/sites",
    { params: { company_id: companyId, limit: 200 } },
  );
  return (data.items ?? []).map((row) => ({ id: row.id, name: row.name }));
};

export type PackWizardSelection = {
  pack_code: string;
  company_id: string;
  site_id?: string | null;
  person_ids: string[];
  data: Record<string, string>;
};

export const previewPack = async (selection: PackWizardSelection) => {
  const { data } = await apiClient.post<PackPreview>(
    "/packs/preview",
    selection,
  );
  return data;
};

export const generatePack = async (selection: PackWizardSelection) => {
  const { data } = await apiClient.post<PackGenerateAccepted>(
    "/packs/generate",
    selection,
    // Ключ идемпотентности обязателен: без него повторное нажатие «Сгенерировать»
    // (или ретрай сети) запустит вторую генерацию и спишет вторую квоту.
    { headers: { "Idempotency-Key": crypto.randomUUID() } },
  );
  return data;
};

export const getPackTaskStatus = async (taskId: string) => {
  const { data } = await apiClient.get<PackTaskStatus>(
    `/tasks/pipeline-runs/${encodeURIComponent(taskId)}`,
    // Пока задача не завершилась, статус опрашивается по кругу — тост на
    // каждый неудачный опрос сделал бы экран нечитаемым.
    { silentApiErrorToast: true },
  );
  return data;
};

/** Ключ готового архива из метаданных задачи. ``null`` — ещё не готов. */
export const archiveKeyOf = (status: PackTaskStatus | null): string | null => {
  if (!status?.metadata) return null;
  const direct = status.metadata["zip_storage_key"];
  if (typeof direct === "string" && direct) return direct;
  const outputs = status.metadata["outputs"];
  if (outputs && typeof outputs === "object") {
    const nested = (outputs as Record<string, unknown>)["zip_storage_key"];
    if (typeof nested === "string" && nested) return nested;
  }
  return null;
};

export const packDownloadUrl = (storageKey: string) =>
  `/api/v1/packs/download?storage_key=${encodeURIComponent(storageKey)}`;

export const publishPackToPortal = async (payload: {
  preset_code: string;
  zip_storage_key: string;
  client_company_id?: string | null;
}) => {
  const { data } = await apiClient.post<{ id: string }>(
    "/packages/publish",
    payload,
  );
  return data;
};
