import { useEffect, useRef, useState } from "react";
import { profileErrors } from "./profileValidation";
import { Check, RefreshCw, SlidersHorizontal, Trash2 } from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { callSidecar } from "./sidecar";
import { translate, normalizeLanguage, localizeError, type AppLanguage } from "./i18n";
import { recordedShortcut } from "./state";
import { useTauriEvent } from "./hooks";
import { defaults, type Settings, type RecognitionMode, type Profile } from "./types";

function HotkeyRecorder({
  value,
  onChange,
  error,
  setError,
  language,
}: {
  value: string;
  onChange: (value: string) => void;
  error: string;
  setError: (value: string) => void;
  language: AppLanguage;
}) {
  const [recording, setRecording] = useState(false);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  useEffect(() => {
    if (!recording) return;
    let candidate: string | undefined;
    let mainCode = "";
    const onKeyDown = (event: KeyboardEvent) => {
      event.preventDefault(); event.stopImmediatePropagation();
      try {
        const shortcut = recordedShortcut(event);
        if (shortcut === null) return;
        candidate = shortcut;
        mainCode = event.code;
        setError("");
      } catch (error) { setError(translate(language, String((error as Error).message))); }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.code !== mainCode || candidate === undefined) return;
      onChangeRef.current(candidate);
      setRecording(false);
    };
    const stop = () => setRecording(false);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("blur", stop);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", stop);
      void invoke("set_hotkey_recording", { recording: false });
    };
  }, [recording, language]);
  const labels: Record<string, string> = {
    cmd: "⌘",
    ctrl: "⌃",
    alt: "⌥",
    shift: "⇧",
  };
  const display = value
    ? value
        .split("+")
        .map((part) => labels[part] || part.toUpperCase())
        .join(" ")
    : translate(language, "未设置");
  return (
    <div className="hotkey-recorder">
      <button
        className={recording ? "keycap recording" : "keycap"}
        onBlur={() => setRecording(false)}
        onClick={() => {
          void invoke("set_hotkey_recording", { recording: true }).then(() => {
            setRecording(true); setError("");
          }).catch((error) => setError(localizeError(language, error)));
        }}
      >
        {recording ? translate(language, "请按组合键…") : display}
      </button>
      <span className="field-help">
        {translate(language, "点击后按组合键，Esc 清空")}
      </span>
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

export function SettingsCenter({
  inline = false,
  initialPage,
  initialLanguage = "zh-CN",
  onClose,
}: {
  inline?: boolean;
  initialPage?: string;
  initialLanguage?: AppLanguage;
  onClose?: () => void;
}) {
  const params = new URLSearchParams(window.location.search);
  const pages = [
    "常规",
    "界面与布局",
    "快捷键",
    "自定义模型与 API",
    "历史记录",
  ];
  const requestedPage = initialPage || params.get("page") || "常规";
  const [page, setPage] = useState(pages.includes(requestedPage) ? requestedPage : "常规");
  const initialSettings = { ...defaults, language: initialLanguage };
  const [settings, setSettings] = useState<Settings>(initialSettings);
  const [savedSettings, setSavedSettings] = useState<Settings>(initialSettings);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [savedProfiles, setSavedProfiles] = useState<Profile[]>([]);
  const [apiEnabled, setApiEnabled] = useState(false);
  const [savedApiEnabled, setSavedApiEnabled] = useState(false);
  const [activeId, setActiveId] = useState("");
  const [savedActiveId, setSavedActiveId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);
  const requestVersion = useRef(0);
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const feedbackTimer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(feedbackTimer.current), []);
  useEffect(() => { requestVersion.current++; setModels([]); setBusy(false); setError(""); setFeedback(""); }, [selectedId]);
  useEffect(() => { setError(""); setFeedback(""); }, [page]);

  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [hotkeyError, setHotkeyError] = useState("");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const allowCloseRef = useRef(false);
  const quittingRef = useRef(false);
  const language = normalizeLanguage(settings.language);
  const t = (text: string, values?: Record<string, string | number>) =>
    translate(language, text, values);
  const selected = profiles.find((profile) => profile.id === selectedId);
  const profilesValid = profiles.every((profile) => !Object.keys(profileErrors(profile)).length);
  const settingsDirty =
    JSON.stringify(settings) !== JSON.stringify(savedSettings);
  const profilesDirty =
    apiEnabled !== savedApiEnabled ||
    activeId !== savedActiveId ||
    JSON.stringify(profiles) !== JSON.stringify(savedProfiles);
  const dirtyRef = useRef(false);
  dirtyRef.current = settingsDirty || profilesDirty;
  useTauriEvent("formulaocr://quit-requested", () => {
    quittingRef.current = true;
    if (dirtyRef.current) setConfirmDiscard(true);
    else void invoke("continue_quit");
  });
  const pageKeys: Record<string, (keyof Settings)[]> = {
    常规: [
      "auto_copy",
      "hide_dock_on_close",
      "default_recognition_mode",
      "language",
    ],
    界面与布局: ["layout_restore_mode"],
    快捷键: ["hotkey"],
    历史记录: ["history_limit"],
  };
  const currentSettingsDirty = (pageKeys[page] || []).some(
    (key) => settings[key] !== savedSettings[key],
  );
  useEffect(() => {
    let alive = true;
    void Promise.all([
      callSidecar<Settings>("settings.get"),
      callSidecar<{ api_enabled: boolean; active_profile_id: string; profiles: Profile[] }>("profiles.list"),
    ]).then(([value, api]) => {
      if (!alive) return;
      const normalized = { ...defaults, ...value, language: normalizeLanguage(value.language) };
      setSettings(normalized); setSavedSettings(normalized);
      setApiEnabled(api.api_enabled); setSavedApiEnabled(api.api_enabled);
      setActiveId(api.active_profile_id); setSavedActiveId(api.active_profile_id);
      setProfiles(api.profiles); setSavedProfiles(api.profiles);
      setSelectedId(api.active_profile_id || api.profiles[0]?.id || "");
      setReady(true);
    }).catch((caught) => { if (alive) setError(localizeError(language, caught)); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    document.documentElement.lang = language;
    if (!inline)
      void getCurrentWindow().setTitle(t("FormulaOCR 设置")).catch(() =>
        undefined,
      );
  }, [inline, language]);
  useTauriEvent<string>("formulaocr://settings-page", (event) => {
    if (pages.includes(event.payload)) setPage(event.payload);
  });
  useEffect(() => {
    if (inline) return;
    const defaultsByPage: Record<string, [number, number]> = {
      常规: [820, 500],
      界面与布局: [820, 520],
      快捷键: [820, 440],
      "自定义模型与 API": [940, 720],
      历史记录: [820, 440],
    };
    const storageKey = `formulaocr.settings.size.v2.${page}`;
    let target = defaultsByPage[page] || [820, 520];
    try {
      const savedSize = JSON.parse(
        localStorage.getItem(storageKey) || "null",
      ) as { width?: number; height?: number } | null;
      if (savedSize?.width && savedSize?.height)
        target = [
          Math.max(760, savedSize.width),
          Math.max(420, savedSize.height),
        ];
    } catch {
      /* corrupted UI state falls back to the safe page default */
    }
    const current = getCurrentWindow();
    void invoke("resize_settings_window", {
      width: target[0],
      height: target[1],
    }).catch(() => undefined);
    let stop: (() => void) | undefined;
    let disposed = false;
    const timer = window.setTimeout(() => {
      void current
        .onResized(({ payload }) => {
          localStorage.setItem(
            storageKey,
            JSON.stringify({
              width: payload.width / window.devicePixelRatio,
              height: payload.height / window.devicePixelRatio,
            }),
          );
        })
        .then((unlisten) => {
          if (disposed) unlisten(); else stop = unlisten;
        });
    }, 250);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      stop?.();
    };
  }, [inline, page]);
  useEffect(() => {
    if (inline) return;
    let unlisten: (() => void) | undefined;
    let disposed = false;
    void getCurrentWindow()
      .onCloseRequested((event) => {
        if (allowCloseRef.current) return;
        if (dirtyRef.current) {
          event.preventDefault();
          setConfirmDiscard(true);
        }
      })
      .then((stop) => {
        if (disposed) stop(); else unlisten = stop;
      });
    return () => { disposed = true; unlisten?.(); };
  }, [inline]);
  const close = () => {
    if (settingsDirty || profilesDirty) {
      setConfirmDiscard(true);
      return;
    }
    if (inline) onClose?.();
    else void getCurrentWindow().close();
  };
  const discardAndClose = () => {
    setConfirmDiscard(false);
    if (quittingRef.current) { void invoke("continue_quit"); return; }
    if (inline) {
      onClose?.();
      return;
    }
    allowCloseRef.current = true;
    // Destroy bypasses a second close-request round-trip after the user has
    // explicitly confirmed discarding the draft.
    void getCurrentWindow().destroy();
  };
  const notify = (message: string) => {
    clearTimeout(feedbackTimer.current);
    setFeedback(message);
    feedbackTimer.current = setTimeout(() => setFeedback(""), 1600);
  };
  const saved = (message = t("已保存")) => {
    void emit("formulaocr://settings-updated");
    notify(message);
  };
  const pageValid = page !== "快捷键" || !hotkeyError;
  const historyValid = Number.isInteger(settings.history_limit) && settings.history_limit >= 20 && settings.history_limit <= 2000;
  const saveSettings = async () => {
    if (saving || !pageValid || (page === "历史记录" && !historyValid)) return;
    if (page === "历史记录" && settings.history_limit < savedSettings.history_limit &&
      !window.confirm(t("降低上限会删除最旧记录，继续保存？"))) return;
    setSaving(true); setError(""); setFeedback("");
    const keys = pageKeys[page] || [];
    const patch = Object.fromEntries(keys.map((key) => [key, settings[key]]));
    const previousHotkey = savedSettings.hotkey;
    let registered = false;
    try {
      if (page === "快捷键") {
        await invoke("set_global_hotkey", { shortcut: settings.hotkey });
        registered = true;
      }
      const result = await callSidecar<Settings>("settings.save", { values: patch });
      if (page === "历史记录") await callSidecar("history.setLimit", { limit: result.history_limit });
      setSavedSettings((previous) => ({ ...previous, ...patch }));
      if (keys.includes("language")) void invoke("set_menu_language", { language: result.language }).catch(() => undefined);
      saved();
    } catch (caught) {
      if (registered) await invoke("set_global_hotkey", { shortcut: previousHotkey }).catch(() => undefined);
      setError(localizeError(language, caught));
    } finally { setSaving(false); }
  };
  const saveProfiles = async () => {
    if (saving || !profilesValid) return;
    setSaving(true); setError(""); setFeedback("");
    try {
      const value = await callSidecar<{
        api_enabled: boolean;
        active_profile_id: string;
        profiles: Profile[];
      }>("profiles.save", {
        api_enabled: apiEnabled,
        active_profile_id: activeId,
        profiles,
      });
      setApiEnabled(value.api_enabled);
      setSavedApiEnabled(value.api_enabled);
      setActiveId(value.active_profile_id);
      setSavedActiveId(value.active_profile_id);
      setProfiles(value.profiles);
      setSavedProfiles(value.profiles.map((profile) => ({ ...profile })));
      if (!value.profiles.some((profile) => profile.id === selectedId)) setSelectedId(value.profiles[0]?.id || "");
      saved();
    } catch (caught) {
      setError(localizeError(language, caught));
    } finally { setSaving(false); }
  };
  const patchProfile = (patch: Partial<Profile>) =>
    setProfiles((items) =>
      items.map((profile) =>
        profile.id === selectedId ? { ...profile, ...patch } : profile,
      ),
    );
  const fetchModels = async () => {
    if (!selected) return;
    const version = ++requestVersion.current;
    const id = selected.id;
    setBusy(true);
    setError("");
    try {
      const result = await callSidecar<{ models: string[]; message?: string }>(
        "api.listModels",
        { profile_id: selected.id, profile: selected },
      );
      if (version !== requestVersion.current || id !== selectedRef.current) return;
      setModels(result.models);
      notify(
        language === "en"
          ? t("已获取 {count} 个模型", { count: result.models.length })
          : result.message ||
            t("已获取 {count} 个模型", { count: result.models.length }),
      );
    } catch (caught) {
      if (version === requestVersion.current) setError(localizeError(language, caught));
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };
  const testProfile = async () => {
    if (!selected) return;
    const version = ++requestVersion.current;
    const id = selected.id;
    setBusy(true);
    setError("");
    try {
      const result = await callSidecar<{ message: string; models?: string[] }>(
        "api.testProfile",
        { profile_id: selected.id, profile: selected },
      );
      if (version !== requestVersion.current || id !== selectedRef.current) return;
      if (result.models) setModels(result.models);
      notify(selected.provider_type === "mathpix" ? t("已检查凭据格式；未联网验证") : (language === "en" ? t("配置测试成功") : result.message));
    } catch (caught) {
      if (version === requestVersion.current) setError(localizeError(language, caught));
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };
  const resetLayout = () => {
    localStorage.removeItem("formulaocr.layout.v2");
    localStorage.removeItem("formulaocr.layout.drawerOpen");
    void emit("formulaocr://reset-layout");
    notify(t("布局已重置"));
  };
  const addProfile = () => {
    const profile: Profile = {
      id: crypto.randomUUID().replaceAll("-", ""),
      name: t("新配置"),
      provider_type: "openai_compatible",
      base_url: "",
      model: "",
      enabled: true,
      timeout_s: 45,
      prompt_override: "",
    };
    setProfiles((items) => [...items, profile]);
    setSelectedId(profile.id);
  };
  return (
    <main
      className={inline ? "settings-app inline" : "settings-app standalone"}
    >
      <nav className="settings-tabs" aria-label={t("设置分类")}>
        {pages.map((item) => (
          <button
            key={item}
            className={
              page === item ? "settings-nav-item selected" : "settings-nav-item"
            }
            onClick={() => setPage(item)}
          >
            {t(item)}
          </button>
        ))}
      </nav>
      <section className="settings-page" aria-busy={saving}>
        <div className="page-heading">
          <h2>{t(page)}</h2>
          <p>
            {page === "自定义模型与 API"
              ? t("管理仅由你主动触发的远程重识别配置。")
              : t("FormulaOCR 的本机行为与显示选项。")}
          </p>
        </div>
        <fieldset className="settings-page-content" disabled={!ready || saving}>
          {page === "常规" && (
            <div className="settings-card">
              <Toggle
                checked={settings.auto_copy}
                onChange={(value) =>
                  setSettings({ ...settings, auto_copy: value })
                }
                title={t("识别完成后自动复制 Word 格式")}
                description={t("本地或 API 识别完成后自动写入剪贴板。")}
              />
              <Toggle
                checked={settings.hide_dock_on_close}
                onChange={(value) =>
                  setSettings({ ...settings, hide_dock_on_close: value })
                }
                title={t("关闭窗口时隐藏 Dock 图标")}
                description={t("菜单栏继续运行，可从菜单栏重新打开主窗口。")}
              />
              <label className="setting-field">
                <span>{t("界面语言")}</span>
                <select
                  value={language}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      language: normalizeLanguage(event.target.value),
                    })
                  }
                >
                  <option value="zh-CN">{t("简体中文")}</option>
                  <option value="en">English</option>
                </select>
              </label>
              <label className="setting-field">
                <span>{t("默认识别模式")}</span>
                <select
                  value={settings.default_recognition_mode}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      default_recognition_mode: event.target
                        .value as RecognitionMode,
                    })
                  }
                >
                  <option value="chemistry">{t("化学")}</option>
                  <option value="math">{t("数学")}</option>
                </select>
              </label>
            </div>
          )}
          {page === "界面与布局" && (
            <div className="settings-card">
              <p className="field-help">
                {t("窗口尺寸通过拖动调整；这里控制下次启动如何恢复窗口和分隔比例。")}
              </p>
              {[
                ["remember_window_history_closed", "记住尺寸，历史关闭"],
                ["restore_full_state", "完整恢复上次状态"],
                ["optimized_default", "每次使用优化默认布局"],
              ].map(([value, label]) => (
                <label className="radio-row" key={value}>
                  <input
                    type="radio"
                    name="layout"
                    checked={settings.layout_restore_mode === value}
                    onChange={() =>
                      setSettings({ ...settings, layout_restore_mode: value })
                    }
                  />
                  <span>{t(label)}</span>
                </label>
              ))}
              <button className="secondary-button" onClick={resetLayout}>
                <SlidersHorizontal size={17} />
                {t("立即重置布局")}
              </button>
            </div>
          )}
          {page === "快捷键" && (
            <div className="settings-card">
              <label className="setting-field">
                <span>{t("截图快捷键")}</span>
                <HotkeyRecorder
                  value={settings.hotkey}
                  onChange={(value) =>
                    setSettings({ ...settings, hotkey: value })
                  }
                  error={hotkeyError}
                  setError={setHotkeyError}
                  language={language}
                />
              </label>
            </div>
          )}
          {page === "历史记录" && (
            <div className="settings-card">
              <label className="setting-field">
                <span>{t("最多保存记录")}</span>
                <input
                  type="number"
                  min={20}
                  max={2000}
                  value={settings.history_limit}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      history_limit: Number(event.target.value),
                    })
                  }
                />
              </label>
              <p className="field-help">
                {t("范围为 20–2000 条，降低上限后会删除最旧记录。")}
              </p>
            </div>
          )}
          {page === "自定义模型与 API" && (
            <APISettings
              profiles={profiles}
              selected={selected}
              selectedId={selectedId}
              setSelectedId={setSelectedId}
              apiEnabled={apiEnabled}
              setApiEnabled={setApiEnabled}
              models={models}
              busy={busy}
              patchProfile={patchProfile}
              fetchModels={fetchModels}
              testProfile={testProfile}
              addProfile={addProfile}
              removeProfile={() => {
                if (!selected) return;
                setProfiles((items) =>
                  items.filter((profile) => profile.id !== selected.id),
                );
                setSelectedId(
                  profiles.find((profile) => profile.id !== selected.id)?.id ||
                    "",
                );
              }}
              setActiveId={setActiveId}
              activeId={activeId}
              language={language}
            />
          )}
        </fieldset>
        <footer className="settings-footer">
          <span className="error-text">{error}</span>
          <span className="toolbar-spacer" />
          {feedback && (
            <span className="saved-hint">
              <Check size={14} />
              {feedback}
            </span>
          )}
          <button
            className="toolbar-button primary"
            disabled={saving || !ready || (page === "自定义模型与 API"
                ? !profilesDirty || !profilesValid
                : !currentSettingsDirty || !pageValid || (page === "历史记录" && !historyValid))}
            aria-busy={saving}
            onClick={() =>
              void (page === "自定义模型与 API"
                ? saveProfiles()
                : saveSettings())
            }
          >
            {t("保存")}
          </button>
        </footer>
      </section>
      {confirmDiscard && (
        <div className="settings-confirm-backdrop" role="presentation">
          <div
            className="settings-confirm"
            role="alertdialog"
            aria-labelledby="discard-title"
            aria-describedby="discard-copy"
          >
            <h2 id="discard-title">{t("放弃未保存的更改？")}</h2>
            <p id="discard-copy">
              {t("设置中还有未保存的修改，关闭后这些修改将丢失。")}
            </p>
            <div className="settings-confirm-actions">
              <button
                className="secondary-button"
                onClick={() => { setConfirmDiscard(false); quittingRef.current = false; void invoke("cancel_quit"); }}
              >
                {t("取消")}
              </button>
              <button
                className="toolbar-button primary"
                onClick={discardAndClose}
              >
                {t("放弃更改")}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function Toggle({
  checked,
  onChange,
  title,
  description,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  title: string;
  description: string;
}) {
  return (
    <label className="toggle-row">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <strong>{title}</strong>
        <small>{description}</small>
      </span>
    </label>
  );
}

function APISettings({
  profiles,
  selected,
  selectedId,
  setSelectedId,
  apiEnabled,
  setApiEnabled,
  models,
  busy,
  patchProfile,
  fetchModels,
  testProfile,
  addProfile,
  removeProfile,
  activeId,
  setActiveId,
  language,
}: {
  profiles: Profile[];
  selected?: Profile;
  selectedId: string;
  setSelectedId: (id: string) => void;
  apiEnabled: boolean;
  setApiEnabled: (value: boolean) => void;
  models: string[];
  busy: boolean;
  patchProfile: (patch: Partial<Profile>) => void;
  fetchModels: () => Promise<void>;
  testProfile: () => Promise<void>;
  addProfile: () => void;
  removeProfile: () => void;
  activeId: string;
  setActiveId: (id: string) => void;
  language: AppLanguage;
}) {
  const t = (text: string, values?: Record<string, string | number>) =>
    translate(language, text, values);
  const validation = selected ? profileErrors(selected) : {};
  return (
    <div className="api-settings-shell">
      <div className="api-master-card">
        <Toggle
          checked={apiEnabled}
          onChange={setApiEnabled}
          title={t("启用 API 重识别")}
          description={t("只有主动点击主窗口的 API 重识别按钮时才会上传当前图片。")}
        />
      </div>
      <div className="api-workspace">
        <aside className="profile-list">
          <div className="profile-list-heading">
            <strong>{t("配置")}</strong>
            <span>{profiles.length}</span>
          </div>
          <div className="profile-list-scroll">
            {profiles.map((profile) => (
              <button
                className={
                  selectedId === profile.id
                    ? "profile-list-item selected"
                    : "profile-list-item"
                }
                key={profile.id}
                onClick={() => setSelectedId(profile.id)}
              >
                <span>{profile.name || t("未命名配置")}</span>
                <small>
                  {profile.provider_type === "mathpix"
                    ? "Mathpix"
                    : "OpenAI-compatible"}{" "}
                  · {profile.enabled ? t("启用") : t("停用")}
                </small>
              </button>
            ))}
          </div>
          <button className="secondary-button add-profile" onClick={addProfile}>
            {t("＋ 新增配置")}
          </button>
        </aside>
        <div className="profile-form">
          {selected ? (
            <>
              <div className="profile-form-heading">
                <div>
                  <strong>{selected.name || t("未命名配置")}</strong>
                  <small>
                    {selected.provider_type === "mathpix"
                      ? "Mathpix"
                      : "OpenAI-compatible"}
                  </small>
                </div>
                <label className="switch-field">
                  <input
                    type="checkbox"
                    checked={selected.enabled}
                    onChange={(event) =>
                      patchProfile({ enabled: event.target.checked })
                    }
                  />
                  <span>{t("启用此配置")}</span>
                </label>
              </div>
              <section className="form-section">
                <h3>{t("连接")}</h3>
                <div className="profile-form-grid">
                  <label className="setting-field">
                    <span>{t("配置名称")}</span>
                    <input
                      value={selected.name}
                      onChange={(event) =>
                        patchProfile({ name: event.target.value })
                      }
                    />
                    {validation.name && <small className="field-error">{t(validation.name)}</small>}
                  </label>
                  <label className="setting-field">
                    <span>{t("服务类型")}</span>
                    <select
                      value={selected.provider_type}
                      onChange={(event) =>
                        patchProfile({ provider_type: event.target.value })
                      }
                    >
                      <option value="openai_compatible">
                        OpenAI-compatible
                      </option>
                      <option value="mathpix">Mathpix</option>
                    </select>
                  </label>
                  <label className="setting-field full-row">
                    <span>Base URL</span>
                    <input
                      value={selected.base_url || ""}
                      placeholder={selected.provider_type === "mathpix" ? "https://api.mathpix.com" : "https://api.example.com/v1"}
                      onChange={(event) =>
                        patchProfile({ base_url: event.target.value })
                      }
                    />
                    {validation.base_url && <small className="field-error">{t(validation.base_url)}</small>}
                  </label>
                </div>
              </section>
              {selected.provider_type === "openai_compatible" ? (
                <section className="form-section">
                  <h3>{t("模型与凭据")}</h3>
                  <div className="profile-form-grid">
                    <label className="setting-field full-row">
                      <span>{t("模型 ID")}</span>
                      {validation.model && <small className="field-error">{t(validation.model)}</small>}
                      <div className="model-row">
                        <input
                          list="formulaocr-models"
                          value={selected.model || ""}
                          onChange={(event) =>
                            patchProfile({ model: event.target.value })
                          }
                        />
                        <datalist id="formulaocr-models">
                          {models.map((model) => (
                            <option key={model} value={model} />
                          ))}
                        </datalist>
                        <button
                          className="secondary-button compact-button"
                          disabled={busy}
                          onClick={() => void fetchModels()}
                        >
                          {busy ? t("获取中…") : t("获取模型")}
                        </button>
                      </div>
                    </label>
                    <label className="setting-field full-row">
                      <span>
                        API Key{" "}
                        <small>{t("留空将保留 Keychain 中已保存的密钥")}</small>
                      </span>
                      <input
                        type="password"
                        placeholder={t("输入新密钥，或留空保持不变")}
                        value={selected.api_key || ""}
                        onChange={(event) =>
                          patchProfile({ api_key: event.target.value })
                        }
                      />
                    </label>
                    <label className="setting-field full-row">
                      <span>
                        {t("高级提示词")} <small>{t("留空使用内置公式转录提示")}</small>
                      </span>
                      <textarea
                        value={selected.prompt_override || ""}
                        onChange={(event) =>
                          patchProfile({ prompt_override: event.target.value })
                        }
                        placeholder={t("使用内置公式转录提示")}
                      />
                    </label>
                  </div>
                </section>
              ) : (
                <section className="form-section">
                  <h3>{t("Mathpix 凭据")}</h3>
                  <div className="profile-form-grid">
                    <label className="setting-field">
                      <span>App ID</span>
                      <input
                        value={selected.app_id || ""}
                        onChange={(event) =>
                          patchProfile({ app_id: event.target.value })
                        }
                      />
                    </label>
                    <label className="setting-field">
                      <span>
                        App Key <small>{t("留空保留已保存密钥")}</small>
                      </span>
                      <input
                        type="password"
                        placeholder={t("Keychain 中已保存")}
                        value={selected.app_key || ""}
                        onChange={(event) =>
                          patchProfile({ app_key: event.target.value })
                        }
                      />
                    </label>
                  </div>
                </section>
              )}
              <section className="form-section compact-section">
                <div className="timeout-row">
                  <label className="inline-field">
                    <span>{t("请求超时")}</span>
                    <input
                      type="number"
                      min={5}
                      max={120}
                      value={selected.timeout_s || ""}
                      onChange={(event) =>
                        patchProfile({
                          timeout_s: Number(event.target.value),
                        })
                      }
                    />
                    <span>{t("秒")}</span>
                  </label>
                  <span className="field-help">{t("范围 5–120 秒")}</span>
                </div>
                {validation.timeout_s && <small className="field-error">{t(validation.timeout_s)}</small>}
              </section>
              <div className="profile-actions">
                <button className="text-danger" onClick={removeProfile}>
                  <Trash2 size={16} />
                  {t("删除配置")}
                </button>
                <span className="toolbar-spacer" />
                <button
                  className="secondary-button"
                  onClick={() => void testProfile()}
                  disabled={busy}
                >
                  <RefreshCw size={16} />
                  {busy ? t("测试中…") : t("测试配置")}
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setActiveId(selected.id)}
                  disabled={activeId === selected.id}
                >
                  {activeId === selected.id ? t("当前配置") : t("设为当前")}
                </button>
              </div>
            </>
          ) : (
            <div className="empty-state">{t("请选择或新增一个 API 配置")}</div>
          )}
        </div>
      </div>
    </div>
  );
}
