import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkspaceDataQualityPage from "@/pages/workspace/WorkspaceDataQualityPage";
import type { DataQualityReportDto } from "@/types/dto/dataQuality";

const getReportMock = vi.fn();

vi.mock("@/api/dataQuality", () => ({
  dataQualityApi: {
    getReport: (...args: unknown[]) => getReportMock(...args)
  }
}));

const sampleReport: DataQualityReportDto = {
  tenant_id: "tenant-1",
  completeness_percent: 82.5,
  total_issues: 4,
  critical_issues: 1,
  high_issues: 2,
  medium_issues: 1,
  low_issues: 0,
  issue_breakdown: {
    expired_record: 2,
    missing_field: 1,
    data_mismatch: 1
  },
  entity_breakdown: {
    person: 2,
    document: 1,
    permit: 1
  },
  issues: [
    {
      id: "missing_mandatory_fields:p1",
      issue_type: "missing_field",
      severity: "critical",
      title: "У сотрудника отсутствует должность",
      description: "Поле position обязательно",
      affected_entity_type: "person",
      affected_entity_id: "p1",
      affected_entity_name: "Иванов И.И.",
      additional_info: { field: "position" },
      found_at: "2026-05-04T10:00:00Z"
    },
    {
      id: "expired_records:p2",
      issue_type: "expired_record",
      severity: "high",
      title: "Истёк медосмотр",
      description: "valid_until < today",
      affected_entity_type: "medical_exam",
      affected_entity_id: "exam-9",
      affected_entity_name: "Медосмотр Петров",
      additional_info: {},
      found_at: "2026-05-04T10:00:00Z"
    },
    {
      id: "expired_permits:permit-1",
      issue_type: "expired_record",
      severity: "high",
      title: "Просроченный наряд-допуск",
      description: null,
      affected_entity_type: "permit",
      affected_entity_id: "permit-1",
      affected_entity_name: null,
      additional_info: {},
      found_at: "2026-05-04T10:00:00Z"
    },
    {
      id: "document_person_company_mismatch:doc-1",
      issue_type: "data_mismatch",
      severity: "medium",
      title: "Документ оформлен не на того контрагента",
      description: "Document.company_id != Person.company_id",
      affected_entity_type: "document",
      affected_entity_id: "doc-1",
      affected_entity_name: null,
      additional_info: {},
      found_at: "2026-05-04T10:00:00Z"
    }
  ],
  check_results: [
    {
      rule_name: "missing_mandatory_fields",
      rule_description: "Required fields are present on entities",
      total_checked: 100,
      issues_found: 1,
      issues: [],
      execution_time_ms: 12.4
    },
    {
      rule_name: "expired_records",
      rule_description: "Records past their validity",
      total_checked: 220,
      issues_found: 2,
      issues: [],
      execution_time_ms: 8.1
    }
  ],
  generated_at: "2026-05-04T10:00:00Z"
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <WorkspaceDataQualityPage />
    </MemoryRouter>
  );

describe("WorkspaceDataQualityPage", () => {
  beforeEach(() => {
    getReportMock.mockReset();
  });

  it("renders severity cards and breakdowns from /data-quality/report", async () => {
    getReportMock.mockResolvedValueOnce(sampleReport);

    renderPage();

    expect(await screen.findByText("Полнота данных")).toBeInTheDocument();
    expect(screen.getByText("82.5%")).toBeInTheDocument();
    expect(screen.getByLabelText("Критичные: 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Высокий риск: 2")).toBeInTheDocument();
    expect(screen.getByText("Истёк медосмотр")).toBeInTheDocument();
    expect(screen.getByText("Просроченный наряд-допуск")).toBeInTheDocument();
    expect(screen.getByText("missing_mandatory_fields")).toBeInTheDocument();
  });

  it("filters issues by severity when chip is pressed", async () => {
    getReportMock.mockResolvedValueOnce(sampleReport);

    renderPage();

    expect(await screen.findByText("Истёк медосмотр")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Критично", pressed: false }));

    await waitFor(() => {
      expect(screen.queryByText("Истёк медосмотр")).not.toBeInTheDocument();
    });
    expect(screen.getByText("У сотрудника отсутствует должность")).toBeInTheDocument();
  });

  it("renders drill-down link for known entity types", async () => {
    getReportMock.mockResolvedValueOnce(sampleReport);

    renderPage();

    const personRow = (await screen.findByText("У сотрудника отсутствует должность")).closest("tr");
    expect(personRow).not.toBeNull();
    const link = within(personRow as HTMLElement).getByRole("link", { name: /Открыть/ });
    expect(link).toHaveAttribute("href", "/persons?focus=p1");
  });

  it("renders empty state when there are no issues", async () => {
    getReportMock.mockResolvedValueOnce({
      ...sampleReport,
      total_issues: 0,
      critical_issues: 0,
      high_issues: 0,
      medium_issues: 0,
      low_issues: 0,
      issue_breakdown: {},
      entity_breakdown: {},
      issues: []
    });

    renderPage();

    expect(await screen.findByText("Все проверки пройдены")).toBeInTheDocument();
  });

  it("renders error state and allows retry", async () => {
    getReportMock.mockRejectedValueOnce({
      status: 500,
      message: "boom",
      field_errors: []
    });

    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();

    getReportMock.mockResolvedValueOnce(sampleReport);
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Истёк медосмотр")).toBeInTheDocument();
  });
});
