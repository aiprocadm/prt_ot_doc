import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import TrainingPage from "@/pages/training/TrainingPage";
import { useAuthStore } from "@/stores/auth";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args)
  }
}));

const baseUser = {
  id: "user-training",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "training@example.com",
  full_name: "Training User",
  roles: ["worker"],
  permissions: [PERMISSIONS.TRAINING_VIEW],
  attributes: { tenant_id: "tenant-1" }
};

describe("TrainingPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockImplementation((url: string) => {
      if (url === "/training/learner/dashboard") {
        return Promise.resolve({
          data: {
            assigned_total: 3,
            completed_total: 1,
            overdue_total: 1,
            next_due_at: null,
            items: []
          }
        });
      }
      if (url === "/training/teacher/dashboard") {
        return Promise.resolve({
          data: {
            groups_total: 2,
            enrollments_total: 12,
            completed_total: 8,
            average_progress_percent: 87
          }
        });
      }
      if (url === "/training/analytics/overview") {
        return Promise.resolve({
          data: {
            completed_total: 8,
            retake_total: 1,
            average_attempt_score: 92,
            material_types: { video: 3 }
          }
        });
      }
      if (url === "/training/programs") {
        return Promise.resolve({ data: { items: [{ id: "program-1" }] } });
      }
      if (url === "/training/programs/program-1/detail") {
        return Promise.resolve({
          data: {
            modules: [{ module: { id: "module-1", title: "Модуль 1" }, lessons: [{ id: "lesson-1", title: "Урок 1" }] }]
          }
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
  });

  it("скрывает teacher surface и не запрашивает teacher endpoints без права назначения", async () => {
    useAuthStore.setState({
      user: baseUser,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    render(
      <MemoryRouter>
        <TrainingPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith("/training/learner/dashboard", { params: { person_id: "me" } });
    });

    const requestedUrls = getMock.mock.calls.map(([url]) => url);
    expect(requestedUrls).not.toContain("/training/teacher/dashboard");
    expect(requestedUrls).not.toContain("/training/analytics/overview");
    expect(requestedUrls).not.toContain("/training/programs");
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /назначить обучение/i })).toBeDisabled();
  });

  it("показывает teacher surface и запрашивает teacher endpoints при наличии права назначения", async () => {
    useAuthStore.setState({
      user: { ...baseUser, permissions: [PERMISSIONS.TRAINING_VIEW, PERMISSIONS.TRAINING_ASSIGN] },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    render(
      <MemoryRouter>
        <TrainingPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      const requestedUrls = getMock.mock.calls.map(([url]) => url);
      expect(requestedUrls).toContain("/training/teacher/dashboard");
      expect(requestedUrls).toContain("/training/analytics/overview");
      expect(requestedUrls).toContain("/training/programs");
    });

    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /назначить обучение/i })).toHaveAttribute("href", "/tasks?type=training_plan");
  });
});