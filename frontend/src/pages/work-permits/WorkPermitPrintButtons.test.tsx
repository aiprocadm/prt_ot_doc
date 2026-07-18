import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { PrintButtons } from "@/features/work-permits/PrintButtons";

describe("PrintButtons", () => {
  it("рендерит кнопки скачивания DOCX и PDF", () => {
    render(<PrintButtons onDownload={vi.fn()} />);
    expect(screen.getByRole("button", { name: /DOCX/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PDF/i })).toBeInTheDocument();
  });

  it("клик по DOCX вызывает onDownload('docx')", async () => {
    const onDownload = vi.fn();
    render(<PrintButtons onDownload={onDownload} />);
    screen.getByRole("button", { name: /DOCX/i }).click();
    expect(onDownload).toHaveBeenCalledWith("docx");
  });
});
