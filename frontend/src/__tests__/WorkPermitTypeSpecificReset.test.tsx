import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { workPermitsApi } from "@/api/workPermits";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog type_specific reset on work_type change", () => {
  it("очищает type_specific при смене вида confined_space → hot_work (нет ventilation в payload)", async () => {
    const create = vi.mocked(workPermitsApi.create);
    create.mockResolvedValue({ id: "wp-1" } as never);

    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));

    // Выбираем замкнутые пространства и задаём вентиляцию
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "confined_space" } });
    fireEvent.change(screen.getByLabelText("Вентиляция"), { target: { value: "forced" } });

    // Переключаемся на огневые работы — type_specific замкнутых должен сброситься
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "hot_work" } });

    // zone_text обязателен — без него handleSubmit не вызовет onSubmit
    fireEvent.change(screen.getByLabelText("Зона работ"), { target: { value: "Цех 1" } });
    fireEvent.click(screen.getByText("Сохранить"));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    const body = create.mock.calls[0][0] as { type_specific?: { ventilation?: string } | null };
    expect(body.type_specific?.ventilation).toBeUndefined();
    expect(body.type_specific).toBeNull();
  });
});
