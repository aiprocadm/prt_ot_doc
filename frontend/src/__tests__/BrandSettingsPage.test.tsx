import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BrandSettingsPage, {
  hexToHslTriplet,
  hslTripletToHex,
} from "@/pages/admin/BrandSettingsPage";

const getOwnMock = vi.fn();
const saveOwnMock = vi.fn();
const uploadMock = vi.fn();
const dropMock = vi.fn();

vi.mock("@/api/appBrand", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/appBrand")>()),
  getOwnAppBranding: () => getOwnMock(),
  saveOwnAppBranding: (payload: unknown) => saveOwnMock(payload),
  uploadOwnBrandImage: (kind: string, file: File) => uploadMock(kind, file),
  deleteOwnBrandImage: (kind: string) => dropMock(kind),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const branding = (overrides: Record<string, unknown> = {}) => ({
  app_name: null,
  primary_color: null,
  support_email: null,
  has_logo: false,
  has_favicon: false,
  effective: {
    app_name: "Платформа ОТ/ПБ",
    primary_color: "222.2 47.4% 11.2%",
    support_email: null,
    source: "platform",
    has_logo: false,
    has_favicon: false,
  },
  ...overrides,
});

/** Отрисовать и дождаться ответа сервера.
 *
 *  Ждём именно подсказку с действующим именем: до загрузки её в разметке нет.
 *  Начни проверку раньше — тест бы кликал по форме, в которую ещё не легли
 *  сохранённые значения, и «сохранение» затирало бы их пустотой. */
const renderLoaded = async () => {
  render(<BrandSettingsPage />);
  await screen.findByText(/Платформа ОТ\/ПБ/);
};

describe("экран настройки бренда (BIZ-52 разд. 52.2)", () => {
  beforeEach(() => {
    getOwnMock.mockReset();
    saveOwnMock.mockReset();
    uploadMock.mockReset();
    dropMock.mockReset();
    getOwnMock.mockResolvedValue(branding());
    saveOwnMock.mockResolvedValue(branding());
    uploadMock.mockResolvedValue(undefined);
    dropMock.mockResolvedValue(undefined);
  });

  it("показывает, что действует, когда своё имя не задано", async () => {
    await renderLoaded();

    // «Пусто» без подсказки читалось бы как «приложение без названия», поэтому
    // проверяем не только сам текст, но и что в нём названо действующее имя.
    expect(
      screen.getByText(/не задано — действует бренд платформы — «Платформа ОТ\/ПБ»/),
    ).toBeInTheDocument();
  });

  it("сохраняет имя и цвет", async () => {
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(
      screen.getByLabelText("Название приложения"),
      "Охрана труда «Партнёр»",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    // Ждём и перечитывание: экран обязан показать то, что реально сохранилось,
    // а не то, что человек набрал.
    await waitFor(() => expect(getOwnMock).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Сохранить" })).toBeEnabled(),
    );
    const payload = saveOwnMock.mock.calls[0][0];
    expect(payload.app_name).toBe("Охрана труда «Партнёр»");
    // Цвет уходит триплетом, а не hex: сервер и тема ждут именно его.
    expect(payload.primary_color).toMatch(/^[\d.]+ [\d.]+% [\d.]+%$/);
  });

  it("пустое имя уходит как «не задано», а не пустой строкой", async () => {
    // Иначе наследование не вернётся и приложение останется без названия.
    const user = userEvent.setup();
    getOwnMock.mockResolvedValue(branding({ app_name: "Временное" }));
    render(<BrandSettingsPage />);
    await screen.findByDisplayValue("Временное");

    await user.clear(screen.getByLabelText("Название приложения"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(getOwnMock).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Сохранить" })).toBeEnabled(),
    );
    expect(saveOwnMock.mock.calls[0][0].app_name).toBeNull();
  });

  it("кнопка «Убрать» появляется только при своей картинке", async () => {
    getOwnMock.mockResolvedValue(branding({ has_logo: true }));
    await renderLoaded();

    // Ровно одна: логотип свой, значок унаследован.
    expect(screen.getAllByRole("button", { name: "Убрать" })).toHaveLength(1);
  });

  it("без своих картинок убирать нечего", async () => {
    await renderLoaded();

    expect(screen.queryByRole("button", { name: "Убрать" })).not.toBeInTheDocument();
  });

  it("«Убрать» снимает именно ту картинку, у которой нажали", async () => {
    const user = userEvent.setup();
    getOwnMock.mockResolvedValue(branding({ has_favicon: true }));
    await renderLoaded();

    await user.click(screen.getByRole("button", { name: "Убрать" }));

    await waitFor(() => expect(dropMock).toHaveBeenCalledWith("favicon"));
  });

  it("выбранный файл уходит на сервер и экран перечитывается", async () => {
    const user = userEvent.setup();
    await renderLoaded();
    const file = new File(["картинка"], "logo.png", { type: "image/png" });

    await user.upload(screen.getByLabelText("Логотип"), file);

    await waitFor(() => expect(uploadMock).toHaveBeenCalledWith("logo", file));
    // Без перечитывания признак `has_logo` остался бы старым, и кнопка «Убрать»
    // не появилась бы до перезагрузки страницы.
    await waitFor(() => expect(getOwnMock).toHaveBeenCalledTimes(2));
  });

  it("тот же файл можно выбрать повторно", async () => {
    // Браузер не шлёт событие, если значение поля не изменилось. Не очисти мы
    // поле — человек, поправивший логотип на диске, выбрал бы его снова и не
    // понял, почему ничего не произошло.
    const user = userEvent.setup();
    await renderLoaded();
    const field = screen.getByLabelText("Логотип") as HTMLInputElement;
    const file = new File(["картинка"], "logo.png", { type: "image/png" });

    await user.upload(field, file);
    await waitFor(() => expect(uploadMock).toHaveBeenCalledTimes(1));
    expect(field.value).toBe("");

    await user.upload(field, file);
    await waitFor(() => expect(uploadMock).toHaveBeenCalledTimes(2));
  });

  it("клиенту раздел объясняется, а не показывается пустой формой", async () => {
    getOwnMock.mockRejectedValue(new Error("403"));
    render(<BrandSettingsPage />);

    expect(
      await screen.findByText(/доступен владельцу платформы и партнёрам/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Название приложения")).not.toBeInTheDocument();
  });

  it("подсказки называют ограничения форматов", async () => {
    await renderLoaded();

    expect(screen.getByText(/SVG не принимается/)).toBeInTheDocument();
    expect(screen.getByText(/WebP не подходит/)).toBeInTheDocument();
  });
});

describe("перевод цвета", () => {
  it("триплет темы превращается в цвет для выбора", () => {
    expect(hslTripletToHex("0 0% 100%")).toBe("#ffffff");
    expect(hslTripletToHex("0 0% 0%")).toBe("#000000");
  });

  it("выбранный цвет превращается обратно в триплет", () => {
    expect(hexToHslTriplet("#ffffff")).toBe("0 0% 100%");
  });

  it("перевод туда-обратно не теряет цвет", () => {
    // Разъедься эти две функции — тема применялась бы не тем цветом, который
    // человек выбрал, и выглядело бы это как «цвет не сохраняется».
    for (const hex of ["#1e293b", "#3b82f6", "#dc2626", "#16a34a"]) {
      expect(hslTripletToHex(hexToHslTriplet(hex))).toBe(hex);
    }
  });

  it("неразбираемый триплет даёт чёрный, а не падение", () => {
    expect(hslTripletToHex("мусор")).toBe("#000000");
  });
});
