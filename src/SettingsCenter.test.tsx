// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsCenter } from "./SettingsCenter";
import { defaults } from "./types";

const mock = vi.hoisted(() => ({
  call: vi.fn(), invoke: vi.fn(), emit: vi.fn(), destroy: vi.fn(),
  close: undefined as undefined | ((event: { preventDefault: () => void }) => void),
  handlers: new Map<string, (event: { payload: unknown }) => void>(),
}));
vi.mock("./sidecar", () => ({ callSidecar: mock.call }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mock.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  emit: mock.emit,
  listen: vi.fn(async (name, handler) => { mock.handlers.set(name, handler); return () => mock.handlers.delete(name); }),
}));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({
  setTitle: vi.fn().mockResolvedValue(undefined),
  onResized: vi.fn().mockResolvedValue(() => {}),
  onCloseRequested: vi.fn(async (handler) => { mock.close = handler; return () => {}; }),
  destroy: mock.destroy,
}) }));

beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key), clear: () => storage.clear() });
  localStorage.clear(); mock.call.mockReset(); mock.invoke.mockReset(); mock.emit.mockReset(); mock.destroy.mockReset();
  mock.invoke.mockResolvedValue(undefined);
  mock.call.mockImplementation(async (method, params) => {
    if (method === "settings.get") return { ...defaults };
    if (method === "profiles.list") return { api_enabled:false, active_profile_id:"", profiles:[] };
    if (method === "settings.save") return { ...defaults, ...params.values };
    return {};
  });
});
afterEach(cleanup);
const open = async (page = "常规") => {
  render(<SettingsCenter initialPage={page} />);
  await waitFor(() => expect(screen.getByRole("button", { name:"保存" }).closest("main")!.querySelector("fieldset")!.disabled).toBe(false));
};
const save = () => screen.getByRole("button", { name:"保存" }) as HTMLButtonElement;

describe("settings interaction", () => {
  it("has a fixed-label disabled Save until a real change, including reverting to saved values", async () => {
    await open();
    expect(save().disabled).toBe(true);
    const checkbox = screen.getByLabelText(/识别完成后自动复制/);
    fireEvent.click(checkbox); expect(save().disabled).toBe(false);
    fireEvent.click(checkbox); expect(save().disabled).toBe(true);
    expect(mock.invoke.mock.calls.some(([name]) => name === "set_global_hotkey")).toBe(false);
  });
  it("saves only the current page and keeps other page drafts", async () => {
    await open();
    fireEvent.click(screen.getByLabelText(/识别完成后自动复制/));
    fireEvent.click(screen.getByRole("button", { name:"历史记录" }));
    fireEvent.change(screen.getByLabelText("最多保存记录"), { target:{ value:"300" } });
    fireEvent.click(save());
    await waitFor(() => expect(save().disabled).toBe(true));
    expect(mock.call).toHaveBeenCalledWith("settings.save", { values:{ history_limit:300 } });
    fireEvent.click(screen.getByRole("button", { name:"常规" }));
    expect(save().disabled).toBe(false);
  });
  it("keeps Save and draft after persistence failure", async () => {
    await open();
    mock.call.mockImplementation(async (method) => { if (method === "settings.save") throw Error("disk full"); return {}; });
    fireEvent.click(screen.getByLabelText(/识别完成后自动复制/));
    fireEvent.click(save());
    await screen.findByText("disk full");
    expect(save().disabled).toBe(false);
    expect(screen.queryByText("已保存")).toBeNull();
  });
  it("finishes a real Option-modified shortcut on key release without registering before Save", async () => {
    await open("快捷键");
    fireEvent.click(screen.getByRole("button", { name:/截图快捷键/ }));
    await screen.findByText("请按组合键…");
    fireEvent.keyDown(window, { code:"KeyP", key:"π", altKey:true, metaKey:true });
    expect(save().disabled).toBe(true);
    fireEvent.keyUp(window, { code:"KeyP", key:"π", altKey:true, metaKey:true });
    expect(save().disabled).toBe(false);
    expect(mock.invoke.mock.calls.some(([method]) => method === "set_global_hotkey")).toBe(false);
    fireEvent.click(save());
    await waitFor(() => expect(mock.invoke).toHaveBeenCalledWith("set_global_hotkey", { shortcut:"alt+cmd+p" }));
    await screen.findByText("已保存");
    expect(save().textContent).toBe("保存");
  });
  it("rolls back the running shortcut if persistence fails", async () => {
    await open("快捷键");
    fireEvent.click(screen.getByRole("button", { name:/截图快捷键/ }));
    await screen.findByText("请按组合键…");
    fireEvent.keyDown(window, { code:"Escape", key:"Escape" });
    fireEvent.keyUp(window, { code:"Escape", key:"Escape" });
    mock.call.mockRejectedValue(Error("disk full"));
    fireEvent.click(save());
    await waitFor(() => expect(mock.invoke).toHaveBeenCalledWith("set_global_hotkey", { shortcut:defaults.hotkey }));
    expect(save().disabled).toBe(false);
  });
  it("confirms unsaved close and discards rather than writing", async () => {
    await open();
    fireEvent.click(screen.getByLabelText(/识别完成后自动复制/));
    const preventDefault = vi.fn();
    act(() => mock.close?.({ preventDefault }));
    expect(preventDefault).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name:"放弃更改" }));
    expect(mock.destroy).toHaveBeenCalled();
    expect(mock.call.mock.calls.some(([method]) => method === "settings.save")).toBe(false);
  });
  it("blocks whole-app Quit while settings contain unsaved drafts", async () => {
    await open();
    fireEvent.click(screen.getByLabelText(/识别完成后自动复制/));
    act(() => mock.handlers.get("formulaocr://quit-requested")?.({ payload:null }));
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name:"取消" }));
    expect(mock.invoke).toHaveBeenCalledWith("cancel_quit");
    expect(save().disabled).toBe(false);
  });
  it("does not confuse model retrieval with saving", async () => {
    mock.call.mockImplementation(async (method) => {
      if (method === "settings.get") return defaults;
      if (method === "profiles.list") return { api_enabled:true, active_profile_id:"a", profiles:[{ id:"a", name:"Test", enabled:true, provider_type:"openai_compatible", base_url:"https://example.com/v1", model:"m", timeout_s:45 }] };
      if (method === "api.listModels") return { models:["a", "b"] };
      return {};
    });
    await open("自定义模型与 API");
    fireEvent.click(screen.getByRole("button", { name:"获取模型" }));
    await screen.findByText("已获取 2 个模型");
    expect(save().disabled).toBe(true);
    expect(mock.emit).not.toHaveBeenCalled();
  });
});
