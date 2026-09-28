import { expect, test, type Page } from "@playwright/test";

// Browser-rendered React/CSS with synthetic pixels and mocked native transport.
// Never reads production history, credentials, or contacts a recognition API.
async function bootFeatures(page: Page, language = "en", settings = false) {
  await page.addInitScript(({ language, settings }) => {
    const w = window as any;
    const callbacks = new Map<number, (value: any) => void>();
    const listeners = new Map<string, number[]>();
    let serial = 0;
    w.featureCalls = [];
    w.featurePending = [];
    w.featureHistory = [];
    w.featureSize = [1600, 800];
    w.featurePng = "";
    const image = () => {
      const canvas = document.createElement("canvas");
      [canvas.width, canvas.height] = w.featureSize;
      const context = canvas.getContext("2d")!;
      context.fillStyle = "white";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.strokeStyle = "#dce3eb";
      context.lineWidth = 2;
      for (let x = 0; x < canvas.width; x += 100) { context.beginPath(); context.moveTo(x, 0); context.lineTo(x, canvas.height); context.stroke(); }
      for (let y = 0; y < canvas.height; y += 100) { context.beginPath(); context.moveTo(0, y); context.lineTo(canvas.width, y); context.stroke(); }
      context.fillStyle = "#162a43";
      context.font = "100px Georgia";
      context.fillText("NdF₃ + F⁻ ⇌ NdF₄⁻", 100, 300);
      context.font = "40px sans-serif";
      context.fillText("Synthetic image · inspect small symbols", 100, 500);
      w.featurePng = canvas.toDataURL("image/png");
    };
    const emit = (event: string, payload: any) => (listeners.get(event) || []).forEach(id => callbacks.get(id)?.({ event, payload }));
    w.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: (_event: string, id: number) => callbacks.delete(id) };
    w.__TAURI_INTERNALS__ = {
      metadata: { currentWindow:{ label:settings ? "settings" : "main" }, currentWebview:{ label:settings ? "settings" : "main" } },
      transformCallback: (callback: any) => { callbacks.set(++serial, callback); return serial; },
      unregisterCallback: (id: number) => callbacks.delete(id),
      convertFileSrc: () => w.featurePng,
      invoke: async (command: string, args: any = {}) => {
        w.featureCalls.push({ command, args });
        if (command === "plugin:event|listen") { listeners.set(args.event, [...(listeners.get(args.event) || []), args.handler]); return args.handler; }
        if (command === "plugin:event|emit") return emit(args.event, args.payload);
        if (command === "plugin:event|unlisten") { listeners.set(args.event, (listeners.get(args.event) || []).filter(id => id !== args.eventId)); return; }
        if (command === "plugin:window|get_all_windows" || command === "plugin:webview|get_all_webviews") return [];
        if (command === "native_paste_image") { image(); return "/tmp/formulaocr-synthetic.png"; }
        if (command !== "sidecar_request") return null;
        const { id, method, params } = args.request;
        let result: any = {};
        if (method === "settings.get") result = { language, auto_copy:false, hide_dock_on_close:true, hotkey:"", history_limit:200, default_recognition_mode:"chemistry", layout_restore_mode:"remember_window_history_closed" };
        if (method === "profiles.list") result = { api_enabled:true, active_profile_id:"sample", profiles:[{ id:"sample", name:"Synthetic Test Profile", provider_type:"openai_compatible", base_url:"https://old.example/v1", model:"old-model", timeout_s:45, enabled:true }] };
        if (method === "history.list") result = { records:w.featureHistory };
        if (method === "ocr.preload") result = { loaded:true, elapsed_ms:1 };
        if (method === "image.openPath") result = { image_id:`sample-${serial++}`, session_id:"test-session" };
        if (method === "system.health") result = { session_id:"test-session" };
        if (method === "ocr.recognize") result = { raw_latex:"x^2", formatted_latex:"x^2", elapsed_ms:1 };
        if (method === "conversion.toMathML") result = { mathml:'<math xmlns="http://www.w3.org/1998/Math/MathML"><msup><mi>x</mi><mn>2</mn></msup></math>' };
        if (method === "api.listModels" || method === "api.testProfile") result = await new Promise(resolve => w.featurePending.push({ method, params, resolve }));
        return { id, ok:true, result };
      },
    };
  }, { language, settings });
  await page.goto(settings ? "/?settings=1&page=" + encodeURIComponent("自定义模型与 API") : "/");
  await expect(page.locator(settings ? ".settings-tabs" : ".toolbar")).toBeVisible();
}

