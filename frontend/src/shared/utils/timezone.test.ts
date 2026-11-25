import { describe, expect, it } from "vitest";
import { localDateTimeToUtcISOString, utcISOStringToLocalDateTime, dateInTimezone, scheduleTimePreview } from "./timezone";

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


describe("wall clock validation", () => {
  it("rejects normalized invalid dates and malformed input", () => {
    for (const value of ["2026-02-30T12:00", "2026-13-01T10:00", "2026-01-01T24:10", "", "2026-01-01"]) {
      expect(() => localDateTimeToUtcISOString(value, "Asia/Riyadh")).toThrow();
    }
  });
  it("rejects DST gaps and repeated hours, including half-hour transitions", () => {
    expect(() => localDateTimeToUtcISOString("2026-03-08T02:30", "America/New_York")).toThrow();
    expect(() => localDateTimeToUtcISOString("2026-11-01T01:30", "America/New_York")).toThrow();
    expect(() => localDateTimeToUtcISOString("2026-04-05T01:45", "Australia/Lord_Howe")).toThrow();
    expect(localDateTimeToUtcISOString("2026-11-01T03:30", "America/New_York")).toBe("2026-11-01T08:30:00.000Z");
  });
  it("uses the displayed timezone day rather than UTC or the browser day", () => {
    expect(dateInTimezone("Asia/Aden", new Date("2026-11-24T22:15:00Z"))).toBe("2026-11-25");
    expect(dateInTimezone("America/Los_Angeles", new Date("2026-11-25T02:15:00Z"))).toBe("2026-11-24");
  });
});


it("previews elapsed intervals across both DST transitions",()=>{
  expect(scheduleTimePreview("2026-03-08T01:30","America/New_York",30,3)).toEqual(["2026-03-08T06:30:00.000Z","2026-03-08T07:00:00.000Z","2026-03-08T07:30:00.000Z"]);
  expect(scheduleTimePreview("2026-11-01T00:30","America/New_York",60,3)).toEqual(["2026-11-01T04:30:00.000Z","2026-11-01T05:30:00.000Z","2026-11-01T06:30:00.000Z"]);
  expect(()=>scheduleTimePreview("2026-11-25T10:00","Asia/Riyadh",1.5,2)).toThrow();
});
