import { expect, test, type Page } from "@playwright/test";

// Only native transport is mocked: real React, CodeMirror, CSS and WebKit render.
// No production history, network API, credentials or model are used by these tests.
async function boot(page: Page, language = "en", settings = false, autoCopy = false) {
  await page.addInitScript(({ language, settings, autoCopy }) => {
    const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhXkAAAAASUVORK5CYII=";
    const callbacks = new Map<number, (value: any) => void>();
    const listeners = new Map<string, number[]>();
    const w = window as any;
    w.testCalls = [];
    w.testPNG = png;
    w.testOverrides = {};
    w.testPending = new Map<string, (value: any) => void>();
    w.testConversions = [];
    w.testEmit = (event: string, payload: any) => (listeners.get(event) || []).forEach(id => callbacks.get(id)?.({ event, payload }));
    let serial = 0;
    w.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: (_event: string, id: number) => callbacks.delete(id) };
    w.__TAURI_INTERNALS__ = {
      metadata: { currentWindow: { label: settings ? "settings" : "main" }, currentWebview: { label: settings ? "settings" : "main" } },
      transformCallback: (cb: any) => { callbacks.set(++serial, cb); return serial; },
      unregisterCallback: (id: number) => callbacks.delete(id),
      convertFileSrc: () => "data:image/png;base64," + png,
      invoke: async (command: string, args: any = {}) => {
        w.testCalls.push({ command, args });
        if (command === "plugin:event|listen") { listeners.set(args.event, [...(listeners.get(args.event) || []), args.handler]); return args.handler; }
        if (command === "plugin:event|emit") return w.testEmit(args.event, args.payload);
        if (command === "plugin:event|unlisten") { listeners.set(args.event, (listeners.get(args.event) || []).filter(id => id !== args.eventId)); return; }
        if (command === "plugin:window|get_all_windows" || command === "plugin:webview|get_all_webviews") return [];
        if (command === "stage_image_bytes" || command === "native_paste_image" || command === "native_screenshot") return "/tmp/test.png";
        if (command !== "sidecar_request") return null;
        const { id, method, params } = args.request;
        let result: any = {};
        if (w.testOverrides[method]) return { id, ok:true, result:await w.testOverrides[method](params) };
        if (method === "settings.get") result = { language, auto_copy: autoCopy, hide_dock_on_close: true, hotkey: "", history_limit: 200, default_recognition_mode: "chemistry", layout_restore_mode: "remember_window_history_closed" };
        if (method === "profiles.list") result = { api_enabled: true, active_profile_id: "test", profiles: [{ id: "test", name: "A very long API configuration name", provider_type: "openai_compatible", base_url: "https://example.org/v1", model: "example-vision", timeout_s: 45, enabled: true }] };
        if (method === "history.list") result = { records: [] };
        if (method === "ocr.preload") result = { loaded: true, elapsed_ms: 15 };
        if (method === "ocr.format") result = { formatted_latex: params.latex };
        if (method === "image.openPath") result = { image_id: "image-" + serial++ };
        if (method === "ocr.recognize" || method === "api.recognize") result = await new Promise(resolve => w.testPending.set(method, resolve));
        if (method === "conversion.toMathML") {
          if (w.testHoldConversions) await new Promise(resolve => w.testConversions.push(resolve));
          result = { mathml: '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mrow><msub><mi mathvariant="normal">NdF</mi><mn>3</mn></msub><mo>+</mo><msup><mi mathvariant="normal">F</mi><mo>−</mo></msup></mrow></math>' };
        }
        if (method === "settings.save") result = params.values;
        if (method === "api.listModels") result = { models: ["a", "b"] };
        return { id, ok: true, result };
      },
    };
  }, { language, settings, autoCopy });
  await page.goto(settings ? "/?settings=1" : "/");
  await expect(page.locator(settings ? ".settings-tabs" : ".toolbar")).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.some((item: any) => item.args?.request?.method === "profiles.list"))).toBe(true);
}

