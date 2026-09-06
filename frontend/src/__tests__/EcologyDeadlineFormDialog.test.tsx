import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EcologyDeadlineFormDialog } from "@/features/ecology/EcologyDeadlineFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { ecologyReportingFormSchema } from "@/types/forms/ecologyReporting";

const createMock = vi.fn();
const updateMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/ecology", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/ecology")>("@/api/ecology");
  return {
    ...actual,
    ecologyApi: {
      createReportingDeadline: (...args: unknown[]) => createMock(...args),
      updateReportingDeadline: (...args: unknown[]) => updateMock(...args),
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

/** Срок, как его отдаёт бэкенд: состояние выведено на сервере. */
const existing = {
  id: "rd-1",
  kind: "payment",
  kind_label: "Платёж",
  title: "Авансовый платёж за НВОС, III квартал",
  period: "3 кв. 2026",
  due_on: "2026-10-20",
  done_on: null,
  responsible: "Эколог Иванова",
  notes: null,
  status: "planned",
  status_label: "Предстоит",
};

const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
  render(<EcologyDeadlineFormDialog trigger={<button>Внести срок</button>} />);
  await user.click(screen.getByRole("button", { name: "Внести срок" }));
};

describe("EcologyDeadlineFormDialog — срок отчётности или платежа (срез-98)", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMock.mockResolvedValue({ ...existing, id: "rd-new" });
    updateMock.mockResolvedValue(existing);
  });

  it("отправляет вид, название и срок; пустые поля — null, не пустой текст", async () => {
    const user = userEvent.setup();
    const onSubmitted = vi.fn();
    render(
      <EcologyDeadlineFormDialog
        trigger={<button>Внести срок</button>}
        onSubmitted={onSubmitted}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Внести срок" }));

    await user.selectOptions(screen.getByLabelText("Вид"), "payment");
    await user.type(
      screen.getByLabelText("Что сдать или оплатить"),
      "  Авансовый платёж за НВОС, III квартал  ",
    );
    await user.type(screen.getByLabelText("Период"), "3 кв. 2026");
    await user.type(screen.getByLabelText("Срок"), "2026-10-20");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0]).toEqual({
      kind: "payment",
      title: "Авансовый платёж за НВОС, III квартал",
      period: "3 кв. 2026",
      due_on: "2026-10-20",
      done_on: null,
      responsible: null,
      notes: null,
    });
    expect(onSubmitted).toHaveBeenCalledWith(
      expect.objectContaining({ id: "rd-new" }),
    );
    expect(toastSuccess).toHaveBeenCalledWith("Срок внесён");
  });

  it("без названия и срока запрос не уходит — ошибки у полей словами", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Назовите, что сдать или оплатить"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Внесите срок по нормативному акту"),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("правка подставляет запись, вид не меняется, дата исполнения уходит в PATCH", async () => {
    const user = userEvent.setup();
    render(
      <EcologyDeadlineFormDialog
        initialData={existing}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    expect(
      screen.getByRole("heading", { name: "Изменить срок" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Что сдать или оплатить")).toHaveValue(
      existing.title,
    );
    expect(screen.getByLabelText("Срок")).toHaveValue("2026-10-20");
    // Вид задаёт «сдать» или «уплатить»; ручка правки его не принимает —
    // поле показано, но заперто, чтобы форма не обещала того, чего не сохранит.
    expect(screen.getByLabelText("Вид")).toBeDisabled();

    await user.type(screen.getByLabelText("Дата исполнения"), "2026-10-15");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock.mock.calls[0][0]).toBe("rd-1");
    expect(updateMock.mock.calls[0][1]).toEqual({
      title: existing.title,
      period: "3 кв. 2026",
      due_on: "2026-10-20",
      done_on: "2026-10-15",
      responsible: "Эколог Иванова",
      notes: null,
    });
    expect(createMock).not.toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith("Срок обновлён");
  });

  it("ответ 422 бэкенда показывается словами, окно не закрывается", async () => {
    const user = userEvent.setup();
    createMock.mockRejectedValueOnce({
      status: 422,
      message: "Срок '2-ТП (отходы)' на 2026-02-01 уже внесён",
      field_errors: [],
    });
    await openCreate(user);

    await user.type(
      screen.getByLabelText("Что сдать или оплатить"),
      "2-ТП (отходы)",
    );
    await user.type(screen.getByLabelText("Срок"), "2026-02-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже внесён");
    expect(
      screen.getByRole("heading", { name: "Внести срок" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне пять полей: ответственный и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Вид");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Дополнительно")).toBeInTheDocument();
    // Подсказки «когда сдавать 2-ТП» в форме нет намеренно: дату задаёт
    // нормативный акт, а не платформа (граница среза-23).
    expect(screen.queryByText(/платформа .* назначает/i)).not.toBeNull();
  });
});

describe("ecologyReportingFormSchema", () => {
  it("отклоняет пустое название и пустой срок", () => {
    expect(
      ecologyReportingFormSchema.safeParse({
        kind: "report",
        title: "   ",
        due_on: "",
      }).success,
    ).toBe(false);
  });

  it("принимает форму с пустыми необязательными полями", () => {
    expect(
      ecologyReportingFormSchema.safeParse({
        kind: "report",
        title: "2-ТП (воздух) за 2025 год",
        due_on: "2026-01-22",
      }).success,
    ).toBe(true);
  });
});
