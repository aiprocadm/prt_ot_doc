import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LegalDocumentPage } from "@/pages/legal/LegalDocumentPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();

vi.mock("@/api/legalDocuments", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/legalDocuments")>()),
  getLegalDocument: (kind: string) => getMock(kind),
}));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/legal/:kind" element={<LegalDocumentPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe("страница юр. текста (BIZ-52 срез-5)", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("показывает текст, редакцию и дату", async () => {
    getMock.mockResolvedValue({
      kind: "offer",
      title: "Публичная оферта",
      body: "Условия оказания услуг.",
      version: 3,
      source: "reseller",
      published_at: "2026-08-12T10:00:00Z",
    });

    renderAt("/legal/offer");

    expect(
      await screen.findByRole("heading", { name: "Публичная оферта" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Условия оказания услуг.")).toBeInTheDocument();
    // Без редакции и даты юридический текст не отвечает на вопрос
    // «что действовало на такую-то дату».
    expect(screen.getByText(/Редакция 3 от/)).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    getMock.mockResolvedValue({
      kind: "offer",
      title: "Публичная оферта",
      body: "Условия оказания услуг.",
      version: 3,
      source: "reseller",
      published_at: "2026-08-12T10:00:00Z",
    });

    renderAt("/legal/offer");
    await screen.findByRole("heading", { name: "Публичная оферта" });

    const budget = uxBudgetDelta(document.body, "LegalDocumentPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("неопубликованный документ объясняется, а не показывает пустоту", async () => {
    getMock.mockRejectedValue(new Error("404"));

    renderAt("/legal/privacy");

    expect(
      await screen.findByRole("heading", { name: "Документ не опубликован" }),
    ).toBeInTheDocument();
  });

  it("неизвестный вид не запрашивается у сервера", async () => {
    renderAt("/legal/contract");

    expect(
      await screen.findByRole("heading", { name: "Документ не опубликован" }),
    ).toBeInTheDocument();
    expect(getMock).not.toHaveBeenCalled();
  });
});
