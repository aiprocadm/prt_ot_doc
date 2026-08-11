import { Camera, Smartphone } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export const MobileFieldModeCard = () => {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Smartphone className="h-4 w-4" />
          Mobile field mode
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">Крупные touch targets, короткая форма и camera-first flow для работы в поле.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <Input className="h-11" placeholder="Краткий комментарий" />
          <Input className="h-11" placeholder="Локация / зона" />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button className="min-h-11 px-4">
            <Camera className="mr-2 h-4 w-4" />
            Снять evidence
          </Button>
          <Button variant="outline" className="min-h-11 px-4">Сохранить черновик</Button>
        </div>
      </CardContent>
    </Card>
  );
};
