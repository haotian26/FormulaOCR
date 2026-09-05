import type { Profile } from "./types";
export function profileErrors(profile: Profile): Partial<Record<"name" | "base_url" | "model" | "timeout_s", string>> {
  const errors: ReturnType<typeof profileErrors> = {};
  if (!profile.name.trim()) errors.name = "请输入配置名称";
  if (!profile.enabled) return errors;
  try {
    const url = new URL(profile.base_url || "");
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (!(url.protocol === "https:" || (local && url.protocol === "http:")) || url.username || url.password || url.search || url.hash) throw new Error();
  } catch { errors.base_url = "请输入 HTTPS 地址；本机服务可使用 HTTP"; }
  if (profile.provider_type === "openai_compatible" && !profile.model?.trim()) errors.model = "请输入模型 ID";
  const timeout = profile.timeout_s ?? 45;
  if (!Number.isInteger(timeout) || timeout < 5 || timeout > 120) errors.timeout_s = "超时应为 5–120 秒";
  return errors;
}
