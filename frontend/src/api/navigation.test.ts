import MockAdapter from "axios-mock-adapter";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { tenantStorage } from "@/api/tenantStorage";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

describe("apiClient: тосты об ошибках", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
    tenantStorage.clear();
    vi.clearAllMocks();
  });

  // СРЕЗ-233: здесь стояла проверка «не показывает тост при 404: метрики —
  // best-effort, эндпоинт может отсутствовать». Она закрепляла как норму то,
  // что приёмника у UX-метрик нет: запрос уходил при каждом переходе между
  // экранами и всегда получал 404. Отправку убрали, проверку — вместе с ней.
  //
  // Флаг «без тоста» остался и используется там, где ответ 404 — обычное дело
  // (например, проверка наличия необязательного файла). Проверка ниже держит
  // обратную сторону: БЕЗ флага тост показывается.

  it("обычные запросы без silent-флага по-прежнему показывают тост на 404", async () => {
    mock.onGet("/documents/missing").reply(404, {
      code: "NOT_FOUND",
      type: "not_found",
      message: "Not Found",
    });

    await expect(apiClient.get("/documents/missing")).rejects.toMatchObject({
      status: 404,
    });
    expect(toast.error).toHaveBeenCalled();
  });
});
