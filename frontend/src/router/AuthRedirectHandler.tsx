import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { AUTH_REDIRECT_EVENT } from "@/router/authRedirect";

export const AuthRedirectHandler = () => {
  const navigate = useNavigate();

  useEffect(() => {
    const onAuthRequired = (event: Event) => {
      event.preventDefault();
      const custom = event as CustomEvent<{ to?: string }>;
      navigate(custom.detail?.to ?? "/auth/login", { replace: true });
    };
    window.addEventListener(AUTH_REDIRECT_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REDIRECT_EVENT, onAuthRequired);
  }, [navigate]);

  return null;
};
