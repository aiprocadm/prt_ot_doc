import type { WorkPermitEventDto } from "@/types/dto/workPermits";
import { EVENT_TYPE_LABELS, MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";

const fmt = (d: string | null | undefined): string =>
  d ? new Date(d).toLocaleString("ru-RU") : "—";

function metaText(
  e: WorkPermitEventDto,
  nameOf: (id: string) => string,
): string | null {
  const m = e.meta;
  if (!m) return null;
  if (e.event_type === "extended" && (m.old_end || m.new_end)) {
    return `с ${fmt(m.old_end)} до ${fmt(m.new_end)}`;
  }
  if ((e.event_type === "member_added" || e.event_type === "member_removed") && m.person_id) {
    const role = m.role ? ` (${labelOf(MEMBER_ROLE_LABELS, m.role)})` : "";
    return `${nameOf(m.person_id)}${role}`;
  }
  return null;
}

interface Props {
  events: WorkPermitEventDto[];
  nameOf?: (id: string) => string;
}

export const WorkPermitEventsTimeline = ({ events, nameOf }: Props) => {
  if (events.length === 0)
    return <p className="text-sm text-muted-foreground">Событий нет</p>;
  const resolve = nameOf ?? ((id: string) => id);
  return (
    <ul className="space-y-1 text-sm">
      {events.map((e) => {
        const detail = e.note ?? metaText(e, resolve);
        return (
          <li key={e.id} className="flex gap-3">
            <span className="w-36 shrink-0 text-muted-foreground">
              {new Date(e.at).toLocaleString("ru-RU")}
            </span>
            <span>{labelOf(EVENT_TYPE_LABELS, e.event_type)}</span>
            {detail ? <span className="text-muted-foreground">— {detail}</span> : null}
          </li>
        );
      })}
    </ul>
  );
};
