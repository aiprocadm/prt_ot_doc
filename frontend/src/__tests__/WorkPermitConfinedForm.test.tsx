import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog confined section", () => {
  it("показывает секцию ОЗП при выборе confined_space и скрывает safety_systems", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    expect(screen.getByText("Системы обеспечения безопасности")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "confined_space" } });
    expect(screen.getByText(/Анализ воздушной среды/i)).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
  });
});
