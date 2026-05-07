import { apiClient } from "@/api/client";
import type {
  CalendarEventsQuery,
  CalendarEventsResponseDto
} from "@/types/dto/calendar";

export const calendarApi = {
  async getEvents(query: CalendarEventsQuery = {}): Promise<CalendarEventsResponseDto> {
    const params: Record<string, unknown> = {};
    if (query.from_at) params.from_at = query.from_at;
    if (query.to_at) params.to_at = query.to_at;
    if (query.source_types && query.source_types.length > 0) {
      params.source_types = query.source_types;
    }
    if (query.person_id) params.person_id = query.person_id;
    if (query.site_id) params.site_id = query.site_id;
    const { data } = await apiClient.get<CalendarEventsResponseDto>(
      "/calendar/events",
      {
        params,
        paramsSerializer: {
          indexes: null
        }
      }
    );
    return data;
  }
};
