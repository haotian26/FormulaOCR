import { describe, expect, it } from "vitest";

import { normalizeLanguage, translate } from "./i18n";

describe("interface localization", () => {
  it("keeps Chinese source copy in the default locale", () => {
    expect(translate("zh-CN", "打开图片")).toBe("打开图片");
  });

  it("provides complete English copy for primary navigation", () => {
    expect(translate("en", "打开图片")).toBe("Open");
    expect(translate("en", "自定义模型与 API")).toBe(
      "Custom Models & API",
    );
    expect(translate("en", "识别历史")).toBe("Recognition History");
  });

  it("interpolates status values", () => {
    expect(translate("en", "API 完成 · {name}", { name: "Local API" })).toBe(
      "API complete · Local API",
    );
  });

  it("normalizes unsupported or missing settings to Chinese", () => {
    expect(normalizeLanguage("en")).toBe("en");
    expect(normalizeLanguage("fr")).toBe("zh-CN");
    expect(normalizeLanguage(undefined)).toBe("zh-CN");
  });
});
