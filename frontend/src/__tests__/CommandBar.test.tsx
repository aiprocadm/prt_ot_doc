import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandBar } from "@/components/layout/CommandBar";
import { PERMISSIONS } from "@/permissions/permissions";
import type { Permission } from "@/permissions/permissions";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

function DummyNavIcon() {
  return null;
}

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
  });

  it("opens palette and lists commands with /dashboard for главная", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);

    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: /главная/i })).toHaveAttribute("href", "/dashboard");
    expect(within(dialog).getByRole("link", { name: /документы/i })).toHaveAttribute("href", "/documents");
  });

  it("filters commands by query", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CommandBar />);

    await user.click(screen.getByRole("button", { name: /открыть палитру команд/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(screen.getByPlaceholderText(/найти раздел/i), "документы");

    expect(within(dialog).queryByRole("link", { name: /главная/i })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /документы/i })).toBeInTheDocument();
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
    expect(within(dialog).queryByRole("link", { name: /^документы$/i })).not.toBeInTheDocument();
  });
});
