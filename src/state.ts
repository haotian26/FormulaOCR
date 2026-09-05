import type { Layout, Source } from "./types";

export const DEFAULT_LAYOUT: Layout = { image: 42, result: 50, drawerWidth: 320 };
export function readLayout(raw: string | null): Layout {
  try {
    const value = JSON.parse(raw || "{}");
    const clamp = (key: keyof Layout, min: number, max: number) =>
      typeof value[key] === "number" && Number.isFinite(value[key])
        ? Math.max(min, Math.min(max, value[key])) : DEFAULT_LAYOUT[key];
    return { image: clamp("image", 25, 70), result: clamp("result", 30, 70), drawerWidth: clamp("drawerWidth", 280, 420) };
  } catch { return { ...DEFAULT_LAYOUT }; }
}

export function recordedShortcut(event: Pick<KeyboardEvent, "code" | "key" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">): string | null {
  if (event.key === "Escape") return "";
  if (/^(Meta|Control|Alt|Shift)/.test(event.code)) return null;
  const modifiers = [event.ctrlKey && "ctrl", event.altKey && "alt", event.shiftKey && "shift", event.metaKey && "cmd"].filter(Boolean);
  if (!modifiers.length) throw new Error("请使用至少一个修饰键和一个主键");
  // macOS Option changes event.key (O becomes ø). Use the physical key code.
  const named: Record<string, string> = { Space: "space", Enter: "enter", Tab: "tab", Backspace: "backspace", Delete: "delete", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Home: "home", End: "end", PageUp: "pageup", PageDown: "pagedown" };
  const key = /^(Key[A-Z]|Digit[0-9])$/.test(event.code) ? event.code.replace(/^(Key|Digit)/, "").toLowerCase() : /^F([1-9]|1[0-9]|2[0-4])$/.test(event.code) ? event.code.toLowerCase() : named[event.code];
  if (!key) throw new Error("不支持的主键");
  return [...modifiers, key].join("+");
}

export type Draft = { id: string; source: Source; latex: string; activate?: boolean };
/** One serialized write chain: a late debounce can never revert a newer edit. */
export class DraftQueue {
  private pending = new Map<string, Draft>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private chain: Promise<void> = Promise.resolve();
  constructor(private write: (draft: Draft) => Promise<unknown>, private failed: (error: unknown) => void, private delay = 400) {}
  schedule(draft: Draft) {
    this.pending.set(`${draft.id}:${draft.source}`, draft);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.flush(); }, this.delay);
  }
  flush(): Promise<void> {
    clearTimeout(this.timer);
    const drafts = [...this.pending.values()];
    this.pending.clear();
    this.chain = this.chain.then(async () => {
      for (const draft of drafts) {
        try { await this.write(draft); } catch (error) { this.failed(error); }
      }
    });
    return this.chain;
  }
}
