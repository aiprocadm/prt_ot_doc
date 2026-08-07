import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const listMock = vi.fn();
const mockedItems = [
  {
    id: "person-1",
    full_name: "Иван Иванов",
    position: "Инженер",
    email: "ivan@example.com",
    phone: "+79999999999",
    status: "active",
    created_at: "2024-01-01",
    updated_at: "2024-01-02",
  },
];
const mockedPagination = { page: 1, page_size: 10, total: 1 };

vi.mock("@/stores/persons", () => ({
  usePersonsStore: () => ({
    list: listMock,
    pagination: mockedPagination,
    items: mockedItems,
  }),
}));

vi.mock("@/features/persons/PersonTable", () => ({
  PersonTable: ({
    onSelect,
  }: {
    onSelect: (person: { id: string }) => void;
  }) => (
    <button type="button" onClick={() => onSelect({ id: "person-1" } as never)}>
      mock-person-table
    </button>
  ),
}));

vi.mock("@/features/persons/PersonFormDialog", () => ({
  PersonFormDialog: ({
    trigger,
    initialData,
  }: {
    trigger: ReactNode;
    initialData?: { id: string };
  }) => (
    <>
      {trigger}
      {initialData ? (
        <span data-testid="edit-initial">{initialData.id}</span>
      ) : null}
    </>
  ),
}));

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: (allowed: boolean) => ReactNode }) => (
    <>{children(true)}</>
  ),
}));

import PersonsPage from "@/pages/persons/PersonsPage";

describe("PersonsPage", () => {
  it("renders employee profile tabs", async () => {
    render(
      <MemoryRouter initialEntries={["/persons?person_id=person-1"]}>
        <PersonsPage />
      </MemoryRouter>,
    );

    expect(listMock).toHaveBeenCalled();
    expect(
      await screen.findByRole("tab", { name: "Обучение" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "СИЗ" })).toBeInTheDocument();
  });

  it("restores focused person from query params", async () => {
    render(
      <MemoryRouter initialEntries={["/persons?person_id=person-1"]}>
        <PersonsPage />
      </MemoryRouter>,
    );

    expect(listMock).toHaveBeenCalled();
    expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
    expect(screen.getByText("Активен")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /сбросить фокус/i }),
    ).toHaveAttribute("href", "/persons");
  });

  it("показывает «Изменить» с данными выбранной персоны (edit-аффорданс)", async () => {
    render(
      <MemoryRouter initialEntries={["/persons?person_id=person-1"]}>
        <PersonsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("button", { name: "Изменить" }),
    ).toBeInTheDocument();
    // edit-диалог получает выбранную персону как initialData (merge-safe правка квалификаций)
    expect(screen.getByTestId("edit-initial")).toHaveTextContent("person-1");
  });
});
