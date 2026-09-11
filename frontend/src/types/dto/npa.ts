/**
 * Реестр НПА — форма ответа `GET /npa` (backend/app/schemas/npa.py).
 *
 * Срез-141: до него витрина ждала от сервера `issuer`/`status`/`effective_at`
 * и страничную обёртку, которых у ручки никогда не было, — колонки «Орган» и
 * «Статус» показывали бы прочерк на любых данных. Теперь типы списаны с
 * сервера, а «действует / утратил силу» считается по датам `valid_from`/`valid_to`.
 */

export interface NpaClauseDto {
  id: string;
  code: string;
  text: string;
}

export interface NpaDto {
  id: string;
  code: string;
  title: string;
  edition: string;
  valid_from?: string | null;
  valid_to?: string | null;
  clauses: NpaClauseDto[];
}

export interface NpaListResponseDto {
  items: NpaDto[];
  /** Право заводить акты и редакции — только у владельца платформы. */
  can_manage: boolean;
}

export interface NpaClauseCreateDto {
  code: string;
  text: string;
}

export interface NpaActCreateDto {
  code: string;
  title: string;
  edition: string;
  valid_from?: string | null;
  valid_to?: string | null;
  clauses?: NpaClauseCreateDto[];
}

export interface NpaRevisionCreateDto {
  revision_code: string;
  title: string;
  effective_from?: string | null;
  effective_to?: string | null;
  change_summary?: string | null;
}

export interface NpaRevisionDto extends NpaRevisionCreateDto {
  id: string;
  act_id: string;
}

export interface NpaFiltersDto {
  /** Подстрока по коду и названию; сервер списка не фильтрует — ищем на витрине. */
  search?: string;
}

/**
 * Срез-142: связи акта с сущностями арендатора — то, что читает оценка
 * влияния. До среза их заводить было нечем, и «Связанные сущности» были пусты
 * на любых данных.
 */
export type NpaBindingTarget = "document" | "template_version" | "pack";

export interface NpaBindingDto {
  id: string;
  npa_id: string;
  entity_type: NpaBindingTarget;
  entity_id: string;
  ref?: string | null;
  /** Имя сущности по-человечески: «Инструкция · ООО Ромашка», «Шаблон v3», имя пакета. */
  title: string;
  /**
   * Срез-144 (разд. 19.4): по какой редакции связь сверяли в последний раз и
   * не разошлась ли она с действующей. `stale` — «не пересмотрена».
   */
  reviewed_revision_id?: string | null;
  reviewed_revision_code?: string | null;
  stale?: boolean;
}

export interface NpaBindingCreateDto {
  entity_type: NpaBindingTarget;
  entity_id: string;
  ref?: string | null;
}
