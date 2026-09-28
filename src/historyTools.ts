import type { RecordItem } from "./types";

/** Missing legacy drafts may fall back; an intentionally empty draft may not. */
export function historyLatex(record: RecordItem): string {
  return record.active_source === "api"
    ? record.api_draft_latex ?? record.api_formatted_latex ?? record.api_raw_latex ?? ""
    : record.local_draft_latex ?? record.local_formatted_latex ?? record.local_raw_latex ?? "";
}

export function filterHistory(records: readonly RecordItem[], query: string): RecordItem[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [...records];
  return records.filter((record) => {
    const text = [
      record.local_draft_latex, record.local_formatted_latex, record.local_raw_latex,
      record.api_draft_latex, record.api_formatted_latex, record.api_raw_latex,
      record.api_profile_name, record.api_model,
    ].filter((value) => value != null).join("\n").toLowerCase();
    return terms.every((term) => text.includes(term));
  });
}

/** Plain UTF-8 LaTeX snippets; metadata is comment-only, never executable markup. */
export function exportHistoryLatex(records: readonly RecordItem[], selectedIds?: readonly string[]): string {
  const selected = selectedIds === undefined ? null : new Set(selectedIds);
  const comment = (value: string) => value.replace(/[\u0000-\u001f\u007f]/g, " ");
  const blocks = records.filter((record) => !selected || selected.has(record.id)).map((record) => {
    const source = record.active_source === "api" ? "API" : "Local";
    const profile = source === "API" && record.api_profile_name ? ` (${comment(record.api_profile_name)})` : "";
    return `% FormulaOCR · ${comment(record.id)} · ${source}${profile}\n${historyLatex(record)}`;
  });
  return blocks.length ? blocks.join("\n\n") + "\n" : "";
}
