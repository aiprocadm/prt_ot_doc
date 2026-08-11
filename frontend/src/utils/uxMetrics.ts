import { localStorageGetItem, localStorageSetItem } from "@/utils/browserStorage";
import { sendUxMetric } from "@/api/navigation";

const UX_METRICS_STORAGE_KEY = "ux.metrics.events.v1";
const MAX_EVENTS = 200;

export type UxMetricEvent = {
  name: "time_to_first_action" | "nav_backtrack_rate" | "empty_state_to_action_rate" | "navigation_click" | "route_view";
  ts: number;
  payload?: Record<string, string | number | boolean | null | undefined>;
};

const readEvents = (): UxMetricEvent[] => {
  const raw = localStorageGetItem(UX_METRICS_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as UxMetricEvent[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeEvents = (events: UxMetricEvent[]) => {
  localStorageSetItem(UX_METRICS_STORAGE_KEY, JSON.stringify(events.slice(-MAX_EVENTS)));
};

export const trackUxMetric = (
  name: UxMetricEvent["name"],
  payload?: UxMetricEvent["payload"]
) => {
  const events = readEvents();
  events.push({ name, ts: Date.now(), payload });
  writeEvents(events);
  void sendUxMetric(name, payload);
};
