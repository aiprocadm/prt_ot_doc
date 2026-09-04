import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TenantFormDialog } from "@/features/tenants/TenantFormDialog";

const industriesMock = vi.fn();
const provisionMock = vi.fn();

vi.mock("@/api/tenants", () => ({
  tenantsApi: {
    industries: () => industriesMock(),
    provision: (payload: unknown) => provisionMock(payload),
  },
  isNotManagingTenantError: () => false,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const openDialog = async (user: ReturnType<typeof userEvent.setup>) => {
  render(<TenantFormDialog trigger={<button>Создать</button>} />);
  await user.click(screen.getByRole("button", { name: "Создать" }));
};

describe("выбор отрасли при заведении клиента (BIZ-52 разд. 52.3)", () => {
  beforeEach(() => {
    industriesMock.mockReset();
    provisionMock.mockReset();
    industriesMock.mockResolvedValue({
      items: [
        { code: "general", title: "Общая (подходит любой организации)" },
        { code: "construction", title: "Строительство" },
      ],
    });
    provisionMock.mockResolvedValue({
      tenant: { name: "ООО Тест" },
      created: [],
      reused: [],
      warnings: [],
    });
  });

  it("показывает отрасли, полученные от сервера", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    // Зашитая копия списка разошлась бы с набором файлов эталонов на сервере.
    expect(
      await screen.findByRole("option", { name: "Строительство" }),
    ).toBeInTheDocument();
  });

  it("объясняет, на что влияет выбор", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    expect(
      await screen.findByText(
        /какие должности, опасности и меры получит новый клиент/,
      ),
    ).toBeInTheDocument();
  });

  it("отправляет выбранную отрасль", async () => {
    const user = userEvent.setup();
    await openDialog(user);
    await screen.findByRole("option", { name: "Строительство" });

    await user.type(screen.getByLabelText("Слаг"), "stroyco");
    await user.type(screen.getByLabelText("Название"), "ООО Строй");
    await user.type(
      screen.getByLabelText("E-mail владельца"),
      "owner@stroyco.ru",
    );
    await user.type(screen.getByLabelText("Пароль владельца"), "OwnerPass123");
    await user.selectOptions(screen.getByLabelText("Отрасль"), "construction");
    await user.click(screen.getByRole("button", { name: "Создать тенант" }));

    await waitFor(() => expect(provisionMock).toHaveBeenCalled());
    expect(provisionMock.mock.calls[0][0].industry).toBe("construction");
  });

  it("по умолчанию общая отрасль", async () => {
    // Прежнее поведение для тех, кто про отрасли не думает.
    const user = userEvent.setup();
    await openDialog(user);

    await waitFor(() =>
      expect(
        (screen.getByLabelText("Отрасль") as HTMLSelectElement).value,
      ).toBe("general"),
    );
  });

  it("сбой запроса списка не ломает форму", async () => {
    // Отрасль — удобство; невозможность её выбрать не должна мешать завести
    // клиента вообще.
    industriesMock.mockRejectedValue(new Error("нет сети"));
    const user = userEvent.setup();
    await openDialog(user);

    expect(await screen.findByLabelText("Слаг")).toBeInTheDocument();
  });
});
