import { describe, expect, it } from "vitest";
import type { RecordItem } from "./types";
import { exportHistoryLatex, filterHistory, historyLatex } from "./historyTools";

const record = (patch: Partial<RecordItem> = {}): RecordItem => ({
  id: "a", image_path: "private/image.png", created_at: 1, updated_at: 2,
  local_raw_latex: "RAW", local_formatted_latex: "FORMATTED", local_draft_latex: "x^2",
  active_source: "local", ...patch,
});

describe("history search and export", () => {
  it("searches formulas, profile and model case-insensitively without mutating order", () => {
    const records = [record(), record({ id:"b", api_draft_latex:"NdF_3", api_profile_name:"Research Model", api_model:"Vision-V2" })];
    expect(filterHistory(records, "  research  ndf ").map(item => item.id)).toEqual(["b"]);
    expect(filterHistory(records, "VISION-v2").map(item => item.id)).toEqual(["b"]);
    expect(filterHistory(records, "missing")).toEqual([]);
    expect(filterHistory(records, "  ")).toEqual(records);
    expect(records.map(item => item.id)).toEqual(["a", "b"]);
  });
  it("exports each record's active source, not whichever branch happens to be non-empty", () => {
    const records = [record(), record({ id:"b", active_source:"api", api_draft_latex:"y^3", api_profile_name:"Vision" })];
    const output = exportHistoryLatex(records);
    expect(output).toContain("Local\nx^2");
    expect(output).toContain("API (Vision)\ny^3");
    expect(output).not.toContain("private/image.png");
    expect(output).not.toContain("RAW");
  });
  it("keeps intentionally empty drafts and falls back only for missing legacy fields", () => {
    expect(historyLatex(record({ local_draft_latex:"" }))).toBe("");
    expect(historyLatex(record({ active_source:"api", api_draft_latex:"", api_raw_latex:"old" }))).toBe("");
    expect(historyLatex(record({ active_source:"api", api_draft_latex:null, api_formatted_latex:"fallback" }))).toBe("fallback");
    expect(exportHistoryLatex([record({ local_draft_latex:"" })])).toBe("% FormulaOCR · a · Local\n\n");
  });
  it("respects explicit selection, deduplicates IDs and keeps display order", () => {
    const records = [record(), record({ id:"b", local_draft_latex:"b" })];
    expect(exportHistoryLatex(records, [])).toBe("");
    expect(exportHistoryLatex(records, ["missing"])).toBe("");
    expect(exportHistoryLatex(records, ["b", "a", "b"])).toBe(exportHistoryLatex(records));
    expect(exportHistoryLatex(records, ["b"])).not.toContain("· a ·");
  });
  it("keeps metadata on comment lines and preserves formula text verbatim", () => {
    const formula = "\\frac{a}{b}\n+ c";
    const output = exportHistoryLatex([record({ id:"id\n\\input{bad}", active_source:"api", api_profile_name:"name\r\n\\input{bad}", api_draft_latex:formula })]);
    expect(output.split("\n")[0]).toContain("% FormulaOCR · id \\input{bad}");
    expect(output).toContain("name  \\input{bad}");
    expect(output.endsWith(formula + "\n")).toBe(true);
  });
});
