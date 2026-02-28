import { Bell, CheckCircle2, ChevronDown, LogOut, Moon, Settings, Sun } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useTenantStore } from "@/stores/tenant";
import { useTheme } from "@/hooks/useTheme";
import { useAuthStore } from "@/stores/auth";
import { GlobalSearch } from "@/components/GlobalSearch";

export const TopNav = () => {
  const { user, logout } = useAuthStore();
  const [theme, , toggleTheme] = useTheme();
  const { tenant, tenants, setTenant } = useTenantStore();
  const kpi = useMemo(
    () => ({
      tasks: 12,
      alerts: 5
    }),
    []
  );

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between gap-4 px-4">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold">Единый контур ОТ/ПБ</span>
          <div className="hidden items-center gap-2 rounded-full border bg-muted/40 px-3 py-1 text-xs text-muted-foreground lg:flex">
            RBAC · ABAC · ЭДО
          </div>
        </div>
        <div className="hidden flex-1 items-center justify-center px-4 lg:flex">
          <GlobalSearch />
        </div>
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="gap-2">
                <span className="hidden text-left text-xs sm:block">
                  <span className="block font-semibold leading-tight">{tenant?.name ?? "Выберите контур"}</span>
                  <span className="block text-[11px] text-muted-foreground">
                    {tenant?.site ?? "Контур не выбран"}
                  </span>
                </span>
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Контур / площадка</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {tenants.map((tenant) => (
                <DropdownMenuItem key={tenant.id} onSelect={() => setTenant(tenant)} className="flex flex-col items-start gap-1">
                  <span className="text-sm font-medium">{tenant.name}</span>
                  <span className="text-xs text-muted-foreground">{tenant.site}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="ghost" size="icon" aria-label="Единый реестр задач" className="relative">
            <CheckCircle2 className="h-5 w-5" />
            <Badge className="absolute -right-1 -top-1 hidden h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] sm:flex">
              {kpi.tasks}
            </Badge>
          </Button>
          <Button asChild variant="ghost" size="icon" aria-label="Уведомления" className="relative"><Link to="/notifications">
            <Bell className="h-5 w-5" />
            <Badge variant="destructive" className="absolute -right-1 -top-1 hidden h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] sm:flex">
              {kpi.alerts}
            </Badge>
          </Link></Button>
          <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={toggleTheme}>
            {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-2">
                <Settings className="h-4 w-4" />
                <span className="hidden sm:inline">{user?.full_name ?? user?.email ?? "Профиль"}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{user?.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => logout()} className="text-destructive">
                <LogOut className="mr-2 h-4 w-4" /> Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
};
