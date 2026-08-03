import { registerSW } from "virtual:pwa-register";

export const registerPwa = () => {
  if (typeof window === "undefined") {
    return;
  }

  if (import.meta.env.DEV) {
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.getRegistrations().then((registrations) => {
        registrations.forEach((registration) => {
          void registration.unregister();
        });
      });
    }
    if ("caches" in window) {
      void caches.keys().then((keys) => {
        keys.forEach((key) => {
          void caches.delete(key);
        });
      });
    }
    return;
  }

  registerSW({
    immediate: true,
    onRegistered(registration: ServiceWorkerRegistration | undefined) {
      if (!registration) {
        return;
      }
      const checkForUpdate = () => {
        void registration.update();
      };
      // Свежая сборка выкатывается часто; проверяем не только по таймеру,
      // но и при каждом возврате во вкладку — иначе открытая страница
      // держит старую версию до часа.
      setInterval(checkForUpdate, 15 * 60 * 1000);
      window.addEventListener("focus", checkForUpdate);
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
          checkForUpdate();
        }
      });
    },
  });
};
