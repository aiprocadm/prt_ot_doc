import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InternshipFormDialog } from "@/features/internships/InternshipFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { internshipFormSchema } from "@/types/forms/internships";

const createMock = vi.fn();
const updateMock = vi.fn();

vi.mock("@/api/internships", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/internships")>(
      "@/api/internships",
    );
  return {
    ...actual,
    internshipsApi: {
      list: vi.fn(),
      summary: vi.fn(),
      create: (...args: unknown[]) => createMock(...args),
      update: (...args: unknown[]) => updateMock(...args),
    },
  };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const persons = [
  { id: "p1", full_name: "Иванов И. И." },
  { id: "p2", full_name: "Петров П. П." },
] as never;

const openDialog = async (user: ReturnType<typeof userEvent.setup>) => {
  render(
    <InternshipFormDialog
      persons={persons}
      trigger={<button>Назначить</button>}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Назначить" }));
};

describe("InternshipFormDialog — назначение стажировки", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    createMock.mockResolvedValue({ id: "i1" });
  });

  it("отправляет стажёра, наставника, смены и состояние; пустые поля — null", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    await user.selectOptions(screen.getByLabelText("Стажёр"), "p1");
    await user.selectOptions(screen.getByLabelText("Наставник"), "p2");
    await user.type(
      screen.getByLabelText("На что стажировка"),
      "Водитель автобуса",
    );
    await user.selectOptions(
      screen.getByLabelText("Дисциплина"),
      "road_safety",
    );
    await user.type(screen.getByLabelText("Смен по плану"), "10");
    await user.selectOptions(screen.getByLabelText("Состояние"), "in_progress");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock.mock.calls[0][0]).toEqual({
      person_id: "p1",
      mentor_person_id: "p2",
      discipline: "road_safety",
      subject: "Водитель автобуса",
      planned_shifts: 10,
      completed_shifts: 0,
      started_on: null,
      finished_on: null,
      status: "in_progress",
      notes: null,
    });
  });

  it("наставник не может быть стажёром — ошибка у поля, запрос не уходит", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    await user.selectOptions(screen.getByLabelText("Стажёр"), "p1");
    await user.selectOptions(screen.getByLabelText("Наставник"), "p1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(/Наставник не может быть стажёром/i),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("на первом уровне не больше семи полей: сроки и заметки свёрнуты", async () => {
    const user = userEvent.setup();
    await openDialog(user);
    await screen.findByLabelText("Стажёр");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Сроки и заметки")).toBeInTheDocument();
  });
});

describe("internshipFormSchema", () => {
  it("отклоняет пустого стажёра и дробные смены", () => {
    expect(
      internshipFormSchema.safeParse({
        person_id: "",
        planned_shifts: "1.5",
        completed_shifts: "",
        status: "planned",
      }).success,
    ).toBe(false);
  });

  it("принимает форму с пустыми необязательными полями", () => {
    expect(
      internshipFormSchema.safeParse({
        person_id: "p1",
        planned_shifts: "",
        completed_shifts: "",
        status: "planned",
      }).success,
    ).toBe(true);
  });
});
