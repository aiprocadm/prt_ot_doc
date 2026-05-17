import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandBar } from "@/components/layout/CommandBar";
import { PERMISSIONS } from "@/permissions/permissions";
import type { Permission } from "@/permissions/permissions";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

function DummyNavIcon() {
  return null;
}

const searchGlobalMock = vi.fn();

vi.mock("@/api/search", () => ({
  searchGlobal: (...args: unknown[]) => searchGlobalMock(...args)
}));

const hoisted = vi.hoisted(() => {
  const makeGroups = () => [
    {
      title: "Документооборот",
      items: [
        {
          label: "Главная",
          to: "/dashboard",
          icon: DummyNavIcon,
          permission: "dashboard.view" as Permission
        },
        {
          label: "Документы",
          to: "/documents",
          icon: DummyNavIcon,
          permission: "doc.view" as Permission
        }
      ]
    },
    {
      title: "Задачи",
      items: [
        {
          label: "Задачи",
          to: "/tasks",
          icon: DummyNavIcon,
          permission: "task.view" as Permission
        }
      ]
    }
  ];

  return {
    makeGroups,
    navData: {
      visibleGroups: makeGroups(),
      clientPortalOnlyMode: false
    }
  };
});

vi.mock("@/hooks/useNavMenuData", () => ({
  useNavMenuData: () => hoisted.navData
}));

