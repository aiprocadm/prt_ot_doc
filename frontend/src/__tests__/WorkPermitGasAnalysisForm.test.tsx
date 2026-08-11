import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { workPermitsApi } from "@/api/workPermits";

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: { create: vi.fn().mockResolvedValue({ id: "x" }), update: vi.fn() },
}));

describe("WorkPermitFormDialog gas_analysis editor", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("показывает редактор замеров для confined_space и добавляет строку в payload", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));

    // Выбираем вид работ — ОЗП (confined_space)
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "confined_space" } });

    // Заполняем обязательное поле зоны
    fireEvent.change(screen.getByLabelText("Зона работ"), { target: { value: "колодец К-9" } });

    // Редактор замеров должен быть виден
    expect(screen.getByText("Добавить замер")).toBeInTheDocument();

    // Добавляем строку
    act(() => {
      fireEvent.click(screen.getByText("Добавить замер"));
    });

    // Вводим значение (параметр по умолчанию — "oxygen")
    fireEvent.change(screen.getByLabelText("Значение"), { target: { value: "20.9" } });

    // Сабмит формы
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    // Ждём завершения асинхронного сабмита
    await waitFor(() => expect(workPermitsApi.create).toHaveBeenCalled());

    const body = (workPermitsApi.create as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(body.type_specific.gas_analysis).toEqual([{ parameter: "oxygen", value: "20.9" }]);
  });

  it("два быстрых добавления накапливаются (защита от stale-snapshot)", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "confined_space" } });
    act(() => {
      fireEvent.click(screen.getByText("Добавить замер"));
      fireEvent.click(screen.getByText("Добавить замер"));
    });
    // оба добавления видны — updateGas читает актуальный стор через getValues, не render-снимок
    expect(screen.getAllByLabelText("Параметр замера")).toHaveLength(2);
  });

  it("показывает редактор замеров для hot_work", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "hot_work" } });
    expect(screen.getByText("Добавить замер")).toBeInTheDocument();
  });

  it("показывает редактор замеров для gas_hazardous", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "gas_hazardous" } });
    expect(screen.getByText("Добавить замер")).toBeInTheDocument();
  });

  it("НЕ показывает редактор замеров для electrical", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "electrical" } });
    expect(screen.queryByText("Добавить замер")).not.toBeInTheDocument();
  });

  it("НЕ показывает редактор замеров для excavation", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "excavation" } });
    expect(screen.queryByText("Добавить замер")).not.toBeInTheDocument();
  });
});
