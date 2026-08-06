import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: { create: vi.fn(), update: vi.fn() },
}));

describe("WorkPermitFormDialog excavation section", () => {
  it("показывает секцию земляных при выборе excavation и скрывает чужие", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), {
      target: { value: "excavation" },
    });
    expect(
      screen.getByText(/Безопасность земляных работ/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Электрические кабели")).toBeInTheDocument();
    expect(
      screen.queryByText(/Меры безопасности в электроустановках/i),
    ).not.toBeInTheDocument();
  });

  it("накапливает чекбоксы коммуникаций и выставляет защиту стенок", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), {
      target: { value: "excavation" },
    });
    act(() => {
      fireEvent.click(screen.getByLabelText("Электрические кабели"));
      fireEvent.click(screen.getByLabelText("Водопровод / канализация"));
    });
    expect(
      (screen.getByLabelText("Электрические кабели") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByLabelText("Водопровод / канализация") as HTMLInputElement)
        .checked,
    ).toBe(true);
    fireEvent.change(screen.getByLabelText("Защита стенок выемки"), {
      target: { value: "shield_bracing" },
    });
    expect(
      (screen.getByLabelText("Защита стенок выемки") as HTMLSelectElement)
        .value,
    ).toBe("shield_bracing");
  });
});
