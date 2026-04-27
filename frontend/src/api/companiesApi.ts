import type { CompanyDto, CompanyStatus, UpdateCompanyDto } from "@/types/dto/companies";
import type { CompanyFormValues } from "@/types/forms/companies";
import type { DocumentDto } from "@/types/dto/documents";

/** Только поля, которые принимает бэкенд (CompanyCreate / CompanyUpdate). Без status, tags, website — в модели API их нет. */
export function buildCompanyWriteBody(values: CompanyFormValues): UpdateCompanyDto {
  const body: UpdateCompanyDto = {
    name: values.name.trim()
  };
  const inn = values.inn.trim();
  if (inn) body.inn = inn;
  const kpp = values.kpp?.trim() ?? "";
  if (kpp) body.kpp = kpp;
  const ogrn = values.ogrn?.trim() ?? "";
  if (ogrn) body.ogrn = ogrn;
  if (values.address != null && values.address !== "") {
    body.address = values.address;
  }
  const email = typeof values.email === "string" ? values.email.trim() : "";
  if (email) body.email = email;
  const phone = values.phone?.trim() ?? "";
  if (phone) body.phone_numbers = [phone];
  return body;
}

const asStatus = (value: unknown): CompanyStatus => {
  if (value === "draft" || value === "active" || value === "archived") return value;
  return "active";
};

/** Приводит ответ API (CompanyRead) к полям CompanyDto для UI. */
export function normalizeCompanyRead(raw: unknown): CompanyDto {
  const r = raw as Record<string, unknown>;
  const now = new Date().toISOString();
  const phoneNumbers = Array.isArray(r.phone_numbers) ? r.phone_numbers : [];
  const phoneFirst = typeof phoneNumbers[0] === "string" ? phoneNumbers[0] : undefined;
  const legal =
    typeof r.legal_address === "string"
      ? r.legal_address
      : typeof r.address === "string"
        ? r.address
        : undefined;

  return {
    id: String(r.id ?? ""),
    created_at: typeof r.created_at === "string" ? r.created_at : now,
    updated_at: typeof r.updated_at === "string" ? r.updated_at : typeof r.created_at === "string" ? r.created_at : now,
    name: String(r.name ?? ""),
    inn: typeof r.inn === "string" ? r.inn : "",
    kpp: typeof r.kpp === "string" ? r.kpp : undefined,
    ogrn: typeof r.ogrn === "string" ? r.ogrn : undefined,
    address: legal,
    email: typeof r.email === "string" ? r.email : undefined,
    phone: phoneFirst,
    website: typeof r.website === "string" ? r.website : undefined,
    status: asStatus(r.status),
    tags: Array.isArray(r.tags) ? (r.tags as string[]) : undefined,
    documents: Array.isArray(r.documents) ? (r.documents as DocumentDto[]) : undefined
  };
}
