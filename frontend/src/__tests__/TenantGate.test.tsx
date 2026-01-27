import { beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TenantGate } from "@/components/tenant/TenantGate";
import { tenantStorage } from "@/api/tenantStorage";
import { useTenantStore } from "@/stores/tenant";

describe("TenantGate", () => {
  beforeEach(() => {
    tenantStorage.clear();
    useTenantStore.getState().clearTenant();
  });

  it("prompts for tenant selection and allows activation", async () => {
    render(
      <TenantGate>
        <div>Контент</div>
      </TenantGate>
    );

    expect(screen.getByText("Выберите контур")).toBeInTheDocument();

    const user = userEvent.setup();
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /северстрой/i }));
    });

    expect(screen.getByText("Контент")).toBeInTheDocument();
    expect(tenantStorage.getTenant()?.slug).toBe("severstroy");
  });
});
