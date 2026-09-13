import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { useCompaniesStore } from "@/stores/companies";
import { useRiskStore } from "@/stores/risk";
import type { RiskAssessmentDto } from "@/types/dto/risk";
import { formatDate } from "@/utils/datetime";

const RISK_STATUS_LABELS: Record<RiskAssessmentDto["status"], string> = {
  draft: "Черновик",
  approved: "Утвержден",
};

const resolveRiskLevel = (score: number) => {
  if (score >= 15) return "Критический";
  if (score >= 10) return "Высокий";
  if (score >= 6) return "Средний";
  return "Низкий";
};

export const RiskAssessmentsTable = () => {
  // Срез-152: колонка «Экспорт» снята — ручки выгрузки расчёта
  // (`GET /risk/assessments/{id}/export`) в контракте сервера нет вовсе,
  // и кнопка всегда кончалась 404. Возврат — вместе с ручкой выгрузки.
  const { assessments, listAssessments, loading } = useRiskStore();
  const companies = useCompaniesStore((state) => state.items);

  const columns = useMemo<ColumnDef<RiskAssessmentDto>[]>(
    () => [
      {
        accessorKey: "id",
        header: "ID",
        cell: ({ row }) => row.original.id,
      },
      {
        accessorKey: "company_id",
        header: "Компания",
        cell: ({ row }) =>
          companies.find((company) => company.id === row.original.company_id)
            ?.name ?? row.original.company_id,
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) =>
          RISK_STATUS_LABELS[row.original.status] ?? row.original.status,
      },
      {
        accessorKey: "total_score",
        header: "Индекс",
        cell: ({ row }) =>
          `${row.original.total_score.toFixed(2)} · ${resolveRiskLevel(row.original.total_score)}`,
      },
      {
        accessorKey: "updated_at",
        header: "Обновлено",
        cell: ({ row }) => formatDate(row.original.updated_at),
      },
    ],
    [companies],
  );

  return (
    <DataTable
      columns={columns}
      data={assessments}
      isLoading={loading}
      pageIndex={1}
      pageSize={assessments.length || 1}
      total={assessments.length}
      onPageChange={() => listAssessments()}
      onPageSizeChange={() => listAssessments()}
      caption="Расчёты рисков"
    />
  );
};
