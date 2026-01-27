import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";

describe("common state components", () => {
  it("renders empty state defaults and custom copy", () => {
    render(<EmptyState />);

    expect(screen.getByText("Данные отсутствуют")).toBeInTheDocument();
    expect(screen.getByText("Попробуйте изменить фильтры")).toBeInTheDocument();

    render(<EmptyState title="Нет записей" description="Выберите другие параметры" />);

    expect(screen.getByText("Нет записей")).toBeInTheDocument();
    expect(screen.getByText("Выберите другие параметры")).toBeInTheDocument();
  });

  it("renders error state details and supports retry", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();

    const { container } = render(
      <ErrorState
        error={{ status: 500, code: "E500", message: "Ошибка загрузки" }}
        onRetry={onRetry}
      />
    );

    expect(container.firstChild).not.toBeNull();
    expect(screen.getByText("Ошибка загрузки")).toBeInTheDocument();
    expect(screen.getByText("Код: E500")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not render error state when error is missing", () => {
    const { container } = render(<ErrorState />);
    expect(container.firstChild).toBeNull();
  });
});
