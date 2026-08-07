import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EmployeeCardPage from "@/pages/employees/EmployeeCardPage";
import type { EmployeeCardDto } from "@/types/dto/employee";

const getCardMock = vi.fn();

vi.mock("@/api/employees", () => ({
  employeesApi: {
    getCard: (...args: unknown[]) => getCardMock(...args),
  },
}));

const sampleCard: EmployeeCardDto = {
  person_id: "p-1",
  tenant_id: "tenant-1",
  generated_at: "2026-05-06T08:00:00Z",
  personal: {
    id: "p-1",
    company_id: "c-1",
    company_name: "ООО Ромашка",
    position_id: "pos-1",
    position_name: "Инженер ОТ",
    workplace_id: "wp-1",
    workplace_name: "Цех №3",
    first_name: "Иван",
    last_name: "Иванов",
    middle_name: "Иванович",
    fio: "Иванов Иван Иванович",
    birth_date: "1990-01-01",
    email: "ivanov@example.com",
    phone: "+79991234567",
    personnel_number: "T-001",
    hired_at: "2020-03-01",
    snils: "123-456-789 00",
    passport: null,
    employment_status: "active",
    working_conditions_class: "3.1",
    hazardous_factors: ["шум", "вибрация"],
    qualifications: [],
    current_ppe: [],
  },
  roles_and_assignments: {
    company_id: "c-1",
    company_name: "ООО Ромашка",
    position_id: "pos-1",
    position_name: "Инженер ОТ",
    workplace_id: "wp-1",
    workplace_name: "Цех №3",
    employment_status: "active",
    user_account: {
      user_id: "u-1",
      email: "ivanov@example.com",
      role: "hr",
      is_active: true,
      last_login_at: "2026-05-04T10:00:00Z",
      additional_roles: ["line_manager"],
    },
  },
  training: {
    sessions_count: 1,
    certificates_count: 1,
    sessions: [
      {
        id: "ts-1",
        course_id: "course-1",
        course_title: "Охрана труда базовый курс",
        plan_id: null,
        status: "completed",
        started_at: "2025-01-10T09:00:00Z",
        completed_at: "2025-01-10T17:00:00Z",
        score: 95,
      },
    ],
    certificates: [
      {
        id: "cert-1",
        code: "ОТ-2025-001",
        course_id: "course-1",
        course_title: "Охрана труда базовый курс",
        issued_at: "2025-01-15",
        valid_until: "2028-01-15",
        status: "active",
      },
    ],
  },
  medicals: {
    count: 1,
    expired_count: 1,
    items: [
      {
        id: "exam-1",
        exam_type: "Периодический",
        exam_date: "2024-01-10",
        valid_until: "2025-01-10",
        conclusion: "годен",
        is_expired: true,
      },
    ],
  },
  ppe: {
    count: 2,
    active_count: 1,
    expired_count: 1,
    items: [
      {
        id: "ppe-1",
        item_id: "ppeitem-1",
        item_name: "Каска защитная",
        quantity: 1,
        issued_at: "2025-01-01T10:00:00Z",
        expires_at: "2026-01-01T10:00:00Z",
        returned_at: null,
        status: "issued",
        is_expired: true,
      },
    ],
  },
  permits: {
    count: 1,
    active_count: 1,
    expired_count: 0,
    items: [
      {
        id: "permit-1",
        permit_type: "Высота",
        issued_at: "2025-06-01",
        valid_until: "2027-06-01",
        status: "active",
        position_id: "pos-1",
        is_expired: false,
      },
    ],
  },
  incidents: {
    count: 1,
    open_count: 1,
    items: [
      {
        id: "inc-1",
        title: "Падение с лестницы",
        incident_type: "accident",
        severity: "high",
        status: "investigating",
        occurred_at: "2026-04-15T14:30:00Z",
        role: "victim",
      },
    ],
  },
  documents: {
    count: 2,
    signed_count: 1,
    items: [
      {
        id: "doc-1",
        template_id: "tmpl-1",
        template_name: "Карточка СИЗ",
        status: "signed",
        is_signed: true,
        created_at: "2026-04-20T10:00:00Z",
      },
      {
        id: "doc-2",
        template_id: "tmpl-2",
        template_name: "Журнал инструктажей",
        status: "draft",
        is_signed: false,
        created_at: "2026-05-01T09:00:00Z",
      },
    ],
  },
  briefings: {
    count: 2,
    expired_count: 1,
    items: [
      {
        id: "brf-1",
        briefing_template_id: "btmpl-1",
        briefing_template_title: "Первичный инструктаж",
        briefing_type: "primary",
        briefing_date: "2026-04-01T08:00:00Z",
        valid_until: "2027-04-01T00:00:00Z",
        status: "signed",
        is_expired: false,
      },
      {
        id: "brf-2",
        briefing_template_id: "btmpl-2",
        briefing_template_title: "Целевой инструктаж",
        briefing_type: "targeted",
        briefing_date: "2025-01-10T08:00:00Z",
        valid_until: "2025-12-31T00:00:00Z",
        status: "signed",
        is_expired: true,
      },
    ],
  },
  compliance_deadlines: {
    count: 2,
    overdue_count: 1,
    upcoming_count: 1,
    items: [
      {
        id: "dl-1",
        entity_type: "medical_exam",
        entity_id: "exam-1",
        due_at: "2026-04-01T00:00:00Z",
        status: "upcoming",
        reminder_policy: "за 14 дней",
        is_overdue: true,
      },
      {
        id: "dl-2",
        entity_type: "training_session",
        entity_id: "ts-1",
        due_at: "2026-06-01T00:00:00Z",
        status: "upcoming",
        reminder_policy: null,
        is_overdue: false,
      },
    ],
  },
  audit: {
    count: 1,
    items: [
      {
        id: "log-1",
        when: "2026-05-04T08:00:00Z",
        action: "person.update",
        actor_email: "admin@example.com",
        correlation_id: "corr-1",
        changed_fields: { phone: "+79991234567" },
      },
    ],
  },
};

