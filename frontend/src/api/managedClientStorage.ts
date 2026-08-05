import { localStorageGetItem, localStorageRemoveItem, localStorageSetItem } from "@/utils/browserStorage";

const CONTEXT_KEY = "prt-managed-client";

export type StoredClientContext = {
  clientId: string;
  clientName: string;
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

const parse = (raw: string | null): StoredClientContext | null => {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.clientId === "string" && typeof parsed.clientName === "string") {
      return { clientId: parsed.clientId, clientName: parsed.clientName };
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
  }
};
