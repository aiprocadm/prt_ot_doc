import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EdoPage from "@/pages/edo/EdoPage";
import SignaturesPage from "@/pages/signatures/SignaturesPage";

const edoApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

const signApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock("@/api/edo", () => ({ edoApi: edoApiMock }));
vi.mock("@/api/sign", () => ({ signApi: signApiMock }));

describe("foundation operational pages", () => {
  beforeEach(() => {
    edoApiMock.list.mockReset();
    signApiMock.list.mockReset();
  });

  it("renders edo empty state with provider warning", async () => {
    edoApiMock.list.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <EdoPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("ЭДО сообщения отсутствуют")).toBeInTheDocument();
    expect(screen.getByText(/Provider mode: non-production/)).toBeInTheDocument();
  });

  it("renders signatures empty state with provider warning", async () => {
    signApiMock.list.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <SignaturesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Запросы на подпись отсутствуют")).toBeInTheDocument();
    expect(screen.getByText(/non-production/)).toBeInTheDocument();
  });
});