const renderPage = (path = "/employees/p-1") =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/employees/:personId" element={<EmployeeCardPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe("EmployeeCardPage", () => {
  beforeEach(() => {
    getCardMock.mockReset();
  });

  it("loads aggregate from /employees/{id} and renders header", async () => {
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Иванов Иван Иванович",
      }),
    ).toBeInTheDocument();
    expect(getCardMock).toHaveBeenCalledWith("p-1");
    expect(
      screen.getByText(/Инженер ОТ · ООО Ромашка · Цех №3/),
    ).toBeInTheDocument();
  });

  it("renders all 11 tab triggers", async () => {
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    expect(
      screen.getByRole("tab", { name: /Персональные данные/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Роли и назначения/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Обучение/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Медосмотры/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /СИЗ/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Допуски/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Документы/ })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Инструктажи/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Сроки/ })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Происшествия/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Аудит/ })).toBeInTheDocument();
  });

  it("opens the Documents tab and renders signed-document drill-down link", async () => {
    const user = userEvent.setup();
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    await user.click(screen.getByRole("tab", { name: /Документы/ }));

    const docLink = await screen.findByRole("link", { name: "Карточка СИЗ" });
    expect(docLink).toHaveAttribute("href", "/documents?focus=doc-1");
    const signedRow = docLink.closest("tr");
    expect(signedRow).not.toBeNull();
    // "Подписан" appears twice in a signed row: once as the document status
    // cell (DOCUMENT_STATUS_LABELS.signed) and once as the is_signed badge.
    expect(
      within(signedRow as HTMLElement).getAllByText("Подписан"),
    ).toHaveLength(2);
  });

  it("opens the Briefings tab and shows expired badge", async () => {
    const user = userEvent.setup();
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    await user.click(screen.getByRole("tab", { name: /Инструктажи/ }));

    const targetedRow = (await screen.findByText("Целевой инструктаж")).closest(
      "tr",
    );
    expect(targetedRow).not.toBeNull();
    expect(
      within(targetedRow as HTMLElement).getByText("Просрочен"),
    ).toBeInTheDocument();
  });

  it("opens the Deadlines tab with overdue badge for medical exam", async () => {
    const user = userEvent.setup();
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    await user.click(screen.getByRole("tab", { name: /Сроки/ }));

    const medicalRow = (await screen.findByText("Медосмотр")).closest("tr");
    expect(medicalRow).not.toBeNull();
    expect(
      within(medicalRow as HTMLElement).getByText("Просрочен"),
    ).toBeInTheDocument();
  });

  it("shows linked user account on the Roles tab when present", async () => {
    const user = userEvent.setup();
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    await user.click(screen.getByRole("tab", { name: /Роли и назначения/ }));

    expect(await screen.findByText("Системный аккаунт")).toBeInTheDocument();
    expect(screen.getByText("hr")).toBeInTheDocument();
    expect(screen.getByText("line_manager")).toBeInTheDocument();
  });

  it("opens the Medicals tab and shows expired badge", async () => {
    const user = userEvent.setup();
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    await user.click(screen.getByRole("tab", { name: /Медосмотры/ }));

    const examRow = (await screen.findByText("Периодический")).closest("tr");
    expect(examRow).not.toBeNull();
    expect(
      within(examRow as HTMLElement).getByText("Просрочен"),
    ).toBeInTheDocument();
  });

  it("opens the Incidents tab with drill-down link", async () => {
    const user = userEvent.setup();
    getCardMock.mockResolvedValueOnce(sampleCard);

    renderPage();

    await screen.findByRole("heading", {
      level: 1,
      name: "Иванов Иван Иванович",
    });

    await user.click(screen.getByRole("tab", { name: /Происшествия/ }));

    const incidentLink = await screen.findByRole("link", {
      name: "Падение с лестницы",
    });
    expect(incidentLink).toHaveAttribute("href", "/incidents?focus=inc-1");
  });

  it("renders error state and allows retry", async () => {
    getCardMock.mockRejectedValueOnce({
      status: 500,
      message: "boom",
      field_errors: [],
    });

    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();

    getCardMock.mockResolvedValueOnce(sampleCard);
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Иванов Иван Иванович",
      }),
    ).toBeInTheDocument();
  });
});
