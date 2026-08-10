import { Link, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isRouteOfDisabledModule } from "@/router/navVisibility";
import { useModulesStore } from "@/stores/modules";

/**
 * «Модуль не подключён» (BIZ-61 срез-5, разд. 61.3).
 *
 * Отдельная страница, а не «Доступ ограничен»: ответы пользователю разные.
 * «Нет прав» решается администратором внутри компании, «модуль не подключён» —
 * тем, кто платит за платформу. Сваливать это в одно сообщение значит послать
 * человека не туда.
 */
export const ModuleDisabledPage = () => {
  const location = useLocation();
  const attempted = (location.state as { from?: { pathname?: string } } | null)
    ?.from?.pathname;
  const modules = useModulesStore((state) => state.modules);

  const module = attempted
    ? modules.find(
        (item) =>
          !item.enabled && isRouteOfDisabledModule(attempted, item.ui_routes),
      )
    : undefined;

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle className="text-xl font-semibold">
            {module ? `Модуль «${module.title}» не подключён` : "Модуль не подключён"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Права у вас есть, но этот раздел не входит в состав вашей
            подписки. Чтобы его подключить, обратитесь к вашему менеджеру.
          </p>
          <div className="flex items-center gap-2">
            <Button asChild>
              <Link to="/dashboard">На главную</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