for (const language of ["en", "zh-CN"]) {
  for (const colorScheme of ["light", "dark"] as const) {
    test(`single-row toolbar and full preview at minimum size: ${language} ${colorScheme}`, async ({ page }) => {
      await page.setViewportSize({ width: 900, height: 650 });
      await page.emulateMedia({ colorScheme });
      await boot(page, language);
      const boxes = await page.locator(".toolbar > button, .toolbar > .mode-selector").evaluateAll(elements => elements.map(el => { const b = el.getBoundingClientRect(); return { x:b.x, y:b.y, right:b.right, height:b.height }; }));
      expect(Math.max(...boxes.map(b => b.right))).toBeLessThanOrEqual(900);
      expect(Math.max(...boxes.map(b => b.y)) - Math.min(...boxes.map(b => b.y))).toBeLessThan(10);
      expect(await page.locator(".preview-surface").evaluate(el => el.clientWidth)).toBeGreaterThan(280);
      const before = await page.locator(".result-card").boundingBox();
      await page.locator(".toolbar > button").first().click();
      expect(await page.locator(".result-card").boundingBox()).toEqual(before);
      await page.screenshot({ path: `test-results/main-${language}-${colorScheme}.png`, animations: "disabled" });
    });
  }
  test(`settings fields align and scroll without losing Save: ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 820, height: 560 });
    await boot(page, language, true);
    for (const tab of await page.locator(".settings-tabs button").all()) {
      await tab.click();
      const footer = await page.locator(".settings-footer").boundingBox();
      expect(footer!.y + footer!.height).toBeLessThanOrEqual(560);
    }
    await page.locator(".settings-tabs button").nth(3).click();
    const height = await page.locator(".profile-form-grid").first().locator("input, select").evaluateAll(elements => elements.map(el => el.getBoundingClientRect().height));
    expect(new Set(height).size).toBe(1);
    const form = page.locator(".profile-form");
    expect(await form.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    await form.hover(); await page.mouse.wheel(0, 3000);
    await expect.poll(() => form.evaluate(el => el.scrollTop)).toBeGreaterThan(100);
    await expect(page.getByRole("button", { name:language === "en" ? "Test Profile" : "测试配置", exact:true })).toBeVisible();
    expect(await page.locator('.timeout-row input').evaluate(el => el.getBoundingClientRect().width)).toBeGreaterThanOrEqual(70);
    await page.screenshot({ path: `test-results/settings-${language}.png`, animations: "disabled" });
  });
}

test("image appears before OCR, API cannot overwrite a newer image, Undo stays within current image", async ({ page }) => {
  await boot(page);
  await page.getByRole("button", { name:"Paste", exact:true }).click();
  await expect(page.locator(".image-card img")).toBeVisible();
  await expect(page.locator(".cm-content")).toHaveText("");
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("ocr.recognize"))).toBe(true);
  await page.evaluate(() => (window as any).testPending.get("ocr.recognize")({ raw_latex:"x^2", formatted_latex:"x^2" }));
  await expect(page.locator(".cm-content")).toHaveText("x^2");
  await page.locator(".cm-content").fill("x^3");
  await page.getByTitle("Undo", { exact:true }).click();
  await expect(page.locator(".cm-content")).toHaveText("x^2");
  await page.getByRole("button", { name:"API OCR", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("api.recognize"))).toBe(true);
  // Real clipboard event remains available while the previous API request runs.
  await page.evaluate(() => {
    const data = new DataTransfer(); data.items.add(new File([new Uint8Array([1,2])], "new.png", { type:"image/png" }));
    window.dispatchEvent(new ClipboardEvent("paste", { clipboardData:data }));
  });
  await expect(page.locator(".cm-content")).toHaveText("");
  await page.evaluate(() => (window as any).testPending.get("api.recognize")({ raw_latex:"OLD API", profile_name:"Old" }));
  await expect(page.locator(".cm-content")).toHaveText("");
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.filter((item: any) => item.args?.request?.method === "ocr.recognize").length)).toBe(2);
  await page.evaluate(() => (window as any).testPending.get("ocr.recognize")({ raw_latex:"y^2", formatted_latex:"y^2" }));
  await expect(page.locator(".cm-content")).toHaveText("y^2");
  await expect(page.getByTitle("Undo", { exact:true })).toBeDisabled();
});

test("manual LaTeX survives mode changes and late formatting cannot overwrite an edit", async ({ page }) => {
  await boot(page);
  page.on("dialog", dialog => dialog.accept());
  const editor = page.locator(".cm-content");
  await editor.fill("x^2");
  await page.getByRole("button", { name:"Math", exact:true }).click();
  await expect(editor).toHaveText("x^2");
  await expect(page.locator(".mode-selector button.active")).toHaveText("Math");
  await page.evaluate(() => {
    const w = window as any;
    w.testOverrides["ocr.format"] = () => new Promise(resolve => w.testPending.set("format", resolve));
  });
  await page.getByRole("button", { name:"Chemistry", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("format"))).toBe(true);
  await editor.fill("x^3");
  await page.evaluate(() => (window as any).testPending.get("format")({ formatted_latex:"OLD" }));
  await expect(page.getByRole("button", { name:"Open", exact:true })).toBeEnabled();
  await expect(editor).toHaveText("x^3");
  await expect(page.getByTitle("Undo", { exact:true })).toBeEnabled();
});

test("editing during mode metadata save keeps the newest persistent draft", async ({ page }) => {
  await boot(page);
  await page.getByRole("button", { name:"Paste", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("ocr.recognize"))).toBe(true);
  await page.evaluate(() => {
    const w = window as any;
    w.testOverrides["history.setMode"] = () => new Promise(resolve => w.testPending.set("mode", resolve));
    w.testPending.get("ocr.recognize")({ raw_latex:"x^2", formatted_latex:"x^2", history_id:"saved-record" });
  });
  await expect(page.locator(".cm-content")).toHaveText("x^2");
  await page.getByRole("button", { name:"Math", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("mode"))).toBe(true);
  await page.locator(".cm-content").fill("x^3");
  await page.evaluate(() => (window as any).testPending.get("mode")({}));
  await expect(page.getByRole("button", { name:"Open", exact:true })).toBeEnabled();
  await page.evaluate(() => (window as any).testEmit("formulaocr://quit-requested", null));
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.some((call: any) => call.command === "complete_quit"))).toBe(true);
  const writes = await page.evaluate(() => (window as any).testCalls.filter((call: any) => call.args?.request?.method === "history.updateDraft").map((call: any) => call.args.request.params.latex));
  expect(writes.at(-1)).toBe("x^3");
  await expect(page.locator(".cm-content")).toHaveText("x^3");
});

test("failed history save blocks quit, preserves the draft, and retries", async ({ page }) => {
  await boot(page);
  await page.getByRole("button", { name:"Paste", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("ocr.recognize"))).toBe(true);
  await page.evaluate(() => {
    const w = window as any;
    w.testOverrides["history.updateDraft"] = async () => { throw Error("Disk full"); };
    w.testPending.get("ocr.recognize")({ raw_latex:"x^2", formatted_latex:"x^2", history_id:"saved-record" });
  });
  await expect(page.locator(".cm-content")).toHaveText("x^2");
  await page.locator(".cm-content").fill("x^3");
  await page.evaluate(() => (window as any).testEmit("formulaocr://quit-requested", null));
  await expect(page.getByRole("alertdialog")).toBeVisible();
  expect(await page.evaluate(() => (window as any).testCalls.some((call: any) => call.command === "complete_quit"))).toBe(false);
  await page.getByRole("button", { name:"Cancel Quit", exact:true }).click();
  await expect(page.locator(".cm-content")).toHaveText("x^3");
  await page.evaluate(() => { const w = window as any; w.testOverrides["history.updateDraft"] = async () => ({}); w.testEmit("formulaocr://quit-requested", null); });
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.some((call: any) => call.command === "complete_quit"))).toBe(true);
  const writes = await page.evaluate(() => (window as any).testCalls.filter((call: any) => call.args?.request?.method === "history.updateDraft").map((call: any) => call.args.request.params.latex));
  expect(writes.length).toBeGreaterThanOrEqual(2);
  expect(writes.every((value: string) => value === "x^3")).toBe(true);
});

test("history search and export preserve the selected active-source draft", async ({ page }) => {
  await boot(page);
  await page.evaluate(() => {
    const w = window as any;
    const records = [
      { id:"one", created_at:1, updated_at:1, local_raw_latex:"NaCl", local_draft_latex:"NaCl", active_source:"local" },
      { id:"two", created_at:2, updated_at:2, local_raw_latex:"HF", local_draft_latex:"HF", api_draft_latex:"HF^{\\circ}", api_profile_name:"Chemistry API", active_source:"api", has_api:true },
    ];
    w.testOverrides["history.list"] = async () => ({ records });
  });
  await page.getByRole("button", { name:"History", exact:true }).click();
  await expect(page.locator(".history-item")).toHaveCount(2);
  await page.getByRole("searchbox", { name:"Search history" }).fill("chemistry");
  await expect(page.locator(".history-item")).toHaveCount(1);
  await page.getByRole("button", { name:"Export Results" }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.some((call: any) => call.command === "export_history_tex"))).toBe(true);
  const text = await page.evaluate(() => (window as any).testCalls.find((call: any) => call.command === "export_history_tex").args.text);
  expect(text).toContain("HF^{\\circ}"); expect(text).not.toContain("NaCl");
});

test("late automatic Word conversion cannot copy a previous image", async ({ page }) => {
  await boot(page, "en", false, true);
  await page.evaluate(() => { (window as any).testHoldConversions = true; });
  await page.getByRole("button", { name:"Paste", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).testPending.has("ocr.recognize"))).toBe(true);
  await page.evaluate(() => (window as any).testPending.get("ocr.recognize")({ raw_latex:"x^2", formatted_latex:"x^2" }));
  await expect.poll(() => page.evaluate(() => (window as any).testConversions.length)).toBeGreaterThan(0);
  await page.evaluate(() => {
    const data = new DataTransfer(); data.items.add(new File([new Uint8Array([1,2])], "new.png", { type:"image/png" }));
    window.dispatchEvent(new ClipboardEvent("paste", { clipboardData:data }));
  });
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.filter((item: any) => item.args?.request?.method === "ocr.recognize").length)).toBe(2);
  await page.evaluate(() => {
    const w = window as any; w.testHoldConversions = false;
    w.testConversions.splice(0).forEach((resolve: any) => resolve());
    w.testPending.get("ocr.recognize")({ raw_latex:"y^2", formatted_latex:"y^2" });
  });
  await expect.poll(() => page.evaluate(() => (window as any).testCalls.filter((item: any) => item.command === "native_copy_word").map((item: any) => item.args.latex))).toEqual(["y^2"]);
});
