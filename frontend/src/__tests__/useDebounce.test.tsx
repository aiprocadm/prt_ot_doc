import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { useDebounce } from "@/hooks/useDebounce";

const DebouncedInput = () => {
  const [value, setValue] = useState("");
  const debounced = useDebounce(value, 200);
  return (
    <div>
      <input
        aria-label="input"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <span data-testid="debounced">{debounced}</span>
    </div>
  );
};

describe("useDebounce", () => {
  it("обновляет значение после задержки", async () => {
    const user = userEvent.setup();
    render(<DebouncedInput />);

    await act(async () => {
      await user.type(screen.getByLabelText("input"), "abc");
    });
    expect(screen.getByTestId("debounced")).toHaveTextContent("");

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 250));
    });
    expect(screen.getByTestId("debounced")).toHaveTextContent("abc");
  });
});
