import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useAsyncResource } from "./useAsyncResource";

describe("useAsyncResource", () => {
  it("applies the latest loader result when the loader changes mid-flight", async () => {
    let resolveFirst: (value: string) => void = () => undefined;
    const firstLoad = new Promise<string>((resolve) => {
      resolveFirst = resolve;
    });
    const loaders = [() => firstLoad, () => Promise.resolve("second")] as const;
    const { result, rerender } = renderHook(
      ({ idx }: { idx: 0 | 1 }) =>
        useAsyncResource({ loader: loaders[idx], initialData: "initial", errorMessage: "err" }),
      { initialProps: { idx: 0 as 0 | 1 } }
    );
    rerender({ idx: 1 });
    await waitFor(() => expect(result.current.data).toBe("second"));
    await act(async () => {
      resolveFirst("first");
      await firstLoad;
    });
    expect(result.current.data).toBe("second");
    expect(result.current.loading).toBe(false);
  });

  it("keeps a stale error from overwriting the latest successful load", async () => {
    let rejectFirst: (err: unknown) => void = () => undefined;
    const firstLoad = new Promise<string>((_resolve, reject) => {
      rejectFirst = reject;
    });
    const loaders = [() => firstLoad, () => Promise.resolve("second")] as const;
    const { result, rerender } = renderHook(
      ({ idx }: { idx: 0 | 1 }) =>
        useAsyncResource({ loader: loaders[idx], initialData: "initial", errorMessage: "err" }),
      { initialProps: { idx: 0 as 0 | 1 } }
    );
    rerender({ idx: 1 });
    await waitFor(() => expect(result.current.data).toBe("second"));
    await act(async () => {
      rejectFirst({ status: 500, message: "boom" });
      await firstLoad.catch(() => undefined);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.data).toBe("second");
  });
});
