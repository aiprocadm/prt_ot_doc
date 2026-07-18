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

  it("сбрасывает type_specific при смене вида работ (confined→hot→confined очищает вентиляцию)", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    const workType = screen.getByLabelText("Вид работ");
    fireEvent.change(workType, { target: { value: "confined_space" } });
    fireEvent.change(screen.getByLabelText("Вентиляция"), { target: { value: "forced" } });
    expect((screen.getByLabelText("Вентиляция") as HTMLSelectElement).value).toBe("forced");
    // смена вида → сброс предыдущего type_specific
    fireEvent.change(workType, { target: { value: "hot_work" } });
    fireEvent.change(workType, { target: { value: "confined_space" } });
    expect((screen.getByLabelText("Вентиляция") as HTMLSelectElement).value).toBe("");
  });
});
