import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OutboxPage from "@/pages/admin/OutboxPage";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

describe("OutboxPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("keeps create form values when endpoint creation fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox/events")
        return Promise.resolve({ data: { items: [] } });
      if (url === "/webhooks/endpoints") return Promise.resolve({ data: [] });
      if (url === "/webhooks/deliveries") return Promise.resolve({ data: [] });
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValueOnce(new Error("endpoint create failed"));

    render(
      <MemoryRouter>
        <OutboxPage />
      </MemoryRouter>,
    );

    await screen.findByText(/точки вебхуков отсутствуют/i);
    fireEvent.change(
      screen.getByPlaceholderText("https://example.com/webhook"),
      { target: { value: "https://hook.test" } },
    );
    fireEvent.change(screen.getByPlaceholderText("Секрет"), {
      target: { value: "secret-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "endpoint create failed",
      );
    });
    expect(
      screen.getByPlaceholderText("https://example.com/webhook"),
    ).toHaveValue("https://hook.test");
    expect(screen.getByPlaceholderText("Секрет")).toHaveValue("secret-1");
  });

  it("keeps endpoint list visible when test action fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox/events")
        return Promise.resolve({ data: { items: [] } });
      if (url === "/webhooks/endpoints") {
        return Promise.resolve({
          data: [
            {
              id: "ep-1",
              url: "https://hook.test",
              enabled: true,
              subscribed_events: ["DocumentGenerated"],
            },
          ],
        });
      }
      if (url === "/webhooks/deliveries") return Promise.resolve({ data: [] });
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValueOnce(new Error("endpoint test failed"));

    render(
      <MemoryRouter>
        <OutboxPage />
      </MemoryRouter>,
    );

    await screen.findByText(/https:\/\/hook\.test/i);
    fireEvent.click(screen.getByRole("button", { name: "Тест" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "endpoint test failed",
      );
    });
    expect(screen.getByText(/https:\/\/hook\.test/i)).toBeInTheDocument();
  });
});
