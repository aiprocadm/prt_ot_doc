import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LegalAcceptanceBanner } from "@/components/common/LegalAcceptanceBanner";

const getStateMock = vi.fn();
const acceptMock = vi.fn();

vi.mock("@/api/legalDocuments", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/legalDocuments")>()),
  getLegalAcceptanceState: () => getStateMock(),
  acceptLegalDocument: (kind: string) => acceptMock(kind),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const status = (overrides: Record<string, unknown> = {}) => ({
  kind: "offer",
  title: "Оферта партнёра",
  current_version: 1,
  accepted_version: null,
  accepted_at: null,
  accepted: false,
  outdated: false,
  ...overrides,
});

const draw = () =>
  render(
    <MemoryRouter>
      <LegalAcceptanceBanner />
    </MemoryRouter>,
  );

describe("напоминание принять юридические тексты (BIZ-52 разд. 52.2)", () => {
  beforeEach(() => {
    getStateMock.mockReset();
    acceptMock.mockReset();
    acceptMock.mockResolvedValue(undefined);
  });

  it("молчит, когда подписывать нечего", async () => {
    getStateMock.mockResolvedValue({
      items: [status({ accepted: true })],
      pending: [],
    });

    const { container } = draw();

    await waitFor(() => expect(getStateMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("просит принять оферту и даёт её прочитать", async () => {
    getStateMock.mockResolvedValue({ items: [status()], pending: ["offer"] });

    draw();

    expect(await screen.findByText(/Примите оферту/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Прочитать" })).toHaveAttribute(
      "href",
      "/legal/offer",
    );
  });

  it("при новой редакции говорит «условия изменились»", async () => {
    // Человека, уже подписавшего прежнюю редакцию, «примите оферту» сбивало бы
    // с толку: он её принимал.
    getStateMock.mockResolvedValue({
      items: [
        status({ accepted_version: 1, current_version: 2, outdated: true }),
      ],
      pending: ["offer"],
    });

    draw();

    expect(await screen.findByText(/Условия изменились/)).toBeInTheDocument();
    expect(screen.queryByText(/Примите оферту/)).not.toBeInTheDocument();
  });

  it("принимает и перечитывает состояние", async () => {
    const user = userEvent.setup();
    getStateMock
      .mockResolvedValueOnce({ items: [status()], pending: ["offer"] })
      .mockResolvedValueOnce({
        items: [status({ accepted: true })],
        pending: [],
      });
    draw();
    await screen.findByText(/Примите оферту/);

    await user.click(screen.getByRole("button", { name: "Принимаю" }));

    await waitFor(() => expect(acceptMock).toHaveBeenCalledWith("offer"));
    // Полоса обязана исчезнуть сразу: оставшись, она выглядела бы как «подпись
    // не сохранилась».
    await waitFor(() =>
      expect(screen.queryByText(/Примите оферту/)).not.toBeInTheDocument(),
    );
  });

  it("показывает все невыполненные подписи, а не первую", async () => {
    getStateMock.mockResolvedValue({
      items: [status(), status({ kind: "privacy", title: "Политика" })],
      pending: ["offer", "privacy"],
    });

    draw();

    expect(await screen.findByText(/Примите оферту/)).toBeInTheDocument();
    expect(
      screen.getByText(/политику обработки персональных данных/),
    ).toBeInTheDocument();
  });

  it("берёт список к подписи у сервера, а не считает сам", async () => {
    // Сервер сказал «ничего не ждёт» — полосы нет, даже если строка выглядит
    // непринятой. Иначе появилась бы вторая правда о том, подписан документ
    // или нет.
    getStateMock.mockResolvedValue({ items: [status()], pending: [] });

    const { container } = draw();

    await waitFor(() => expect(getStateMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("при сбое запроса не пугает человека", async () => {
    getStateMock.mockRejectedValue(new Error("нет сети"));

    const { container } = draw();

    await waitFor(() => expect(getStateMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
