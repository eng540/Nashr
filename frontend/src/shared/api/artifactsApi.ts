import { get, patch, post, postForm } from "./client";

export type GenericArtifactReviewStatus = "DRAFT" | "APPROVED" | "REJECTED";

export interface GenericReviewableArtifact {
  id: string;
  source_knowledge_unit_id: string;
  kind: "TEXT" | "IMAGE" | "VIDEO" | "AUDIO" | "QUIZ";
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

export interface PlatformVariantConstraints {
  max_text: number | null;
  measure: string | null;
  measured_length: number | null;
  original_length: number | null;
  trimmed: boolean | null;
  trim_boundary: string | null;
  provenance: string | null;
}

export interface ManualPublicationRecord {
  published_at: string;
  external_url: string | null;
  recorded_at: string;
}

export interface PlatformVariantDraft {
  id: string;
  kind: string | null;
  mime_type: string | null;
  content: string;
  platform: string | null;
  platform_label_ar: string | null;
  review_status: GenericArtifactReviewStatus | null;
  excerpt: string;
  full_length: number;
  adaptation: string | null;
  needs_review: boolean;
  source_kind_ar: string | null;
  source_artifact_id: string | null;
  source_post_id: string | null;
  constraints: PlatformVariantConstraints;
  manual_publication: ManualPublicationRecord | null;
  created_at: string | null;
}

export interface GenericArtifactPage {
  items: GenericReviewableArtifact[];
  total: number;
  limit: number;
  offset: number;
}

export const genericArtifactsApi = {
  async list(status: GenericArtifactReviewStatus = "DRAFT", offset = 0, limit = 100): Promise<GenericArtifactPage> {
    const data = await get<GenericArtifactPage | GenericReviewableArtifact[]>(`/api/artifacts?review_status=${status}&limit=${limit}&offset=${offset}`);
    if (Array.isArray(data)) return { items: data, total: data.length, limit, offset };
    return data;
  },
  async listAll(status: GenericArtifactReviewStatus = "DRAFT"): Promise<GenericArtifactPage> {
    const first = await genericArtifactsApi.list(status, 0, 100);
    if (first.items.length >= first.total) return first;
    const rest = await Promise.all(
      Array.from({ length: Math.ceil((first.total - first.items.length) / 100) }, (_, index) => genericArtifactsApi.list(status, (index + 1) * 100, 100)),
    );
    const items = [...first.items, ...rest.flatMap((page) => page.items)];
    return { ...first, items, total: Math.max(first.total, items.length) };
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
  createQuizDraft(id: string): Promise<{ id: string; artifact_id: string | null; status: string; content: string }> {
    return post<{ id: string; artifact_id: string | null; status: string; content: string }>(`/api/artifacts/${id}/telegram-draft`, {});
  },
  ingestReadyMedia(input: { file: File; caption?: string }): Promise<GenericReviewableArtifact> {
    const form = new FormData();
    form.append("file", input.file);
    if (input.caption?.trim()) form.append("caption", input.caption.trim());
    return postForm<GenericReviewableArtifact>("/api/artifacts/ingest-media", form);
  },
  listPlatformVariants(): Promise<PlatformVariantDraft[]> {
    return get<PlatformVariantDraft[]>("/api/artifacts/platform-variants");
  },
  recordManualPublication(id: string, input: { published_at: string; external_url?: string | null }): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>(`/api/artifacts/${id}/manual-publication`, input);
  },
  derivePlatformVariant(id: string, platform: string): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>(`/api/artifacts/${id}/platform-variant`, { platform });
  },
  derivePlatformVariantFromPost(postId: string, platform: string): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>(`/api/artifacts/post-source/${postId}/platform-variant`, { platform });
  },
  createTelegramMediaDraft(id: string): Promise<{ id: string; status: string; external_id?: string | null }> {
    return post<{ id: string; status: string; external_id?: string | null }>(`/api/artifacts/${id}/telegram-media-draft`);
  },
  scheduleArtifact(id: string, input: { name: string; timezone: string; scheduled_at: string }): Promise<{ id: string; name: string; status: string; timezone: string; items: Array<{ id: string; artifact_id: string | null; post_id: string | null; scheduled_at: string; status: string }> }> {
    return post(`/api/artifacts/${id}/schedule`, input);
  },
  publishQuiz(publicationId: string, content: string): Promise<{ id: string; status: string; external_id: string | null; error_message: string | null }> {
    return post<{ id: string; status: string; external_id: string | null; error_message: string | null }>(`/publications/${publicationId}/publish`, { content });
  },
};
