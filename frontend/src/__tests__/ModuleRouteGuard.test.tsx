import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import { ModuleDisabledPage } from "@/pages/access/ModuleDisabledPage";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { useAuthStore } from "@/stores/auth";
import { useModulesStore } from "@/stores/modules";
import type { MyModule } from "@/api/modules";

/**
 * BIZ-61 срез-5, разд. 61.3, слой «роутинг».
 *
 * Спрятать пункт меню мало: заказчик, знающий адрес, дошёл бы до экрана
 * выключенного модуля. ТЗ прямо про это: «Иначе заказчик, знающий URL,
 * достучится до выключенного модуля».
 */

const SoutPage = () => <div>Экран спецоценки</div>;

const SOUT: MyModule = {
  code: "sout",
  title: "Спецоценка",
  category: "Охрана труда",
  is_core: false,
  enabled: false,
  trial_until: null,
  ui_routes: ["/sout"],
};

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<ProtectedRoute permission={PERMISSIONS.SOUT_VIEW} />}>
          <Route path="/sout" element={<SoutPage />} />
          <Route path="/sout/cards" element={<SoutPage />} />
        </Route>
        <Route path="/module-unavailable" element={<ModuleDisabledPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe("охрана маршрутов по модулям", () => {
  beforeEach(() => {
    useModulesStore.getState().reset();
    useAuthStore.setState({
      user: {
        id: "guard-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
        email: "guard@test.local",
        full_name: "Guard User",
        roles: ["owner"],
        permissions: [PERMISSIONS.SOUT_VIEW],
        attributes: { tenant_id: "tenant-1" },
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("прямой переход на выключенный модуль ведёт на «модуль не подключён»", () => {
    useModulesStore.setState({
      modules: [SOUT],
      loaded: true,
      disabledRoutes: ["/sout"],
    });

    renderAt("/sout");

    expect(screen.queryByText("Экран спецоценки")).not.toBeInTheDocument();
    expect(screen.getByText(/не подключён/)).toBeInTheDocument();
  });

  it("страница называет модуль, а не отделывается общей фразой", () => {
    useModulesStore.setState({
      modules: [SOUT],
      loaded: true,
      disabledRoutes: ["/sout"],
    });

    renderAt("/sout");

    // «Нет прав» решает администратор компании, «модуль не подключён» — тот,
    // кто платит за платформу. Без названия человек не поймёт, о чём просить.
    expect(screen.getByText(/Спецоценка/)).toBeInTheDocument();
  });

  it("вложенный экран модуля закрывается вместе с ним", () => {
    useModulesStore.setState({
      modules: [SOUT],
      loaded: true,
      disabledRoutes: ["/sout"],
    });

    renderAt("/sout/cards");

    expect(screen.queryByText("Экран спецоценки")).not.toBeInTheDocument();
  });

  it("выданный модуль открывается", () => {
    useModulesStore.setState({
      modules: [{ ...SOUT, enabled: true }],
      loaded: true,
      disabledRoutes: [],
    });

    renderAt("/sout");

    expect(screen.getByText("Экран спецоценки")).toBeInTheDocument();
  });

  it("пока список не загружен, экран не закрывается", () => {
    // Пустой список значит «скрывать нечего», а не «всё выключено»: настоящий
    // запрет стоит на сервере, и закрыть интерфейс из-за неудачного запроса
    // хуже, чем показать лишний раздел.
    renderAt("/sout");

    expect(screen.getByText("Экран спецоценки")).toBeInTheDocument();
  });
});
