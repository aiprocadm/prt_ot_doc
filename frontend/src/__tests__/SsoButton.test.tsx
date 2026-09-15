import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const ssoApiMock = vi.hoisted(() => ({ status: vi.fn(), start: vi.fn() }));

vi.mock("@/api/sso", () => ({
  ssoApi: {
    status: (...args: unknown[]) => ssoApiMock.status(...args),
    start: (...args: unknown[]) => ssoApiMock.start(...args),
  },
}));

import { SsoButton } from "@/features/auth/SsoButton";

/**
 * Единый вход на экране входа (срез-204, BIZ-53 разд. 53.3).
 *
 * Главное здесь — кнопка появляется ТОЛЬКО там, где вход настроен. Кнопка,
 * которая всегда кончается отказом, хуже отсутствующей: человек нажмёт её
 * первой, получит ошибку и решит, что сломана платформа.
 */
describe("SsoButton", () => {
  beforeEach(() => {
    ssoApiMock.status.mockReset();
    ssoApiMock.start.mockReset();
  });

  it("не показывается там, где единый вход не настроен", async () => {
    ssoApiMock.status.mockResolvedValue({ enabled: false });

    await act(async () => {
      render(<SsoButton tenantSlug="demo" />);
    });

    expect(screen.queryByTestId("sso-login")).not.toBeInTheDocument();
  });

  it("не спрашивает сервер, пока организация не введена", async () => {
    await act(async () => {
      render(<SsoButton tenantSlug="   " />);
    });

    expect(ssoApiMock.status).not.toHaveBeenCalled();
  });

  it("уводит к провайдеру, когда вход настроен", async () => {
    const user = userEvent.setup();
    ssoApiMock.status.mockResolvedValue({ enabled: true });
    ssoApiMock.start.mockResolvedValue({
      authorization_url: "https://login.acme.ru/authorize?x=1",
    });
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign },
      writable: true,
    });

    await act(async () => {
      render(<SsoButton tenantSlug="acme" />);
    });
    await act(async () => {
      await user.click(
        await screen.findByRole("button", {
          name: "Войти через корпоративный вход",
        }),
      );
    });

    expect(assign).toHaveBeenCalledWith("https://login.acme.ru/authorize?x=1");
  });

  it("показывает ПРИЧИНУ отказа, а не общее «не удалось»", async () => {
    // «Не настроен», «заполнено не полностью» и «секрет не выдан окружению»
    // чинят разные люди; общее сообщение отправляет всех в поддержку.
    const user = userEvent.setup();
    ssoApiMock.status.mockResolvedValue({ enabled: true });
    ssoApiMock.start.mockRejectedValue({
      message: "Секрет приложения не выдан окружению — вход временно невозможен",
    });

    await act(async () => {
      render(<SsoButton tenantSlug="acme" />);
    });
    await act(async () => {
      await user.click(
        await screen.findByRole("button", {
          name: "Войти через корпоративный вход",
        }),
      );
    });

    await waitFor(() =>
      expect(
        screen.getByText(/Секрет приложения не выдан/),
      ).toBeInTheDocument(),
    );
  });
});
