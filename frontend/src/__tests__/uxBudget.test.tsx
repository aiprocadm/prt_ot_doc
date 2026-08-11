import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";
import {
  countDashboardBlocks,
  countPrimaryCta,
  countTableColumns,
  countVisibleFormFields,
  uxBudgetViolations,
} from "@/test-utils/uxBudget";

/**
 * BIZ-59 — измеритель UX-бюджета (ТЗ разд. 59.2).
 *
 * Проверяем сам измеритель на заведомых примерах. Без этого он рискует стать
 * «проверкой, которая ничего не проверяет»: считает ноль на любом экране и
 * всегда зелёный.
 */

const measured = (markup: React.ReactElement) => render(markup).container;

describe("измеритель UX-бюджета", () => {
  it("отличает главное действие от вторичных", () => {
    const container = measured(
      <div>
        <Button>Сохранить</Button>
        <Button variant="outline">Отмена</Button>
        <Button variant="ghost">Ещё</Button>
        <Button variant="secondary">Вторичное</Button>
      </div>,
    );

    // Именно один: иначе «один доминирующий CTA» из разд. 59.1 не проверить.
    expect(countPrimaryCta(container)).toBe(1);
  });

  it("не путает наведение с главным действием", () => {
    // У вторичных кнопок в классах есть `hover:bg-primary/90` — сравнение
    // подстрокой посчитало бы их главными и обнулило смысл проверки.
    const container = measured(<Button variant="outline">Отмена</Button>);

    expect(countPrimaryCta(container)).toBe(0);
  });

  it("считает видимые поля и пропускает скрытые", () => {
    const container = measured(
      <form>
        <input aria-label="Первое" />
        <select aria-label="Второе" />
        <textarea aria-label="Третье" />
        <input type="hidden" value="служебное" readOnly />
        <input aria-label="Скрытое" hidden />
      </form>,
    );

    expect(countVisibleFormFields(container)).toBe(3);
  });

  it("отметки множественного выбора — не поля формы", () => {
    // Иначе список из двадцати сотрудников в мастере объявлялся бы
    // нарушением бюджета, хотя это один ответ на один вопрос.
    const container = measured(
      <form>
        <input aria-label="ФИО" />
        {Array.from({ length: 20 }, (_, index) => (
          <input key={index} type="checkbox" aria-label={`Человек ${index}`} />
        ))}
      </form>,
    );

    expect(countVisibleFormFields(container)).toBe(1);
  });

  it("считает колонки первой таблицы", () => {
    const container = measured(
      <table>
        <thead>
          <tr>
            <th>Раз</th>
            <th>Два</th>
            <th>Три</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>1</td>
            <td>2</td>
            <td>3</td>
          </tr>
        </tbody>
      </table>,
    );

    expect(countTableColumns(container)).toBe(3);
  });

  it("вложенные блоки не считаются отдельными", () => {
    const container = measured(
      <div>
        <section>
          Блок
          <section>Часть блока</section>
        </section>
        <section>Второй блок</section>
      </div>,
    );

    expect(countDashboardBlocks(container)).toBe(2);
  });

  it("называет нарушение и что с ним делать", () => {
    const container = measured(
      <table>
        <thead>
          <tr>
            {Array.from({ length: 9 }, (_, index) => (
              <th key={index}>Колонка {index}</th>
            ))}
          </tr>
        </thead>
      </table>,
    );

    const violations = uxBudgetViolations(container);
    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain("колонок 9");
    expect(violations[0]).toContain("настройку колонок");
  });

  it("экран в пределах бюджета не даёт нарушений", () => {
    const container = measured(
      <form>
        <input aria-label="Одно" />
        <Button>Сохранить</Button>
      </form>,
    );

    expect(uxBudgetViolations(container)).toEqual([]);
  });
});
