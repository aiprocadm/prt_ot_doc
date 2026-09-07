import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CdDocumentFormDialog } from "@/features/civil-defense/CdDocumentFormDialog";
import { CdFormationMembersDialog } from "@/features/civil-defense/CdFormationMembersDialog";
import { CdProfileFormDialog } from "@/features/civil-defense/CdProfileFormDialog";
import { uxBudgetViolations } from "@/test-utils/uxBudget";
import { cdProfileFormSchema } from "@/types/forms/civilDefense";

const createProfileMock = vi.fn();
const updateProfileMock = vi.fn();
const createDocumentMock = vi.fn();
const updateDocumentMock = vi.fn();
const listMembersMock = vi.fn();
const addMemberMock = vi.fn();
const updateMemberMock = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("@/api/civilDefense", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  civilDefenseApi: {
    createProfile: (...args: unknown[]) => createProfileMock(...args),
    updateProfile: (...args: unknown[]) => updateProfileMock(...args),
    createDocument: (...args: unknown[]) => createDocumentMock(...args),
    updateDocument: (...args: unknown[]) => updateDocumentMock(...args),
    listFormationMembers: (...args: unknown[]) => listMembersMock(...args),
    addFormationMember: (...args: unknown[]) => addMemberMock(...args),
    updateFormationMember: (...args: unknown[]) => updateMemberMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const sites = [{ id: "site-1", name: "Площадка №1" }] as never;
const persons = [
  { id: "person-1", full_name: "Иванов Иван Иванович" },
  { id: "person-2", full_name: "Петров Пётр Петрович" },
] as never;

const formation = {
  id: "cd-1",
  name: "Звено пожаротушения",
  kind: "nasf",
  kind_label: "НАСФ (аварийно-спасательное формирование)",
  purpose: null,
  commander_person_id: null,
  commander_name: null,
  equipment_notes: null,
  notes: null,
  members_active: 1,
} as never;

const activeMember = {
  id: "m-1",
  formation_id: "cd-1",
  person_id: "person-1",
  person_name: "Иванов Иван Иванович",
  role_in_formation: "командир звена",
  assigned_on: "2026-01-10",
  released_on: null,
  notes: null,
  status: "active",
  status_label: "В составе",
};

const releasedMember = {
  ...activeMember,
  id: "m-2",
  person_id: "person-2",
  person_name: "Петров Пётр Петрович",
  role_in_formation: null,
  released_on: "2026-06-01",
  status: "released",
  status_label: "Выведен из состава",
};

describe("CdProfileFormDialog — сведения по ГО (срез-110)", () => {
  beforeEach(() => {
    createProfileMock.mockReset();
    updateProfileMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createProfileMock.mockResolvedValue({ id: "profile-new" });
    updateProfileMock.mockResolvedValue({ id: "profile-1" });
  });

  const openCreate = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <CdProfileFormDialog
        sites={sites}
        trigger={<button>Внести сведения по ГО</button>}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Внести сведения по ГО" }),
    );
  };

  it("«категория не присвоена» уходит без реквизитов решения", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Площадка"), "site-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createProfileMock).toHaveBeenCalled());
    expect(createProfileMock.mock.calls[0][0]).toEqual({
      site_id: "site-1",
      category: "none",
      decision_number: null,
      decision_date: null,
      responsible: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Сведения по ГО внесены");
  });

  it("присвоенная категория без реквизитов решения не проходит", async () => {
    const user = userEvent.setup();
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Площадка"), "site-1");
    await user.selectOptions(screen.getByLabelText("Категория по ГО"), "first");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText(
        "У присвоенной категории укажите номер или дату решения",
      ),
    ).toBeInTheDocument();
    expect(createProfileMock).not.toHaveBeenCalled();
  });

  it("повтор сведений по объекту: ответ сервера словами, окно открыто", async () => {
    const user = userEvent.setup();
    createProfileMock.mockRejectedValueOnce({
      status: 422,
      message: "Сведения по ГО для объекта 'Площадка №1' уже заведены",
      field_errors: [],
    });
    await openCreate(user);

    await user.selectOptions(screen.getByLabelText("Площадка"), "site-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toContain("уже заведены");
    expect(
      screen.getByRole("heading", { name: "Внести сведения по ГО" }),
    ).toBeInTheDocument();
  });

  it("на первом уровне четыре поля; категорирование за органом", async () => {
    const user = userEvent.setup();
    await openCreate(user);
    await screen.findByLabelText("Площадка");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(
      screen.getByText(/Категорирование выполняет орган/i),
    ).toBeInTheDocument();
  });
});

