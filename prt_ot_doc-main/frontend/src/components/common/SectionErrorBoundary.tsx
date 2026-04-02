import { Component, type ErrorInfo, type ReactNode } from "react";

interface SectionErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface SectionErrorBoundaryState {
  hasError: boolean;
}

export class SectionErrorBoundary extends Component<SectionErrorBoundaryProps, SectionErrorBoundaryState> {
  state: SectionErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("Section render failure", error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
            Часть интерфейса временно недоступна. Обновите страницу или попробуйте позже.
          </div>
        )
      );
    }

    return this.props.children;
  }
}