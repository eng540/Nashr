import { describe, expect, it } from "vitest";
import { localDateTimeToUtcISOString, utcISOStringToLocalDateTime } from "./timezone";

describe("schedule timezone conversion", () => {
  it("preserves an Asia/Aden wall-clock start time through UTC storage and display", () => {
    const utc = localDateTimeToUtcISOString("2026-10-08T20:00", "Asia/Aden");
    expect(utc).toBe("2026-10-08T17:00:00.000Z");
    expect(utcISOStringToLocalDateTime(utc, "Asia/Aden")).toBe("2026-10-08T20:00");
  });

  it("does not silently display stored UTC as the user's browser timezone", () => {
    expect(utcISOStringToLocalDateTime("2026-10-08T17:00:00.000Z", "Asia/Aden")).toBe("2026-10-08T20:00");
  });
});
