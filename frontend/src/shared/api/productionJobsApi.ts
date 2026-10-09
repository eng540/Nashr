import { get, post } from "./client";

export type ProductionScope = "SOURCE" | "TOPIC" | "SELECTION";
export interface SourceSummary { id: string; filename: string; book_title: string; status: string; material_count: number; produced_count: number; pending_count: number; }
export interface BookTopic { id: string; position: number; title: string; description: string; materials: Array<{ id: string; title: string; kind: string | null; content: string; has_post: boolean; }>; }
export interface BookMap { source_id: string; book: { title: string; description: string }; topics: BookTopic[]; count: number; }
export interface ProductionJob {
  job_id: string; source_id: string; status: string; scope: ProductionScope;
  total_items: number; completed_items: number; failed_items: number; pending_items: number;
  current_item_id: string | null; error_code: string | null; error_message: string | null;
  attempts: number; created_at: string; updated_at: string; started_at: string | null; completed_at: string | null;
  progress_percent: number; next_action: "RETRY_FAILED_ITEMS" | "INSPECT_FAILURE" | "WAIT" | "REVIEW_DRAFTS" | "NONE";
  resolved_prompt: { key: string | null; version: number | null; body: string | null; available: boolean };
  resolved_context: {
    available: boolean; invalid: boolean; schema_version: number | null; origin: string | null;
    captured_at: string | null;
    prompt_template: { template_id: string; version_id: string; key: string; version: number; body: string } | null;
    recipe?: { key: string; version: number; stages: Array<{ key: string; capability_key: string; capability_version: number }> } | null;
  };
}
export interface ProductionJobItem {
  item_id: string; position: number; status: string; attempts: number;
  knowledge_unit_id: string; title: string; source_id: string; source_title: string;
  source_reference: string | null; page_start: number | null; page_end: number | null;
  post_id: string | null; error_code: string | null; error_message: string | null;
  created_at: string; updated_at: string; completed_at: string | null;
}
export interface ProductionJobItemsPage { job_id: string; total: number; limit: number; offset: number; items: ProductionJobItem[]; }
export const productionJobsApi = {
  sources(): Promise<SourceSummary[]> { return get<SourceSummary[]>("/sources"); },
  bookMap(sourceId: string): Promise<BookMap> { return get<BookMap>(`/sources/${sourceId}/book-map`); },
  create(input: { source_id: string; scope: ProductionScope; topic_id?: string; knowledge_unit_ids?: string[] }): Promise<ProductionJob> { return post<ProductionJob>("/production-jobs", input); },
  get(jobId: string): Promise<ProductionJob> { return get<ProductionJob>(`/production-jobs/${jobId}`); },
  items(jobId: string, offset = 0, limit = 20): Promise<ProductionJobItemsPage> {
    return get<ProductionJobItemsPage>(`/production-jobs/${jobId}/items?offset=${offset}&limit=${limit}`);
  },
  resume(jobId: string): Promise<ProductionJob> { return post<ProductionJob>(`/production-jobs/${jobId}/resume`, { retry_failed: true }); },
};
