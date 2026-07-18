import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { workPermitsApi } from "@/api/workPermits";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const createMock = () => workPermitsApi.create as unknown as Mock;

type SubmittedBody = {
  safety_systems?: string[];
  type_specific?: { respiratory_ppe?: string[]; fire_fighting_means?: string[] } | null;
};

const openWith = (workType: string) => {
  render(<WorkPermitFormDialog trigger={<button>open</button>} />);
  fireEvent.click(screen.getByText("open"));
  fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: workType } });
  fireEvent.change(screen.getByLabelText("Зона работ"), { target: { value: "Колодец К-99" } });
};

const submitAndBody = async (): Promise<SubmittedBody> => {
  fireEvent.click(screen.getByText("Сохранить"));
  await waitFor(() => expect(createMock()).toHaveBeenCalled());
  return createMock().mock.calls[0][0] as SubmittedBody;
};

describe("WorkPermitFormDialog — поведение тогглеров чек-листов", () => {
  beforeEach(() => createMock().mockReset());

  // #3 латентный stale-snapshot: два клика в одном render-батче не должны терять первый.
  it("газоопасные: два чекбокса СИЗОД, отмеченные в одном батче, оба попадают в type_specific.respiratory_ppe", async () => {
    openWith("gas_hazardous");
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Шланговый противогаз (ПШ-1/ПШ-2)"));
      fireEvent.click(screen.getByLabelText("Изолирующий противогаз"));
    });
    const body = await submitAndBody();
    expect(body.type_specific?.respiratory_ppe).toEqual(
      expect.arrayContaining(["hose_mask", "isolating_mask"]),
    );
    expect(body.type_specific?.respiratory_ppe).toHaveLength(2);
    // ключ именно respiratory_ppe (защита от копи-паста fire_fighting_means)
    expect(body.type_specific?.fire_fighting_means).toBeUndefined();
  });

  it("газоопасные: повторный клик по чекбоксу снимает выбор", async () => {
    openWith("gas_hazardous");
    const cb = screen.getByLabelText("Фильтрующий противогаз/респиратор");
    fireEvent.click(cb);
    fireEvent.click(cb);
    const body = await submitAndBody();
    expect(body.type_specific?.respiratory_ppe ?? []).not.toContain("filter_mask");
  });

  // #3 для огневых + защита ключа fire_fighting_means.
  it("огневые: два средства, отмеченные в одном батче, оба попадают в type_specific.fire_fighting_means", async () => {
    openWith("hot_work");
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Огнетушитель порошковый"));
      fireEvent.click(screen.getByLabelText("Ящик с песком"));
    });
    const body = await submitAndBody();
    expect(body.type_specific?.fire_fighting_means).toEqual(
      expect.arrayContaining(["extinguisher_powder", "sand"]),
    );
    expect(body.type_specific?.fire_fighting_means).toHaveLength(2);
    expect(body.type_specific?.respiratory_ppe).toBeUndefined();
  });

  // #3 для высоты (safety_systems — отдельный top-level массив).
  it("высота: две системы безопасности, отмеченные в одном батче, обе попадают в safety_systems", async () => {
    openWith("height");
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Удерживающие системы"));
      fireEvent.click(screen.getByLabelText("Страховочные системы"));
    });
    const body = await submitAndBody();
    expect(body.safety_systems).toEqual(expect.arrayContaining(["restraint", "fall_arrest"]));
    expect(body.safety_systems).toHaveLength(2);
  });

  // Смена вида работ не должна тащить height-специфичный чеклист на чужой вид.
  it("смена height→gas_hazardous сбрасывает safety_systems и не отправляет их на сервер", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    // вид по умолчанию height — отмечаем систему безопасности
    fireEvent.click(screen.getByLabelText("Удерживающие системы"));
    // переключаемся на газоопасные
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "gas_hazardous" } });
    fireEvent.change(screen.getByLabelText("Зона работ"), { target: { value: "ГРП-3" } });
    const body = await submitAndBody();
    expect(body.safety_systems == null || body.safety_systems.length === 0).toBe(true);
  });
});
