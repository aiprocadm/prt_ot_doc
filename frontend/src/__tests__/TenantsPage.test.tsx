import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TenantsPage from "@/pages/admin/TenantsPage";
import { renderWithRouter } from "@/test-utils/renderWithRouter";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import type {
  PlanCatalog,
  TenantFeatureDto,
  TenantFleetPage,
} from "@/types/dto/tenants";

const listMock = vi.fn();
const setStatusMock = vi.fn();
const provisionMock = vi.fn();
const plansMock = vi.fn();
const setPlanMock = vi.fn();
const updateQuotasMock = vi.fn();

vi.mock("@/api/tenants", () => ({
  tenantsApi: {
    list: (...args: unknown[]) => listMock(...args),
    setStatus: (...args: unknown[]) => setStatusMock(...args),
    provision: (...args: unknown[]) => provisionMock(...args),
    plans: (...args: unknown[]) => plansMock(...args),
    setPlan: (...args: unknown[]) => setPlanMock(...args),
    updateQuotas: (...args: unknown[]) => updateQuotasMock(...args),
  },
  isNotManagingTenantError: (error: unknown) =>
    Boolean(error && (error as { status?: number }).status === 403),
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({ can: () => true }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const CATALOG: { code: string; title: string }[] = [
  { code: "committees", title: "Комитеты" },
  { code: "contractors", title: "Подрядчики" },
  { code: "medical", title: "Медосмотры" },
  { code: "report_builder", title: "Конструктор отчётов" },
  { code: "budget", title: "Бюджет безопасности" },
  { code: "sout", title: "СОУТ" },
  { code: "rules_engine", title: "Правила автоматизации" },
  { code: "warehouse", title: "Склад СИЗ" },
];

const features = (onCodes: string[]): TenantFeatureDto[] =>
  CATALOG.map((f) => ({
    code: f.code,
    title: f.title,
    on: onCodes.includes(f.code),
  }));

const planCatalog = (): PlanCatalog => ({
  features: CATALOG,
  plans: [
    {
      code: "free",
      title: "Базовый",
      feature_codes: ["committees", "contractors", "medical"],
      quotas: {
        max_doc_generations_per_month: 500,
        max_storage_mb: 5120,
        max_parallel_jobs: 2,
      },
    },
    {
      code: "pro",
      title: "Про",
      feature_codes: [
        "committees",
        "contractors",
        "medical",
        "report_builder",
        "budget",
        "sout",
      ],
      quotas: {
        max_doc_generations_per_month: 5000,
        max_storage_mb: 20480,
        max_parallel_jobs: 4,
      },
    },
  ],
});

const fleet = (overrides: Partial<TenantFleetPage> = {}): TenantFleetPage => ({
  managing_tenant_slug: "demo",
  // По умолчанию смотрит владелец платформы — так вели себя все прежние тесты
  // этой страницы. Партнёрский взгляд проверяется отдельными случаями ниже.
  viewer_level: "platform",
  can_manage_commercials: true,
  total: 2,
  items: [
    {
      tenant: {
        id: "t-1",
        name: "Демо",
        slug: "demo",
        contact_email: "admin@example.com",
        is_active: true,
        kind: "customer",
      },
      quotas: null,
      plan: null,
      features: features(CATALOG.map((f) => f.code)),
    },
    {
      tenant: {
        id: "t-2",
        name: "ООО Ньюко",
        slug: "newco",
        contact_email: "owner@newco.ru",
        is_active: true,
        kind: "customer",
      },
      quotas: {
        tenant_id: "t-2",
        max_parallel_jobs: 4,
        max_doc_generations_per_month: 2500,
        max_storage_mb: 5120,
        monthly_edo_outgoing: 0,
        enforce_billing_gate: false,
      },
      plan: "free",
      features: features(["committees", "contractors", "medical"]),
    },
  ],
  ...overrides,
});

describe("TenantsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    setStatusMock.mockReset();
    provisionMock.mockReset();
    plansMock.mockReset();
    setPlanMock.mockReset();
    updateQuotasMock.mockReset();
    plansMock.mockResolvedValue(planCatalog());
  });

  it("показывает список тенантов и помечает управляющий", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText("ООО Ньюко")).toBeInTheDocument();
    expect(screen.getByText("Демо")).toBeInTheDocument();
    expect(screen.getByText("управляющий")).toBeInTheDocument();
  });

  // BIZ-52 срез-2: тот же экран, но глазами партнёра.
  it("у партнёра экран называется «Мои клиенты»", async () => {
    listMock.mockResolvedValue(
      fleet({ viewer_level: "reseller", can_manage_commercials: false }),
    );

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText("Мои клиенты")).toBeInTheDocument();
  });

  it("партнёру не показывают кнопку смены тарифа", async () => {
    listMock.mockResolvedValue(
      fleet({ viewer_level: "reseller", can_manage_commercials: false }),
    );

    renderWithRouter(<TenantsPage />);

    await screen.findByText("ООО Ньюко");
    // Кнопка, которая всегда отвечает отказом, хуже отсутствующей.
    expect(
      screen.queryByRole("button", { name: "Изменить" }),
    ).not.toBeInTheDocument();
  });

  it("владелец платформы кнопку смены тарифа видит", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    await screen.findByText("ООО Ньюко");
    expect(
      screen.getAllByRole("button", { name: "Изменить" }).length,
    ).toBeGreaterThan(0);
  });

  it("партнёру не показывают слаг управляющего арендатора", async () => {
    listMock.mockResolvedValue(
      fleet({ viewer_level: "reseller", can_manage_commercials: false }),
    );

    renderWithRouter(<TenantsPage />);

    await screen.findByText("ООО Ньюко");
    expect(screen.queryByText("Управляющий")).not.toBeInTheDocument();
  });

  it("показывает лимиты подписки", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText(/2500 док\/мес/)).toBeInTheDocument();
  });

  it("показывает тариф тенанта", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    // newco = free → "Базовый"; demo = enterprise-набор без тарифа в мок-каталоге → "Свой набор"
    expect(await screen.findByText("Базовый")).toBeInTheDocument();
    expect(screen.getByText("Свой набор")).toBeInTheDocument();
  });

  it("назначает тенанту тариф", async () => {
    listMock.mockResolvedValue(fleet());
    setPlanMock.mockResolvedValue({});
    const user = userEvent.setup();

    renderWithRouter(<TenantsPage />);
    await screen.findByText("ООО Ньюко");

    // Открыть диалог тарифа второго тенанта (ООО Ньюко)
    const editButtons = screen.getAllByRole("button", { name: "Изменить" });
    await user.click(editButtons[1]);

    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Тариф"), "pro");
    await user.click(
      within(dialog).getByRole("button", { name: "Применить тариф" }),
    );

    await waitFor(() => expect(setPlanMock).toHaveBeenCalledWith("t-2", "pro"));
  });

  it("приостанавливает доступ тенанта", async () => {
    listMock.mockResolvedValue(fleet());
    setStatusMock.mockResolvedValue({ id: "t-2", is_active: false });
    const user = userEvent.setup();

    renderWithRouter(<TenantsPage />);
    const toggle = await screen.findByLabelText("Доступ для ООО Ньюко");
    await user.click(toggle);

    await waitFor(() =>
      expect(setStatusMock).toHaveBeenCalledWith("t-2", false),
    );
  });

  it("не даёт отключить сам управляющий тенант", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByLabelText("Доступ для Демо")).toBeDisabled();
  });

  it("объясняет ситуацию, когда тенант не управляющий", async () => {
    listMock.mockRejectedValue({ status: 403, message: "Forbidden" });

    renderWithRouter(<TenantsPage />);

    expect(
      await screen.findByText("Раздел доступен только управляющему тенанту"),
    ).toBeInTheDocument();
  });

  it("показывает пустое состояние, когда тенантов нет", async () => {
    listMock.mockResolvedValue(fleet({ items: [], total: 0 }));

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText("Тенантов пока нет")).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Замер только НАПОЛНЕННОГО экрана: пустой список карточек прошёл бы
    // любой бюджет, и проверка мерила бы пустоту (урок NotificationsPage).
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);
    await screen.findByText("ООО Ньюко");
    await screen.findByText("Базовый");

    const budget = uxBudgetDelta(document.body, "TenantsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
