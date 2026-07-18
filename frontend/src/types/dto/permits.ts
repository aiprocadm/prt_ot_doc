export type PermitStatus = "active" | "expired" | "revoked";

export interface PermitDto {
  id: string;
  person_id: string;
  position_id?: string | null;
  permit_type: string;
  issued_at: string;
  valid_until?: string | null;
  status: PermitStatus;
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface PermitPage {
  items: PermitDto[];
  total: number;
}

export interface PermitCreatePayload {
  person_id: string;
  permit_type: string;
  issued_at?: string;
  valid_until?: string;
}

export interface PermitUpdatePayload {
  permit_type?: string;
  valid_until?: string;
}
