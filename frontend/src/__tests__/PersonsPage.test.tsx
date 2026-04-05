import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import PersonsPage from "@/pages/persons/PersonsPage";

const listMock = vi.fn();

vi.mock("@/stores/persons", () => ({
  usePersonsStore: () => ({
    list: listMock,
    pagination: { page: 1, page_size: 10, total: 1 },
    items: [
      {
        id: "person-1",
        full_name: "Иван Иванов",
        position: "Инженер",
        email: "ivan@example.com",
        phone: "+79999999999",
        status: "active",
        created_at: "2024-01-01",
        updated_at: "2024-01-02"
      }
    ]
  })
}));

describe("PersonsPage", () => {
  it("renders employee profile tabs", async () => {
    render(
      <MemoryRouter>
        <PersonsPage />
      </MemoryRouter>
    );

    expect(listMock).toHaveBeenCalled();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /иван иванов/i }));

    expect(screen.getByRole("tab", { name: "Обучение" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "СИЗ" })).toBeInTheDocument();
  });
});
