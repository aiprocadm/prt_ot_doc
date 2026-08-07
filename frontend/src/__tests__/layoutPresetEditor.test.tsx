import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

const apiClientMock = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
}));

const brandingApiMock = vi.hoisted(() => ({
  listLayoutPresets: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => apiClientMock.post(...args),
    patch: (...args: unknown[]) => apiClientMock.patch(...args),
  },
}));

vi.mock("@/api/branding", () => ({
  listLayoutPresets: (...args: unknown[]) =>
    brandingApiMock.listLayoutPresets(...args),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { LayoutPresetEditor } from "@/components/LayoutPresetEditor/LayoutPresetEditor";

const presetList = [
  {
    id: "preset-1",
    tenant_id: "tenant-1",
    code: "company_brand",
    name: "Company brand",
    different_first: false,
    different_odd_even: false,
    header_first_xml: null,
    header_odd_xml: "{{company.name}}",
    header_even_xml: null,
    footer_first_xml: null,
    footer_odd_xml: "{{doc.title}}",
    footer_even_xml: null,
    watermark: { enabled: false },
  },
];

describe("LayoutPresetEditor", () => {
  beforeEach(() => {
    apiClientMock.post.mockReset();
    apiClientMock.patch.mockReset();
    brandingApiMock.listLayoutPresets.mockReset();
    vi.mocked(toast.success).mockReset();
    vi.mocked(toast.error).mockReset();

    brandingApiMock.listLayoutPresets.mockResolvedValue(presetList);
  });

  it("shows toast when presets list loading fails", async () => {
    brandingApiMock.listLayoutPresets.mockRejectedValue(
      new Error("load failed"),
    );

    render(<LayoutPresetEditor />);

    expect(await screen.findByText(/токены:/i)).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith(
      "Не удалось загрузить список пресетов",
    );
  });

  it("prevents save without required code and name", async () => {
    const user = userEvent.setup();
    render(<LayoutPresetEditor />);

    await screen.findByDisplayValue("company_brand");
    await user.click(screen.getByRole("button", { name: /новый/i }));
    await user.click(screen.getByRole("button", { name: /сохранить пресет/i }));

    expect(toast.error).toHaveBeenCalledWith("Укажите code и name");
    expect(apiClientMock.post).not.toHaveBeenCalled();
  });

  it("creates new preset and reloads list", async () => {
    const user = userEvent.setup();
    brandingApiMock.listLayoutPresets
      .mockResolvedValueOnce(presetList)
      .mockResolvedValueOnce([
        ...presetList,
        {
          ...presetList[0],
          id: "preset-2",
          code: "branch_brand",
          name: "Branch brand",
        },
      ]);
    apiClientMock.post.mockResolvedValue({ data: {} });

    render(<LayoutPresetEditor />);

    await screen.findByDisplayValue("company_brand");
    await user.click(screen.getByRole("button", { name: /новый/i }));
    const textInputs = screen.getAllByRole("textbox");
    await user.type(textInputs[0], "branch_brand");
    await user.type(textInputs[1], "Branch brand");
    await user.click(screen.getByRole("button", { name: /сохранить пресет/i }));

    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/layout-presets",
      expect.objectContaining({ code: "branch_brand", name: "Branch brand" }),
    );
    expect(toast.success).toHaveBeenCalledWith("Пресет создан");
    expect(brandingApiMock.listLayoutPresets).toHaveBeenCalledTimes(2);
  });

  it("shows unresolved token preview for current form", async () => {
    const user = userEvent.setup();
    render(<LayoutPresetEditor />);

    await screen.findByDisplayValue("company_brand");
    await user.click(screen.getByRole("button", { name: /проверить токены/i }));

    expect(screen.getByText(/Warnings:/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Unresolved: .*\{\{company.name\}\}.*\{\{doc.title\}\}/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows toast when preset save fails", async () => {
    const user = userEvent.setup();
    apiClientMock.patch.mockRejectedValue(new Error("save failed"));

    render(<LayoutPresetEditor />);

    await screen.findByDisplayValue("company_brand");
    await user.click(screen.getByRole("button", { name: /сохранить пресет/i }));

    expect(toast.error).toHaveBeenCalledWith("save failed");
  });
});
