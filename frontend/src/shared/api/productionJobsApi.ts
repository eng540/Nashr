import { get, post } from "./client";

export type ProductionScope = "SOURCE" | "TOPIC" | "SELECTION";
export interface SourceSummary { id: string; filename: string; book_title: string; status: string; material_count: number; produced_count: number; pending_count: number; }
export interface BookTopic { id: string; position: number; title: string; description: string; materials: Array<{ id: string; title: string; kind: string | null; content: string; has_post: boolean; }>; }
export interface BookMap { source_id: string; book: { title: string; description: string }; topics: BookTopic[]; count: number; }
export interface ProductionJob { job_id: string; source_id: string; status: string; scope: ProductionScope; total_items: number; completed_items: number; failed_items: number; pending_items: number; current_item_id: string | null; error_message: string | null; }
export const productionJobsApi = {
  sources(): Promise<SourceSummary[]> { return get<SourceSummary[]>("/sources"); },
  bookMap(sourceId: string): Promise<BookMap> { return get<BookMap>(`/sources/${sourceId}/book-map`); },
  create(input: { source_id: string; scope: ProductionScope; topic_id?: string; knowledge_unit_ids?: string[] }): Promise<ProductionJob> { return post<ProductionJob>("/production-jobs", input); },
  get(jobId: string): Promise<ProductionJob> { return get<ProductionJob>(`/production-jobs/${jobId}`); },
  resume(jobId: string): Promise<ProductionJob> { return post<ProductionJob>(`/production-jobs/${jobId}/resume`, { retry_failed: true }); },
};
