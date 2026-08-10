import { createWithEqualityFn } from "zustand/traditional";

import { getMyModules, type MyModule } from "@/api/modules";

/**
 * Модули текущего арендатора (BIZ-61 срез-5, Доп. №2 разд. 61.3).
 *
 * Отдельное хранилище, а не контекст внутри разметки: список нужен и меню, и
 * охране маршрутов, а они живут в разных местах дерева. Контекст пришлось бы
 * поднимать выше роутера — и он ломался бы от перестановки провайдеров.
 *
 * **Не закрываемся при ошибке.** Пустой список выключенных модулей значит
 * «скрывать нечего», а не «всё выключено»: настоящий запрет стоит на сервере
 * (он отвечает 404 на выключенный модуль), а спрятать всё меню из-за одного
 * неудачного запроса — потерять работоспособность там, где всё оплачено.
 */
interface ModulesState {
  modules: MyModule[];
  loaded: boolean;
  loading: boolean;
  /** Экраны выключенных модулей — по ним прячется меню и закрывается переход. */
  disabledRoutes: string[];
  load: () => Promise<void>;
  reset: () => void;
}

const initial = {
  modules: [] as MyModule[],
  loaded: false,
  loading: false,
  disabledRoutes: [] as string[],
};

export const useModulesStore = createWithEqualityFn<ModulesState>(
  (set, get) => ({
    ...initial,
    load: async () => {
      // Список меняется, когда арендатору выдают модуль, — не в течение сеанса.
      // Повторные вызовы из разных мест дерева не должны множить запросы.
      if (get().loading || get().loaded) {
        return;
      }
      set({ loading: true });
      try {
        const modules = await getMyModules();
        set({
          modules,
          loaded: true,
          loading: false,
          disabledRoutes: modules
            .filter((item) => !item.enabled)
            .flatMap((item) => item.ui_routes),
        });
      } catch {
        // Осознанно тихо: см. заголовок хранилища.
        set({ loading: false });
      }
    },
    reset: () => set({ ...initial }),
  }),
  Object.is,
);
