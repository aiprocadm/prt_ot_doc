import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it, vi } from "vitest";

import { DataTable } from "@/components/common/DataTable";

type Row = { id: number; name: string };

const columns: ColumnDef<Row>[] = [
  {
    accessorKey: "name",
    header: "Название",
    cell: ({ getValue }) => <span>{getValue<string>()}</span>
  }
];

describe("DataTable", () => {
  it("рендерит строки и поддерживает пагинацию", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: "A" }, { id: 2, name: "B" }]}
        pageIndex={1}
        pageSize={10}
        total={25}
        onPageChange={onPageChange}
        onPageSizeChange={() => undefined}
        emptyMessage="Нет строк"
      />
    );

    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Вперёд →" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("вызывает поиск после дебаунса", async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={[]}
        pageIndex={1}
        pageSize={10}
        total={0}
        onPageChange={() => undefined}
        onPageSizeChange={() => undefined}
        onSearchChange={onSearchChange}
      />
    );

    await act(async () => {
      await user.type(screen.getByRole("textbox", { name: "Поиск" }), "ABC");
    });
    await waitFor(() => {
      const lastCall = onSearchChange.mock.calls.at(-1);
      expect(lastCall?.[0]).toBe("ABC");
    }, { timeout: 1000 });
  });

  it("отображает сообщение об отсутствии данных", () => {
    render(
      <DataTable
        columns={columns}
        data={[]}
        pageIndex={1}
        pageSize={10}
        total={0}
        onPageChange={() => undefined}
        onPageSizeChange={() => undefined}
        emptyMessage="Данных нет"
      />
    );

    expect(screen.getByText("Данных нет")).toBeInTheDocument();
  });
});
