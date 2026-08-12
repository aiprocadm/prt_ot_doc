import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LegalLinks } from "@/components/common/LegalLinks";

const listMock = vi.fn();

vi.mock("@/api/legalDocuments", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/legalDocuments")>()),
  listLegalDocuments: () => listMock(),
}));

describe("ссылки на юр. тексты (BIZ-52 срез-5)", () => {
  beforeEach(() => {
    listMock.mockReset();
  });

  it("показывает опубликованные документы", async () => {
    listMock.mockResolvedValue([
      {
        kind: "offer",
        title: "Публичная оферта",
        version: 2,
        source: "reseller",
        published_at: "2026-08-12T10:00:00Z",
      },
    ]);

    render(<LegalLinks />);

    const link = await screen.findByRole("link", { name: "Публичная оферта" });
    expect(link).toHaveAttribute("href", "/legal/offer");
  });

  it("не показывает пустой блок, когда ничего не опубликовано", async () => {
    // Пустой заголовок без ссылок читался бы как поломка загрузки.
    listMock.mockResolvedValue([]);

    const { container } = render(<LegalLinks />);

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("ошибка загрузки не мешает войти в систему", async () => {
    listMock.mockRejectedValue(new Error("сеть"));

    const { container } = render(<LegalLinks />);

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
