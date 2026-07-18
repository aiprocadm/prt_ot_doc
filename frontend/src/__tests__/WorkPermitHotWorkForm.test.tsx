import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog hot_work section", () => {
  it("показывает секцию огневых при выборе hot_work и скрывает safety_systems/ОЗП", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "hot_work" } });
    expect(screen.getByText(/Средства пожаротушения/i)).toBeInTheDocument();
    expect(screen.getByText("Огнетушитель порошковый")).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
    expect(screen.queryByText(/Анализ воздушной среды/i)).not.toBeInTheDocument();
  });
});
