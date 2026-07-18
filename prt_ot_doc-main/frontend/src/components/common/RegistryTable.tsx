import { type ColumnDef } from "@tanstack/react-table";
import type { ReactNode } from "react";

import { DataTable } from "@/components/common/DataTable";

interface RegistryTableProps<TData> {
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
  emptyMessage?: string;
  caption: string;
  renderToolbar?: ReactNode;
}

export function RegistryTable<TData>(props: RegistryTableProps<TData>) {
  return <DataTable {...props} />;
}
