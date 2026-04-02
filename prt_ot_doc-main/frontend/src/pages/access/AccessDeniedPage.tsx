import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const AccessDeniedPage = () => (
  <div className="flex min-h-[60vh] items-center justify-center">
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle className="text-xl font-semibold">Доступ ограничен</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        <p>У вас нет прав для просмотра этого раздела. Обратитесь к администратору для получения доступа.</p>
        <div className="flex items-center gap-2">
          <Button asChild>
            <Link to="/dashboard">На главную</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
);
