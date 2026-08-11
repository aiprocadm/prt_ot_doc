import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClosingPanel } from "./ClosingPanel";
import type { SignerRow } from "./SignaturesPanel";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import type { WorkPermitClosingSummaryDto } from "@/types/dto/workPermits";

const baseSummary: WorkPermitClosingSummaryDto = {
  completion_text: null,
  completion_recorded_at: null,
  signatures: [],
  can_close: false,
  missing: ["completion_act", "handover_signature", "acceptance_signature"],
};

const baseSigners: SignerRow[] = [
  { personId: "p1", name: "Иванов Иван Иванович", roleLabel: "Производитель работ" },
  { personId: "p2", name: "Петров Пётр Петрович", roleLabel: "Ответственный руководитель" },
];

const setWithManage = () =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["ot_specialist"], permissions: [PERMISSIONS.WORK_PERMIT_MANAGE] } as never,
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });

const setWithoutManage = () =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["worker"], permissions: [] } as never,
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });

describe("ClosingPanel", () => {
  beforeEach(() => {
    setWithManage();
  });

  it("кнопка «Закрыть» disabled и показывает причину пока can_close=false", () => {
    render(
      <ClosingPanel
        summary={baseSummary}
        signers={baseSigners}
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
        signers={baseSigners}
        canManage
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={() => "ФИО"}
      />,
    );
    expect(screen.getByRole("button", { name: /закрыть наряд/i })).toBeEnabled();
  });

  it("скрывает кнопку «Оформить акт» при canManage=false", () => {
    setWithoutManage();
    render(
      <ClosingPanel
        summary={baseSummary}
        signers={baseSigners}
        canManage={false}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={() => "ФИО"}
      />,
    );
    // Кнопка «Оформить акт» не должна быть видна
    expect(screen.queryByRole("button", { name: /оформить акт/i })).not.toBeInTheDocument();
  });

  it("при canManage=true и подписанте без подписи рендерится кнопка «Зафиксировать»", () => {
    render(
      <ClosingPanel
        summary={baseSummary}
        signers={baseSigners}
        canManage
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        nameOf={() => "ФИО"}
      />,
    );
    // SignaturesPanel рендерит кнопки для каждого подписанта без подписи
    const fixButtons = screen.getAllByRole("button", { name: /зафиксировать/i });
    expect(fixButtons.length).toBe(baseSigners.length);
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
        signers={[{ personId: "p1", name: "Иванов Иван Иванович", roleLabel: "Производитель работ" }]}
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
