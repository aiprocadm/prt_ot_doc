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
      setInterval(() => {
        void registration.update();
      }, 60 * 60 * 1000);
    },
  });
};
