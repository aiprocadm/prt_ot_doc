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
    is_admin?: boolean;
  };
  last_login_at?: string;
}

export interface LoginRequestDto {
  email: string;
  password: string;
}

export interface LoginResponseDto {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserDto;
}

export interface RefreshResponseDto {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}


export interface PermissionsResponseDto {
  roles: string[];
  permissions: string[];
  abac_scopes: {
    company_ids?: string[];
    site_ids?: string[];
    project_ids?: string[];
    contractor_ids?: string[];
    allowed_statuses?: string[];
    max_risk_level?: number | null;
  };
}
