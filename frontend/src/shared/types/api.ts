export type PostStatus = "DRAFT" | "APPROVED" | "REJECTED" | string;

export interface Post {
  post_id: string;
  title: string;
  status: PostStatus;
  knowledge_unit_id: string;
  topic_id: string | null;
  topic_title: string | null;
  source_id: string;
  source_title: string;
  content: string;
  content_preview: string;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
  review_note: string | null;
  published: boolean;
}

export interface PostListResponse {
  items: Post[];
  total: number;
  limit: number;
  offset: number;
}

export interface EligibilityRow {
  post_id: string;
  eligible?: boolean;
  reason_code?: string;
  message?: string;
}

export interface EligibilityResponse {
  eligible?: EligibilityRow[];
  blocked: EligibilityRow[];
}

export interface Schedule {
  id: string;
  name: string;
  status: string;
  timezone: string;
  total_items: number;
  pending_items: number;
  published_items: number;
  failed_items: number;
  next_scheduled_at: string | null;
}

export interface ScheduleCreateInput {
  name: string;
  timezone: string;
  post_ids: string[];
  start_at: string;
  interval_minutes: number;
  idempotency_key: string;
}
