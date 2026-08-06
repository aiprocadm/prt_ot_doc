import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: getMock,
  },
}));

import ClientPortalPackagesPage from "@/pages/client-portal/ClientPortalPackagesPage";

describe("ClientPortalPackagesPage", () => {
  it("loads packages and renders selected package details", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/client-portal/packages") {
        return Promise.resolve({
          data: [
            {
              id: "run-1",
              status: "published",
              started_at: "2026-03-18T10:00:00Z",
            },
          ],
        });
      }
      return Promise.resolve({
        data: {
          run: { id: "run-1", status: "published" },
          history: {
            status_flow: ["running", "published"],
            events_count: 2,
            tickets_count: 1,
            requirements_total: 3,
            requirements_missing: 1,
          },
          files: [
            {
              kind: "zip",
              signed_url: "memory://signed/file",
              sha256: "abc",
              size: 128,
            },
          ],
          events: [
            {
              id: "evt-1",
              type: "package_run.published",
              created_at: "2026-03-18T11:00:00Z",
            },
          ],
          tickets: [],
        },
      });
    });

    render(
      <MemoryRouter>
        <ClientPortalPackagesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Список пакетов")).toBeInTheDocument();
    });
    expect(screen.getAllByText("run-1")).toHaveLength(2);
    expect(screen.getByText(/package_run.published/i)).toBeInTheDocument();
    expect(screen.getByText(/SHA256: abc/i)).toBeInTheDocument();
  });

  it("клик по пакету грузит детали по package_id (а не по служебному id read-model)", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/client-portal/packages") {
        return Promise.resolve({
          data: [
            {
              id: "rm-1",
              package_id: "run-1",
              status: "published",
              started_at: "2026-03-18T10:00:00Z",
            },
            {
              id: "rm-2",
              package_id: "run-2",
              status: "published",
              started_at: "2026-03-19T10:00:00Z",
            },
          ],
        });
      }
      if (url === "/client-portal/packages/run-2") {
        return Promise.resolve({
          data: {
            run: { id: "run-2", status: "published" },
            history: {
              status_flow: ["published"],
              events_count: 1,
              tickets_count: 0,
              requirements_total: 0,
              requirements_missing: 0,
            },
            files: [],
            events: [
              {
                id: "evt-2",
                type: "RUN2_MARKER_EVENT",
                created_at: "2026-03-19T11:00:00Z",
              },
            ],
            tickets: [],
          },
        });
      }
      if (url === "/client-portal/packages/run-1") {
        return Promise.resolve({
          data: {
            run: { id: "run-1", status: "published" },
            history: {
              status_flow: ["published"],
              events_count: 0,
              tickets_count: 0,
              requirements_total: 0,
              requirements_missing: 0,
            },
            files: [],
            events: [],
            tickets: [],
          },
        });
      }
      // любой запрос по read-model id (rm-*) — 404, как настоящий бэкенд
      return Promise.reject({ status: 404, message: "not found" });
    });

    render(
      <MemoryRouter>
        <ClientPortalPackagesPage />
      </MemoryRouter>,
    );

    // Ждём именно строку второго пакета: заголовок «Список пакетов» статичен
    // и появляется ДО загрузки списка — «последняя кнопка» на медленном CI
    // оказывалась не строкой пакета (гонка).
    const runTwo = await screen.findByText("run-2");
    fireEvent.click(runTwo.closest("button") as HTMLElement);
    expect(await screen.findByText(/RUN2_MARKER_EVENT/i)).toBeInTheDocument();
  });
});
