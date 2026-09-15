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

/**
 * Срез-201: из какого ящика акт. `registry` — общий реестр платформы
 * (федеральный приказ), `own` — собственный акт этой организации. Подпись
 * словами приходит С СЕРВЕРА (`scope_title`): витрина не должна знать, что
 * "own" значит «Акт организации».
 */
export type NpaScope = "registry" | "own";

export interface NpaDto {
  id: string;
  code: string;
  title: string;
  edition: string;
  valid_from?: string | null;
  valid_to?: string | null;
  clauses: NpaClauseDto[];
  scope?: NpaScope;
  scope_title?: string;
}

export interface NpaListResponseDto {
  items: NpaDto[];
  /** Право заводить акты и редакции ОБЩЕГО реестра — у владельца платформы. */
  can_manage: boolean;
  /**
   * Срез-201: право завести СВОЙ акт. Оно шире предыдущего: свой приказ ведёт
   * любая организация. Без отдельного флага кнопка «Добавить свой акт»
   * пряталась бы ровно у тех, кому она и нужна.
   */
  can_create_own?: boolean;
}

export interface NpaClauseCreateDto {
  code: string;
  text: string;
}

export interface NpaActCreateDto {
  /** Срез-201: в какой ящик писать. По умолчанию — общий реестр. */
  scope?: NpaScope;
  code: string;
  title: string;
  edition: string;
  valid_from?: string | null;
  valid_to?: string | null;
  clauses?: NpaClauseCreateDto[];
}

/**
 * Срез-202: что изменилось между двумя редакциями акта (B.18 разд. 19.4).
 *
 * `comparable: false` — это ОТКАЗ, а не «изменений нет». У редакций, заведённых
 * до среза-202, текста нет вовсе, и показать по ним пустой список значило бы
 * сказать «закон не менялся» — после чего документы никто не пересмотрит.
 */
export type NpaClauseChangeKind = "added" | "removed" | "modified";

export interface NpaClauseChangeDto {
  code: string;
  change: NpaClauseChangeKind;
  /** Подпись словами приходит с сервера: витрина код не переводит. */
  change_title: string;
  before?: string | null;
  after?: string | null;
}

export interface NpaRevisionDiffDto {
  comparable: boolean;
  /** Причина отказа словами. Пусто, когда сравнение состоялось. */
  reason: string;
  changes: NpaClauseChangeDto[];
  summary: {
    added: number;
    removed: number;
    modified: number;
    unchanged: number;
  };
  base: { id: string; revision_code: string; title: string };
  target: { id: string; revision_code: string; title: string };
}

/**
 * Срез-203 (B.18 разд. 19.1 «owner»): кто ведёт этот акт в НАШЕЙ организации.
 *
 * Ответственный арендаторский: один и тот же приказ Минтруда ведут в разных
 * организациях разные люди. `responsible: null` — «акт никто не ведёт», и это
 * честное состояние, а не пропуск данных.
 */
export interface NpaResponsibleDto {
  user_id: string;
  name: string;
}

export interface NpaResponsibleResponseDto {
  responsible: NpaResponsibleDto | null;
  candidates: Array<{ id: string; name: string; role_label?: string }>;
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
  /**
   * Срез-197: область действия связи — кого и где касается, СЛОВАМИ
   * (`{role, site}`). Пустой объект означает «весь акт»: это отдельное
   * состояние, а не пробел.
   */
  context?: Record<string, string>;
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
  /** Срез-197: кого и где касается связь. Пустой объект — «весь акт». */
  context?: { role_code?: string; site_id?: string };
}

/** Справочники области действия связи (срез-197). */
export interface NpaBindingOptionsDto {
  roles: Array<{ code: string; label: string }>;
  sites: Array<{ id: string; name: string; company_name: string }>;
}
