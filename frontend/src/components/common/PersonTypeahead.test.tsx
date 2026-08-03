import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PersonTypeahead } from "@/components/common/PersonTypeahead";

const searchPersons = vi.hoisted(() => vi.fn());
vi.mock("@/api/personsApi", () => ({ searchPersons }));

describe("PersonTypeahead", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    searchPersons.mockResolvedValue([
      { id: "p1", full_name: "Иванов Иван Иванович", first_name: "Иван", last_name: "Иванов" },
      { id: "p2", full_name: "Иванова Анна", first_name: "Анна", last_name: "Иванова" }
    ]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("ищет с задержкой и отдаёт выбранного через onChange", async () => {
    const onChange = vi.fn();
    render(<PersonTypeahead value={null} onChange={onChange} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Иван" } });
    expect(searchPersons).not.toHaveBeenCalled(); // до истечения задержки — тихо

    vi.advanceTimersByTime(350);
    await waitFor(() => expect(searchPersons).toHaveBeenCalledWith("Иван"));

    const option = await screen.findByText("Иванов Иван Иванович");
    fireEvent.click(option);
    expect(onChange).toHaveBeenCalledWith({ id: "p1", label: "Иванов Иван Иванович" });
  });

  it("короткий запрос (1 символ) не дёргает сервер", () => {
    render(<PersonTypeahead value={null} onChange={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "И" } });
    vi.advanceTimersByTime(500);
    expect(searchPersons).not.toHaveBeenCalled();
  });

  it("показывает подпись выбранного значения", () => {
    render(
      <PersonTypeahead value={{ id: "p1", label: "Иванов Иван" }} onChange={vi.fn()} />
    );
    expect(screen.getByRole("textbox")).toHaveValue("Иванов Иван");
  });
});
