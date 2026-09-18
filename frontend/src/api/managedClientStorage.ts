import {
  localStorageGetItem,
  localStorageRemoveItem,
  localStorageSetItem,
} from "@/utils/browserStorage";

const CONTEXT_KEY = "prt-managed-client";

/**
 * Ключ от СОБСТВЕННОГО контура Dedicated-клиента (срез-215 выдал его на
 * сервере, срез-225 научил витрину им пользоваться).
 *
 * У Lightweight-клиента данные лежат в пространстве аутсорсера, и работать с
 * ними можно тем же токеном — контура тут нет вовсе. У Dedicated они в ДРУГОМ
 * арендаторе, куда прежний токен не пускает: без этого ключа специалист входил
 * в контекст клиента и не видел ничего.
 */
export type StoredClientContour = {
  tenantSlug: string;
  accessToken: string;
  /** Роль, которую специалист получил в контуре клиента (там он не админ). */
  role: string;
  /** Как личность подписана в списке пользователей клиента. */
  displayName: string;
};

export type StoredClientContext = {
  clientId: string;
  clientName: string;
  /**
   * Когда работа «от имени» истекает (срез-10). Храним МОМЕНТ, а не остаток:
   * вкладка, пролежавшая ночь в фоне, при пробуждении обязана показать
   * «время вышло», а не досчитывать вчерашние 40 минут.
   */
  expiresAt?: string;
  /** Есть только у Dedicated-клиента; у Lightweight поле пустое. */
  contour?: StoredClientContour;
};

/**
 * BIZ-49 разд. 49.3: активный контекст «работаю от имени клиента».
 *
 * Контекст ПЕРЕЖИВАЕТ перезагрузку страницы — специалист не должен терять его
 * от случайного F5. Плата за это — риск забыть, что работаешь от чужого имени,
 * поэтому интерфейс обязан показывать постоянный заметный индикатор
 * (`ClientContextBanner`), а не прятать состояние в выпадающем списке.
 */
let contextValue: StoredClientContext | null = null;

const parseContour = (raw: unknown): StoredClientContour | undefined => {
  if (!raw || typeof raw !== "object") return undefined;
  const value = raw as Record<string, unknown>;
  // Половина ключа хуже, чем его отсутствие: запрос ушёл бы к чужому
  // арендатору со своим токеном. Принимаем только полную пару.
  if (
    typeof value.tenantSlug !== "string" ||
    typeof value.accessToken !== "string" ||
    !value.tenantSlug ||
    !value.accessToken
  ) {
    return undefined;
  }
  return {
    tenantSlug: value.tenantSlug,
    accessToken: value.accessToken,
    role: typeof value.role === "string" ? value.role : "",
    displayName:
      typeof value.displayName === "string" ? value.displayName : "",
  };
};

const parse = (raw: string | null): StoredClientContext | null => {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed.clientId === "string" &&
      typeof parsed.clientName === "string"
    ) {
      return {
        clientId: parsed.clientId,
        clientName: parsed.clientName,
        expiresAt:
          typeof parsed.expiresAt === "string" ? parsed.expiresAt : undefined,
        contour: parseContour(parsed.contour),
      };
    }
    return null;
  } catch {
    return null;
  }
};

export const managedClientStorage = {
  hydrate(): void {
    contextValue = parse(localStorageGetItem(CONTEXT_KEY));
  },

  get(): StoredClientContext | null {
    if (contextValue) return contextValue;
    contextValue = parse(localStorageGetItem(CONTEXT_KEY));
    return contextValue;
  },

  set(context: StoredClientContext): void {
    contextValue = context;
    localStorageSetItem(CONTEXT_KEY, JSON.stringify(context));
  },

  clear(): void {
    contextValue = null;
    localStorageRemoveItem(CONTEXT_KEY);
  },

  /**
   * Ключ от контура активного клиента, если он есть.
   *
   * Отдельный метод, а не чтение поля: ключом пользуется перехватчик запросов
   * на КАЖДОМ обращении, и истёкший контекст не должен продолжать открывать
   * чужой контур. Срок проверяется здесь же — одним местом для всех.
   */
  contour(now: number = Date.now()): StoredClientContour | null {
    const context = this.get();
    if (!context || this.isExpired(context, now)) return null;
    return context.contour ?? null;
  },

  /** Истёк ли срок работы «от имени» (проверяется на КАЖДОМ чтении в интерфейсе). */
  isExpired(
    context: StoredClientContext | null,
    now: number = Date.now(),
  ): boolean {
    if (!context?.expiresAt) return false;
    const at = Date.parse(context.expiresAt);
    return Number.isFinite(at) && at <= now;
  },
};
