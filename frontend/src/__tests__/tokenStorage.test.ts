import { beforeEach, describe, expect, it } from "vitest";

import { tokenStorage } from "@/api/tokenStorage";

const createTokenWithExp = (expiresAtSeconds: number) => {
  const payload = btoa(JSON.stringify({ exp: expiresAtSeconds }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return ["header", payload, "signature"].join(".");
};

describe("tokenStorage", () => {
  beforeEach(() => {
    tokenStorage.clear();
    window.sessionStorage.clear();
  });

  it("сохраняет и возвращает токены", () => {
    tokenStorage.setTokens({ accessToken: "access", refreshToken: "refresh", expiresIn: 10 });
    expect(tokenStorage.getAccessToken()).toBe("access");
    expect(tokenStorage.getRefreshToken()).toBe("refresh");
    expect(window.sessionStorage.getItem("prt-refresh-token")).toBe("refresh");
  });

  it("восстанавливает refresh токен из sessionStorage", () => {
    window.sessionStorage.setItem("prt-refresh-token", "stored");
    tokenStorage.hydrate();
    expect(tokenStorage.getRefreshToken()).toBe("stored");

    tokenStorage.clear();
    expect(tokenStorage.getRefreshToken()).toBeNull();
    expect(window.sessionStorage.getItem("prt-refresh-token")).toBeNull();
  });

  it("derives expiry from JWT when expiresIn is absent", () => {
    const expiresAtSeconds = Math.floor(Date.now() / 1000) + 120;
    const accessToken = createTokenWithExp(expiresAtSeconds);

    tokenStorage.setTokens({ accessToken, refreshToken: "refresh" });

    expect(tokenStorage.getExpiresAt()).toBe(expiresAtSeconds * 1000 - 10_000);
  });
});
