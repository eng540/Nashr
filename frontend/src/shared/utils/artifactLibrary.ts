import type { GenericReviewableArtifact } from "../api/artifactsApi";

export function artifactSeriesKey(artifact: GenericReviewableArtifact): string {
  if(artifact.organization?.series)return artifact.organization.series;
  const name = String(artifact.metadata.original_filename ?? "").replace(/^\d+-/, "");
  if (/^b\d+v\d+/.test(name)) return "وش معنى";
  if (/^womdha-\d+/.test(name)) return "ومضة";
  if (/^v\d+-/.test(name)) return "فيديو تعريفي";
  return typeof artifact.metadata.series === "string" ? artifact.metadata.series : "غير مصنف";
}

export function artifactSearchText(artifact: GenericReviewableArtifact): string {
  const video = artifact.metadata.video_library;
  const library = video && typeof video === "object" && !Array.isArray(video) ? video as Record<string, unknown> : {};
  return [artifact.id, artifact.organization?.title,artifact.organization?.category,artifact.organization?.series, artifact.content, artifact.metadata.title, artifact.metadata.caption,
    artifact.metadata.full_caption, artifact.metadata.description, artifact.metadata.original_filename,
    artifactSeriesKey(artifact), library.source_original, library.tiktok_text, library.telegram_caption]
    .filter((value): value is string => typeof value === "string").join(" ").toLowerCase();
}
