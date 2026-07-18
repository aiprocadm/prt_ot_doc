import { Outlet } from "react-router-dom";

export const AuthLayout = () => (
  <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-background via-background to-muted">
    <div className="w-full max-w-md rounded-xl border bg-background/80 p-8 shadow-lg backdrop-blur">
      <Outlet />
    </div>
  </div>
);
