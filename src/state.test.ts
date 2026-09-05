import { describe, it, expect, vi, afterEach } from "vitest";
import { DraftQueue, readLayout, DEFAULT_LAYOUT, recordedShortcut } from "./state";

afterEach(() => vi.useRealTimers());
describe("layout restoration", () => {
  it.each([null, "{bad", "null", "[]"])("recovers invalid saved layout %s", (raw) => expect(readLayout(raw)).toEqual(DEFAULT_LAYOUT));
  it("clamps ratios and drawer size", () => expect(readLayout('{"image":95,"result":-1,"drawerWidth":999}')).toEqual({ image:70, result:30, drawerWidth:420 }));
});
describe("physical shortcut recording", () => {
  const event = { code: "KeyO", key: "ø", ctrlKey: true, altKey: true, metaKey: true, shiftKey: false };
  it("recognizes Option-modified macOS keys", () => expect(recordedShortcut(event)).toBe("ctrl+alt+cmd+o"));
  it("allows clearing", () => expect(recordedShortcut({ ...event, code:"Escape", key:"Escape" })).toBe(""));
  it("waits for a main key", () => expect(recordedShortcut({ ...event, code:"MetaLeft", key:"Meta" })).toBeNull());
  it("rejects unmodified keys", () => expect(() => recordedShortcut({ ...event, ctrlKey:false, altKey:false, metaKey:false })).toThrow());
  it("rejects unsupported keys", () => expect(() => recordedShortcut({ ...event, code:"AudioVolumeUp" })).toThrow());
});
describe("durable draft queue", () => {
  it("debounces actual writes and preserves an intentionally empty draft", async () => {
    vi.useFakeTimers();
    const write = vi.fn().mockResolvedValue(undefined);
    const queue = new DraftQueue(write, vi.fn());
    queue.schedule({ id:"a", source:"local", latex:"old" });
    queue.schedule({ id:"a", source:"local", latex:"" });
    await vi.advanceTimersByTimeAsync(400);
    expect(write).toHaveBeenCalledTimes(1);
    expect(write).toHaveBeenCalledWith({ id:"a", source:"local", latex:"" });
  });
  it("flushes both sources on switching or quit", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    const queue = new DraftQueue(write, vi.fn());
    queue.schedule({ id:"a", source:"local", latex:"A" });
    queue.schedule({ id:"a", source:"api", latex:"B" });
    await queue.flush();
    expect(write.mock.calls.map(([value]) => value.latex)).toEqual(["A","B"]);
  });
  it("serializes writes across in-flight flushes", async () => {
    let release!: () => void;
    const write = vi.fn().mockImplementationOnce(() => new Promise<void>((resolve) => { release = resolve; })).mockResolvedValue(undefined);
    const queue = new DraftQueue(write, vi.fn());
    queue.schedule({ id:"a", source:"local", latex:"1" });
    const first = queue.flush();
    await Promise.resolve();
    queue.schedule({ id:"a", source:"local", latex:"2" });
    const second = queue.flush();
    expect(write).toHaveBeenCalledTimes(1);
    release(); await first; await second;
    expect(write.mock.calls.map(([value]) => value.latex)).toEqual(["1","2"]);
  });
  it("reports disk failures without breaking subsequent saves", async () => {
    const error = vi.fn();
    const write = vi.fn().mockRejectedValueOnce(Error("disk")).mockResolvedValue(undefined);
    const queue = new DraftQueue(write, error);
    queue.schedule({ id:"a", source:"local", latex:"1" }); await queue.flush();
    queue.schedule({ id:"a", source:"local", latex:"2" }); await queue.flush();
    expect(error).toHaveBeenCalledTimes(1); expect(write).toHaveBeenCalledTimes(2);
  });
});
