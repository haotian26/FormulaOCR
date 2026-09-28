import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ExternalLink, RefreshCw } from "lucide-react";
import { translate, localizeError, type AppLanguage } from "./i18n";
import { version } from "../package.json";

type Update = { current: string; latest: string; update_available: boolean; url: string };
export function AboutPanel({ language }: { language: AppLanguage }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(language, key, values);
  const [busy, setBusy] = useState(false);
  const [update, setUpdate] = useState<Update | null>(null);
  const [error, setError] = useState("");
  const check = async () => {
    setBusy(true); setError(""); setUpdate(null);
    try { setUpdate(await invoke<Update>("check_for_updates")); }
    catch (error) { setError(localizeError(language, error)); }
    finally { setBusy(false); }
  };
  return <details className="about-panel">
    <summary>{t("关于 FormulaOCR")} <span>{version}</span></summary>
    <p>{t("离线公式识别 · MIT 开源许可")}</p>
    <p className="setting-help">{t("仅点击检查时连接 GitHub，不自动下载或安装。")}</p>
    <div className="about-actions">
      <button type="button" className="secondary-button" disabled={busy} onClick={() => void check()}><RefreshCw size={15}/>{t(busy ? "正在检查…" : "检查更新")}</button>
      {update && <button type="button" className="secondary-button" onClick={() => void invoke("open_release_page", { url: update.url }).catch(error => setError(localizeError(language, error)))}><ExternalLink size={15}/>{t(update.update_available ? "查看新版本" : "查看发布说明")}</button>}
    </div>
    <div role="status" aria-live="polite">{update && t(update.update_available ? "发现新版本 {version}" : "当前已是最新版本", { version: update.latest })}</div>
    {error && <p role="alert" className="preview-error">{error}</p>}
  </details>;
}
