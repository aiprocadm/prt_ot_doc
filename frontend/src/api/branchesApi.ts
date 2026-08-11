import type {
  BranchDto,
  CreateBranchDto,
  UpdateBranchDto,
} from "@/types/dto/branches";
import type { BranchFormValues } from "@/types/forms/branches";

const clean = (value: string | undefined): string | undefined => {
  const trimmed = (value ?? "").trim();
  return trimmed ? trimmed : undefined;
};

/** Тело для POST /branches (BranchCreate — с company_id). */
export function buildBranchCreateBody(
  values: BranchFormValues,
): CreateBranchDto {
  const body: CreateBranchDto = {
    company_id: values.company_id.trim(),
    name: values.name.trim(),
    status: values.status.trim() || "active",
  };
  const code = clean(values.code);
  if (code) body.code = code;
  const address = clean(values.address);
  if (address) body.address = address;
  const contactName = clean(values.contact_name);
  if (contactName) body.contact_name = contactName;
  const contactPhone = clean(values.contact_phone);
  if (contactPhone) body.contact_phone = contactPhone;
  const contactEmail = clean(values.contact_email);
  if (contactEmail) body.contact_email = contactEmail;
  return body;
}

/** Тело для PATCH /branches/{id} (BranchUpdate — без company_id). */
export function buildBranchUpdateBody(
  values: BranchFormValues,
): UpdateBranchDto {
  const body: UpdateBranchDto = {
    name: values.name.trim(),
    status: values.status.trim() || "active",
  };
  const code = clean(values.code);
  if (code) body.code = code;
  const address = clean(values.address);
  if (address) body.address = address;
  const contactName = clean(values.contact_name);
  if (contactName) body.contact_name = contactName;
  const contactPhone = clean(values.contact_phone);
  if (contactPhone) body.contact_phone = contactPhone;
  const contactEmail = clean(values.contact_email);
  if (contactEmail) body.contact_email = contactEmail;
  return body;
}

const asString = (value: unknown): string | undefined =>
  typeof value === "string" && value !== "" ? value : undefined;

/** Приводит ответ API (BranchRead) к BranchDto для UI. */
export function normalizeBranchRead(raw: unknown): BranchDto {
  const r = raw as Record<string, unknown>;
  return {
    id: String(r.id ?? ""),
    company_id: String(r.company_id ?? ""),
    name: String(r.name ?? ""),
    code: asString(r.code),
    address: asString(r.address),
    contact_name: asString(r.contact_name),
    contact_phone: asString(r.contact_phone),
    contact_email: asString(r.contact_email),
    status: asString(r.status) ?? "active",
  };
}
