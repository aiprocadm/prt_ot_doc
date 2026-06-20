import type { WorkPermitEventDto } from "@/types/dto/workPermits";
import { EVENT_TYPE_LABELS, labelOf } from "@/lib/workPermitVocab";

export const WorkPermitEventsTimeline = ({ events }: { events: WorkPermitEventDto[] }) => {
  if (events.length === 0)
    return <p className="text-sm text-muted-foreground">Событий нет</p>;
  return (
    <ul className="space-y-1 text-sm">
      {events.map((e) => (
        <li key={e.id} className="flex gap-3">
          <span className="w-36 shrink-0 text-muted-foreground">
            {new Date(e.at).toLocaleString("ru-RU")}
          </span>
          <span>{labelOf(EVENT_TYPE_LABELS, e.event_type)}</span>
          {e.note ? <span className="text-muted-foreground">— {e.note}</span> : null}
        </li>
      ))}
    </ul>
  );
};
