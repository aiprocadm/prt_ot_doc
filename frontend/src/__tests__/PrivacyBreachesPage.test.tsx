import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const privacyApiMock = vi.hoisted(() => ({
  breaches: vi.fn(),
  registerBreach: vi.fn(),
  markBreachStep: vi.fn(),
}));

vi.mock("@/api/privacy", () => ({
  privacyApi: {
    breaches: (...args: unknown[]) => privacyApiMock.breaches(...args),
    registerBreach: (...args: unknown[]) =>
      privacyApiMock.registerBreach(...args),
    markBreachStep: (...args: unknown[]) =>
      privacyApiMock.markBreachStep(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import PrivacyBreachesPage from "@/pages/privacy/PrivacyBreachesPage";

/**
 * Экран утечек ПДн (срез-208, 152-ФЗ разд. 66.3).
 *
 * Срез-207 завёл реестр и сроки, но только ручками: пользоваться этим не мог
 * никто, кроме того, кто умеет звать API. Обязательство, которое нельзя
 * выполнить через продукт, не выполняется вовсе.
 */

const NOTICE =
  "Платформа не отправляет уведомления в Роскомнадзор: их подают через форму регулятора.";

const breach = {
  id: "b-1",
  summary: "Выгрузка личных дел ушла на посторонний адрес",
  discovered_at: "2026-09-15T09:00:00+00:00",
  happened_at: null,
  affected_people: 37,
  deadlines: [
    {
      stage: "notify_regulator" as const,
      title: "Уведомить Роскомнадзор о факте утечки",
      due_at: "2026-09-16T09:00:00+00:00",
      done_at: null,
      status: "pending" as const,
      status_title: "Срок идёт",
      hours_left: 5,
    },
    {
      stage: "report_findings" as const,
      title: "Сообщить результаты внутреннего расследования",
      due_at: "2026-09-18T09:00:00+00:00",
      done_at: null,
      status: "overdue" as const,
      status_title: "ПРОСРОЧЕНО",
      hours_left: null,
    },
    {
      stage: "notify_subjects" as const,
      title: "Уведомить людей, чьи данные затронуты",
      due_at: null,
      done_at: null,
      status: "no_deadline" as const,
      status_title: "Срок в часах законом не задан",
      hours_left: null,
    },
  ],
};

describe("PrivacyBreachesPage", () => {
  beforeEach(() => {
    privacyApiMock.breaches.mockReset();
    privacyApiMock.registerBreach.mockReset();
    privacyApiMock.markBreachStep.mockReset();
    privacyApiMock.breaches.mockResolvedValue({
      items: [breach],
      notice: NOTICE,
    });
  });

  const renderPage = async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <PrivacyBreachesPage />
        </MemoryRouter>,
      );
    });
  };

  it("наверху говорит, чего платформа НЕ делает", async () => {
    // ГЛАВНОЕ ДЛЯ ЧЕЛОВЕКА: без этой строки экран читается как «мы уведомим
    // за вас», и организация пропустит срок, считая, что всё сделано.
    await renderPage();

    expect(screen.getByTestId("privacy-breach-notice")).toHaveTextContent(
      "не отправляет уведомления",
    );
  });

  it("показывает срок в ЧАСАХ, а не в днях", async () => {
    // «Через 1 день» потеряло бы ровно то, ради чего срок считается.
    await renderPage();

    const rows = await screen.findAllByTestId("privacy-breach-deadline");
    expect(rows[0]).toHaveTextContent("осталось часов: 5");
    expect(rows[0]).toHaveAttribute("data-status", "pending");
  });

  it("просроченный срок назван словами с сервера", async () => {
    await renderPage();

    const rows = await screen.findAllByTestId("privacy-breach-deadline");
    expect(rows[1]).toHaveTextContent("ПРОСРОЧЕНО");
    expect(rows[1]).toHaveAttribute("data-status", "overdue");
  });

  it("у каждого шага СВОЯ кнопка отметки", async () => {
    // Три обязательства закона выполняются по-разному; одна кнопка на три
    // означала бы, что выполнив лёгкое, организация считает закрытым и трудное.
    const user = userEvent.setup();
    privacyApiMock.markBreachStep.mockResolvedValue(breach);
    await renderPage();

    const buttons = await screen.findAllByRole("button", {
      name: "Отметить выполненным",
    });
    expect(buttons).toHaveLength(3);

    await act(async () => {
      await user.click(buttons[0]);
    });

    expect(privacyApiMock.markBreachStep).toHaveBeenCalledWith(
      "b-1",
      "notify_regulator",
    );
  });

  it("регистрирует утечку с моментом обнаружения", async () => {
    const user = userEvent.setup();
    privacyApiMock.registerBreach.mockResolvedValue(breach);
    await renderPage();

    await user.type(screen.getByLabelText("Что случилось"), "Письмо не туда");
    await user.type(
      screen.getByLabelText("Когда обнаружили"),
      "2026-09-15T09:00",
    );
    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Зарегистрировать" }),
      );
    });

    expect(privacyApiMock.registerBreach).toHaveBeenCalledTimes(1);
    const payload = privacyApiMock.registerBreach.mock.calls[0][0] as {
      summary: string;
      discovered_at: string;
    };
    expect(payload.summary).toBe("Письмо не туда");
    // Момент обнаружения вводит ЧЕЛОВЕК и уходит на сервер.
    expect(payload.discovered_at).toContain("2026-09-15");
  });
});
