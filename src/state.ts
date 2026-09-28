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
  private activeSources = new Map<string, Source>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private chain: Promise<void> = Promise.resolve();
  constructor(private write: (draft: Draft) => Promise<unknown>, private failed: (error: unknown) => void, private delay = 400) {}
  schedule(draft: Draft) {
    const key = `${draft.id}:${draft.source}`;
    if (draft.activate !== false) this.activeSources.set(draft.id, draft.source);
    // Replacing a Map entry does not change its insertion order. Move the
    // latest edit to the end so rapid source switches retain their order.
    this.pending.delete(key);
    this.pending.set(key, draft);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.flush(); }, this.delay);
  }
  hasPending(): boolean { return this.pending.size > 0; }
  discard(): void { clearTimeout(this.timer); this.pending.clear(); this.activeSources.clear(); }
  flush(): Promise<boolean> {
    clearTimeout(this.timer);
    const result = this.chain.then(async () => {
      // Read at execution time: another flush or edit may have superseded work
      // while this one waited. Never retry an older value over a newer draft.
      for (const [key, draft] of [...this.pending]) {
        if (this.pending.get(key) !== draft) continue;
        this.pending.delete(key);
        const write = draft.activate !== false && this.activeSources.get(draft.id) !== draft.source
          ? { ...draft, activate: false } : draft;
        try { await this.write(write); } catch (error) {
          if (!this.pending.has(key)) this.pending.set(key, draft);
          this.failed(error);
        }
      }
      const pendingIds = new Set([...this.pending.values()].map(draft => draft.id));
      for (const id of this.activeSources.keys()) if (!pendingIds.has(id)) this.activeSources.delete(id);
      return this.pending.size === 0;
    });
    this.chain = result.then(() => undefined);
    return result;
  }
}
