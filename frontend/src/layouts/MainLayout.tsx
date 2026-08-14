import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { Toaster } from "sonner";

import { ConnectivityBanner } from "@/components/common/ConnectivityBanner";
import { LegalAcceptanceBanner } from "@/components/common/LegalAcceptanceBanner";
import { SectionErrorBoundary } from "@/components/common/SectionErrorBoundary";
import { RightDrawer } from "@/components/layout/RightDrawer";
import { SideNav } from "@/components/layout/SideNav";
import { Sidebar } from "@/components/layout/Sidebar";
import { NavMenuProvider } from "@/components/layout/NavMenuProvider";
import { TopNav } from "@/components/layout/TopNav";
import { TenantGate } from "@/components/tenant/TenantGate";
import { BILLING_ALERT_STORAGE_KEY } from "@/api/errorHandling";
import {
  sessionStorageGetItem,
  sessionStorageRemoveItem,
} from "@/utils/browserStorage";

interface SidebarContextValue {
  setSidebar: (content: ReactNode) => void;
}

const SidebarContext = createContext<SidebarContextValue | undefined>(
  undefined,
);

export const useSidebar = () => {
  const context = useContext(SidebarContext);
  if (!context) throw new Error("useSidebar must be used within MainLayout");
  return context;
};

export const MainLayout = () => {
  const location = useLocation();
  const [sidebarContent, setSidebarContent] = useState<ReactNode>(null);
  const [billingAlert, setBillingAlert] = useState<string | null>(null);
  const contextValue = useMemo(() => ({ setSidebar: setSidebarContent }), []);

  useEffect(() => {
    const raw = sessionStorageGetItem(BILLING_ALERT_STORAGE_KEY);
    if (!raw) return;
    try {
      const payload = JSON.parse(raw) as { code?: string; ts?: number };
      if (!payload.code) return;
      if (payload.ts && Date.now() - payload.ts > 1000 * 60 * 30) {
        sessionStorageRemoveItem(BILLING_ALERT_STORAGE_KEY);
        return;
      }
      setBillingAlert(payload.code);
    } catch {
      sessionStorageRemoveItem(BILLING_ALERT_STORAGE_KEY);
    }
  }, []);

  return (
    <SidebarContext.Provider value={contextValue}>
      <TenantGate>
        <NavMenuProvider>
          <div className="min-h-screen bg-background text-foreground">
            <SectionErrorBoundary>
              <TopNav />
            </SectionErrorBoundary>
            <SectionErrorBoundary>
              <ConnectivityBanner />
            </SectionErrorBoundary>
            {billingAlert && (
              <div className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">
                {billingAlert === "BILLING_BLOCKED"
                  ? "Доступ ограничен из-за статуса оплаты."
                  : "Достигнут лимит тарифа."}{" "}
                <Link className="font-medium underline" to="/admin/billing">
                  Перейти в биллинг
                </Link>
              </div>
            )}
            <div className="flex">
              <SectionErrorBoundary>
                <SideNav />
              </SectionErrorBoundary>
              <div className="flex-1">
                <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-6 lg:flex-row">
                  <Sidebar title="Фильтры">{sidebarContent}</Sidebar>
                  <SectionErrorBoundary key={location.pathname}>
                    <main className="flex-1 pb-16">
                      {/* BIZ-52 срез-11: подпись под офертой нужна на любом
                          экране — страницу с текстом по своей воле не
                          открывают. Полоса сама исчезает, когда подписывать
                          нечего. */}
                      <LegalAcceptanceBanner />
                      <Outlet />
                    </main>
                  </SectionErrorBoundary>
                  <SectionErrorBoundary>
                    <RightDrawer />
                  </SectionErrorBoundary>
                </div>
              </div>
            </div>
            <Toaster richColors position="top-right" closeButton />
          </div>
        </NavMenuProvider>
      </TenantGate>
    </SidebarContext.Provider>
  );
};