for (const language of ["en", "zh-CN"]) {
  test(`image fit, actual size and bounded drag/keyboard pan: ${language}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width:900, height:650 });
    await page.emulateMedia({ colorScheme:language === "en" ? "light" : "dark" });
    await bootFeatures(page, language);
    const paste = page.getByRole("button", { name:language === "en" ? "Paste" : "粘贴图片", exact:true });
    await paste.click();
    const image = page.locator(".image-viewer-image");
    const viewport = page.locator(".image-viewer-viewport");
    await expect(image).toHaveClass(/is-loaded/);
    const fitted = await image.boundingBox();
    const area = await viewport.boundingBox();
    expect(fitted!.width).toBeLessThanOrEqual(area!.width + 1);
    expect(fitted!.height).toBeLessThanOrEqual(area!.height + 1);
    expect(Math.abs(fitted!.x + fitted!.width / 2 - area!.x - area!.width / 2)).toBeLessThan(1);
    expect(Math.abs(fitted!.y + fitted!.height / 2 - area!.y - area!.height / 2)).toBeLessThan(1);
    await expect(page.locator(".mathml-content math")).toBeVisible();
    await page.screenshot({ path:testInfo.outputPath("image-fit.png") });
    await page.getByRole("button", { name:language === "en" ? "Actual size" : "实际大小", exact:true }).click();
    await expect.poll(async () => (await image.boundingBox())!.width).toBe(1600);
    expect(await image.evaluate(element => getComputedStyle(element).maxWidth)).toBe("none");
    await page.getByRole("button", { name:language === "en" ? "Zoom in" : "放大图片", exact:true }).click();
    await expect.poll(async () => (await image.boundingBox())!.width).toBe(2000);
    await page.getByRole("button", { name:language === "en" ? "Zoom out" : "缩小图片", exact:true }).click();
    const before = await image.boundingBox();
    const start = { x:area!.x + area!.width / 2, y:area!.y + area!.height / 2 };
    await page.mouse.move(start.x, start.y); await page.mouse.down();
    await page.mouse.move(start.x + 80, start.y + 60, { steps:5 }); await page.mouse.up();
    await expect.poll(async () => (await image.boundingBox())!.x).toBeGreaterThan(before!.x + 70);
    const dragged = await image.boundingBox();
    await viewport.press("ArrowLeft");
    await expect.poll(async () => (await image.boundingBox())!.x).toBeGreaterThan(dragged!.x + 30);
    await viewport.press("ArrowUp");
    await viewport.press("ArrowUp");
    await page.screenshot({ path:testInfo.outputPath("image-actual-pan.png") });
    const fit = page.getByRole("button", { name:language === "en" ? "Fit" : "适合窗口", exact:true });
    await fit.click();
    await expect(fit).toHaveAttribute("aria-pressed", "true");
    await expect.poll(async () => (await image.boundingBox())!.x).toBeCloseTo(fitted!.x, 0);
    // A portrait image must start a new fitting session, not inherit old zoom.
    await page.getByRole("button", { name:language === "en" ? "Actual size" : "实际大小", exact:true }).click();
    await page.evaluate(() => { (window as any).featureSize = [800, 1200]; });
    await paste.click();
    await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalHeight)).toBe(1200);
    await expect(fit).toHaveAttribute("aria-pressed", "true");
    expect((await image.boundingBox())!.height).toBeLessThanOrEqual(area!.height + 1);
  });
}

test("a 1px image remains visible and centered at actual size", async ({ page }) => {
  await bootFeatures(page);
  await page.evaluate(() => { (window as any).featureSize = [1, 1]; });
  await page.getByRole("button", { name:"Paste", exact:true }).click();
  const image = page.locator(".image-viewer-image");
  await expect(image).toHaveClass(/is-loaded/);
  await expect(image).toBeVisible();
  const bounds = await image.boundingBox();
  const viewport = await page.locator(".image-viewer-viewport").boundingBox();
  expect(bounds!.width).toBe(1); expect(bounds!.height).toBe(1);
  expect(Math.abs(bounds!.x + .5 - viewport!.x - viewport!.width / 2)).toBeLessThan(1);
  expect(Math.abs(bounds!.y + .5 - viewport!.y - viewport!.height / 2)).toBeLessThan(1);
});

test("same-profile edits reject late model/test responses in WebKit", async ({ page }) => {
  await page.setViewportSize({ width:940, height:720 });
  await bootFeatures(page, "en", true);
  await page.getByRole("button", { name:"Fetch Models", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).featurePending.length)).toBe(1);
  await page.getByLabel("Base URL", { exact:true }).fill("https://new.example/v1");
  await page.evaluate(() => (window as any).featurePending[0].resolve({ models:["stale-old-model"] }));
  await expect(page.locator("#formulaocr-models option")).toHaveCount(0);
  await expect(page.locator(".saved-hint")).toHaveCount(0);
  await page.getByRole("button", { name:"Test Profile", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).featurePending.length)).toBe(2);
  await page.locator(".model-row input").fill("new-model");
  await page.evaluate(() => (window as any).featurePending[1].resolve({ message:"old test passed", models:["stale-tested-model"] }));
  await expect(page.locator("#formulaocr-models option")).toHaveCount(0);
  await expect(page.locator(".saved-hint")).toHaveCount(0);
  // A newly requested result belongs to the edited values and may be shown.
  await page.getByRole("button", { name:"Test Profile", exact:true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).featurePending.length)).toBe(3);
  const tested = await page.evaluate(() => (window as any).featurePending[2].params.profile);
  expect(tested.base_url).toBe("https://new.example/v1");
  expect(tested.model).toBe("new-model");
  await page.evaluate(() => (window as any).featurePending[2].resolve({ message:"current test passed", models:["new-model"] }));
  await expect(page.locator(".saved-hint")).toHaveText("Profile test succeeded");
  await expect(page.locator("#formulaocr-models option")).toHaveCount(1);
});

for (const language of ["en", "zh-CN"]) {
  test(`About is inspectable at minimum settings height without enabling Save: ${language}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width:820, height:500 });
    await page.emulateMedia({ colorScheme:language === "en" ? "light" : "dark" });
    await bootFeatures(page, language, true);
    await page.getByRole("button", { name:language === "en" ? "General" : "常规", exact:true }).click();
    await page.locator(".about-panel summary").click();
    const check = page.getByRole("button", { name:language === "en" ? "Check for Updates" : "检查更新", exact:true });
    await check.scrollIntoViewIfNeeded();
    await expect(check).toBeVisible();
    await expect(page.getByRole("button", { name:language === "en" ? "Save" : "保存", exact:true })).toBeDisabled();
    const footer = await page.locator(".settings-footer").boundingBox();
    expect(footer!.y + footer!.height).toBeLessThanOrEqual(500);
    expect(await page.evaluate(() => (window as any).featureCalls.some((call: any) => call.command === "check_for_updates"))).toBe(false);
    await page.screenshot({ path:testInfo.outputPath("about-expanded.png") });
  });
  test(`history search and selected export controls fit a narrow drawer: ${language}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width:900, height:650 });
    await page.emulateMedia({ colorScheme:language === "en" ? "light" : "dark" });
    await bootFeatures(page, language);
    await page.evaluate(() => {
      (window as any).featureHistory = [
        { id:"sample-one", image_path:"", created_at:1, updated_at:1, local_raw_latex:"NdF_3 + F^-", local_draft_latex:"NdF_3 + F^-", active_source:"local", api_profile_name:"Vision" },
        { id:"sample-two", image_path:"", created_at:2, updated_at:2, local_raw_latex:"x^2", local_draft_latex:"x^2", api_draft_latex:"\\sum_{i=1}^{n} i^2", active_source:"api", has_api:true, api_profile_name:"Vision" },
      ];
    });
    await page.getByRole("button", { name:language === "en" ? "History" : "历史", exact:true }).click();
    await page.getByRole("searchbox", { name:language === "en" ? "Search history" : "搜索历史" }).fill("vision");
    await expect(page.locator(".history-item")).toHaveCount(2);
    await page.locator(".history-item input[type=checkbox]").first().check();
    await expect(page.getByRole("button", { name:language === "en" ? "Export Selected" : "导出所选", exact:true })).toBeVisible();
    const drawer = await page.locator(".history-drawer").boundingBox();
    for (const button of await page.locator(".drawer-header button, .history-actions button").all()) {
      const bounds = await button.boundingBox();
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(drawer!.x + drawer!.width);
    }
    await page.screenshot({ path:testInfo.outputPath("history-search-selected.png") });
  });
}
