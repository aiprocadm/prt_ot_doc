const REFRESH_KEY = "prt-refresh-token";
let accessToken: string | null = null;
let refreshToken: string | null = null;
let expiresAt: number | null = null;

const readRefreshToken = () => {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(REFRESH_KEY);
};

const persistRefreshToken = (token: string | null) => {
  if (typeof window === "undefined") return;
  if (token) {
    window.sessionStorage.setItem(REFRESH_KEY, token);
  } else {
    window.sessionStorage.removeItem(REFRESH_KEY);
  }
};

export const tokenStorage = {
  getAccessToken: () => accessToken,
  getRefreshToken: () => refreshToken ?? readRefreshToken(),
  getExpiresAt: () => expiresAt,
  setTokens: (tokens: { accessToken: string; refreshToken: string; expiresIn: number }) => {
    accessToken = tokens.accessToken;
    refreshToken = tokens.refreshToken;
    expiresAt = Date.now() + tokens.expiresIn * 1000 - 10_000;
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
