import { setReturnTo } from "@/utils/returnTo";

export const AUTH_REDIRECT_EVENT = "app:auth-required";

type AuthRedirectDetail = {
  to: string;
  reason?: string;
};

export const requestAuthRedirect = (reason?: string) => {
  if (typeof window === "undefined") return;
  const current = `${window.location.pathname}${window.location.search}`;
  if (!window.location.pathname.startsWith("/auth")) {
    setReturnTo(current);
  }

  const event = new CustomEvent<AuthRedirectDetail>(AUTH_REDIRECT_EVENT, {
    cancelable: true,
    detail: { to: "/auth/login", reason },
  });
  const notCancelled = window.dispatchEvent(event);
  if (notCancelled) {
    window.location.assign("/auth/login");
  }
};
