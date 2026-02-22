import { type ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/common/DataTable";
import { ActionButton } from "@/components/permissions/ActionButton";
import { PERMISSIONS } from "@/permissions/permissions";
import { useRiskStore } from "@/stores/risk";
import type { RiskAssessmentDto } from "@/types/dto/risk";
import { formatDate } from "@/utils/datetime";
import { downloadBlob } from "@/utils/download";

export const RiskAssessmentsTable = () => {
  const { assessments, listAssessments, exportAssessment, loading } = useRiskStore();

  const columns = useMemo<ColumnDef<RiskAssessmentDto>[]>(
    () => [
      {
        accessorKey: "id",
        header: "ID",
        cell: ({ row }) => row.original.id
      },
      {
        accessorKey: "company_id",
        header: "Компания",
        cell: ({ row }) => row.original.company_id
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => row.original.status
      },
      {
        accessorKey: "total_score",
        header: "Индекс",
        cell: ({ row }) => row.original.total_score.toFixed(2)
      },
      {
        accessorKey: "updated_at",
        header: "Обновлено",
        cell: ({ row }) => formatDate(row.original.updated_at)
      },
      {
        id: "export",
        header: "Экспорт",
        cell: ({ row }) => (
          <ActionButton
            permission={PERMISSIONS.RISK_EXPORT}
            abilityResource={{ status: row.original.status, company_id: row.original.company_id }}
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
        )
      }
    ],
    [exportAssessment]
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
