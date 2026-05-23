import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useLocation, useNavigate } from "react-router-dom";

import { tenantStorage } from "@/api/tenantStorage";
import { TENANT_OPTIONS } from "@/config/tenants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/stores/auth";
import { loginSchema, type LoginFormValues } from "@/types/forms/auth";
import { consumeReturnTo } from "@/utils/returnTo";

const LoginPage = () => {
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      tenant: tenantStorage.getTenant()?.slug ?? TENANT_OPTIONS[0]?.slug ?? "",
      email: "",
      password: ""
    }
  });
  const { login, loading, isAuthenticated } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (isAuthenticated) {
      const returnTo = consumeReturnTo();
      const redirectTo = returnTo ?? (location.state as { from?: Location })?.from?.pathname ?? "/companies";
      navigate(redirectTo, { replace: true });
    }
  }, [isAuthenticated, location.state, navigate]);

  const onSubmit = async (values: LoginFormValues) => {
    try {
      await login(values);
    } catch (error) {
      form.setError("password", { message: (error as Error).message });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Вход в платформу</h1>
        <p className="text-sm text-muted-foreground">Авторизуйтесь для управления документами</p>
      </div>
      <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
        <div className="space-y-2">
          <Label htmlFor="tenant">Tenant</Label>
          <Input id="tenant" list="tenant-options" {...form.register("tenant")} autoComplete="organization" placeholder="демо" />
          <datalist id="tenant-options">
            {TENANT_OPTIONS.map((tenant) => (
              <option key={tenant.slug} value={tenant.slug}>
                {tenant.name}
              </option>
            ))}
          </datalist>
          {form.formState.errors.tenant && <p className="text-xs text-destructive">{form.formState.errors.tenant.message}</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">E-mail</Label>
          <Input id="email" type="email" {...form.register("email")} autoComplete="email" />
          {form.formState.errors.email && <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Пароль</Label>
          <Input id="password" type="password" {...form.register("password")} autoComplete="current-password" />
          {form.formState.errors.password && (
            <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>
          )}
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Вход..." : "Войти"}
        </Button>
      </form>
    </div>
  );
};

export default LoginPage;
