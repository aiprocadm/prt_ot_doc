import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ApprovalTaskCard from "@/components/ApprovalTaskCard";
import { approvalsApi } from "@/api/approvals";
import { toast } from "sonner";

vi.mock("@/api/approvals", () => ({
  approvalsApi: { decide: vi.fn(), decideTask: vi.fn(), delegateTask: vi.fn() },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const task = { id: "task-1234abcd", instance_id: "inst-9", status: "pending" };

describe("ApprovalTaskCard — действия по задаче", () => {
  beforeEach(() => {
    (approvalsApi.decideTask as Mock).mockReset().mockResolvedValue({});
    (approvalsApi.delegateTask as Mock).mockReset().mockResolvedValue({});
    (approvalsApi.decide as Mock).mockReset();
    (toast.error as Mock).mockReset();
  });

  it("«Согласовать» вызывает task-эндпоинт decideTask (а не process-уровневый decide)", async () => {
    render(<ApprovalTaskCard task={task} onChanged={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("Комментарий"), { target: { value: "ок" } });
    fireEvent.click(screen.getByText("Согласовать"));
    await waitFor(() => expect(approvalsApi.decideTask).toHaveBeenCalledWith("task-1234abcd", "approve", "ок"));
    expect(approvalsApi.decide).not.toHaveBeenCalled();
  });

  it("«Делегировать» вызывает delegateTask с id пользователя", async () => {
    render(<ApprovalTaskCard task={task} onChanged={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("ID пользователя для делегирования"), {
      target: { value: "user-7" },
    });
    fireEvent.click(screen.getByText("Делегировать"));
    await waitFor(() => expect(approvalsApi.delegateTask).toHaveBeenCalledWith("task-1234abcd", "user-7", ""));
    expect(approvalsApi.decide).not.toHaveBeenCalled();
  });

  it("при ошибке действия показывает toast.error, а не молча проглатывает", async () => {
    (approvalsApi.decideTask as Mock).mockRejectedValue(new Error("boom"));
    render(<ApprovalTaskCard task={task} onChanged={() => {}} />);
    fireEvent.click(screen.getByText("Отклонить"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
