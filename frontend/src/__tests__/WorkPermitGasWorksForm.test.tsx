import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog gas_hazardous section", () => {
  it("показывает секцию газоопасных при выборе gas_hazardous и скрывает огневую/ОЗП/высоту", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "gas_hazardous" } });
    expect(screen.getByText(/Защита органов дыхания/i)).toBeInTheDocument();
    expect(screen.getByText("Шланговый противогаз (ПШ-1/ПШ-2)")).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
    expect(screen.queryByText(/Пожарная безопасность/i)).not.toBeInTheDocument();
  });
});
