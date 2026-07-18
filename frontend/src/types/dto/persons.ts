import type { BaseEntityDto, FileLinkDto } from "./common";

export type PersonStatus = "active" | "inactive" | "dismissed";

export interface CertificationDto {
  id: string;
  title: string;
  valid_to?: string;
  issued_at?: string;
  issuer?: string;
  attachment?: FileLinkDto | null;
}

export interface PersonDto extends BaseEntityDto {
  company_id?: string;
  first_name: string;
  last_name: string;
  middle_name?: string;
  full_name: string;
  position?: string;
  email?: string;
  phone?: string;
  status: PersonStatus;
  certifications?: CertificationDto[];
  photo?: FileLinkDto | null;
  qualifications?: Array<Record<string, unknown>>;
}

export interface UpdatePersonDto {
  company_id?: string;
  first_name: string;
  last_name: string;
  middle_name?: string;
  position?: string;
  email?: string;
  phone?: string;
  status?: PersonStatus;
  certifications?: CertificationDto[];
}
