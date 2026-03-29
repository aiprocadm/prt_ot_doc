const resolveStorage = (kind: "local" | "session"): Storage | null => {
  if (typeof window === "undefined") return null;
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
};

export const localStorageGetItem = (key: string): string | null => {
  try {
    return resolveStorage("local")?.getItem(key) ?? null;
  } catch {
    return null;
  }
};

export const localStorageSetItem = (key: string, value: string) => {
  try {
    resolveStorage("local")?.setItem(key, value);
  } catch {
    // Ignore storage access failures in restricted browser contexts.
  }
};

export const localStorageRemoveItem = (key: string) => {
  try {
    resolveStorage("local")?.removeItem(key);
  } catch {
    // Ignore storage access failures in restricted browser contexts.
  }
};

export const sessionStorageGetItem = (key: string): string | null => {
  try {
    return resolveStorage("session")?.getItem(key) ?? null;
  } catch {
    return null;
  }
};

export const sessionStorageSetItem = (key: string, value: string) => {
  try {
    resolveStorage("session")?.setItem(key, value);
  } catch {
    // Ignore storage access failures in restricted browser contexts.
  }
};

export const sessionStorageRemoveItem = (key: string) => {
  try {
    resolveStorage("session")?.removeItem(key);
  } catch {
    // Ignore storage access failures in restricted browser contexts.
  }
};