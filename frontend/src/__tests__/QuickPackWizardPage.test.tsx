import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QuickPackWizardPage } from "@/pages/packs/QuickPackWizardPage";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

/**
 * BIZ-50 срез-7 — экран мастера разового комплекта (ТЗ разд. 50.2).
 *
 * Шесть ручек мастера были сделаны шестью срезами бэкенда и не вызывались ни
 * одной строкой фронта: пользоваться мастером мог только тот, кто ходит в API
 * руками.
 */

const listPackScenarios = vi.fn();
const getPackScenarioFields = vi.fn();
const previewPack = vi.fn();
const generatePack = vi.fn();
const getPackTaskStatus = vi.fn();
const publishPackToPortal = vi.fn();
const listCompanies = vi.fn();
const listCompanyPersons = vi.fn();
const listCompanySites = vi.fn();

vi.mock("@/api/packWizard", async (importOriginal) => {
  // Чистые помощники (`archiveKeyOf`, `packDownloadUrl`) берём НАСТОЯЩИЕ:
  // подменив их, тест перестал бы проверять разбор ответа задачи.
  const actual = await importOriginal<typeof import("@/api/packWizard")>();
  return {
    ...actual,
    listPackScenarios: (...args: unknown[]) => listPackScenarios(...args),
    getPackScenarioFields: (...args: unknown[]) => getPackScenarioFields(...args),
    previewPack: (...args: unknown[]) => previewPack(...args),
    generatePack: (...args: unknown[]) => generatePack(...args),
    getPackTaskStatus: (...args: unknown[]) => getPackTaskStatus(...args),
    publishPackToPortal: (...args: unknown[]) => publishPackToPortal(...args),
    listCompanyPersons: (...args: unknown[]) => listCompanyPersons(...args),
    listCompanySites: (...args: unknown[]) => listCompanySites(...args),
  };
});

vi.mock("@/api/companiesApi", () => ({
  listCompanies: (...args: unknown[]) => listCompanies(...args),
}));

const SCENARIO = {
  code: "OT_NEW_EMPLOYEE",
  name: "Приём нового сотрудника",
  description: "Инструктажи, медосмотр, СИЗ",
  discipline: "Охрана труда",
  templates: [],
};

const COMPANY = { id: "c-1", name: "ООО Ромашка" };

const fillStepOne = async () => {
  const user = userEvent.setup();
  renderWithRouter(<QuickPackWizardPage />);
  await screen.findByRole("option", { name: /Приём нового сотрудника/ });
  await user.selectOptions(screen.getByLabelText("Сценарий"), SCENARIO.code);
  await user.selectOptions(screen.getByLabelText("Организация клиента"), COMPANY.id);
  await user.click(screen.getByRole("button", { name: "Дальше" }));
  return user;
};

