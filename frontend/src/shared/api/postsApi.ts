import { get, patch, post } from "./client";
import type { Post, PostListResponse } from "../types/api";

export interface PostListParams {
  sourceId?: string;
  topicId?: string;
  status?: string;
  kind?: string;
  publicationState?: string;
  query?: string;
  sort?: "created" | "title" | "kind" | "topic";
  limit?: number;
  offset?: number;
}

export interface BulkApproveResult {
  approved_count: number;
  failed_count: number;
  results: Array<{
    post_id: string;
    status: string;
    reason_code?: string | null;
    message?: string | null;
  }>;
}

export interface PostFilterOptions {
  kinds: string[];
  topics: Array<{ id: string; title: string; position: number }>;
}

export const postsApi = {
  list(params: PostListParams = {}): Promise<PostListResponse> {
    const query = new URLSearchParams();
    if (params.sourceId) query.set("source_id", params.sourceId);
    if (params.topicId) query.set("topic_id", params.topicId);
    if (params.status) query.set("status", params.status);
    if (params.kind) query.set("kind", params.kind);
    if (params.publicationState) query.set("publication_state", params.publicationState);
    if (params.query) query.set("q", params.query);
    if (params.sort) query.set("sort", params.sort);
    query.set("limit", String(params.limit ?? 30));
    query.set("offset", String(params.offset ?? 0));
    return get<PostListResponse>(`/posts?${query.toString()}`);
  },
  filterOptions(sourceId?: string): Promise<PostFilterOptions> {
    const query = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : "";
    return get<PostFilterOptions>(`/posts/filter-options${query}`);
  },
  get(postId: string): Promise<Post> {
    return get<Post>(`/posts/${postId}`);
  },
  update(postId: string, content: string): Promise<Post> {
    return patch<Post>(`/posts/${postId}`, { content });
  },
  approve(postId: string, note: string): Promise<Post> {
    return post<Post>(`/posts/${postId}/approve`, { note: note || undefined });
  },
  reject(postId: string, reason: string): Promise<Post> {
    return post<Post>(`/posts/${postId}/reject`, { reason });
  },
  bulkApprove(postIds: string[], note = ""): Promise<BulkApproveResult> {
    return post<BulkApproveResult>("/posts/bulk-approve", {
      post_ids: postIds,
      note: note || undefined,
    });
  },
};
