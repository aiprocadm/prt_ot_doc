import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpoAttestationFormDialog } from "@/features/industrial-safety/OpoAttestationFormDialog";
import { PcMeasureFormDialog } from "@/features/industrial-safety/PcMeasureFormDialog";
import { PcPlanFormDialog } from "@/features/industrial-safety/PcPlanFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import {
  opoAttestationFormSchema,
  pcMeasureFormSchema,
} from "@/types/forms/industrialSafety";

const createPlanMock = vi.fn();
const updatePlanMock = vi.fn();
const createMeasureMock = vi.fn();
const updateMeasureMock = vi.fn();
const createAttestationMock = vi.fn();
const updateAttestationMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/industrialSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  industrialSafetyApi: {
    createPcPlan: (...args: unknown[]) => createPlanMock(...args),
    updatePcPlan: (...args: unknown[]) => updatePlanMock(...args),
    createPcMeasure: (...args: unknown[]) => createMeasureMock(...args),
    updatePcMeasure: (...args: unknown[]) => updateMeasureMock(...args),
  },
}));

vi.mock("@/api/attestations", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  attestationsApi: {
    create: (...args: unknown[]) => createAttestationMock(...args),
    update: (...args: unknown[]) => updateAttestationMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const plans = [
  {
    id: "plan-1",
    year: 2026,
    title: "План ПК на 2026 год",
    responsible: "Петров",
    approved_on: "2026-01-10",
    status: "approved",
    status_label: "Утверждён",
    notes: null,
    measures_total: 2,
    measures_overdue: 1,
  },
] as never;

const overdueMeasure = {
  id: "measure-1",
  plan_id: "plan-1",
  section: "inspections",
  section_label: "Обследования и проверки состояния ОПО",
  title: "Обследование зданий",
  due_on: "2026-05-01",
  responsible: "Сидоров",
  status: "overdue",
  status_label: "Просрочено",
  completed_on: null,
  result: null,
};

const persons = [
  { id: "person-1", full_name: "Иванов Иван Иванович" },
] as never;

describe("PcPlanFormDialog — план производственного контроля (срез-106)", () => {
  beforeEach(() => {
    createPlanMock.mockReset();
    updatePlanMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createPlanMock.mockResolvedValue({ id: "plan-new" });
    updatePlanMock.mockResolvedValue(plans[0]);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(<PcPlanFormDialog trigger={<button>Завести план ПК</button>} />);
    await user.click(screen.getByRole("button", { name: "Завести план ПК" }));
  };

  it("отправляет год числом, название и состояние", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.clear(screen.getByLabelText("Год"));
    await user.type(screen.getByLabelText("Год"), "2027");
    await user.type(screen.getByLabelText("План"), "План ПК на 2027 год");
    await user.type(
      screen.getByLabelText("Ответственный за осуществление ПК"),
      "Петров",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createPlanMock).toHaveBeenCalled());
    expect(createPlanMock.mock.calls[0][0]).toEqual({
      year: 2027,
      title: "План ПК на 2027 год",
      status: "draft",
      responsible: "Петров",
      approved_on: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("План заведён");
  });

  it("утверждённый план без даты утверждения не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.type(screen.getByLabelText("План"), "План ПК");
    await user.selectOptions(screen.getByLabelText("Состояние"), "approved");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("У утверждённого плана нужна дата утверждения"),
    ).toBeInTheDocument();
    expect(createPlanMock).not.toHaveBeenCalled();
  });

  it("на первом уровне четыре поля; отсутствие плана не объявляется нарушением", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Год");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/нарушением его не объявляет/i),
    ).toBeInTheDocument();
  });
});

