/**
 * Тест контрола «Группа по электробезопасности» на форме персоны.
 *
 * Footgun: update-API заменяет qualifications ЦЕЛИКОМ → форма ДОЛЖНА
 * сохранять прочие квалификации (merge).
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { MemoryRouter } from "react-router-dom";

// --- моки стора ---
const createMock = vi.fn();
const updateMock = vi.fn();

vi.mock("@/stores/persons", () => ({
  usePersonsStore: () => ({
    create: createMock,
    update: updateMock
  })
}));

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    list: vi.fn().mockResolvedValue(undefined),
    items: [{ id: "company-1", name: "ООО Тест" }],
    getById: vi.fn(),
    item: null
  }),
  // zustand static getState
  useCompaniesStore_getState: undefined
}));

// мок getState для useCompaniesStore.getState() внутри onSubmit
vi.mock("@/stores/companies", () => {
  const getStateMock = vi.fn(() => ({ item: null, getById: vi.fn() }));
  const storeFn = () => ({
    list: vi.fn().mockResolvedValue(undefined),
    items: [{ id: "company-1", name: "ООО Тест" }],
    getById: vi.fn(),
    item: null
  });
  storeFn.getState = getStateMock;
  return { useCompaniesStore: storeFn };
});

import { PersonFormDialog } from "@/features/persons/PersonFormDialog";
import type { PersonDto } from "@/types/dto/persons";

// Минимальная PersonDto с qualifications
const makeInitialData = (qualifications: Array<Record<string, unknown>>): PersonDto => ({
  id: "person-42",
  company_id: "company-1",
  first_name: "Иван",
  last_name: "Петров",
  full_name: "Петров Иван",
  status: "active",
  created_at: "2025-01-01",
  updated_at: "2025-01-01",
  qualifications
});

const renderDialog = (initialData?: PersonDto) =>
  render(
    <MemoryRouter>
      <PersonFormDialog trigger={<button>Открыть</button>} initialData={initialData} />
    </MemoryRouter>
  );

describe("PersonFormDialog — группа по электробезопасности", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
    updateMock.mockResolvedValue({
      id: "person-42",
      full_name: "Петров Иван",
      first_name: "Иван",
      last_name: "Петров",
      status: "active",
      company_id: "company-1",
      created_at: "2025-01-01",
      updated_at: "2025-01-01"
    });
    createMock.mockResolvedValue({
      id: "new-person",
      full_name: "Новый Человек",
      first_name: "Новый",
      last_name: "Человек",
      status: "active",
      company_id: "company-1",
      created_at: "2025-01-01",
      updated_at: "2025-01-01"
    });
  });

  // ─── Тест A: footgun-merge ────────────────────────────────────────────────
  it("Тест A: выбор группы IV сохраняет ОБОИХ — и новую electrical_safety_group, и существующий training", async () => {
    const initialData = makeInitialData([{ kind: "training", name: "Обучение по ОТ" }]);

    renderDialog(initialData);
    fireEvent.click(screen.getByText("Открыть"));

    // Ожидаем отрисовку формы
    await screen.findByLabelText(/Группа по электробезопасности/i);

    // Выбираем группу IV
    fireEvent.change(screen.getByLabelText(/Группа по электробезопасности/i), {
      target: { value: "IV" }
    });

    // Сабмит
    fireEvent.click(screen.getByRole("button", { name: /Сохранить/i }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());

    const [calledId, calledPayload] = (updateMock as Mock).mock.calls[0] as [
      string,
      Record<string, unknown>
    ];
    expect(calledId).toBe("person-42");

    // qualifications должен быть массивом
    expect(Array.isArray(calledPayload.qualifications)).toBe(true);
    const quals = calledPayload.qualifications as Array<Record<string, unknown>>;

    // Тренинг сохранён (merge)
    expect(quals).toEqual(
      expect.arrayContaining([expect.objectContaining({ kind: "training", name: "Обучение по ОТ" })])
    );

    // Электробезопасность добавлена
    expect(quals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "electrical_safety_group", level: "IV" })
      ])
    );
  });

  // ─── Тест B: предзаполнение + очистка ────────────────────────────────────
  it("Тест B: initialData с группой III предзаполняет select; сброс на «—» убирает запись из payload", async () => {
    const initialData = makeInitialData([
      { kind: "training", name: "Обучение по ОТ" },
      { kind: "electrical_safety_group", level: "III", name: "Группа по электробезопасности", valid_until: "2027-01-01" }
    ]);

    renderDialog(initialData);
    fireEvent.click(screen.getByText("Открыть"));

    const groupSelect = await screen.findByLabelText(/Группа по электробезопасности/i);

    // Предзаполнение — значение должно быть III
    expect((groupSelect as HTMLSelectElement).value).toBe("III");

    // Меняем на «—» (пусто)
    fireEvent.change(groupSelect, { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: /Сохранить/i }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());

    const [, calledPayload] = (updateMock as Mock).mock.calls[0] as [
      string,
      Record<string, unknown>
    ];

    const quals = calledPayload.qualifications as Array<Record<string, unknown>>;

    // Электробезопасность убрана
    expect(quals).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ kind: "electrical_safety_group" })])
    );

    // Тренинг сохранён
    expect(quals).toEqual(
      expect.arrayContaining([expect.objectContaining({ kind: "training" })])
    );
  });

  // ─── Тест C: обычное редактирование без изменения группы сохраняет все квалификации ──
  it("Тест C: редактирование персоны без изменения группы — qualifications в payload не изменены", async () => {
    const existingQuals = [
      { kind: "training", name: "Обучение по ОТ" },
      { kind: "electrical_safety_group", level: "II", name: "Группа по электробезопасности" }
    ];
    const initialData = makeInitialData(existingQuals);

    renderDialog(initialData);
    fireEvent.click(screen.getByText("Открыть"));

    await screen.findByLabelText(/Группа по электробезопасности/i);

    // Не трогаем группу, просто сабмитим
    fireEvent.click(screen.getByRole("button", { name: /Сохранить/i }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());

    const [, calledPayload] = (updateMock as Mock).mock.calls[0] as [
      string,
      Record<string, unknown>
    ];

    const quals = calledPayload.qualifications as Array<Record<string, unknown>>;

    // Обе квалификации в payload
    expect(quals).toEqual(
      expect.arrayContaining([expect.objectContaining({ kind: "training" })])
    );
    expect(quals).toEqual(
      expect.arrayContaining([expect.objectContaining({ kind: "electrical_safety_group", level: "II" })])
    );
  });
});
