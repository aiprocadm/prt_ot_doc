import { UX_BUDGET } from "@/ux/budget";
import { UX_BUDGET_DEBT } from "@/test-utils/uxBudgetDebt";

/**
 * Измерение экрана против UX-бюджета (ТЗ разд. 59.2).
 *
 * Меряем ОТРИСОВАННЫЙ экран, а не исходный текст. Статический разбор здесь
 * врёт: колонки таблиц и поля форм строятся условно и в циклах, и проверка по
 * тексту исходника показывала бы «всё в порядке» ровно там, где на экране
 * пятнадцать колонок. Такие проверки хуже отсутствующих — они создают
 * уверенность.
 */

export type UxMeasurement = {
  primaryCta: number;
  visibleFormFields: number;
  tableColumns: number;
  dashboardBlocks: number;
};

const isVisible = (element: Element): boolean => {
  if (element.hasAttribute("hidden")) return false;
  if (element.getAttribute("aria-hidden") === "true") return false;
  if (element.getAttribute("type") === "hidden") return false;
  // Поле внутри свёрнутого «Дополнительно» не видно пользователю, а значит и
  // в бюджет уровня 1 не входит (разд. 59.3: три уровня раскрытия).
  const collapsed = element.closest(
    "[hidden], [aria-expanded='false'] + *, details:not([open])",
  );
  return collapsed === null;
};

/**
 * Главные действия экрана.
 *
 * Признак — класс `bg-primary` у кнопки: именно им вариант `default` кнопки
 * отличается от вторичных (`secondary`, `outline`, `ghost`). Сравниваем по
 * токенам класса, а не подстрокой: `hover:bg-primary/90` есть и у вторичных.
 */
export const countPrimaryCta = (container: HTMLElement): number =>
  Array.from(container.querySelectorAll("button, a")).filter(
    (element) => element.classList.contains("bg-primary") && isVisible(element),
  ).length;

export const countVisibleFormFields = (container: HTMLElement): number =>
  Array.from(container.querySelectorAll("input, select, textarea")).filter(
    (element) => {
      // Отметки в списке выбора — это один ответ на один вопрос, а не двадцать
      // полей: считать каждую строкой формы значит объявить нарушением любой
      // множественный выбор.
      if (element.getAttribute("type") === "checkbox") return false;
      if (element.getAttribute("type") === "radio") return false;
      return isVisible(element);
    },
  ).length;

/** Колонок в первой таблице экрана — столько человек видит по умолчанию. */
export const countTableColumns = (container: HTMLElement): number => {
  const table = container.querySelector("table");
  if (!table) return 0;
  const headerRow =
    table.querySelector("thead tr") ?? table.querySelector("tr");
  if (!headerRow) return 0;
  return Array.from(
    headerRow.querySelectorAll("th, [role='columnheader']"),
  ).filter(isVisible).length;
};

/** Блоков-карточек верхнего уровня: вложенные не считаем — это части блока. */
export const countDashboardBlocks = (container: HTMLElement): number =>
  Array.from(
    container.querySelectorAll("[data-ux-block], section, article"),
  ).filter(
    (element) =>
      isVisible(element) &&
      element.parentElement?.closest("[data-ux-block], section, article") ==
        null,
  ).length;

export const measureUxBudget = (container: HTMLElement): UxMeasurement => ({
  primaryCta: countPrimaryCta(container),
  visibleFormFields: countVisibleFormFields(container),
  tableColumns: countTableColumns(container),
  dashboardBlocks: countDashboardBlocks(container),
});

/**
 * Нарушения бюджета человеческим языком.
 *
 * ТЗ разд. 59.2: «Превышение допустимо только с явным обоснованием». Поэтому
 * функция возвращает СПИСОК нарушений, а не бросает исключение на первом:
 * экран чинят целиком, а не по одному замечанию за прогон.
 */
export const uxBudgetViolations = (container: HTMLElement): string[] => {
  const measured = measureUxBudget(container);
  const violations: string[] = [];
  if (measured.primaryCta > UX_BUDGET.maxPrimaryCta) {
    violations.push(
      `основных действий ${measured.primaryCta} при лимите ${UX_BUDGET.maxPrimaryCta}: ` +
        "оставьте одно, остальные сделайте вторичными",
    );
  }
  if (measured.visibleFormFields > UX_BUDGET.maxVisibleFormFields) {
    violations.push(
      `видимых полей ${measured.visibleFormFields} при лимите ${UX_BUDGET.maxVisibleFormFields}: ` +
        "лишнее — под «Дополнительно» или в шаги мастера",
    );
  }
  if (measured.tableColumns > UX_BUDGET.maxDefaultTableColumns) {
    violations.push(
      `колонок ${measured.tableColumns} при лимите ${UX_BUDGET.maxDefaultTableColumns}: ` +
        "остальные — в настройку колонок или карточку строки",
    );
  }
  if (measured.dashboardBlocks > UX_BUDGET.maxDashboardBlocks) {
    violations.push(
      `блоков ${measured.dashboardBlocks} при лимите ${UX_BUDGET.maxDashboardBlocks}: ` +
        "приоритизируйте, лишнее — на второй экран",
    );
  }
  return violations;
};

/**
 * Нарушения экрана против записанного по нему долга (ТЗ разд. 59.2).
 *
 * Возвращает пару «лишнее / протухшее»:
 *
 * - **лишнее** — нарушение, которого нет в списке долга: экран стал хуже;
 * - **протухшее** — запись долга, нарушения по которой больше нет: экран
 *   починили, а пометку забыли снять. Без этой половины список превратился бы
 *   в кладбище неверных строк, и по нему нельзя было бы понять, сколько
 *   экранов на самом деле вне бюджета.
 */
export const uxBudgetDelta = (
  container: HTMLElement,
  screen: string,
): { unexpected: string[]; stale: string[] } => {
  const actual = uxBudgetViolations(container);
  const known = UX_BUDGET_DEBT[screen] ?? [];
  return {
    unexpected: actual.filter((item) => !known.includes(item)),
    stale: known.filter((item) => !actual.includes(item)),
  };
};
