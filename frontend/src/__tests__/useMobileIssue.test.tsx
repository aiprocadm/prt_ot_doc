import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useMobileIssue } from "@/pages/ppe/mobile-issue/useMobileIssue";

const getPpeOverviewMock = vi.fn();
const createPpeIssueMock = vi.fn();
const listLevelsMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...a: unknown[]) => getPpeOverviewMock(...a),
    createPpeIssue: (...a: unknown[]) => createPpeIssueMock(...a)
  }
}));

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...a: unknown[]) => listLevelsMock(...a)
  }
}));

const person = (id: string, full_name: string, status = "active") => ({
  id,
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  first_name: full_name.split(" ")[0] ?? full_name,
  last_name: full_name.split(" ")[1] ?? "",
  full_name,
  position: "Сварщик",
  company_id: "c1",
  status
});

const item = (id: string, name: string) => ({ id, name, code: id, category: "head" });

beforeEach(() => {
  getPpeOverviewMock.mockReset();
  createPpeIssueMock.mockReset();
  listLevelsMock.mockReset();
  getPpeOverviewMock.mockResolvedValue({
    persons: [person("p1", "Иван Иванов"), person("p2", "Пётр Петров", "dismissed")],
    items: [item("i1", "Каска"), item("i2", "Перчатки")],
    issues: [],
    expiring: []
  });
  listLevelsMock.mockResolvedValue([{ item_id: "i1", item_name: "Каска", total_quantity: 5, batch_count: 1 }]);
  createPpeIssueMock.mockResolvedValue({ id: "x", person_id: "p1", item_id: "i1", quantity: 1, status: "issued" });
});

describe("useMobileIssue", () => {
  it("loads data, exposes only active persons, is stock-aware when listLevels resolves", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.activePersons.map((p) => p.id)).toEqual(["p1"]);
    expect(result.current.stockAware).toBe(true);
    expect(result.current.onHandFor("i1")).toBe(5);
    expect(result.current.onHandFor("i2")).toBe(0);
  });

  it("degrades silently when listLevels rejects (warehouse flag off)", async () => {
    listLevelsMock.mockRejectedValue({ message: "404" });
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.stockAware).toBe(false);
    expect(result.current.onHandFor("i1")).toBeNull();
  });

  it("selects worker, merges duplicate cart items, clamps qty, removes", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    expect(result.current.step).toBe("items");
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    expect(result.current.cart).toHaveLength(1);
    expect(result.current.cart[0].quantity).toBe(2);
    act(() => result.current.setQty("i1", 0));
    expect(result.current.cart[0].quantity).toBe(1);
    act(() => result.current.removeItem("i1"));
    expect(result.current.cart).toHaveLength(0);
  });

  it("issues all lines, clears cart, calls createPpeIssue per line with worker id", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    act(() => result.current.addItem({ id: "i2", name: "Перчатки", code: "i2", category: "hand" }));
    await act(async () => { await result.current.issueAll(); });
    expect(createPpeIssueMock).toHaveBeenCalledTimes(2);
    expect(createPpeIssueMock).toHaveBeenCalledWith({ person_id: "p1", item_id: "i1", quantity: 1 });
    expect(result.current.results?.every((r) => r.status === "ok")).toBe(true);
    expect(result.current.allIssued).toBe(true);
    expect(result.current.cart).toHaveLength(0);
  });

  it("on partial failure keeps only failed lines; retry re-sends only those", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    act(() => result.current.addItem({ id: "i2", name: "Перчатки", code: "i2", category: "hand" }));
    createPpeIssueMock
      .mockResolvedValueOnce({ id: "a" })
      .mockRejectedValueOnce({ message: "Недостаточно остатка" });
    await act(async () => { await result.current.issueAll(); });
    expect(result.current.cart).toEqual([expect.objectContaining({ item_id: "i2" })]);
    expect(result.current.results?.find((r) => r.item_id === "i2")?.error).toBe("Недостаточно остатка");
    expect(result.current.allIssued).toBe(false);
    createPpeIssueMock.mockResolvedValue({ id: "b" });
    await act(async () => { await result.current.issueAll(); });
    expect(createPpeIssueMock).toHaveBeenCalledTimes(3); // 2 first attempt + 1 retry
    expect(result.current.cart).toHaveLength(0);
  });

  it("guards against synchronous double submit", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    let release!: () => void;
    createPpeIssueMock.mockReturnValue(new Promise((res) => { release = () => res({ id: "z" }); }));
    await act(async () => {
      const first = result.current.issueAll();
      const second = result.current.issueAll(); // must be a no-op (in-flight)
      release();
      await Promise.all([first, second]);
    });
    expect(createPpeIssueMock).toHaveBeenCalledTimes(1);
  });
});
