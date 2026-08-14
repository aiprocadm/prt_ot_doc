import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FleetUsagePanel, formatBytes } from "@/features/tenants/FleetUsagePanel";

const usageMock = vi.fn();

vi.mock("@/api/tenants", () => ({
  tenantsApi: { usage: (period?: string) => usageMock(period) },
  isNotManagingTenantError: () => false,
}));

const report = (overrides: Record<string, unknown> = {}) => ({
  period: "202608",
  items: [
    {
      tenant_id: "t-1",
      slug: "acme",
      name: "ООО Акме",
      doc_generations: 12,
      storage_bytes: 1_572_864,
      active_workers: 42,
    },
  ],
  total_doc_generations: 12,
  total_storage_bytes: 1_572_864,
  total_active_workers: 42,
  not_measured: ["ЭДО: отправка не подключена, считать нечего"],
  ...overrides,
});

describe("расход клиентов в кабинете (BIZ-52 разд. 52.4)", () => {
  beforeEach(() => {
    usageMock.mockReset();
    usageMock.mockResolvedValue(report());
  });

  it("показывает расход по клиенту", async () => {
    render(<FleetUsagePanel />);

    expect(await screen.findByText("ООО Акме")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("байты показывает по-человечески", async () => {
    render(<FleetUsagePanel />);

    // 1 572 864 байта — это 1,5 МБ; сырое число человек читать не станет.
    expect(await screen.findByText("1,5 МБ")).toBeInTheDocument();
  });

  it("называет то, что не учитывается", async () => {
    // Молчание читалось бы как «ЭДО не пользуются».
    render(<FleetUsagePanel />);

    expect(await screen.findByText(/ЭДО: отправка не подключена/)).toBeInTheDocument();
  });

  it("пустой месяц объясняется словами", async () => {
    usageMock.mockResolvedValue(
      report({
        items: [],
        total_doc_generations: 0,
        total_storage_bytes: 0,
        total_active_workers: 0,
      }),
    );
    render(<FleetUsagePanel />);

    expect(await screen.findByText(/расхода не было/)).toBeInTheDocument();
  });

  it("сбой запроса не ломает страницу клиентов", async () => {
    // Расход — не главное на этой странице: без него заводить клиентов можно.
    usageMock.mockRejectedValue(new Error("нет доступа"));
    const { container } = render(<FleetUsagePanel />);

    await waitFor(() => expect(usageMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("перевод байтов", () => {
  it("подбирает единицу по величине", () => {
    expect(formatBytes(512)).toBe("512 Б");
    expect(formatBytes(2048)).toBe("2 КБ");
    expect(formatBytes(1_572_864)).toBe("1,5 МБ");
    expect(formatBytes(3 * 1024 ** 3)).toBe("3 ГБ");
  });

  it("ноль и мусор не ломают показ", () => {
    expect(formatBytes(0)).toBe("0 Б");
    expect(formatBytes(-5)).toBe("0 Б");
    expect(formatBytes(Number.NaN)).toBe("0 Б");
  });

  it("целые байты не дробит", () => {
    // «1536,0 Б» выглядело бы как ошибка расчёта.
    expect(formatBytes(999)).toBe("999 Б");
  });
});
