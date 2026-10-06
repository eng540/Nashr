import { get, post } from "./client";
import type { EligibilityResponse, Schedule, ScheduleCreateInput } from "../types/api";

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
