import { type ColumnDef, type SortingState, flexRender, getCoreRowModel, getSortedRowModel, useReactTable } from "@tanstack/react-table";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounce } from "@/hooks/useDebounce";

interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  isLoading?: boolean;
  pageIndex: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  renderToolbar?: React.ReactNode;
  emptyMessage?: string;
  caption?: string;
}

const pageSizeOptions = [10, 25, 50, 100];

export function DataTable<TData>({
  columns,
  data,
  isLoading = false,
  pageIndex,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  onSearchChange,
  searchPlaceholder = "Поиск",
  renderToolbar,
  emptyMessage = "Нет данных",
  caption
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [search, setSearch] = React.useState("");
  const debouncedSearch = useDebounce(search, 400);

  React.useEffect(() => {
    if (onSearchChange) onSearchChange(debouncedSearch);
  }, [debouncedSearch, onSearchChange]);

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting
    },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true
  });

  const pageCount = Math.ceil(total / pageSize) || 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {onSearchChange && (
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={searchPlaceholder}
              className="w-64"
              aria-label={searchPlaceholder}
            />
          )}
          {renderToolbar}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="page-size">
            Строк на странице
          </label>
          <select
            id="page-size"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {pageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="rounded-md border">
        <Table>
          {caption && <TableCaption>{caption}</TableCaption>}
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  return (
                    <TableHead key={header.id}>
                      {canSort ? (
                        <Button
                          variant="ghost"
                          className="-ml-3 h-8 px-3"
                          onClick={header.column.getToggleSortingHandler()}
                          aria-label="Сортировать"
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          <span className="ml-2 text-xs text-muted-foreground">
                            {header.column.getIsSorted() === "asc"
                              ? "↑"
                              : header.column.getIsSorted() === "desc"
                              ? "↓"
                              : ""}
                          </span>
                        </Button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  <Loader2 className="mx-auto h-6 w-6 animate-spin" aria-label="Загрузка" />
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() && "selected"}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Страница {pageIndex} из {pageCount} • Всего {total}
        </p>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => onPageChange(1)} disabled={pageIndex === 1}>
            « Первая
          </Button>
          <Button variant="outline" size="sm" onClick={() => onPageChange(Math.max(1, pageIndex - 1))} disabled={pageIndex === 1}>
            ← Назад
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(Math.min(pageCount, pageIndex + 1))}
            disabled={pageIndex >= pageCount}
          >
            Вперёд →
          </Button>
          <Button variant="outline" size="sm" onClick={() => onPageChange(pageCount)} disabled={pageIndex >= pageCount}>
            Последняя »
          </Button>
        </div>
      </div>
    </div>
  );
}
