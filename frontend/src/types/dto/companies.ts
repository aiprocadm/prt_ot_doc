import type { BaseEntityDto, FileLinkDto } from "./common";
import type { DocumentDto } from "./documents";
import type { PersonDto } from "./persons";

export type CompanyStatus = "draft" | "active" | "archived";

export interface CompanyDto extends BaseEntityDto {
  name: string;
  inn: string;
  kpp?: string;
  ogrn?: string;
  address?: string;
  email?: string;
  phone?: string;
  website?: string;
  status: CompanyStatus;
  updated_by?: string;
  logo?: FileLinkDto | null;
  contacts?: {
    position?: string;
    full_name?: string;
    phone?: string;
    email?: string;
  }[];
  persons?: PersonDto[];
  documents?: DocumentDto[];
  tags?: string[];
}

export interface CompanyFiltersDto {
  search?: string;
  status?: CompanyStatus;
}

export interface UpdateCompanyDto {
  name: string;
  /** Необязательно: бэкенд принимает пустое значение */
  inn?: string;
  kpp?: string;
  ogrn?: string;
  address?: string;
  email?: string;
  phone?: string;
  /** API: список телефонов компании */
  phone_numbers?: string[];
  website?: string;
  status?: CompanyStatus;
  logo_id?: string | null;
  person_ids?: string[];
  tags?: string[];
}
