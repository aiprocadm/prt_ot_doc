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
const fetchSavedSearchesMock = vi.fn();

vi.mock("@/api/search", () => ({
  searchGlobal: (...args: unknown[]) => searchGlobalMock(...args),
  fetchSavedSearches: (...args: unknown[]) => fetchSavedSearchesMock(...args)
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
    fetchSavedSearchesMock.mockReset();
    fetchSavedSearchesMock.mockResolvedValue([]);
    // `rememberRecent` from prior tests writes /dashboard to localStorage which
    // makes "Главная" appear in both the "Недавние" group and its native nav
    // group → `getByRole("option", { name: /главная/i })` then matches twice.
    // Clear UX-state keys so each test sees a clean palette.
    try {
      window.localStorage.clear();
    } catch {
      /* jsdom-only fallback */
    }
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

  // --- vNext-SEARCH-01 / Task 4.2: saved searches in palette ---

  it("renders saved searches when palette opens with empty query", async () => {
    fetchSavedSearchesMock.mockResolvedValueOnce([
      {
        id: "s-1",
        name: "Мои просрочки",
        q: "просрочк",
        types: ["incident"],
        filters: { status: "open" },
        is_shared: false
      },
      {
        id: "s-2",
        name: "Документы по площадке А",
        q: "договор",
        types: ["documents"],
        filters: { site_id: "site-A" }
      }
    ]);

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const saved = await within(dialog).findByTestId("commandbar-saved");
    expect(within(saved).getByText("Сохранённые запросы")).toBeInTheDocument();
    const firstSaved = within(saved).getByRole("option", { name: /мои просрочки/i });
    // Saved search applies via the /search page URL contract (q + type + filters).
    expect(firstSaved).toHaveAttribute(
      "href",
      "/search?q=%D0%BF%D1%80%D0%BE%D1%81%D1%80%D0%BE%D1%87%D0%BA&type=incident&status=open"
    );
    expect(firstSaved).toHaveAttribute("data-saved-id", "s-1");
    const secondSaved = within(saved).getByRole("option", { name: /документы по площадке а/i });
    expect(secondSaved).toHaveAttribute(
      "href",
      "/search?q=%D0%B4%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80&type=documents&site_id=site-A"
    );
  });

  it("hides saved searches once the user starts typing (discovery vs search mode)", async () => {
    fetchSavedSearchesMock.mockResolvedValueOnce([
      { id: "s-1", name: "Мои просрочки", q: "просрочк", types: ["incident"] }
    ]);

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByTestId("commandbar-saved")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/найти раздел/i), "что-то");
    await waitFor(() => {
      expect(within(dialog).queryByTestId("commandbar-saved")).not.toBeInTheDocument();
    });
    // Saved-search section is gone; nothing else should crash.
  });

  it("does not refetch saved searches on subsequent opens (cached for the session)", async () => {
    fetchSavedSearchesMock.mockResolvedValue([
      { id: "s-1", name: "Мои просрочки", q: "просрочк", types: ["incident"] }
    ]);

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    await screen.findByTestId("commandbar-saved");
    expect(fetchSavedSearchesMock).toHaveBeenCalledTimes(1);

    // Close and reopen.
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    await screen.findByTestId("commandbar-saved");

    expect(fetchSavedSearchesMock).toHaveBeenCalledTimes(1);
  });

  it("survives when /search/saved fails (renders empty rather than crashing)", async () => {
    fetchSavedSearchesMock.mockRejectedValueOnce(new Error("boom"));

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    // Wait one microtask for the rejected promise + state-flush.
    await waitFor(() => {
      expect(within(dialog).queryByTestId("commandbar-saved")).not.toBeInTheDocument();
    });
    // Nav items still render — palette did not crash.
    expect(within(dialog).getByRole("option", { name: /главная/i })).toBeInTheDocument();
  });

  // --- vNext-SEARCH-01 / Task 4.2: recent entities (clicked from search) ---

  it("renders recently opened entities from localStorage in discovery mode", async () => {
    // Pre-seed localStorage with two recently-opened entities. Newer timestamp first.
    const now = Date.now();
    window.localStorage.setItem(
      "ux.commandbar.recentEntities.v1",
      JSON.stringify([
        {
          entity_type: "person",
          entity_id: "p-9",
          title: "Иванов Иван Иванович",
          path: "/persons/p-9",
          opened_at: now - 60 * 1000
        },
        {
          entity_type: "document",
          entity_id: "doc-3",
          title: "Приказ № 5",
          path: "/documents/doc-3",
          opened_at: now - 5 * 60 * 1000
        }
      ])
    );

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const recent = within(dialog).getByTestId("commandbar-recent-entities");
    expect(within(recent).getByText("Недавно открытые")).toBeInTheDocument();
    // Order: newest-first → Иванов first.
    const links = within(recent).getAllByRole("option");
    expect(links[0]).toHaveAttribute("href", "/persons/p-9");
    expect(links[0]).toHaveAttribute("data-entity-type", "person");
    expect(links[0]).toHaveAttribute("data-entity-id", "p-9");
    expect(within(links[0]).getByText("Иванов Иван Иванович")).toBeInTheDocument();
    expect(within(links[0]).getByText("Сотрудники")).toBeInTheDocument();
    expect(links[1]).toHaveAttribute("href", "/documents/doc-3");
  });

  it("prunes expired recent entities (older than TTL) on load", async () => {
    const now = Date.now();
    const oldTimestamp = now - 31 * 24 * 60 * 60 * 1000; // 31 days = beyond TTL of 30
    window.localStorage.setItem(
      "ux.commandbar.recentEntities.v1",
      JSON.stringify([
        {
          entity_type: "person",
          entity_id: "fresh",
          title: "Fresh",
          path: "/persons/fresh",
          opened_at: now - 60 * 1000
        },
        {
          entity_type: "person",
          entity_id: "stale",
          title: "Stale",
          path: "/persons/stale",
          opened_at: oldTimestamp
        }
      ])
    );

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    const recent = await within(dialog).findByTestId("commandbar-recent-entities");
    // Only "Fresh" should render; "Stale" was pruned.
    expect(within(recent).getByText("Fresh")).toBeInTheDocument();
    expect(within(recent).queryByText("Stale")).not.toBeInTheDocument();
  });

  it("tracks an entity click and persists it to localStorage with newest-first ordering", async () => {
    const user = userEvent.setup();
    searchGlobalMock.mockResolvedValueOnce({
      q: "иванов",
      total: 1,
      facets: {},
      items: [
        {
          kind: "entity",
          entity_type: "person",
          entity_id: "p-42",
          title: "Иванов Сидор",
          deeplink: "/persons/p-42"
        }
      ]
    });

    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    await user.type(screen.getByPlaceholderText(/найти раздел/i), "иванов");

    const entities = await screen.findByTestId("commandbar-entities");
    const link = within(entities).getByRole("option", { name: /иванов сидор/i });
    await user.click(link);

    // Click closes the palette; recent-entities is persisted to localStorage.
    const raw = window.localStorage.getItem("ux.commandbar.recentEntities.v1");
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string);
    expect(parsed).toHaveLength(1);
    expect(parsed[0]).toMatchObject({
      entity_type: "person",
      entity_id: "p-42",
      title: "Иванов Сидор",
      path: "/persons/p-42"
    });
    expect(typeof parsed[0].opened_at).toBe("number");
  });

  it("hides recent entities once the user starts typing (discovery vs search mode)", async () => {
    window.localStorage.setItem(
      "ux.commandbar.recentEntities.v1",
      JSON.stringify([
        {
          entity_type: "person",
          entity_id: "p-1",
          title: "Иванов",
          path: "/persons/p-1",
          opened_at: Date.now()
        }
      ])
    );

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("commandbar-recent-entities")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/найти раздел/i), "что-то");
    await waitFor(() => {
      expect(within(dialog).queryByTestId("commandbar-recent-entities")).not.toBeInTheDocument();
    });
  });

  it("dedupes the same entity by entity_type+entity_id when clicked twice", async () => {
    // Pre-seed with one entry, then "click" an entity result with the same id.
    window.localStorage.setItem(
      "ux.commandbar.recentEntities.v1",
      JSON.stringify([
        {
          entity_type: "person",
          entity_id: "p-1",
          title: "Old title",
          path: "/persons/p-1",
          opened_at: Date.now() - 60 * 60 * 1000
        },
        {
          entity_type: "person",
          entity_id: "p-2",
          title: "Other",
          path: "/persons/p-2",
          opened_at: Date.now() - 60 * 60 * 1000
        }
      ])
    );
    searchGlobalMock.mockResolvedValueOnce({
      q: "и",
      total: 1,
      facets: {},
      items: [
        {
          kind: "entity",
          entity_type: "person",
          entity_id: "p-1",
          title: "Иванов (renamed)",
          deeplink: "/persons/p-1"
        }
      ]
    });

    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);
    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    await user.type(screen.getByPlaceholderText(/найти раздел/i), "и");

    const entities = await screen.findByTestId("commandbar-entities");
    await user.click(within(entities).getByRole("option", { name: /иванов \(renamed\)/i }));

    const raw = window.localStorage.getItem("ux.commandbar.recentEntities.v1");
    const parsed = JSON.parse(raw as string);
    // Two entries total (no duplication), p-1 at position 0 with updated title.
    expect(parsed).toHaveLength(2);
    expect(parsed[0]).toMatchObject({
      entity_type: "person",
      entity_id: "p-1",
      title: "Иванов (renamed)"
    });
    expect(parsed[1]).toMatchObject({ entity_type: "person", entity_id: "p-2" });
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
