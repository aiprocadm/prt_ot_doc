import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ClosingPanel } from "./ClosingPanel";
import type { WorkPermitClosingSummaryDto } from "@/types/dto/workPermits";

const baseSummary: WorkPermitClosingSummaryDto = {
  completion_text: null,
  completion_recorded_at: null,
  signatures: [],
  can_close: false,
  missing: ["completion_act", "handover_signature", "acceptance_signature"],
};

describe("ClosingPanel", () => {
  it("кнопка «Закрыть» disabled и показывает причину пока can_close=false", () => {
    render(
      <ClosingPanel
        summary={baseSummary}
        canManage
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={() => "ФИО"}
      />,
    );
    const btn = screen.getByRole("button", { name: /закрыть наряд/i });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/не оформлен акт окончания работ/i)).toBeInTheDocument();
  });

  it("кнопка «Закрыть» активна при can_close=true", () => {
    render(
      <ClosingPanel
        summary={{ ...baseSummary, completion_text: "работы окончены", can_close: true, missing: [] }}
        canManage
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={() => "ФИО"}
      />,
    );
    expect(screen.getByRole("button", { name: /закрыть наряд/i })).toBeEnabled();
  });

  it("скрывает кнопки действий при canManage=false", () => {
    render(
      <ClosingPanel
        summary={baseSummary}
        canManage={false}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={() => "ФИО"}
      />,
    );
    // Кнопка «Оформить акт» не должна быть видна
    expect(screen.queryByRole("button", { name: /оформить акт/i })).not.toBeInTheDocument();
  });

  it("показывает статус подписей из summary", () => {
    const summary: WorkPermitClosingSummaryDto = {
      ...baseSummary,
      signatures: [
        {
          id: "sig1",
          stream: "closing",
          object_type: "work_permit_closing",
          object_id: "wp1",
          purpose: "work_permit_closing",
          status: "signed",
          signer_person_id: "p1",
          signer_name: "Иванов И.И.",
          content_hash: null,
          signed_at: "2026-06-20T10:00:00Z",
        },
      ],
    };
    render(
      <ClosingPanel
        summary={summary}
        canManage
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={(id) => (id === "p1" ? "Иванов Иван Иванович" : id)}
      />,
    );
    expect(screen.getByText(/иванов иван иванович/i)).toBeInTheDocument();
    expect(screen.getByText(/подписан/i)).toBeInTheDocument();
  });
});
