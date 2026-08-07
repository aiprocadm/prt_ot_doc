import { Component, type ErrorInfo, type ReactNode } from "react";

interface SectionErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface SectionErrorBoundaryState {
  hasError: boolean;
}

export class SectionErrorBoundary extends Component<
  SectionErrorBoundaryProps,
  SectionErrorBoundaryState
> {
  state: SectionErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("Section render failure", error, errorInfo);
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-50">
            <p className="font-medium">
              Не удалось показать этот фрагмент интерфейса
            </p>
            <p className="mt-1 text-xs opacity-90">
              Нажмите «Повторить» или перейдите в другой раздел и вернитесь.
            </p>
            <button
              type="button"
              className="mt-3 text-sm font-semibold text-amber-900 underline underline-offset-4 hover:no-underline dark:text-amber-100"
              onClick={this.handleRetry}
            >
              Повторить
            </button>
          </div>
        )
      );
    }

    return this.props.children;
  }
}
