import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { managedClientStorage } from "@/api/managedClientStorage";

const api = vi.hoisted(() => ({
  my: vi.fn(),
  enterContext: vi.fn()
}));

vi.mock("@/api/managedClients", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  managedClientsApi: api
}));

import { ClientContextSwitcher } from "@/components/common/ClientContextSwitcher";

const CLIENTS = [
  {
    client_id: "mc1",
    client_name: "ООО Ромашка",
    mode: "lightweight" as const,
    all_modules: true,
    modules: []
  },
  {
    client_id: "mc2",
    client_name: "АО Крупный",
    mode: "dedicated" as const,
    all_modules: false,
    modules: ["documents"]
  }
];

beforeEach(() => {
  managedClientStorage.clear();
  Object.values(api).forEach((fn) => fn.mockReset());
  api.my.mockResolvedValue(CLIENTS);
  api.enterContext.mockResolvedValue({
    client_id: "mc1",
    client_name: "ООО Ромашка",
    mode: "lightweight",
    all_modules: true,
    modules: [],
    audit_recorded: true
  });
});

describe("ClientContextSwitcher", () => {
  it("показывает мои клиенты для выбора", async () => {
    render(<ClientContextSwitcher />);
    await waitFor(() => expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "ООО Ромашка" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "АО Крупный" })).toBeInTheDocument();
  });

  it("вход в контекст подтверждается сервером до записи локально", async () => {
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() => expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Работать от имени клиента"), "mc1");

    await waitFor(() => expect(api.enterContext).toHaveBeenCalledWith("mc1"));
    expect(managedClientStorage.get()).toEqual({
      clientId: "mc1",
      clientName: "ООО Ромашка"
    });
  });

  it("отказ сервера не оставляет ложный контекст", async () => {
    api.enterContext.mockRejectedValue({ status: 403, message: "Нет доступа к этому клиенту" });
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() => expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Работать от имени клиента"), "mc1");

    await waitFor(() => expect(api.enterContext).toHaveBeenCalled());
    // локально ничего не записано — интерфейс не показывает работу «от имени»,
    // которой на сервере не случилось
    expect(managedClientStorage.get()).toBeNull();
    expect(screen.queryByTestId("client-context-banner")).not.toBeInTheDocument();
  });

  it("активный контекст показан ЗАМЕТНЫМ постоянным индикатором", async () => {
    managedClientStorage.set({ clientId: "mc1", clientName: "ООО Ромашка" });
    render(<ClientContextSwitcher />);

    const banner = await screen.findByTestId("client-context-banner");
    expect(banner).toHaveAttribute("role", "status");
    expect(banner).toHaveTextContent("Вы работаете от имени");
    expect(banner).toHaveTextContent("ООО Ромашка");
    expect(banner).toHaveTextContent("Действия фиксируются в аудите");
  });

  it("выход из контекста — в один клик", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    managedClientStorage.set({ clientId: "mc1", clientName: "ООО Ромашка" });
    render(<ClientContextSwitcher onContextChange={onChange} />);

    await user.click(await screen.findByRole("button", { name: "Выйти из контекста" }));

    expect(managedClientStorage.get()).toBeNull();
    expect(onChange).toHaveBeenCalledWith(null);
    expect(screen.queryByTestId("client-context-banner")).not.toBeInTheDocument();
  });

  it("без доступных клиентов переключатель не мозолит глаза", async () => {
    api.my.mockResolvedValue([]);
    const { container } = render(<ClientContextSwitcher />);
    await waitFor(() => expect(api.my).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("выключенный модуль не ломает шапку", async () => {
    api.my.mockRejectedValue({ status: 404, code: "MANAGED_CLIENTS_DISABLED" });
    const { container } = render(<ClientContextSwitcher />);
    await waitFor(() => expect(api.my).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
