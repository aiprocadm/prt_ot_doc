import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  exportSubject: vi.fn(),
  accessLog: vi.fn(),
  consents: vi.fn(),
  withdrawConsent: vi.fn(),
  anonymize: vi.fn(),
}));
const downloadMock = vi.hoisted(() => ({ downloadBlob: vi.fn() }));

vi.mock("@/api/privacy", () => ({
  privacySubjectApi: {
    exportSubject: (...a: unknown[]) => apiMock.exportSubject(...a),
    accessLog: (...a: unknown[]) => apiMock.accessLog(...a),
    consents: (...a: unknown[]) => apiMock.consents(...a),
    withdrawConsent: (...a: unknown[]) => apiMock.withdrawConsent(...a),
    anonymize: (...a: unknown[]) => apiMock.anonymize(...a),
  },
}));

vi.mock("@/utils/download", () => ({
  downloadBlob: (...a: unknown[]) => downloadMock.downloadBlob(...a),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/stores/persons", () => ({
  usePersonsStore: () => ({
    items: [{ id: "p-1", full_name: "Иванов Иван" }],
    list: vi.fn(),
  }),
}));

import PrivacySubjectPage from "@/pages/privacy/PrivacySubjectPage";

/**
 * Права человека на его персональные данные (срез-209, 152-ФЗ разд. 66.2).
 *
 * Срез-208 завёл первый экран контура и назвал остаток: четыре права субъекта
 * жили только ручками. Право, которым нельзя воспользоваться через продукт, не
 * работает: человек пишет заявление, а кадровик не может его исполнить, не
 * позвав программиста.
 */

const CONSENTS_WITH_BASIS = {
  items: [
    {
      id: "c-1",
      purpose: "Кадровый учёт",
      legal_basis: "consent",
      version: 1,
      status: "active",
      granted_at: "2026-01-10T10:00:00+00:00",
      withdrawn_at: null,
    },
  ],
  total: 1,
  remaining_legal_bases: ["labor_contract"],
};

const selectPerson = async (user: ReturnType<typeof userEvent.setup>) => {
  await act(async () => {
    await user.selectOptions(screen.getByLabelText("Человек"), "p-1");
  });
};

describe("PrivacySubjectPage", () => {
  beforeEach(() => {
    Object.values(apiMock).forEach((fn) => fn.mockReset());
    downloadMock.downloadBlob.mockReset();
    apiMock.accessLog.mockResolvedValue({ items: [], total: 0 });
    apiMock.consents.mockResolvedValue(CONSENTS_WITH_BASIS);
  });

  const renderPage = async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <PrivacySubjectPage />
        </MemoryRouter>,
      );
    });
  };

  it("без выбранного человека ничего не спрашивает у сервера", async () => {
    await renderPage();

    expect(apiMock.accessLog).not.toHaveBeenCalled();
    expect(apiMock.consents).not.toHaveBeenCalled();
  });

  it("«оснований обработки не осталось» показывается КРУПНО", async () => {
    // ГЛАВНОЕ НА ЭКРАНЕ. Пустой список оснований означает, что обрабатывать
    // человека больше не на чем и обезличивание стало ОБЯЗАННОСТЬЮ. Спрятать
    // это значило бы оставить организацию нарушать закон молча.
    const user = userEvent.setup();
    apiMock.consents.mockResolvedValue({
      ...CONSENTS_WITH_BASIS,
      remaining_legal_bases: [],
    });
    await renderPage();

    await selectPerson(user);

    expect(await screen.findByTestId("pdn-no-legal-basis")).toHaveTextContent(
      "Обработку нужно прекратить",
    );
  });

  it("пока основание есть — тревоги нет", async () => {
    // Сторож не должен кричать всегда: иначе на предупреждение перестанут
    // смотреть ровно тогда, когда оно настоящее.
    const user = userEvent.setup();
    await renderPage();

    await selectPerson(user);

    expect(await screen.findByTestId("pdn-consent")).toBeInTheDocument();
    expect(screen.queryByTestId("pdn-no-legal-basis")).not.toBeInTheDocument();
  });

  it("неполная выгрузка честно помечена", async () => {
    // Неполные данные, принятые за полные, хуже отказа: человек получит
    // выгрузку и решит, что это всё, что о нём хранят.
    const user = userEvent.setup();
    apiMock.exportSubject.mockResolvedValue({
      format_version: "1.0",
      generated_at: "2026-09-15T10:00:00+00:00",
      subject: { person_id: "p-1", full_name: "Иванов Иван", email: null },
      data_categories: ["regular", "special_health"],
      truncated: true,
      max_items_per_section: 500,
    });
    await renderPage();
    await selectPerson(user);

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Выгрузить данные" }),
      );
    });

    expect(await screen.findByTestId("pdn-export-truncated")).toHaveTextContent(
      "Выгрузка неполная",
    );
    // Файл отдают человеку на руки — выгрузка скачивается.
    expect(downloadMock.downloadBlob).toHaveBeenCalledTimes(1);
  });

  it("отзыв согласия уходит с причиной", async () => {
    const user = userEvent.setup();
    apiMock.withdrawConsent.mockResolvedValue(undefined);
    await renderPage();
    await selectPerson(user);

    await user.type(
      screen.getByLabelText("Причина (для отзыва или обезличивания)"),
      "Заявление от 15.09",
    );
    await act(async () => {
      await user.click(
        await screen.findByRole("button", { name: "Отозвать согласие" }),
      );
    });

    expect(apiMock.withdrawConsent).toHaveBeenCalledWith(
      "p-1",
      "Кадровый учёт",
      "Заявление от 15.09",
    );
  });

  it("обезличивание спрашивает подтверждение и называет последствия", async () => {
    // Действие НЕОБРАТИМО. «Вы уверены?» без объяснения не даёт человеку
    // понять, что именно исчезнет, а что останется.
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    await renderPage();
    await selectPerson(user);

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Обезличить субъекта" }),
      );
    });

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(confirmSpy.mock.calls[0][0]).toContain("необратимо");
    // Отказ в подтверждении НЕ выполняет действие.
    expect(apiMock.anonymize).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("после обезличивания показывает доказательство", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    apiMock.anonymize.mockResolvedValue({
      pseudonym: "Субъект №42",
      scrubbed_fields: { full_name: true, email: true, phone: false },
    });
    await renderPage();
    await selectPerson(user);

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Обезличить субъекта" }),
      );
    });

    const result = await screen.findByTestId("pdn-erasure-result");
    expect(result).toHaveTextContent("Субъект №42");
    // Считаем только те поля, где значение БЫЛО: «вычищено 3» там, где
    // чистить было нечего, — неправда в доказательстве исполнения.
    expect(result).toHaveTextContent("Вычищено полей: 2");
    confirmSpy.mockRestore();
  });
});
