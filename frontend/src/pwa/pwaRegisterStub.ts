// Заглушка "virtual:pwa-register" для vitest: плагин VitePWA в тестовом
// режиме отключён (vite.config.ts), и виртуальный модуль иначе не резолвится.
type RegisterSWOptions = {
  immediate?: boolean;
  onRegistered?: (registration: ServiceWorkerRegistration | undefined) => void;
};

export const registerSW = (_options?: RegisterSWOptions) => () => Promise.resolve();
