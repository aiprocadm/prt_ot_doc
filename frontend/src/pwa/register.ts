import { registerSW } from "virtual:pwa-register";

export const registerPwa = () => {
  if (typeof window === "undefined") {
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
