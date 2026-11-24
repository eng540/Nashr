import { get, patch, post, postForm } from "./client";

export type GenericArtifactReviewStatus = "DRAFT" | "APPROVED" | "REJECTED";

export interface GenericReviewableArtifact {
  id: string;
  source_knowledge_unit_id: string;
  kind: "TEXT" | "IMAGE" | "VIDEO" | "AUDIO" | "QUIZ" | "DOCUMENT" | "ANIMATION" | "VOICE" | "VIDEO_NOTE" | "STICKER";
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

export interface ArtifactPublicationRecord { id:string; platform:string; destination:string; status:string; content:string; external_id:string|null; external_ids:string[]; error_message:string|null; published_at:string|null; created_at:string; schedules:Array<{schedule_id:string; name:string; schedule_status:string; item_status:string; scheduled_at:string; attempts:number; last_error:string|null}>; }

export interface DistributionReadiness { artifact_id:string; source_fingerprint:string; central_approval:string; original_text:string; selection_stale:boolean; targets:Array<{platform:string; label:string; selected:boolean; copy_status:string; copy_blockers:string[]; execution_blockers:string[]}>; }

export interface TelegramBatchPreview { destination:string|null;ready_count:number;blocked_count:number;caveat:string;items:Array<{artifact_id:string;title:string;kind:string;content:string;source_fingerprint:string;copy_version:number|null;ready:boolean;blockers:string[];publications:Array<{id:string;status:string;external_ids:string[]}>;schedules:Array<{name:string;schedule_status:string;item_status:string}>}>; }

export interface CopyMedia {id:string;platform:string;source_stale:boolean;mime_type:string;sha256:string;measurements:Record<string,unknown>;recipe:Record<string,unknown>;}
export interface CopyMediaList {selected_media_id:string|null;copy_version:number;source_fingerprint:string;items:CopyMedia[];caveat:string;}
export interface CentralPlatformCopy {selected_media_id?:string|null;platform:string;label:string;fields:{title:string;description:string;tags:string[];alt_text:string};version:number;source_fingerprint:string;current_source_fingerprint:string;origin:string;source_stale:boolean;central_approval:string;field_status:string;blockers:string[];warnings:string[];media_checks_pending:string[];execution_blockers:string[];sources:string[];}
export interface PlatformMediaInspection {source_fingerprint:string;copy_version:number;status:string;measurements:Record<string,unknown>;blockers:string[];pending:string[];}
export interface JpegPreview {data_url:string;source_fingerprint:string;copy_version:number;measurements:Record<string,unknown>;blockers:string[];pending:string[];sha256:string;}
export interface SavedMediaInspection {id:string;created_at:string;selected:boolean;media_id:string|null;sha256:string;copy_version:number;probe_version:string;stale:boolean;stale_reasons:string[];result:PlatformMediaInspection;caveat:string;}
export const genericArtifactsApi = {
  mediaInspections(id:string,platform:string):Promise<{items:SavedMediaInspection[]}>{return get(`/api/artifacts/${id}/platform-copies/${platform}/media-inspections`);},
  saveMediaInspection(id:string,platform:string,input:{source_fingerprint:string;copy_version:number;selected:boolean}):Promise<SavedMediaInspection>{return post(`/api/artifacts/${id}/platform-copies/${platform}/media-inspections`,input);},
  copyMedia(id:string,platform:string):Promise<CopyMediaList>{return get(`/api/artifacts/${id}/platform-copies/${platform}/media`);},
  saveCopyJpeg(id:string,platform:string,input:{source_fingerprint:string;copy_version:number;background:string;expected_sha256:string}):Promise<{copy_version:number}>{return post(`/api/artifacts/${id}/platform-copies/${platform}/media/jpeg`,input);},
  selectCopyMedia(id:string,platform:string,input:{source_fingerprint:string;copy_version:number;media_id:string|null}):Promise<{copy_version:number}>{return post(`/api/artifacts/${id}/platform-copies/${platform}/media/selection`,input);},
  copyMediaUrl(id:string,platform:string,mediaId:string):Promise<{url:string;source_stale:boolean}>{return get(`/api/artifacts/${id}/platform-copies/${platform}/media/${mediaId}/url`);},
  inspectSelectedMedia(id:string,platform:string):Promise<PlatformMediaInspection>{return post(`/api/artifacts/${id}/platform-copies/${platform}/inspect-media?selected=true`,{});},
  jpegPreview(id:string,platform:string,source_fingerprint:string,copy_version:number,background:string):Promise<JpegPreview>{return post(`/api/artifacts/${id}/platform-copies/${platform}/jpeg-preview`,{source_fingerprint,copy_version,background});},
  inspectMedia(id:string,platform:string):Promise<PlatformMediaInspection>{return post(`/api/artifacts/${id}/platform-copies/${platform}/inspect-media`,{});},
  prepareBatchCopies(ids:string[]):Promise<{prepared:number;items:Array<{artifact_id:string;items:CentralPlatformCopy[]}>}>{return post('/api/artifacts/platform-copies/prepare-batch',{artifact_ids:ids});},
  platformCopies(id:string):Promise<{items:CentralPlatformCopy[]}>{return get(`/api/artifacts/${id}/platform-copies`);},
  prepareCopies(id:string):Promise<{items:CentralPlatformCopy[]}>{return post(`/api/artifacts/${id}/platform-copies/prepare`,{});},
  updateCopy(id:string,copy:CentralPlatformCopy):Promise<CentralPlatformCopy>{return patch(`/api/artifacts/${id}/platform-copies/${copy.platform}`,{fields:copy.fields,version:copy.version,current_source_fingerprint:copy.current_source_fingerprint});},
  telegramBatchSchedule(input:{artifact_ids:string[];fingerprints:Record<string,string>;name:string;timezone:string;start_at:string;interval_minutes:number;destination:string;copy_versions:Record<string,number|null>}):Promise<{id:string;status:string;items:Array<{artifact_id:string;scheduled_at:string}>}> {return post('/api/artifacts/telegram-batch-schedule',input);},
  telegramBatchPreview(ids:string[]):Promise<TelegramBatchPreview> { return post('/api/artifacts/telegram-batch-preview',{artifact_ids:ids}); },
  readiness(id:string):Promise<DistributionReadiness> { return get(`/api/artifacts/${id}/distribution-readiness`); },
  saveDistribution(input:{artifact_ids:string[];platforms:string[];fingerprints:Record<string,string>}):Promise<{saved:number;items:DistributionReadiness[]}> { return post('/api/artifacts/distribution-selection',input); },
  publications(id:string):Promise<{items:ArtifactPublicationRecord[];total:number}> { return get(`/api/artifacts/${id}/publications`); },
  liveLocations(id: string): Promise<LiveLocationRecord[]> { return get(`/api/artifacts/${id}/live-locations`); },
  locationOperation(publicationId: string, input: {action: string; latitude?: number; longitude?: number}): Promise<LiveLocationOperation> { return post(`/api/artifacts/live-locations/${publicationId}/operations`, input); },
  cancelLocationOperation(id: string): Promise<LiveLocationOperation> { return post(`/api/artifacts/live-location-operations/${id}/cancel`); },
  executeLocationOperation(id: string): Promise<LiveLocationOperation> { return post(`/api/artifacts/live-location-operations/${id}/execute`); },
  livePhotoDraft(input: { photo_id: string; video_id: string; title: string }): Promise<GenericReviewableArtifact> { return post('/api/artifacts/live-photo-draft', input); },
  get(id: string): Promise<GenericReviewableArtifact> { return get(`/api/artifacts/${id}`); },
  albumDraft(input: { artifact_ids: string[]; title: string }): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>("/api/artifacts/album-draft", input);
  },
  manualDraft(input: { kind: string; title: string; content: string; quiz?: Record<string, unknown>; native?: Record<string, unknown> }): Promise<GenericReviewableArtifact> {
    return post<GenericReviewableArtifact>("/api/artifacts/manual-draft", input);
  },
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
  ingestReadyMedia(input: { file: File; caption?: string; media_kind?: string }): Promise<GenericReviewableArtifact> {
    const form = new FormData();
    form.append("file", input.file);
    if (input.media_kind) form.append("media_kind", input.media_kind);
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

export interface LiveLocationOperation { id: string; publication_id: string; action: string; payload: Record<string, number>; status: string; error_message: string | null; }
export interface LiveLocationRecord { publication_id: string; message_id: string; destination: string; expires_at: string; active: boolean; operations: LiveLocationOperation[]; }
