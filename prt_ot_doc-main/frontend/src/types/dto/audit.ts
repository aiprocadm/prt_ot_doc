import type { AuditMetadataDto, BaseEntityDto } from "./common";
import type { UserDto } from "./auth";

export interface AuditLogDto extends BaseEntityDto {
  actor: Pick<UserDto, "id" | "email" | "full_name">;
  action: string;
  entity_type: string;
  entity_id?: string;
  metadata?: AuditMetadataDto;
}

export interface AuditFiltersDto {
  search?: string;
  user_id?: string;
  action?: string;
  date_from?: string;
  date_to?: string;
}
