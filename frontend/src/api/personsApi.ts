import { apiClient } from "@/api/client";
import type { PersonDto, PersonStatus } from "@/types/dto/persons";
import type { PersonFormValues } from "@/types/forms/persons";

/** Формирует запись electrical_safety_group из полей формы (или undefined, если группа не выбрана). */
const buildElectricalGroupQual = (
  values: PersonFormValues
): Record<string, unknown> | undefined => {
  if (!values.electrical_group) return undefined;
  return {
    kind: "electrical_safety_group",
    level: values.electrical_group,
    name: "Группа по электробезопасности",
    ...(values.electrical_group_valid_until
      ? { valid_until: values.electrical_group_valid_until }
      : {})
  };
};

/**
 * Merge-safe: берёт существующие qualifications (кроме electrical_safety_group),
 * добавляет новую запись если группа выбрана.
 */
export const mergeElectricalGroupQuals = (
  existingQuals: Array<Record<string, unknown>>,
  values: PersonFormValues
): Array<Record<string, unknown>> => {
  const others = existingQuals.filter((q) => q.kind !== "electrical_safety_group");
  const newEntry = buildElectricalGroupQual(values);
  return newEntry ? [...others, newEntry] : others;
};

type ApiEmploymentStatus = "active" | "on_leave" | "suspended" | "terminated";

const toApiEmploymentStatus = (status: PersonFormValues["status"]): ApiEmploymentStatus => {
  switch (status) {
    case "inactive":
      return "suspended";
    case "dismissed":
      return "terminated";
    default:
      return "active";
  }
};

export const employmentStatusToUi = (value: string | undefined): PersonStatus => {
  switch (value) {
    case "terminated":
      return "dismissed";
    case "suspended":
    case "on_leave":
      return "inactive";
    default:
      return "active";
  }
};

export const normalizePersonRead = (raw: unknown): PersonDto => {
  const r = raw as Record<string, unknown>;
  const employment = String(r.employment_status ?? "");
  const fio = typeof r.fio === "string" ? r.fio.trim() : "";
  const first = String(r.first_name ?? "");
  const last = String(r.last_name ?? "");
  const middle = r.middle_name != null ? String(r.middle_name) : undefined;
  const fullName =
    typeof r.full_name === "string" && r.full_name.trim()
      ? String(r.full_name).trim()
      : fio || [last, first, middle].filter(Boolean).join(" ").trim() || first || last;

  const now = new Date().toISOString();

  return {
    id: String(r.id),
    created_at: typeof r.created_at === "string" ? r.created_at : now,
    updated_at: typeof r.updated_at === "string" ? r.updated_at : typeof r.created_at === "string" ? r.created_at : now,
    first_name: first,
    last_name: last,
    middle_name: middle,
    full_name: fullName,
    position: typeof r.position_title === "string" ? r.position_title : undefined,
    email: r.email != null ? String(r.email) : undefined,
    phone: r.phone != null ? String(r.phone) : undefined,
    status: employmentStatusToUi(employment),
    company_id: typeof r.company_id === "string" ? r.company_id : undefined,
    // Прокидываем qualifications, чтобы будущий edit-режим формы не затирал прочие квалификации
    // (merge в PersonFormDialog читает их из initialData). См. handoff: пробел захвата.
    qualifications: Array.isArray(r.qualifications)
      ? (r.qualifications as Array<Record<string, unknown>>)
      : [],
  };
};

export const buildPersonCreateBody = (values: PersonFormValues) => ({
  company_id: values.company_id,
  first_name: values.first_name.trim(),
  last_name: values.last_name.trim(),
  middle_name: values.middle_name?.trim() || undefined,
  position_title: values.position?.trim() || undefined,
  email: values.email?.trim() || undefined,
  phone: values.phone?.trim() || undefined,
  employment_status: toApiEmploymentStatus(values.status),
  ...(values.qualifications !== undefined ? { qualifications: values.qualifications } : {})
});

export const buildPersonPatchBody = (values: PersonFormValues) => ({
  company_id: values.company_id,
  first_name: values.first_name.trim(),
  last_name: values.last_name.trim(),
  middle_name: values.middle_name?.trim() || undefined,
  position_title: values.position?.trim() || undefined,
  email: values.email?.trim() || undefined,
  phone: values.phone?.trim() || undefined,
  employment_status: toApiEmploymentStatus(values.status),
  ...(values.qualifications !== undefined ? { qualifications: values.qualifications } : {})
});

type PersonListResponse = { items?: unknown[]; total?: number };

/**
 * Список сотрудников по организации (API компании не отдаёт вложенных persons).
 * Берём страницу реестра и фильтруем по company_id (бэкенд пока без query company_id).
 */
export async function fetchPersonsForCompany(companyId: string, listLimit = 200): Promise<PersonDto[]> {
  const { data } = await apiClient.get<PersonListResponse>("/persons", {
    params: { limit: listLimit, offset: 0 }
  });
  const rows = (data.items ?? []).map((row) => normalizePersonRead(row));
  return rows.filter((p) => p.company_id === companyId);
}

/** Все сотрудники тенанта (для маппинга person_id→ФИО и выпадающего списка в форме допуска). */
export async function fetchAllPersons(listLimit = 500): Promise<PersonDto[]> {
  const { data } = await apiClient.get<PersonListResponse>("/persons", {
    params: { limit: listLimit, offset: 0 }
  });
  return (data.items ?? []).map((row) => normalizePersonRead(row));
}
