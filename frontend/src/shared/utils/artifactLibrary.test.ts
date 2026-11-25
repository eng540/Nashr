import { describe, expect, it } from "vitest";
import { artifactSearchText, artifactSeriesKey, isSelectableOriginal } from "./artifactLibrary";
import type { GenericReviewableArtifact } from "../api/artifactsApi";

const sample = (name: string): GenericReviewableArtifact => ({ id: "fixed-id", kind: "VIDEO", content: null,
  metadata: { original_filename: name, title: "عنوان", video_library: {
    source_original: "الأصل الكامل طويل", tiktok_text: "وصف تيك توك", telegram_caption: "تعليق تيليجرام" } },
} as unknown as GenericReviewableArtifact);

describe("artifact library indexing", () => {
  it("indexes full originals and both platform copies without changing them", () => {
    const item = sample("9-b3v4-ehkaam.mp4");
    const before = JSON.stringify(item);
    for (const text of ["الأصل الكامل", "تيك توك", "تيليجرام", "عنوان", "fixed-id", "b3v4", "وش معنى"])
      expect(artifactSearchText(item)).toContain(text);
    expect(JSON.stringify(item)).toBe(before);
  });
  it("groups all named video series, including upload prefixes", () => {
    expect(artifactSeriesKey(sample("9-b3v4-ehkaam.mp4"))).toBe("وش معنى");
    expect(artifactSeriesKey(sample("20-womdha-9-final.mp4"))).toBe("ومضة");
    expect(artifactSeriesKey(sample("112-v4-hisab.mp4"))).toBe("فيديو تعريفي");
    expect(artifactSeriesKey(sample("other.mp4"))).toBe("غير مصنف");
  });
});

it("explicit catalog labels override inferred series and remain searchable",()=>{
 const item=sample("9-b3v4-ehkaam.mp4");item.organization={title:"عنوان فهرسة",series:"سلسلة صريحة",category:"تصنيف معين",version:1,updated_at:"2026-11-24"};
 expect(artifactSeriesKey(item)).toBe("سلسلة صريحة");
 expect(artifactSearchText(item)).toContain("تصنيف معين");
 expect(artifactSearchText(item)).toContain("عنوان فهرسة");
});

it("selection includes originals needing media repair but excludes unavailable or derived records",()=>{
 const item={...sample("missing.mp4"),review_status:"APPROVED",status:"AVAILABLE",storage_uri:null} as GenericReviewableArtifact;
 expect(isSelectableOriginal(item)).toBe(true);
 expect(isSelectableOriginal({...item,status:"DELETED"})).toBe(false);
 expect(isSelectableOriginal({...item,review_status:"DRAFT"})).toBe(false);
 expect(isSelectableOriginal({...item,metadata:{source_type:"PLATFORM_VARIANT"}})).toBe(false);
 expect(isSelectableOriginal({...item,kind:"POST"} as unknown as GenericReviewableArtifact)).toBe(false);
});
