import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { managedClientStorage } from "@/api/managedClientStorage";

const api = vi.hoisted(() => ({
  my: vi.fn(),
  enterContext: vi.fn(),
  leaveContext: vi.fn(),
}));

vi.mock("@/api/managedClients", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  managedClientsApi: api,
}));

// Срез-225: в контуре клиента у специалиста ДРУГИЕ права, и личность обязана
// перечитаться. Держим вызов под наблюдением, а не верим на слово.
const reloadIdentity = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock("@/stores/auth", () => ({
  useAuthStore: (selector: (state: { reloadIdentity: () => Promise<void> }) => unknown) =>
    selector({ reloadIdentity }),
}));

import { ClientContextSwitcher } from "@/components/common/ClientContextSwitcher";

const CLIENTS = [
  {
    client_id: "mc1",
    client_name: "ООО Ромашка",
    mode: "lightweight" as const,
    all_modules: true,
    modules: [],
  },
  {
    client_id: "mc2",
    client_name: "АО Крупный",
    mode: "dedicated" as const,
    all_modules: false,
    modules: ["documents"],
  },
];

beforeEach(() => {
  managedClientStorage.clear();
  reloadIdentity.mockClear();
  Object.values(api).forEach((fn) => fn.mockReset());
  api.my.mockResolvedValue({
    items: CLIENTS,
    scopedSections: ["Люди", "Медосмотры", "СИЗ", "Обучение", "Документы"],
  });
  api.enterContext.mockResolvedValue({
    client_id: "mc1",
    client_name: "ООО Ромашка",
    mode: "lightweight",
    all_modules: true,
    modules: [],
    audit_recorded: true,
    scoped_sections: ["Люди", "Медосмотры", "СИЗ", "Обучение", "Документы"],
    expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
  });
  api.leaveContext.mockResolvedValue(undefined);
});

