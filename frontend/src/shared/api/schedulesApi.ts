import { get, patch, post } from "./client";
import type { EligibilityResponse, Schedule, ScheduleCreateInput } from "../types/api";\n\nexport interface ScheduleDetail extends Schedule { items: Array<{ id: string; position: number; post_id: string; title: string; status: string; scheduled_at: string; attempts: number; published_at: string | null; last_error: string | null; content_preview: string; }>; }\nexport interface ScheduleListResponse { items: Schedule[]; total: number; limit: number; offset: number; }\nexport interface UpcomingResponse { items: Array<{ id: string; schedule_id: string; schedule_name: string; post_id: string; title: string; content_preview: string; scheduled_at: string; timezone: string; position: number; status: string }>; days: number; limit: number; }\nexport interface CalendarResponse { date: string; timezone: string; items: Array<{ id: string; schedule_id: string; schedule_name: string; post_id: string; title: string; content_preview: string; scheduled_at: string; timezone: string; position: number; status: string }> }

export const schedulesApi = {
  eligibility(postIds: string[]): Promise<EligibilityResponse> {
    const query = new URLSearchParams();
    postIds.forEach((id) => query.append("post_ids", id));
    return get<EligibilityResponse>(`/schedules/eligibility?${query.toString()}`);
  },
  create(input: ScheduleCreateInput): Promise<Schedule> {
    return post<Schedule>("/schedules", input);
  },
};
