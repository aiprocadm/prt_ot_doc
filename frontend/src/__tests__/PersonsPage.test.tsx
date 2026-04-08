import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

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

vi.mock("@/features/persons/PersonTable", () => ({
  PersonTable: ({ onSelect }: { onSelect: (person: { id: string }) => void }) => (
    <button type="button" onClick={() => onSelect({ id: "person-1" } as never)}>
      mock-person-table
    </button>
  )
}));

vi.mock("@/features/persons/PersonFormDialog", () => ({
  PersonFormDialog: ({ trigger }: { trigger: ReactNode }) => <>{trigger}</>
}));

describe("PersonsPage", () => {
  it("renders employee profile tabs", async () => {
    render(
      <MemoryRouter initialEntries={["/persons?person_id=person-1"]}>
        <PersonsPage />
      </MemoryRouter>
    );

    expect(listMock).toHaveBeenCalled();
    expect(await screen.findByRole("tab", { name: "Обучение" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "СИЗ" })).toBeInTheDocument();
  });

  it("restores focused person from query params", async () => {
    render(
      <MemoryRouter initialEntries={["/persons?person_id=person-1"]}>
        <PersonsPage />
      </MemoryRouter>
    );

    expect(listMock).toHaveBeenCalled();
    expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
    expect(screen.getByText("Активен")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /сбросить фокус/i })).toHaveAttribute("href", "/persons");
  });
});
