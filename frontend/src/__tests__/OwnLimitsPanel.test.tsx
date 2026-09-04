import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  describeLine,
  OwnLimitsPanel,
} from "@/features/tenants/OwnLimitsPanel";
import type { OwnLimitLine } from "@/types/dto/tenants";

const ownLimitsMock = vi.fn();

vi.mock("@/api/tenants", () => ({
  tenantsApi: { ownLimits: (period?: string) => ownLimitsMock(period) },
  isNotManagingTenantError: () => false,
}));

const line = (overrides: Partial<OwnLimitLine> = {}): OwnLimitLine => ({
  code: "doc_generations",
  title: "Документы за месяц",
  unit: "шт.",
  limit: 100,
  used: 80,
  remaining: 20,
  exhausted: false,
  ...overrides,
});

const report = (items: OwnLimitLine[]) => ({
  period: "202608",
  tenant_slug: "beta",
  items,
});

describe("свои лимиты в кабинете (BIZ-52 разд. 52.4)", () => {
  beforeEach(() => {
    ownLimitsMock.mockReset();
    ownLimitsMock.mockResolvedValue(report([line()]));
  });

  it("показывает расход рядом с пределом", async () => {
    // Один предел не отвечает на вопрос «хватит ли до конца месяца».
    render(<OwnLimitsPanel />);

    expect(
      await screen.findByText(/80 шт\. из 100 шт\., осталось 20 шт\./),
    ).toBeInTheDocument();
  });

  it("исчерпание называет словом, а не только цветом", async () => {
    // Цвет один не читается людьми, которые его не различают.
    ownLimitsMock.mockResolvedValue(
      report([line({ used: 100, remaining: 0, exhausted: true })]),
    );
    render(<OwnLimitsPanel />);

    expect(await screen.findByText(/предел выбран/)).toBeInTheDocument();
  });

  it("несчитаемый расход не выдаётся за ноль", async () => {
    ownLimitsMock.mockResolvedValue(
      report([
        line({
          code: "edo_outgoing",
          title: "Исходящие ЭДО за месяц",
          used: null,
          remaining: null,
          limit: 50,
        }),
      ]),
    );
    render(<OwnLimitsPanel />);

    expect(await screen.findByText(/расход не считается/)).toBeInTheDocument();
  });

  it("байты показывает по-человечески", async () => {
    ownLimitsMock.mockResolvedValue(
      report([
        line({
          code: "storage",
          title: "Хранилище",
          unit: "байт",
          limit: 10 * 1024 * 1024,
          used: 5 * 1024 * 1024,
          remaining: 5 * 1024 * 1024,
        }),
      ]),
    );
    render(<OwnLimitsPanel />);

    expect(await screen.findByText(/5 МБ из 10 МБ/)).toBeInTheDocument();
  });

  it("клиенту панель не показывается вовсе", async () => {
    // Ручка ему закрыта — это не ошибка страницы.
    ownLimitsMock.mockRejectedValue(new Error("403"));
    const { container } = render(<OwnLimitsPanel />);

    await waitFor(() => expect(ownLimitsMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("текст строки лимита", () => {
  it("различает три случая", () => {
    expect(describeLine(line())).toBe("80 шт. из 100 шт., осталось 20 шт.");
    expect(describeLine(line({ used: null, remaining: null }))).toBe(
      "предел 100 шт., расход не считается",
    );
    expect(describeLine(line({ limit: null, remaining: null }))).toBe(
      "80 шт., без ограничения",
    );
  });

  it("без предела и без расхода говорит «не ограничено»", () => {
    expect(
      describeLine(line({ limit: null, used: null, remaining: null })),
    ).toBe("не ограничено");
  });
});
