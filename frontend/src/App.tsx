import { useEffect } from "react";

import AppRouter from "@/router/AppRouter";
import { AppErrorBoundary } from "@/components/common/AppErrorBoundary";
import { applyBrandTheme, useBrandStore } from "@/stores/brand";

/**
 * Бренд грузится ЗДЕСЬ, а не внутри защищённого дерева (BIZ-52 разд. 52.2):
 * имя и цвет нужны экрану входа, который живёт снаружи. Загрузи их после
 * входа — и человек увидит сначала вендора, а потом подмену.
 */
const App = () => {
  const brand = useBrandStore((state) => state.brand);
  const load = useBrandStore((state) => state.load);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    applyBrandTheme(brand);
  }, [brand]);

  return (
    <AppErrorBoundary>
      <AppRouter />
    </AppErrorBoundary>
  );
};

export default App;
