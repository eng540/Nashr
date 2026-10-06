import { get, patch, post } from "./client";
import type { Post, PostListResponse } from "../types/api";

export interface PostListParams {
  sourceId?: string;
  status?: string;
  publicationState?: string;
  query?: string;
  limit?: number;
  offset?: number;
}

export const postsApi = {
  list(params: PostListParams = {}): Promise<PostListResponse> {
    const query = new URLSearchParams();
    if (params.sourceId) query.set("source_id", params.sourceId);
    if (params.status) query.set("status", params.status);
    if (params.publicationState) query.set("publication_state", params.publicationState);
    if (params.query) query.set("q", params.query);
    query.set("limit", String(params.limit ?? 500));
    query.set("offset", String(params.offset ?? 0));
    return get<PostListResponse>(`/posts?${query.toString()}`);
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
};