describe("PcMeasureFormDialog — мероприятие плана ПК (срез-106)", () => {
  beforeEach(() => {
    createMeasureMock.mockReset();
    updateMeasureMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createMeasureMock.mockResolvedValue({ id: "measure-new" });
    updateMeasureMock.mockResolvedValue(overdueMeasure);
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <PcMeasureFormDialog
        plans={plans}
        trigger={<button>Запланировать мероприятие</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Запланировать мероприятие" }),
    );
  };

  it("«Просрочено» выбрать нельзя: это вычисляемое состояние", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    const statuses = Array.from(
      screen.getByLabelText("Состояние").querySelectorAll("option"),
    ).map((option) => option.getAttribute("value"));
    expect(statuses).toEqual(["planned", "done", "cancelled"]);
  });

  it("выполненное без даты выполнения не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("План ПК"), "plan-1");
    await user.type(screen.getByLabelText("Мероприятие"), "Обследование");
    await user.type(screen.getByLabelText("Срок"), "2026-05-01");
    await user.selectOptions(screen.getByLabelText("Состояние"), "done");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "У выполненного мероприятия обязательна дата выполнения",
      ),
    ).toBeInTheDocument();
    expect(createMeasureMock).not.toHaveBeenCalled();
  });

  it("правка просроченного мероприятия не отправляет «overdue» обратно", async () => {
    const user = userEvent.setup();
    render(
      <PcMeasureFormDialog
        plans={plans}
        initialData={overdueMeasure}
        trigger={<button>Изменить</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Изменить" }));

    // Состояние подставлено как «запланировано»: «просрочено» сервер не примет.
    expect(screen.getByLabelText("Состояние")).toHaveValue("planned");

    await user.clear(screen.getByLabelText("Срок"));
    await user.type(screen.getByLabelText("Срок"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateMeasureMock).toHaveBeenCalled());
    expect(updateMeasureMock.mock.calls[0][1]).toMatchObject({
      status: "planned",
      due_on: "2026-09-01",
      responsible: "Сидоров",
    });
  });

  it("на первом уровне пять полей: выполнение свёрнуто", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("План ПК");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText("Ответственный, выполнение и результат"),
    ).toBeInTheDocument();
  });
});

describe("OpoAttestationFormDialog — аттестация по промбезопасности (срез-106)", () => {
  beforeEach(() => {
    createAttestationMock.mockReset();
    updateAttestationMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createAttestationMock.mockResolvedValue({ id: "att-new" });
    updateAttestationMock.mockResolvedValue({ id: "att-1" });
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <OpoAttestationFormDialog
        persons={persons}
        trigger={<button>Внести аттестацию</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Внести аттестацию" }));
  };

  it("область обязательна: без неё запись не попала бы в реестр контура", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Работник"), "person-1");
    await user.type(screen.getByLabelText("Аттестация"), "Аттестация Б.9");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Выберите область аттестации"),
    ).toBeInTheDocument();
    expect(createAttestationMock).not.toHaveBeenCalled();
  });

  it("срок раньше даты выдачи не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Работник"), "person-1");
    await user.selectOptions(
      screen.getByLabelText("Область аттестации"),
      "А.1",
    );
    await user.type(screen.getByLabelText("Аттестация"), "Аттестация А.1");
    await user.type(screen.getByLabelText("Действует до"), "2026-01-01");
    await user.click(screen.getByText("Дата выдачи и заметки"));
    await user.type(screen.getByLabelText("Выдана"), "2026-06-01");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Срок действия не может быть раньше даты выдачи"),
    ).toBeInTheDocument();
    expect(createAttestationMock).not.toHaveBeenCalled();
  });

  it("на первом уровне пять полей: дата выдачи свёрнута", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Работник");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText("Дата выдачи и заметки")).toBeInTheDocument();
  });
});

describe("схемы форм ПромБеза (срез-106)", () => {
  it("мероприятие: «выполнено» требует дату", () => {
    expect(
      pcMeasureFormSchema.safeParse({
        plan_id: "plan-1",
        section: "epb",
        title: "Диагностирование",
        due_on: "2026-05-01",
        status: "done",
      }).success,
    ).toBe(false);
  });

  it("аттестация: одинаковые даты выдачи и окончания допустимы", () => {
    expect(
      opoAttestationFormSchema.safeParse({
        person_id: "person-1",
        area_code: "Б.9",
        name: "Аттестация",
        status: "active",
        issued_at: "2026-01-01",
        expires_at: "2026-01-01",
      }).success,
    ).toBe(true);
  });
});
