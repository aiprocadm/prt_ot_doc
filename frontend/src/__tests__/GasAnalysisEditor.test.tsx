import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { GasAnalysisEditor } from "@/features/work-permits/GasAnalysisEditor";

const rows = [
  { parameter: "oxygen", value: "20.9", norm: "≥ 20" },
  { parameter: "flammable", value: "0" },
];

describe("GasAnalysisEditor", () => {
  it("рендерит строки замеров", () => {
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={vi.fn()} onCell={vi.fn()} />);
    expect(screen.getAllByLabelText("Параметр замера")).toHaveLength(2);
    expect((screen.getAllByLabelText("Значение")[0] as HTMLInputElement).value).toBe("20.9");
  });

  it("пустой список показывает только кнопку добавления", () => {
    render(<GasAnalysisEditor rows={[]} onAdd={vi.fn()} onRemove={vi.fn()} onCell={vi.fn()} />);
    expect(screen.queryByLabelText("Параметр замера")).not.toBeInTheDocument();
    expect(screen.getByText("Добавить замер")).toBeInTheDocument();
  });

  it("клик «Добавить замер» зовёт onAdd", () => {
    const onAdd = vi.fn();
    render(<GasAnalysisEditor rows={[]} onAdd={onAdd} onRemove={vi.fn()} onCell={vi.fn()} />);
    fireEvent.click(screen.getByText("Добавить замер"));
    expect(onAdd).toHaveBeenCalledOnce();
  });

  it("удаление строки зовёт onRemove с индексом", () => {
    const onRemove = vi.fn();
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={onRemove} onCell={vi.fn()} />);
    fireEvent.click(screen.getAllByLabelText("Удалить замер")[1]);
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it("изменение значения зовёт onCell(index, 'value', newValue)", () => {
    const onCell = vi.fn();
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={vi.fn()} onCell={onCell} />);
    fireEvent.change(screen.getAllByLabelText("Значение")[0], { target: { value: "19.5" } });
    expect(onCell).toHaveBeenCalledWith(0, "value", "19.5");
  });

  it("смена параметра зовёт onCell(index, 'parameter', code)", () => {
    const onCell = vi.fn();
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={vi.fn()} onCell={onCell} />);
    fireEvent.change(screen.getAllByLabelText("Параметр замера")[1], { target: { value: "harmful" } });
    expect(onCell).toHaveBeenCalledWith(1, "parameter", "harmful");
  });
});
