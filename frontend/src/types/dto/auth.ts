import type { BaseEntityDto } from "./common";

export interface UserDto extends BaseEntityDto {
  email: string;
  full_name: string;
  roles: string[];
  permissions?: string[];
  attributes?: {
    tenant_id?: string;
    company_ids?: string[];
    site_ids?: string[];
    project_ids?: string[];
    contractor_ids?: string[];
    risk_level_max?: number | null;
    is_admin?: boolean;
  };
  last_login_at?: string;
}

export interface LoginRequestDto {
  email: string;
  password: string;
}

export interface AuthTokenPairDto {
  access_token: string;
}

export type LoginResponseDto = AuthTokenPairDto;

export type RefreshResponseDto = AuthTokenPairDto;


export interface PermissionsResponseDto {
  roles: string[];
  permissions: string[];
  abac_scopes: {
    company_ids?: string[];
    site_ids?: string[];
    project_ids?: string[];
    contractor_ids?: string[];
    risk_level_max?: number | null;
  };
}
