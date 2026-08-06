import { describe, it, expect, vi, type Mock } from "vitest";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { workPermitsApi } from "@/api/workPermits";

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: { create: vi.fn(), update: vi.fn() },
}));

const createMock = () => workPermitsApi.create as unknown as Mock;

type SubmittedBody = {
  type_specific?: {
    technical_measures?: string[];
    voltage_condition?: string;
    voltage_level?: string;
  } | null;
};

const openWith = (workType: string) => {
  render(<WorkPermitFormDialog trigger={<button>open</button>} />);
  fireEvent.click(screen.getByText("open"));
  fireEvent.change(screen.getByLabelText("Вид работ"), {
    target: { value: workType },
  });
  fireEvent.change(screen.getByLabelText("Зона работ"), {
    target: { value: "ТП-17" },
  });
};

const submitAndBody = async (): Promise<SubmittedBody> => {
  fireEvent.click(screen.getByText("Сохранить"));
  await waitFor(() => expect(createMock()).toHaveBeenCalled());
  return createMock().mock.calls[0][0] as SubmittedBody;
};

describe("WorkPermitFormDialog electrical section", () => {
  beforeEach(() => createMock().mockReset());

  it("показывает секцию электроустановок при выборе electrical и скрывает высоту/газоопасные", () => {
    openWith("electrical");
    expect(
      screen.getByText(/Меры безопасности в электроустановках/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Проверено отсутствие напряжения"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Системы обеспечения безопасности"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Защита органов дыхания/i),
    ).not.toBeInTheDocument();
  });

  it("два чекбокса техмероприятий, отмеченных в одном батче, оба попадают в type_specific.technical_measures", async () => {
    openWith("electrical");
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Проверено отсутствие напряжения"));
      fireEvent.click(
        screen.getByLabelText("Установлено заземление (ЗН / переносные)"),
      );
    });
    const body = await submitAndBody();
    expect(body.type_specific?.technical_measures).toEqual(
      expect.arrayContaining(["verify_no_voltage", "grounding"]),
    );
    expect(body.type_specific?.technical_measures).toHaveLength(2);
  });

  it("select «Условие проведения» выставляет voltage_condition=de_energized", async () => {
    openWith("electrical");
    fireEvent.change(screen.getByLabelText("Условие проведения"), {
      target: { value: "de_energized" },
    });
    const body = await submitAndBody();
    expect(body.type_specific?.voltage_condition).toBe("de_energized");
  });

  it("select «Класс напряжения» виден в электро-секции и пишет voltage_level отдельно от voltage_condition", async () => {
    openWith("electrical");
    // контрол присутствует
    expect(screen.getByLabelText("Класс напряжения")).toBeInTheDocument();
    // выбираем «Выше 1000 В»
    fireEvent.change(screen.getByLabelText("Класс напряжения"), {
      target: { value: "gt_1000" },
    });
    const body = await submitAndBody();
    expect(body.type_specific?.voltage_level).toBe("gt_1000");
    // voltage_condition не затронут (undefined/отсутствует)
    expect(body.type_specific?.voltage_condition).toBeUndefined();
  });
});
