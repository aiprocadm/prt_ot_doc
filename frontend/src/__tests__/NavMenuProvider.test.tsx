import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  NavMenuProvider,
  useNavMenuData,
} from "@/components/layout/NavMenuProvider";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { useModulesStore } from "@/stores/modules";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

const getMyModulesMock = vi.fn();

vi.mock("@/api/modules", () => ({
  getMyModules: (...args: unknown[]) => getMyModulesMock(...args),
}));

const NavMenuConsumerProbe = () => {
  const { visibleGroups, clientPortalOnlyMode } = useNavMenuData();
  const labels = visibleGroups.flatMap((group) =>
    group.items.map((item) => item.to),
  );
  return (
    <div>
      <span data-testid="groups-count">{visibleGroups.length}</span>
      <span data-testid="portal-only">{String(clientPortalOnlyMode)}</span>
      <span data-testid="paths">{labels.join(" ")}</span>
    </div>
  );
};

const signIn = (id: string) => {
  useAuthStore.setState({
    user: {
      id,
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
      email: `${id}@test.local`,
      full_name: "Provider User",
      roles: ["owner"],
      permissions: [
        PERMISSIONS.DASHBOARD_VIEW,
        PERMISSIONS.DOCUMENT_VIEW,
        PERMISSIONS.SOUT_VIEW,
      ],
      attributes: { tenant_id: "tenant-1" },
    },
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });
};

describe("NavMenuProvider", () => {
  beforeEach(() => {
    getMyModulesMock.mockReset();
    // Список модулей кешируется на сеанс — без сброса второй тест увидел бы
    // ответ первого и «прошёл» бы вхолостую.
    useModulesStore.getState().reset();
  });

  it("спрашивает модули арендатора один раз и отдаёт навигацию", async () => {
    getMyModulesMock.mockResolvedValue([]);
    signIn("provider-user");

    renderWithRouter(
      <NavMenuProvider>
        <NavMenuConsumerProbe />
      </NavMenuProvider>,
    );

    await waitFor(() => {
      expect(getMyModulesMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByTestId("groups-count")).toHaveTextContent(/[1-9]\d*/);
    expect(screen.getByTestId("portal-only")).toHaveTextContent("false");
  });

  it("прячет пункты меню выключенного модуля (разд. 61.3)", async () => {
    getMyModulesMock.mockResolvedValue([
      {
        code: "sout",
        title: "Спецоценка",
        category: "Охрана труда",
        is_core: false,
        enabled: false,
        trial_until: null,
        ui_routes: ["/sout"],
      },
    ]);
    signIn("provider-user-sout");

    renderWithRouter(
      <NavMenuProvider>
        <NavMenuConsumerProbe />
      </NavMenuProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("paths")).not.toHaveTextContent("/sout");
    });
  });

  it("выданный модуль остаётся в меню", async () => {
    getMyModulesMock.mockResolvedValue([
      {
        code: "sout",
        title: "Спецоценка",
        category: "Охрана труда",
        is_core: false,
        enabled: true,
        trial_until: null,
        ui_routes: ["/sout"],
      },
    ]);
    signIn("provider-user-sout-on");

    renderWithRouter(
      <NavMenuProvider>
        <NavMenuConsumerProbe />
      </NavMenuProvider>,
    );

    await waitFor(() => {
      expect(getMyModulesMock).toHaveBeenCalled();
    });
    expect(screen.getByTestId("paths")).toHaveTextContent("/sout");
  });

  it("при отказе запроса меню остаётся рабочим", async () => {
    // Закрыться при сбое было бы хуже: настоящий запрет стоит на сервере, а
    // пустое меню из-за одного неудачного запроса лишает работы всех.
    getMyModulesMock.mockRejectedValue(new Error("modules unavailable"));
    signIn("provider-user-2");

    renderWithRouter(
      <NavMenuProvider>
        <NavMenuConsumerProbe />
      </NavMenuProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("groups-count")).toHaveTextContent(/[1-9]\d*/);
    });
  });
});
