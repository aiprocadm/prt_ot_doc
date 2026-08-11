/**
 * Числовой UX-бюджет экрана (ТЗ Доп. №2, разд. 59.2).
 *
 * Числа обязаны совпадать с `UX_BUDGET` в `backend/app/core/product_spec.py` —
 * это ОДНА величина, записанная на двух языках. Совпадение стережёт тест
 * `backend/tests/test_ux_budget_single_source.py`: разойдись они, ревью и
 * автоматическая проверка начали бы требовать разного, и «бюджет соблюдён»
 * означало бы разное в зависимости от того, кто смотрит.
 */
export const UX_BUDGET = {
  /** Основных действий (primary CTA) на экране: 1, максимум 2. */
  maxPrimaryCta: 2,
  /** Видимых полей формы без «Дополнительно». */
  maxVisibleFormFields: 7,
  /** Колонок в таблице по умолчанию. */
  maxDefaultTableColumns: 7,
  /** Блоков информации (карточек/секций) на дашборде. */
  maxDashboardBlocks: 6,
  /** Уровней вложенности навигации до цели. */
  maxNavDepth: 3,
} as const;

export type UxBudgetKey = keyof typeof UX_BUDGET;
