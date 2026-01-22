import { beforeEach, describe, expect, it } from "vitest";

import { tokenStorage } from "@/api/tokenStorage";

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
});
