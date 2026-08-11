import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MobileIssuePage from "@/pages/ppe/MobileIssuePage";

const getPpeOverviewMock = vi.fn();
const createPpeIssueMock = vi.fn();
const listLevelsMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...a: unknown[]) => getPpeOverviewMock(...a),
    createPpeIssue: (...a: unknown[]) => createPpeIssueMock(...a)
  }
}));
vi.mock("@/api/warehouse", () => ({
  warehouseApi: { listLevels: (...a: unknown[]) => listLevelsMock(...a) }
}));

const person = (id: string, full_name: string, status = "active") => ({
  id, created_at: "2024-01-01", updated_at: "2024-01-02",
  first_name: full_name, last_name: "", full_name, position: "Сварщик", company_id: "c1", status
});
const item = (id: string, name: string) => ({ id, name, code: id, category: "head" });

const renderPage = () =>
  render(
    <MemoryRouter>
      <MobileIssuePage />
    </MemoryRouter>
  );

beforeEach(() => {
  getPpeOverviewMock.mockReset();
  createPpeIssueMock.mockReset();
  listLevelsMock.mockReset();
  getPpeOverviewMock.mockResolvedValue({
    persons: [person("p1", "Иван Иванов"), person("p2", "Уволенный Работник", "dismissed")],
    items: [item("i1", "Каска"), item("i2", "Перчатки")],
    issues: [],
    expiring: []
  });
  listLevelsMock.mockResolvedValue([{ item_id: "i1", item_name: "Каска", total_quantity: 5, batch_count: 1 }]);
  createPpeIssueMock.mockResolvedValue({ id: "x" });
});

describe("MobileIssuePage — worker step", () => {
  it("renders the page and lists only active workers, selecting one advances to items", async () => {
    renderPage();
    expect(await screen.findByText("Мобильная выдача СИЗ")).toBeInTheDocument();
    expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
    expect(screen.queryByText("Уволенный Работник")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Иван Иванов"));

    await waitFor(() => expect(screen.getByLabelText("Поиск СИЗ")).toBeInTheDocument());
  });

  it("filters workers by query", async () => {
    getPpeOverviewMock.mockResolvedValue({
      persons: [person("p1", "Иван Иванов"), person("p3", "Сидор Сидоров")],
      items: [], issues: [], expiring: []
    });
    renderPage();
    await screen.findByText("Иван Иванов");
    fireEvent.change(screen.getByLabelText("Поиск сотрудника"), { target: { value: "сидор" } });
    expect(screen.getByText("Сидор Сидоров")).toBeInTheDocument();
    expect(screen.queryByText("Иван Иванов")).not.toBeInTheDocument();
  });
});

describe("MobileIssuePage — items & cart", () => {
  const gotoItems = async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Иван Иванов"));
    await screen.findByLabelText("Поиск СИЗ");
  };

  it("adds items to the cart and merges duplicates", async () => {
    await gotoItems();
    const addButtons = screen.getAllByRole("button", { name: "+ Добавить" });
    fireEvent.click(addButtons[0]); // Каска
    expect(await screen.findByText("Корзина (1)")).toBeInTheDocument();
    fireEvent.click(addButtons[0]); // Каска again → merge → qty 2
    expect(await screen.findByText("Корзина (2)")).toBeInTheDocument();
    expect(screen.getByLabelText("Количество Каска")).toHaveTextContent("2");
  });

  it("shows on-hand badge when stock-aware", async () => {
    await gotoItems();
    expect(await screen.findByText("На складе: 5")).toBeInTheDocument();
  });

  it("hides on-hand badge when stock levels unavailable (degraded)", async () => {
    listLevelsMock.mockRejectedValue({ message: "404" });
    await gotoItems();
    await screen.findByText("Каска");
    expect(screen.queryByText(/На складе:/)).not.toBeInTheDocument();
  });
});

describe("MobileIssuePage — review & issue", () => {
  const gotoReviewWithKaska = async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Иван Иванов"));
    await screen.findByLabelText("Поиск СИЗ");
    fireEvent.click(screen.getAllByRole("button", { name: "+ Добавить" })[0]); // Каска
    fireEvent.click(await screen.findByRole("button", { name: /К обзору/ }));
    await screen.findByRole("button", { name: /Выдать всё/ });
  };

  it("issues the whole cart and shows a success panel", async () => {
    await gotoReviewWithKaska();
    fireEvent.click(screen.getByRole("button", { name: /Выдать всё/ }));
    expect(await screen.findByText(/Выдано позиций: 1/)).toBeInTheDocument();
    expect(createPpeIssueMock).toHaveBeenCalledWith({ person_id: "p1", item_id: "i1", quantity: 1 });
  });

  it("on failure shows the error and keeps the failed line for retry", async () => {
    createPpeIssueMock.mockRejectedValueOnce({ message: "Недостаточно остатка" });
    await gotoReviewWithKaska();
    fireEvent.click(screen.getByRole("button", { name: /Выдать всё/ }));
    expect(await screen.findByText(/Недостаточно остатка/)).toBeInTheDocument();
    // failed line still issuable → button present, not a success panel
    expect(screen.getByRole("button", { name: /Выдать всё/ })).toBeInTheDocument();
    expect(screen.queryByText(/Выдано позиций/)).not.toBeInTheDocument();
  });
});
