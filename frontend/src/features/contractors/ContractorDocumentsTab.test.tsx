import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ContractorDocumentsTab } from "./ContractorDocumentsTab";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listDocuments: vi.fn(),
      listEmployees: vi.fn(),
      createDocument: vi.fn(),
      archiveDocument: vi.fn(),
    },
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function"
      ? (children as (v: boolean) => unknown)(true)
      : children,
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listDocuments as any).mockResolvedValue({
    items: [
      {
        id: "d1",
        contractor_id: "c1",
        doc_type: "license",
        title: "Лицензия №1",
        status: "active",
        expiry_status: "ok",
      },
    ],
    total: 1,
  });
  (contractorsApi.listEmployees as any).mockResolvedValue({
    items: [],
    total: 0,
  });
  (contractorsApi.createDocument as any).mockResolvedValue({ id: "d2" });
});

describe("ContractorDocumentsTab", () => {
  it("lists documents scoped by contractor", async () => {
    render(<ContractorDocumentsTab contractorId="c1" />);
    expect(await screen.findByText("Лицензия №1")).toBeInTheDocument();
    expect(contractorsApi.listDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ contractor_id: "c1" }),
    );
  });

  it("renders a soft state when the feature is disabled", async () => {
    (contractorsApi.listDocuments as any).mockRejectedValue({
      status: 404,
      message: "Contractors feature is not enabled for this tenant",
    });
    render(<ContractorDocumentsTab contractorId="c1" />);
    expect(await screen.findByText(/Функция недоступна/)).toBeInTheDocument();
  });

  it("creates a document for the contractor", async () => {
    render(<ContractorDocumentsTab contractorId="c1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Добавить документ" }),
    );
    fireEvent.change(await screen.findByLabelText("Название"), {
      target: { value: "Новый документ" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createDocument).toHaveBeenCalledWith(
        expect.objectContaining({
          contractor_id: "c1",
          title: "Новый документ",
          doc_type: "license",
        }),
      ),
    );
  });
});
