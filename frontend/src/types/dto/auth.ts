import type { BaseEntityDto } from "./common";

export interface UserDto extends BaseEntityDto {
  email: string;
  full_name: string;
  roles: string[];
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
