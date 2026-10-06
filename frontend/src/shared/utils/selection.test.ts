import { describe, expect, it } from "vitest";
import { selectionFromQuery, toggleSelection } from "./selection";

describe("selection contract", () => {
  it("adds and removes one selection without duplicates", () => {
    expect(toggleSelection([], "a", true)).toEqual(["a"]);
    expect(toggleSelection(["a"], "a", true)).toEqual(["a"]);
    expect(toggleSelection(["a"], "a", false)).toEqual([]);
  });

  it("hydrates ids from URL state", () => {
    expect(selectionFromQuery("a,b,a, ,c")).toEqual(["a", "b", "c"]);
  });
});
