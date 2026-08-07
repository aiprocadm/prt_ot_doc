import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { ActionButton } from "@/components/permissions/ActionButton";
import { PERMISSIONS } from "@/permissions/permissions";
import { useCompaniesStore } from "@/stores/companies";
import { useRiskStore } from "@/stores/risk";
import type { RiskAssessmentDto } from "@/types/dto/risk";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

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
  const { assessments, listAssessments, exportAssessment, loading } =
    useRiskStore();
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
      {
        id: "export",
        header: "Экспорт",
        cell: ({ row }) => (
          <ActionButton
            permission={PERMISSIONS.RISK_EXPORT}
            abilityResource={{
              status: row.original.status,
              company_id: row.original.company_id,
            }}
            variant="ghost"
            size="sm"
            disabledReason="Экспорт доступен после утверждения расчёта"
            onClick={async () => {
              const blob = await exportAssessment(row.original.id);
              downloadBlob(blob, `risk-${row.original.id}.pdf`);
            }}
          >
            Скачать
          </ActionButton>
        ),
      },
    ],
    [companies, exportAssessment],
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
