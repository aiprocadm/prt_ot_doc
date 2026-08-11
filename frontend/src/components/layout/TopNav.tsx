import { Bell, CheckCircle2, ChevronDown, LogOut, Moon, Settings, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { GlobalSearch } from "@/components/GlobalSearch";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { CommandBar } from "@/components/layout/CommandBar";
import { MobileNavDrawer } from "@/components/layout/MobileNavDrawer";
import { getTopNavKpi } from "@/api/navigation";
import { useTheme } from "@/hooks/useTheme";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { trackUxMetric } from "@/utils/uxMetrics";

export const TopNav = () => {
  const { user, logout } = useAuthStore();
  const [theme, , toggleTheme] = useTheme();
  const { tenant, tenants, setTenant } = useTenantStore();
  const [kpi, setKpi] = useState({ tasks: 0, alerts: 0 });

  useEffect(() => {
    let mounted = true;
    const loadCounts = async () => {
      try {
        const data = await getTopNavKpi();
        if (!mounted) return;
        setKpi(data);
      } catch {
        if (mounted) setKpi({ tasks: 0, alerts: 0 });
      }
    };
    void loadCounts();
    const timer = window.setInterval(() => void loadCounts(), 60000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center gap-2 px-4">
        <div className="flex min-w-0 shrink-0 items-center gap-2 sm:gap-3">
          <MobileNavDrawer />
          <span className="truncate text-base font-semibold sm:text-lg">Единый контур ОТ/ПБ</span>
          <div className="hidden items-center gap-2 rounded-full border bg-muted/40 px-3 py-1 text-xs text-muted-foreground lg:flex">
            RBAC · ABAC · ЭДО
          </div>
        </div>
        <div className="flex min-w-0 flex-1 items-center justify-center px-1 sm:px-4">
          <GlobalSearch />
        </div>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <CommandBar />
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
          <Button asChild variant="ghost" size="icon" aria-label="Единый реестр задач" className="relative h-11 w-11">
            <Link
              to="/tasks"
              onClick={() => {
                trackUxMetric("navigation_click", { source: "topnav", target: "tasks" });
                trackUxMetric("time_to_first_action", { source: "topnav" });
              }}
            >
              <CheckCircle2 className="h-5 w-5" />
              <Badge className="absolute -right-1 -top-1 hidden h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] sm:flex">
                {kpi.tasks}
              </Badge>
            </Link>
          </Button>
          <Button asChild variant="ghost" size="icon" aria-label="Уведомления" className="relative h-11 w-11">
            <Link
              to="/notifications"
              onClick={() => {
                trackUxMetric("navigation_click", { source: "topnav", target: "notifications" });
                trackUxMetric("time_to_first_action", { source: "topnav" });
              }}
            >
              <Bell className="h-5 w-5" />
              <Badge variant="destructive" className="absolute -right-1 -top-1 hidden h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] sm:flex">
                {kpi.alerts}
              </Badge>
            </Link>
          </Button>
          <Button variant="ghost" size="icon" aria-label="Переключить тему оформления" onClick={toggleTheme} className="h-11 w-11">
            {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-2" data-testid="user-menu-trigger">
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
