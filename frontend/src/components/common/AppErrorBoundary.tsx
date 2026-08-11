import type { ReactNode } from "react";
import { Component } from "react";

import { Button } from "@/components/ui/button";

interface AppErrorBoundaryState {
  hasError: boolean;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center text-foreground">
          <h1 className="text-2xl font-semibold">Что-то пошло не так</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            Произошла непредвиденная ошибка интерфейса. Обновите страницу или попробуйте позже.
          </p>
          <Button onClick={() => window.location.reload()}>Обновить страницу</Button>
        </div>
      );
    }

    return this.props.children;
  }
}