describe("CdDocumentFormDialog — документ планирования ГО (срез-110)", () => {
  beforeEach(() => {
    createDocumentMock.mockReset();
    updateDocumentMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    createDocumentMock.mockResolvedValue({ id: "doc-new" });
    updateDocumentMock.mockResolvedValue({ id: "doc-1" });
  });

  it("отправляет вид и название; пустой срок пересмотра — «бессрочный»", async () => {
    const user = userEvent.setup();
    render(
      <CdDocumentFormDialog
        sites={sites}
        trigger={<button>Завести документ</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести документ" }));

    await user.selectOptions(
      screen.getByLabelText("Вид документа"),
      "plan_emergency",
    );
    await user.type(
      screen.getByLabelText("Документ"),
      "План действий по предупреждению ЧС",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDocumentMock).toHaveBeenCalled());
    expect(createDocumentMock.mock.calls[0][0]).toEqual({
      kind: "plan_emergency",
      title: "План действий по предупреждению ЧС",
      number: null,
      site_id: null,
      review_due: null,
      approved_on: null,
      responsible: null,
      notes: null,
    });
    expect(toastSuccess).toHaveBeenCalledWith("Документ заведён");
  });

  it("на первом уровне пять полей; перечень обязательного не выдумывается", async () => {
    const user = userEvent.setup();
    render(
      <CdDocumentFormDialog
        sites={sites}
        trigger={<button>Завести документ</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Завести документ" }));
    await screen.findByLabelText("Вид документа");

    expect(uxBudgetViolations(document.body)).toEqual([]);
    expect(screen.getByText(/платформа этого не решает/i)).toBeInTheDocument();
  });
});

describe("CdFormationMembersDialog — состав формирования (срез-110)", () => {
  beforeEach(() => {
    listMembersMock.mockReset();
    addMemberMock.mockReset();
    updateMemberMock.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    listMembersMock.mockResolvedValue([activeMember, releasedMember]);
    addMemberMock.mockResolvedValue({ id: "m-3" });
    updateMemberMock.mockResolvedValue({ id: "m-1" });
  });

  const openDialog = async (user: ReturnType<typeof userEvent.setup>) => {
    render(
      <CdFormationMembersDialog
        formation={formation}
        persons={persons}
        trigger={<button>Состав</button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Состав" }));
    await screen.findByText(/командир звена/);
  };

  it("состав читается при открытии, а не вместе с экраном", async () => {
    const user = userEvent.setup();
    render(
      <CdFormationMembersDialog
        formation={formation}
        persons={persons}
        trigger={<button>Состав</button>}
      />,
    );

    expect(listMembersMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Состав" }));
    await waitFor(() => expect(listMembersMock).toHaveBeenCalledWith("cd-1"));
  });

  it("вывод из состава — дата, а не удаление строки", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    await user.click(screen.getByRole("button", { name: "Вывести" }));

    await waitFor(() => expect(updateMemberMock).toHaveBeenCalled());
    expect(updateMemberMock.mock.calls[0][0]).toBe("cd-1");
    expect(updateMemberMock.mock.calls[0][1]).toBe("m-1");
    expect(updateMemberMock.mock.calls[0][2].released_on).toMatch(
      /^\d{4}-\d{2}-\d{2}$/,
    );
    expect(toastSuccess).toHaveBeenCalledWith("Работник выведен из состава");
  });

  it("выведенного возвращают в состав снятием даты", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    await user.click(screen.getByRole("button", { name: "Вернуть" }));

    await waitFor(() => expect(updateMemberMock).toHaveBeenCalled());
    expect(updateMemberMock.mock.calls[0][2]).toEqual({ released_on: null });
    expect(toastSuccess).toHaveBeenCalledWith("Работник возвращён в состав");
  });

  it("без выбранного работника включение не уходит", async () => {
    const user = userEvent.setup();
    await openDialog(user);

    await user.click(screen.getByRole("button", { name: "Включить в состав" }));

    expect(await screen.findByText("Выберите работника")).toBeInTheDocument();
    expect(addMemberMock).not.toHaveBeenCalled();
  });
});

describe("cdProfileFormSchema (срез-110)", () => {
  it("«не присвоена» допустима без решения, присвоенная — нет", () => {
    expect(
      cdProfileFormSchema.safeParse({
        site_id: "site-1",
        category: "none",
      }).success,
    ).toBe(true);
    expect(
      cdProfileFormSchema.safeParse({
        site_id: "site-1",
        category: "special",
      }).success,
    ).toBe(false);
  });
});