describe("мастер разового комплекта", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listPackScenarios.mockResolvedValue([SCENARIO]);
    listCompanies.mockResolvedValue([COMPANY]);
    listCompanyPersons.mockResolvedValue([
      { id: "p-1", label: "Иванов Иван" },
      { id: "p-2", label: "Петров Пётр" },
    ]);
    listCompanySites.mockResolvedValue([{ id: "s-1", name: "Площадка №1" }]);
    getPackScenarioFields.mockResolvedValue({
      scenario_code: SCENARIO.code,
      scenario_name: SCENARIO.name,
      fields: [
        { name: "employee_name", label: "ФИО работника", required: true },
        { name: "internship_days", label: "Дней стажировки", required: false },
      ],
      known_from_client: ["Организация клиента (наименование, ИНН, адрес)"],
    });
    previewPack.mockResolvedValue({
      ready: true,
      score: 100,
      documents_total: 1,
      persons_total: 0,
      persons_ready: 0,
      documents: [{ template_name: "Приказ о приёме", person_name: null }],
      problems: [],
    });
    generatePack.mockResolvedValue({ task_id: "task-1", status_url: "/x" });
    getPackTaskStatus.mockResolvedValue({ task_id: "task-1", status: "running" });
    publishPackToPortal.mockResolvedValue({ id: "run-1" });
  });

  it("спрашивает только недостающее и называет то, что подставится само", async () => {
    await fillStepOne();

    expect(await screen.findByLabelText(/ФИО работника/)).toBeInTheDocument();
    // Разд. 50.2: «система подтягивает всё, что уже знает о клиенте» — и
    // говорит об этом, иначе специалист ищет, где это ввести.
    expect(screen.getByText(/Платформа подставит сама/)).toBeInTheDocument();
    expect(screen.getByText(/наименование, ИНН, адрес/)).toBeInTheDocument();
  });

  it("показывает состав комплекта до генерации", async () => {
    const user = await fillStepOne();
    await screen.findByLabelText(/ФИО работника/);

    await user.click(screen.getByRole("button", { name: /Показать, что получится/ }));

    expect(await screen.findByText("Приказ о приёме")).toBeInTheDocument();
    expect(screen.getByText(/Готовность:/)).toBeInTheDocument();
  });

  it("при блокирующей причине генерация недоступна, и причина названа", async () => {
    previewPack.mockResolvedValue({
      ready: false,
      score: 0,
      documents_total: 0,
      persons_total: 0,
      persons_ready: 0,
      documents: [],
      problems: [
        {
          code: "REQUIRED_FIELDS_BLANK",
          message: "Не заполнено обязательное: ФИО работника.",
          blocking: true,
          rows_total: 1,
        },
      ],
    });

    const user = await fillStepOne();
    await screen.findByLabelText(/ФИО работника/);
    await user.click(screen.getByRole("button", { name: /Показать, что получится/ }));

    expect(await screen.findByText(/Пока сгенерировать нельзя/)).toBeInTheDocument();
    expect(screen.getByText(/Не заполнено обязательное/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сгенерировать" })).toBeDisabled();
  });

  it("предупреждение не мешает генерации", async () => {
    previewPack.mockResolvedValue({
      ready: true,
      score: 50,
      documents_total: 1,
      persons_total: 0,
      persons_ready: 0,
      documents: [{ template_name: "Приказ", person_name: null }],
      problems: [
        {
          code: "OPTIONAL_FIELDS_BLANK",
          message: "Останется пустым в документах: Дней стажировки.",
          blocking: false,
          rows_total: 1,
        },
      ],
    });

    const user = await fillStepOne();
    await screen.findByLabelText(/ФИО работника/);
    await user.click(screen.getByRole("button", { name: /Показать, что получится/ }));

    expect(await screen.findByText(/Выйдет, но с пробелами/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сгенерировать" })).toBeEnabled();
  });

  it("готовый архив можно скачать и выдать клиенту", async () => {
    getPackTaskStatus.mockResolvedValue({
      task_id: "task-1",
      status: "success",
      metadata: { outputs: { zip_storage_key: "tenants/test/packs/result.zip" } },
    });

    const user = await fillStepOne();
    await screen.findByLabelText(/ФИО работника/);
    await user.click(screen.getByRole("button", { name: /Показать, что получится/ }));
    await screen.findByText("Приказ о приёме");
    await user.click(screen.getByRole("button", { name: "Сгенерировать" }));

    const download = await screen.findByRole("link", { name: "Скачать архив" }, { timeout: 5000 });
    expect(download).toHaveAttribute(
      "href",
      expect.stringContaining("storage_key=tenants%2Ftest%2Fpacks%2Fresult.zip"),
    );

    await user.click(screen.getByRole("button", { name: /Выдать в кабинет клиента/ }));
    await waitFor(() => {
      expect(publishPackToPortal).toHaveBeenCalledWith({
        preset_code: SCENARIO.code,
        zip_storage_key: "tenants/test/packs/result.zip",
        client_company_id: COMPANY.id,
      });
    });
    expect(await screen.findByRole("button", { name: "Выдан клиенту" })).toBeDisabled();
  });

  it("состав бригады уходит в предпросмотр — комплект на нескольких сразу", async () => {
    // ТЗ: «один сценарий → комплект на 50 человек одним запуском». Генерация
    // это умела с самого начала, интерфейс просто не предлагал выбрать людей.
    const user = userEvent.setup();
    renderWithRouter(<QuickPackWizardPage />);
    await screen.findByRole("option", { name: /Приём нового сотрудника/ });
    await user.selectOptions(screen.getByLabelText("Сценарий"), SCENARIO.code);
    await user.selectOptions(screen.getByLabelText("Организация клиента"), COMPANY.id);

    await user.click(await screen.findByLabelText("Иванов Иван"));
    await user.click(screen.getByLabelText("Петров Пётр"));
    await user.selectOptions(screen.getByLabelText("Объект"), "s-1");

    await user.click(screen.getByRole("button", { name: "Дальше" }));
    await screen.findByLabelText(/ФИО работника/);
    await user.click(screen.getByRole("button", { name: /Показать, что получится/ }));

    await waitFor(() => {
      expect(previewPack).toHaveBeenCalledWith(
        expect.objectContaining({ person_ids: ["p-1", "p-2"], site_id: "s-1" }),
      );
    });
  });

  it("смена организации сбрасывает выбранных людей", async () => {
    // Иначе в запрос уехал бы сотрудник ПРЕЖНЕЙ организации, а генерация
    // такого отвергает: «комплект оформляется по одной организации».
    const user = userEvent.setup();
    listCompanies.mockResolvedValue([COMPANY, { id: "c-2", name: "ООО Вторая" }]);
    renderWithRouter(<QuickPackWizardPage />);
    await screen.findByRole("option", { name: /Приём нового сотрудника/ });
    await user.selectOptions(screen.getByLabelText("Сценарий"), SCENARIO.code);
    await user.selectOptions(screen.getByLabelText("Организация клиента"), COMPANY.id);
    await user.click(await screen.findByLabelText("Иванов Иван"));
    expect(screen.getByText("Выбрано: 1")).toBeInTheDocument();

    listCompanyPersons.mockResolvedValue([{ id: "p-9", label: "Сидоров Сидор" }]);
    await user.selectOptions(screen.getByLabelText("Организация клиента"), "c-2");

    await waitFor(() => {
      expect(screen.queryByText(/Выбрано:/)).not.toBeInTheDocument();
    });
  });
});
