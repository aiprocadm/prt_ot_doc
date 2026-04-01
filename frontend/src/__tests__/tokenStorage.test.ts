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
  });

  it("сохраняет и возвращает access токен", () => {
    tokenStorage.setTokens({ accessToken: "access", expiresIn: 10 });
    expect(tokenStorage.getAccessToken()).toBe("access");

    tokenStorage.clear();
    expect(tokenStorage.getAccessToken()).toBeNull();
  });

  it("derives expiry from JWT when expiresIn is absent", () => {
    const expiresAtSeconds = Math.floor(Date.now() / 1000) + 120;
    const accessToken = createTokenWithExp(expiresAtSeconds);

    tokenStorage.setTokens({ accessToken });

    expect(tokenStorage.getExpiresAt()).toBe(expiresAtSeconds * 1000 - 10_000);
  });
});
