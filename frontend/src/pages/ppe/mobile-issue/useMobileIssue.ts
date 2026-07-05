import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { opsApi, type PpeItemDto } from "@/api/ops";
import { warehouseApi } from "@/api/warehouse";
import type { ApiError } from "@/types/dto/common";
import type { PersonDto } from "@/types/dto/persons";

import type { CartLine, IssueResultLine, MobileIssueStep } from "./types";

export function useMobileIssue() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [persons, setPersons] = useState<PersonDto[]>([]);
  const [items, setItems] = useState<PpeItemDto[]>([]);
  const [stockAware, setStockAware] = useState(false);
  const [onHand, setOnHand] = useState<Map<string, number>>(new Map());

  const [step, setStep] = useState<MobileIssueStep>("worker");
  const [worker, setWorker] = useState<PersonDto | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<IssueResultLine[] | null>(null);
  const submittingRef = useRef(false); // synchronous double-tap guard

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await opsApi.getPpeOverview();
      setPersons(snapshot.persons);
      setItems(snapshot.items);
      // /ppe/stock/levels is gated by the warehouse feature flag; a 404/403 just
      // means "no stock tracking" — degrade silently, issuance still works.
      try {
        const levels = await warehouseApi.listLevels();
        setOnHand(new Map(levels.map((lvl) => [lvl.item_id, lvl.total_quantity])));
        setStockAware(true);
      } catch {
        setOnHand(new Map());
        setStockAware(false);
      }
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить данные выдачи СИЗ" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activePersons = useMemo(() => persons.filter((p) => p.status === "active"), [persons]);

  const onHandFor = useCallback(
    (itemId: string): number | null => (stockAware ? onHand.get(itemId) ?? 0 : null),
    [stockAware, onHand]
  );

  const selectWorker = useCallback((person: PersonDto) => {
    setWorker(person);
    setStep("items");
  }, []);

  const reset = useCallback(() => {
    setWorker(null);
    setCart([]);
    setResults(null);
    setStep("worker");
  }, []);

  const addItem = useCallback(
    (item: PpeItemDto) => {
      setResults(null);
      setCart((prev) => {
        const existing = prev.find((line) => line.item_id === item.id);
        if (existing) {
          return prev.map((line) =>
            line.item_id === item.id ? { ...line, quantity: line.quantity + 1 } : line
          );
        }
        return [...prev, { item_id: item.id, item_name: item.name, quantity: 1, on_hand: onHandFor(item.id) }];
      });
    },
    [onHandFor]
  );

  const setQty = useCallback((itemId: string, quantity: number) => {
    setResults(null);
    setCart((prev) =>
      prev.map((line) =>
        line.item_id === itemId ? { ...line, quantity: Math.max(1, Math.floor(quantity) || 1) } : line
      )
    );
  }, []);

  const removeItem = useCallback((itemId: string) => {
    setResults(null);
    setCart((prev) => prev.filter((line) => line.item_id !== itemId));
  }, []);

  const issueAll = useCallback(async () => {
    if (submittingRef.current || !worker || cart.length === 0) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const lineResults: IssueResultLine[] = [];
      for (const line of cart) {
        try {
          await opsApi.createPpeIssue({ person_id: worker.id, item_id: line.item_id, quantity: line.quantity });
          lineResults.push({ item_id: line.item_id, item_name: line.item_name, quantity: line.quantity, status: "ok" });
        } catch (err) {
          const apiErr = err as ApiError;
          lineResults.push({
            item_id: line.item_id,
            item_name: line.item_name,
            quantity: line.quantity,
            status: "error",
            error: apiErr?.message || "Не удалось выдать позицию"
          });
        }
      }
      // Drop successfully-issued lines so a retry re-sends only failed ones
      // (prevents double-issue without server-side idempotency).
      const okIds = new Set(lineResults.filter((r) => r.status === "ok").map((r) => r.item_id));
      setCart((prev) => prev.filter((line) => !okIds.has(line.item_id)));
      setResults(lineResults);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, [worker, cart]);

  const allIssued = useMemo(
    () => results !== null && results.length > 0 && results.every((r) => r.status === "ok"),
    [results]
  );

  return {
    loading,
    error,
    reload: load,
    step,
    setStep,
    persons,
    activePersons,
    items,
    stockAware,
    onHandFor,
    worker,
    selectWorker,
    reset,
    cart,
    addItem,
    setQty,
    removeItem,
    submitting,
    results,
    issueAll,
    allIssued
  };
}

export type UseMobileIssue = ReturnType<typeof useMobileIssue>;
