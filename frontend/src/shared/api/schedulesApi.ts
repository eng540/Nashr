import { get, patch, post } from "./client";
import type { EligibilityResponse, Schedule, ScheduleCreateInput } from "../types/api";

export interface ScheduleDetail extends Schedule {
  items: Array<{
    id: string;
    position: number;
    post_id: string;
    title: string;
    status: string;
    scheduled_at: string;
    attempts: number;
    published_at: string | null;
    last_error: string | null;
    content_preview: string;
  }>;
}

export interface ScheduleListResponse {
  items: Schedule[];
  total: number;
  limit: number;
  offset: number;
}

export interface UpcomingResponse {
  items: Array<{
    id: string;
    schedule_id: string;
    schedule_name: string;
    post_id: string;
    title: string;
    content_preview: string;
    scheduled_at: string;
    timezone: string;
    position: number;
    status: string;
  }>;
  days: number;
  limit: number;
}

export interface CalendarResponse {
  date: string;
  timezone: string;
  items: Array<{
    id: string;
    schedule_id: string;
    schedule_name: string;
    post_id: string;
    title: string;
    content_preview: string;
    scheduled_at: string;
    timezone: string;
    position: number;
    status: string;
  }>;
}

export const schedulesApi = {
  eligibility(postIds: string[]): Promise<EligibilityResponse> {
    const query = new URLSearchParams();
    postIds.forEach((id) => query.append("post_ids", id));
    return get<EligibilityResponse>(`/schedules/eligibility?${query.toString()}`);
  },
  create(input: ScheduleCreateInput): Promise<Schedule> {
    return post<Schedule>("/schedules", input);
  },
  list(): Promise<ScheduleListResponse> {
    return get<ScheduleListResponse>("/schedules?limit=50&offset=0");
  },
  get(scheduleId: string): Promise<ScheduleDetail> {
    return get<ScheduleDetail>(`/schedules/${scheduleId}`);
  },
  validation(scheduleId: string): Promise<{ valid: boolean; errors: string[]; warnings?: string[] }> {
    return get(`/schedules/${scheduleId}/validation`);
  },
  activate(scheduleId: string): Promise<ScheduleDetail> {
    return post<ScheduleDetail>(`/schedules/${scheduleId}/activate`, {});
  },
  pause(scheduleId: string): Promise<ScheduleDetail> {
    return post<ScheduleDetail>(`/schedules/${scheduleId}/pause`, {});
  },
  cancel(scheduleId: string): Promise<ScheduleDetail> {
    return post<ScheduleDetail>(`/schedules/${scheduleId}/cancel`, {});
  },
  retryFailed(scheduleId: string): Promise<{ retried_items: number; schedule: ScheduleDetail }> {
    return post(`/schedules/${scheduleId}/retry-failed`, {});
  },
  retryItem(scheduleId: string, itemId: string): Promise<{ retried_item_id: string; schedule: ScheduleDetail }> {
    return post(`/schedules/${scheduleId}/items/${itemId}/retry`, {});
  },
  updateItemTime(scheduleId: string, itemId: string, scheduledAt: string): Promise<ScheduleDetail> {
    return patch<ScheduleDetail>(`/schedules/${scheduleId}/items/${itemId}`, {
      scheduled_at: scheduledAt,
    });
  },
  upcoming(): Promise<UpcomingResponse> {
    return get<UpcomingResponse>("/schedules/upcoming?days=7&limit=100");
  },
  calendar(date: string, timezone: string): Promise<CalendarResponse> {
    const query = new URLSearchParams({ date, timezone });
    return get<CalendarResponse>(`/schedules/calendar?${query.toString()}`);
  },
  telegramPreview(postId: string): Promise<{
    post_id: string;
    platform: string;
    destination: string;
    content: string;
    status: string;
    ready: boolean;
  }> {
    return get(`/posts/${postId}/telegram-preview`);
  },
};
