import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";
import SyncConflictHelpPage from "@/pages/help/SyncConflictHelpPage";

// Экран статичный: без API и сторов, только Breadcrumb (ему нужен роутер)
// и карточка с порядком действий — моки данных не требуются.
describe("SyncConflictHelpPage", () => {
  const renderPage = () =>
    render(
      <MemoryRouter>
        <SyncConflictHelpPage />
      </MemoryRouter>,
    );

  it("рендерит справку по конфликтам синхронизации", async () => {
    renderPage();

    expect(
      await screen.findByText("Офлайн и конфликты синхронизации"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Рекомендованный порядок действий"),
    ).toBeInTheDocument();
    // Хлебные крошки: ссылка в настройки + текущий раздел.
    expect(screen.getByRole("link", { name: "Настройки" })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(
      screen.getByText("Синхронизация и конфликты"),
    ).toBeInTheDocument();
    // Содержимое сценария действительно на экране, а не пустая карточка.
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(
      screen.getByText(/приоритет у подтверждённой/),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете (BIZ-60 волна 5)", async () => {
    renderPage();
    expect(
      await screen.findByText("Офлайн и конфликты синхронизации"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "SyncConflictHelpPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
