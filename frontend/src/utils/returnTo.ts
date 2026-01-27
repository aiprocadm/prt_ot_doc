const RETURN_TO_KEY = "prt-return-to";

export const setReturnTo = (path: string) => {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(RETURN_TO_KEY, path);
};

export const consumeReturnTo = (): string | null => {
  if (typeof window === "undefined") return null;
  const value = window.sessionStorage.getItem(RETURN_TO_KEY);
  if (value) {
    window.sessionStorage.removeItem(RETURN_TO_KEY);
  }
  return value;
};
