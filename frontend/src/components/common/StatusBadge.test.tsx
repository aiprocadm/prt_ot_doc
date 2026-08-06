import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge medical oversight statuses", () => {
  it("renders russian labels for contingent/referral/suspension statuses", () => {
    render(
      <>
        <StatusBadge status="overdue" />
        <StatusBadge status="due_soon" />
        <StatusBadge status="missing" />
        <StatusBadge status="scheduled" />
        <StatusBadge status="completed" />
        <StatusBadge status="lifted" />
      </>,
    );
    expect(screen.getByText("Просрочен")).toBeInTheDocument();
    expect(screen.getByText("Истекает")).toBeInTheDocument();
    expect(screen.getByText("Отсутствует")).toBeInTheDocument();
    expect(screen.getByText("Запланировано")).toBeInTheDocument();
    expect(screen.getByText("Завершено")).toBeInTheDocument();
    expect(screen.getByText("Снято")).toBeInTheDocument();
  });
});
