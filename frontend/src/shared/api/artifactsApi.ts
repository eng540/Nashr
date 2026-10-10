import { get, patch, post } from "./client";

export type GenericArtifactReviewStatus = "DRAFT" | "APPROVED" | "REJECTED";

export interface GenericReviewableArtifact {
  id: string;
  source_knowledge_unit_id: string;
  kind: "TEXT" | "IMAGE" | "VIDEO" | "AUDIO";
  status: string;
  content: string | null;
  storage_uri: string | null;
  mime_type: string | null;
  output_contract_key: string | null;
  output_contract_version: number | null;
  metadata: Record<string, unknown>;
  review_status: GenericArtifactReviewStatus;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export const genericArtifactsApi = {
  list(status: GenericArtifactReviewStatus = "DRAFT"): Promise<GenericReviewableArtifact[]> {
    return get<GenericReviewableArtifact[]>(`/api/artifacts?review_status=${status}`);
  },
  mediaUrl(id: string): Promise<{ url: string; expires_in: number }> {
    return get<{ url: string; expires_in: number }>(`/api/artifacts/${id}/media-url`);
  },
  update(id: string, input: { content?: string; metadata?: Record<string, unknown> }): Promise<GenericReviewableArtifact> {
    return patch<GenericReviewableArtifact>(`/api/artifacts/${id}`, input);
  },
  approve(id: string, review_note?: string): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>(`/api/artifacts/${id}/approve`, { review_note });
  },
  reject(id: string, review_note: string): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>(`/api/artifacts/${id}/reject`, { review_note });
  },
};
