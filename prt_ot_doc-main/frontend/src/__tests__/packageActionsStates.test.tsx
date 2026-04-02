import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PackagePresetsPage from "@/pages/packs/PackagePresetsPage";
import PackageProfilesPage from "@/pages/packs/PackageProfilesPage";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

describe("package action states", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("keeps profile form values and shows error when profile creation fails", async () => {
    getMock.mockResolvedValue({ data: [] });
    postMock.mockRejectedValueOnce({ status: 500, message: "profile create failed" });

    render(
      <MemoryRouter>
        <PackageProfilesPage />
      </MemoryRouter>
    );

    await screen.findByText(/package profiles отсутствуют/i);
    fireEvent.change(screen.getByPlaceholderText("code"), { target: { value: "pack-default" } });
    fireEvent.change(screen.getByPlaceholderText("name"), { target: { value: "Pack profile" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("profile create failed");
    });
    expect(screen.getByPlaceholderText("code")).toHaveValue("pack-default");
    expect(screen.getByPlaceholderText("name")).toHaveValue("Pack profile");
  });

  it("shows error when preset validation fails without reloading away the list", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/package-presets") {
        return Promise.resolve({ data: [{ id: "preset-1", code: "pack-a", name: "Pack A", status: "draft" }] });
      }
      if (url === "/package-profiles") {
        return Promise.resolve({ data: [{ id: "profile-1", code: "profile-a" }] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValueOnce({ status: 500, message: "preset validate failed" });

    render(
      <MemoryRouter>
        <PackagePresetsPage />
      </MemoryRouter>
    );

    await screen.findByText(/pack-a — pack a \(draft\)/i);
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("preset validate failed");
    });
    expect(screen.getByText(/pack-a — pack a \(draft\)/i)).toBeInTheDocument();
  });
});