// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { ImageSession } from "./imageSession";

describe("image recovery", () => {
  it("reuses the loaded image without sending bytes", async () => {
    const call = vi.fn().mockResolvedValue({ session_id:"one" });
    const images = new ImageSession(call);
    images.adopt("image", new Blob(["png"]), "one");
    expect(await images.ensure()).toBe("image");
    expect(call).toHaveBeenCalledTimes(1);
  });
  it("rehydrates after restart with the same history association, not recognition", async () => {
    const call = vi.fn().mockResolvedValueOnce({ session_id:"two" }).mockResolvedValueOnce({ image_id:"image", session_id:"two" });
    const images = new ImageSession(call);
    images.adopt("image", new Blob(["png"], { type:"image/png" }), "one", "history");
    expect(await images.ensure()).toBe("image");
    expect(call.mock.calls[1]).toEqual(["image.open", { image_id:"image", png_base64:"cG5n", history_id:"history" }]);
    expect(call.mock.calls.every(([method]) => !method.includes("recognize"))).toBe(true);
  });
  it("does not restore a stale image after navigation", async () => {
    let resolve!: (value: unknown) => void;
    const call = vi.fn().mockImplementation(() => new Promise(done => { resolve = done; }));
    const images = new ImageSession(call);
    images.adopt("old", new Blob(["old"]), "one");
    const pending = images.ensure(); images.adopt("new", new Blob(["new"]), "two");
    resolve({ session_id:"two" });
    await expect(pending).rejects.toThrow("图片已切换");
    expect(call).toHaveBeenCalledTimes(1);
  });
});