describe("ClientContextSwitcher", () => {
  it("показывает мои клиенты для выбора", async () => {
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("option", { name: "ООО Ромашка" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "АО Крупный" }),
    ).toBeInTheDocument();
  });

  it("вход в контекст подтверждается сервером до записи локально", async () => {
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() => expect(api.enterContext).toHaveBeenCalledWith("mc1"));
    expect(managedClientStorage.get()).toMatchObject({
      clientId: "mc1",
      clientName: "ООО Ромашка",
    });
    // Срок приезжает с сервера: считать его на клиенте значит разъехаться
    // с сервером на часовых поясах и подведённых часах.
    expect(managedClientStorage.get()?.expiresAt).toBeTruthy();
  });

  it("отказ сервера не оставляет ложный контекст", async () => {
    api.enterContext.mockRejectedValue({
      status: 403,
      message: "Нет доступа к этому клиенту",
    });
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() => expect(api.enterContext).toHaveBeenCalled());
    // локально ничего не записано — интерфейс не показывает работу «от имени»,
    // которой на сервере не случилось
    expect(managedClientStorage.get()).toBeNull();
    expect(
      screen.queryByTestId("client-context-banner"),
    ).not.toBeInTheDocument();
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

  it("индикатор честно называет разделы, где фильтр уже действует", async () => {
    managedClientStorage.set({ clientId: "mc1", clientName: "ООО Ромашка" });
    render(<ClientContextSwitcher />);

    const sections = await screen.findByTestId("client-context-sections");
    expect(sections).toHaveTextContent("Люди");
    expect(sections).toHaveTextContent("Медосмотры");
    expect(sections).toHaveTextContent("СИЗ");
    expect(sections).toHaveTextContent("Документы");
    // Обещать фильтр там, где его нет, — прямой путь к данным не того клиента.
    expect(sections).toHaveTextContent("В остальных — данные всех клиентов");
  });

  it("выход из контекста — в один клик", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    managedClientStorage.set({ clientId: "mc1", clientName: "ООО Ромашка" });
    render(<ClientContextSwitcher onContextChange={onChange} />);

    await user.click(
      await screen.findByRole("button", { name: "Выйти из контекста" }),
    );

    expect(managedClientStorage.get()).toBeNull();
    expect(onChange).toHaveBeenCalledWith(null);
    expect(
      screen.queryByTestId("client-context-banner"),
    ).not.toBeInTheDocument();
  });

  it("без доступных клиентов переключатель не мозолит глаза", async () => {
    api.my.mockResolvedValue({ items: [], scopedSections: [] });
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

describe("ClientContextSwitcher — контур Dedicated-клиента (срез-225)", () => {
  it("ключ от контура сохраняется вместе с контекстом", async () => {
    // Порознь они бессмысленны: контекст без ключа открывает пустоту, ключ без
    // контекста — это запрос к чужому арендатору без основания.
    api.enterContext.mockResolvedValue({
      client_id: "mc1",
      client_name: "ООО Ромашка",
      mode: "dedicated",
      all_modules: true,
      modules: [],
      audit_recorded: true,
      scoped_sections: [],
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      contour: {
        tenant_slug: "romashka",
        access_token: "contour-token",
        token_type: "bearer",
        role: "ot_specialist",
        display_name: "Иванов (Северстрой)",
      },
    });
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() => expect(api.enterContext).toHaveBeenCalledWith("mc1"));
    expect(managedClientStorage.get()?.contour).toMatchObject({
      tenantSlug: "romashka",
      accessToken: "contour-token",
      role: "ot_specialist",
    });
  });

  it("контура нет — человеку говорят ПОЧЕМУ, а не показывают пустые разделы", async () => {
    api.enterContext.mockResolvedValue({
      client_id: "mc1",
      client_name: "ООО Ромашка",
      mode: "dedicated",
      all_modules: true,
      modules: [],
      audit_recorded: true,
      scoped_sections: [],
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      contour: null,
      contour_reason: "Клиент отозвал согласие на ведение",
    });
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("client-context-contour-reason"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("client-context-contour-reason"),
    ).toHaveTextContent("Клиент отозвал согласие на ведение");
    expect(managedClientStorage.get()?.contour).toBeUndefined();
  });

  it("вход в контур перечитывает права: меню не останется от аутсорсера", async () => {
    // Без этого повторяется расхождение среза-223, только между арендаторами:
    // меню нарисовано по правам аутсорсера, а ручки клиента отвечают отказом.
    api.enterContext.mockResolvedValue({
      client_id: "mc1",
      client_name: "ООО Ромашка",
      mode: "dedicated",
      all_modules: true,
      modules: [],
      audit_recorded: true,
      scoped_sections: [],
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      contour: {
        tenant_slug: "romashka",
        access_token: "contour-token",
        token_type: "bearer",
        role: "ot_specialist",
        display_name: "Иванов (Северстрой)",
      },
    });
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() => expect(reloadIdentity).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Выйти из контекста" }));

    // Вернулись к себе — права тоже свои.
    await waitFor(() => expect(reloadIdentity).toHaveBeenCalledTimes(2));
  });

  it("у Lightweight-клиента права не перечитываются: контур не менялся", async () => {
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() =>
      expect(screen.getByTestId("client-context-banner")).toBeInTheDocument(),
    );
    expect(reloadIdentity).not.toHaveBeenCalled();
  });

  it("у Lightweight-клиента причины нет и она не показывается", async () => {
    const user = userEvent.setup();
    render(<ClientContextSwitcher />);
    await waitFor(() =>
      expect(screen.getByTestId("client-context-switcher")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Работать от имени клиента"),
      "mc1",
    );

    await waitFor(() =>
      expect(screen.getByTestId("client-context-banner")).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("client-context-contour-reason"),
    ).not.toBeInTheDocument();
  });
});

describe("ClientContextSwitcher — срок работы «от имени» (срез-10)", () => {
  it("показывает, сколько осталось", async () => {
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "ООО Ромашка",
      expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    });
    render(<ClientContextSwitcher />);

    const counter = await screen.findByTestId("client-context-countdown");
    expect(counter).toHaveTextContent(/Осталось \d+ мин/);
  });

  it("протухший контекст не показывается вовсе", async () => {
    // Вкладка пролежала ночь. Показать баннер «вы работаете от имени» нельзя:
    // сервер такой контекст уже не признаёт, а данные НЕ отфильтрованы.
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "ООО Ромашка",
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });
    render(<ClientContextSwitcher />);

    await waitFor(() =>
      expect(
        screen.queryByTestId("client-context-banner"),
      ).not.toBeInTheDocument(),
    );
    expect(managedClientStorage.get()).toBeNull();
  });

  it("выход сообщает серверу, а не только гасит баннер", async () => {
    const user = userEvent.setup();
    managedClientStorage.set({ clientId: "mc1", clientName: "ООО Ромашка" });
    render(<ClientContextSwitcher />);

    await user.click(
      await screen.findByRole("button", { name: "Выйти из контекста" }),
    );

    await waitFor(() => expect(api.leaveContext).toHaveBeenCalled());
    expect(managedClientStorage.get()).toBeNull();
  });

  it("сбой сети при выходе всё равно выпускает из контекста", async () => {
    // Иначе специалист остаётся в чужом контексте с ошибкой на экране —
    // худшее сочетание из возможных.
    api.leaveContext.mockRejectedValue(new Error("network"));
    const user = userEvent.setup();
    managedClientStorage.set({ clientId: "mc1", clientName: "ООО Ромашка" });
    render(<ClientContextSwitcher />);

    await user.click(
      await screen.findByRole("button", { name: "Выйти из контекста" }),
    );

    await waitFor(() => expect(managedClientStorage.get()).toBeNull());
    expect(
      screen.queryByTestId("client-context-banner"),
    ).not.toBeInTheDocument();
  });
});
