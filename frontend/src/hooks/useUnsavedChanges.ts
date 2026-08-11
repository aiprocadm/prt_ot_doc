import { useEffect } from "react";

export const DEFAULT_UNSAVED_CHANGES_MESSAGE = "Есть несохраненные изменения. Покинуть страницу?";

export function useUnsavedChanges(
  isDirty: boolean,
  message: string = DEFAULT_UNSAVED_CHANGES_MESSAGE,
): void {
  useEffect(() => {
    if (!isDirty || typeof window === "undefined") {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = message;
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty, message]);
}