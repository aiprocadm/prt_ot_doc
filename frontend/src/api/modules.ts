import { apiClient } from "@/api/client";

/**
 * Модули текущего арендатора (BIZ-61 срез-5, Доп. №2 разд. 61.3).
 *
 * Связь «модуль → экраны» приходит с сервера намеренно. Опиши её здесь — и она
 * будет заведена дважды, а однажды разойдётся с бэкендом: выключенный модуль
 * останется в меню или, наоборот, спрячется работающий раздел.
 */
export type MyModule = {
  code: string;
  title: string;
  category: string;
  is_core: boolean;
  enabled: boolean;
  trial_until: string | null;
  ui_routes: string[];
};

export const getMyModules = async () => {
  const { data } = await apiClient.get<{ modules: MyModule[] }>(
    "/tenants/me/modules",
    // Ошибка здесь не должна сыпать тостом на каждом входе: меню в этом случае
    // остаётся полным, а настоящий запрет всё равно стоит на сервере.
    { silentApiErrorToast: true },
  );
  return data.modules;
};