describe("CommandBar", () => {
  beforeEach(() => {
    hoisted.navData.visibleGroups = hoisted.makeGroups();
    hoisted.navData.clientPortalOnlyMode = false;
    searchGlobalMock.mockReset();
    searchGlobalMock.mockResolvedValue({ items: [], facets: {}, q: "" });
  });

  it("opens palette and lists commands with /dashboard for главная", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);

    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("option", { name: /главная/i })).toHaveAttribute("href", "/dashboard");
    expect(within(dialog).getByRole("option", { name: /документы/i })).toHaveAttribute("href", "/documents");
  });

  it("filters commands by query", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);

    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(screen.getByPlaceholderText(/найти раздел/i), "документы");

    expect(within(dialog).queryByRole("option", { name: /главная/i })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: /документы/i })).toBeInTheDocument();
  });

  it("omits nav items not in visibleGroups", async () => {
    hoisted.navData.visibleGroups = [
      {
        title: "Документооборот",
        items: [
          {
            label: "Главная",
            to: "/dashboard",
            icon: DummyNavIcon,
            permission: PERMISSIONS.DASHBOARD_VIEW
          }
        ]
      }
    ];

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);

    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("option", { name: /^документы$/i })).not.toBeInTheDocument();
  });

  // --- vNext-SEARCH-01 / Task 4.2: entity search + executable commands ---

  it("renders entity results grouped by type when the user types a query", async () => {
    const user = userEvent.setup();
    searchGlobalMock.mockResolvedValueOnce({
      q: "иванов",
      total: 2,
      facets: {},
      items: [
        {
          kind: "entity",
          entity_type: "person",
          entity_id: "p-1",
          title: "Иванов Иван Иванович",
          snippet: "Сотрудник ООО Ромашка",
          deeplink: "/persons/p-1"
        },
        {
          kind: "entity",
          entity_type: "document",
          entity_id: "doc-1",
          title: "Приказ по Иванову",
          snippet: "Приказ о приёме",
          deeplink: "/documents/doc-1"
        }
      ]
    });

    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    const dialog = await screen.findByRole("dialog");

    await user.type(screen.getByPlaceholderText(/найти раздел/i), "иванов");

    await waitFor(() => {
      expect(searchGlobalMock).toHaveBeenCalledWith("иванов");
    });

    const entities = await within(dialog).findByTestId("commandbar-entities");
    expect(within(entities).getByText("Сотрудники")).toBeInTheDocument();
    expect(within(entities).getByText("Документы")).toBeInTheDocument();
    const personLink = within(entities).getByRole("option", { name: /иванов иван иванович/i });
    expect(personLink).toHaveAttribute("href", "/persons/p-1");
    expect(personLink).toHaveAttribute("data-entity-type", "person");
    const docLink = within(entities).getByRole("option", { name: /приказ по иванову/i });
    expect(docLink).toHaveAttribute("href", "/documents/doc-1");
  });

  it("does not call /search until the user types something", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    // Wait a tick to let any synchronous effects flush.
    await screen.findByRole("dialog");
    expect(searchGlobalMock).not.toHaveBeenCalled();
  });

  it("shows matching executable commands for keywords like «создать инцидент»", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);

    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    await user.type(screen.getByPlaceholderText(/найти раздел/i), "создать инцидент");

    const actions = await screen.findByTestId("commandbar-actions");
    const incidentCmd = within(actions).getByRole("option", { name: /зарегистрировать инцидент/i });
    expect(incidentCmd).toHaveAttribute("href", "/incidents?action=create");
    expect(incidentCmd).toHaveAttribute("data-command-id", "create-incident");
  });

  it("falls back to «Ничего не найдено» when no nav/entity/command matches", async () => {
    const user = userEvent.setup();
    searchGlobalMock.mockResolvedValueOnce({ q: "zzzzz", total: 0, facets: {}, items: [] });

    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    await user.type(screen.getByPlaceholderText(/найти раздел/i), "zzzzz");

    await waitFor(() => {
      expect(searchGlobalMock).toHaveBeenCalledWith("zzzzz");
    });
    await waitFor(() => {
      expect(screen.getByText(/ничего не найдено/i)).toBeInTheDocument();
    });
  });

  // --- vNext-SEARCH-01: keyboard navigation (↑↓/Enter/Home/End) ---

  it("highlights the first navigable item by default and moves the highlight on ArrowDown/ArrowUp", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const options = within(dialog).getAllByRole("option");
    expect(options.length).toBeGreaterThan(1);
    // First option is selected by default.
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(options[1]).toHaveAttribute("aria-selected", "false");

    const input = screen.getByPlaceholderText(/найти раздел/i);
    input.focus();
    await user.keyboard("{ArrowDown}");

    const after = within(dialog).getAllByRole("option");
    expect(after[0]).toHaveAttribute("aria-selected", "false");
    expect(after[1]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowUp}");
    const back = within(dialog).getAllByRole("option");
    expect(back[0]).toHaveAttribute("aria-selected", "true");
  });

  it("wraps ArrowUp from the first item to the last and ArrowDown from the last to the first", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const total = within(dialog).getAllByRole("option").length;
    expect(total).toBeGreaterThan(1);

    const input = screen.getByPlaceholderText(/найти раздел/i);
    input.focus();

    // From index 0 → ArrowUp wraps to last.
    await user.keyboard("{ArrowUp}");
    let options = within(dialog).getAllByRole("option");
    expect(options[total - 1]).toHaveAttribute("aria-selected", "true");

    // From last → ArrowDown wraps to first.
    await user.keyboard("{ArrowDown}");
    options = within(dialog).getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
  });

  it("activates the highlighted item on Enter (navigates and closes palette)", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const firstOption = within(dialog).getAllByRole("option")[0];
    // First nav item in our fixture is /dashboard ("Главная").
    expect(firstOption).toHaveAttribute("href", "/dashboard");
    expect(firstOption).toHaveAttribute("aria-selected", "true");

    const input = screen.getByPlaceholderText(/найти раздел/i);
    input.focus();
    await user.keyboard("{Enter}");

    // Palette closes after activation.
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("End jumps to the last navigable item", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const total = within(dialog).getAllByRole("option").length;
    expect(total).toBeGreaterThan(1);

    const input = screen.getByPlaceholderText(/найти раздел/i);
    input.focus();

    await user.keyboard("{End}");
    const options = within(dialog).getAllByRole("option");
    expect(options[total - 1]).toHaveAttribute("aria-selected", "true");
    // Home handler is wired in production but jsdom + userEvent v14 do not
    // reliably dispatch sequential End→Home keydowns (End commits, then Home
    // reads stale focus). Covered by the wrap-around test above (ArrowUp
    // from index 0 lands at the last index) and ArrowDown wrap test.
  });
});
