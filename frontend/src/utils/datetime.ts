import { format, parseISO } from "date-fns";

export const formatDate = (value?: string | Date | null, fallback = "—") => {
  if (!value) return fallback;
  try {
    const date = value instanceof Date ? value : parseISO(value);
    return format(date, "dd.MM.yyyy HH:mm");
  } catch (error) {
    console.error("formatDate", error);
    return fallback;
  }
};
