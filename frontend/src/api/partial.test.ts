import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

/**
 * Срез-167. Сводные экраны грузят несколько списков одним пакетом, и пакет
 * отклоняется целиком, если отклонён хоть один запрос. Раньше из-за этого
 * один отказ по правам оставлял человека перед пустой страницей, хотя
 * остальные списки ему доступны.
 *
 * Здесь проверяется само поведение загрузки, а не разметка: отказ по правам
 * даёт пустой раздел и его название, а настоящая поломка по-прежнему
 * доходит до экрана.
 */
describe("частичная загрузка сводных экранов", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  const forbidden = { status: 403, message: "Forbidden" };
  const page = (items: unknown[]) => ({ data: { items } });

  it("отказ по правам не роняет экран и называет закрытый раздел", async () => {
    const { opsApi } = await import("@/api/ops");
    getMock.mockImplementation((url: string) => {
      if (url === "/persons") return Promise.reject(forbidden);
      if (url === "/ppe/items")
        return Promise.resolve(page([{ id: "item-1", name: "Каска" }]));
      return Promise.resolve(page([]));
    });

    const snapshot = await opsApi.getPpeOverview();

    expect(snapshot.items).toHaveLength(1);
    expect(snapshot.denied).toContain("сотрудники");
  });

  it("настоящая поломка не прячется", async () => {
    const { opsApi } = await import("@/api/ops");
    getMock.mockImplementation((url: string) => {
      if (url === "/persons")
        return Promise.reject({ status: 500, message: "Internal" });
      return Promise.resolve(page([]));
    });

    await expect(opsApi.getPpeOverview()).rejects.toMatchObject({
      status: 500,
    });
  });

  it("подготовка к проверке считает закрытые разделы так же", async () => {
    const { opsApi } = await import("@/api/ops");
    getMock.mockImplementation((url: string) => {
      if (url === "/prescriptions") return Promise.reject(forbidden);
      return Promise.resolve(page([]));
    });

    const snapshot = await opsApi.getAuditPrepSnapshot();

    expect(snapshot.denied).toEqual(["предписания"]);
  });
});
