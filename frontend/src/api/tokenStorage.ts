import { sessionStorageGetItem, sessionStorageRemoveItem, sessionStorageSetItem } from "@/utils/browserStorage";

const REFRESH_KEY = "prt-refresh-token";
let accessToken: string | null = null;
let refreshToken: string | null = null;
let expiresAt: number | null = null;

const EXPIRY_SKEW_MS = 10_000;

const readRefreshToken = () => {
  return sessionStorageGetItem(REFRESH_KEY);
};

const persistRefreshToken = (token: string | null) => {
  if (token) {
    sessionStorageSetItem(REFRESH_KEY, token);
  } else {
    sessionStorageRemoveItem(REFRESH_KEY);
  }
};

const decodeJwtPayload = (token: string) => {
  const [, rawPayload = ""] = token.split(".");
  if (!rawPayload) return null;
  try {
    const normalized = rawPayload
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(rawPayload.length / 4) * 4, "=");
    const decoded = globalThis.atob(normalized);
    const payload = JSON.parse(decoded) as { exp?: number };
    return typeof payload.exp === "number" ? payload : null;
  } catch {
    return null;
  }
};

const resolveExpiresAt = (token: string, expiresIn?: number) => {
  if (typeof expiresIn === "number") {
    return Date.now() + expiresIn * 1000 - EXPIRY_SKEW_MS;
  }
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000 - EXPIRY_SKEW_MS;
};

export const tokenStorage = {
  getAccessToken: () => accessToken,
  getRefreshToken: () => refreshToken ?? readRefreshToken(),
  getExpiresAt: () => expiresAt,
  setTokens: (tokens: { accessToken: string; refreshToken: string; expiresIn?: number }) => {
    accessToken = tokens.accessToken;
    refreshToken = tokens.refreshToken;
    expiresAt = resolveExpiresAt(tokens.accessToken, tokens.expiresIn);
    persistRefreshToken(refreshToken);
  },
  hydrate: () => {
    refreshToken = readRefreshToken();
  },
  clear: () => {
    accessToken = null;
    refreshToken = null;
    expiresAt = null;
    persistRefreshToken(null);
  }
};
