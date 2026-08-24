import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ClipboardPaste,
  Copy,
  FolderOpen,
  History,
  ImageUp,
  Settings,
  Sparkles,
  Undo2,
  Redo2,
  RotateCcw,
  RefreshCw,
  Trash2,
  X,
  Check,
  SlidersHorizontal,
} from "lucide-react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { emit, listen } from "@tauri-apps/api/event";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { callSidecar } from "./sidecar";

type Source = "local" | "api";
type RecognitionMode = "chemistry" | "math";
type Settings = {
  auto_copy: boolean;
  hide_dock_on_close: boolean;
  hotkey: string;
  history_limit: number;
  layout_restore_mode: string;
  layout_version?: number;
  default_recognition_mode: RecognitionMode;
};
type Profile = {
  id: string;
  name: string;
  enabled: boolean;
  provider_type: string;
  base_url?: string;
  model?: string;
  timeout_s?: number;
  prompt_override?: string;
  api_key?: string;
  app_id?: string;
  app_key?: string;
};
type RecordItem = {
  id: string;
  image_path: string;
  created_at: number;
  updated_at: number;
  local_raw_latex: string;
  local_formatted_latex?: string;
  local_draft_latex: string;
  local_render_error?: string | null;
  api_raw_latex?: string | null;
  api_formatted_latex?: string | null;
  api_draft_latex?: string | null;
  api_profile_name?: string | null;
  api_model?: string | null;
  active_source?: string;
  recognition_mode?: RecognitionMode;
  has_api?: boolean;
};
type Layout = { image: number; result: number; drawerWidth: number };

const defaults: Settings = {
  auto_copy: false,
  hide_dock_on_close: true,
  hotkey: "ctrl+alt+cmd+o",
  history_limit: 200,
  layout_restore_mode: "remember_window_history_closed",
  default_recognition_mode: "chemistry",
};

function pngBase64ToBlob(value: string): Blob {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1)
    bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], { type: "image/png" });
}

function openSettings(page = "常规", onFallback?: () => void) {
  void (async () => {
    try {
      const existing = await WebviewWindow.getByLabel("settings");
      if (existing) {
        await existing.show();
        await existing.setFocus();
        await emit("formulaocr://settings-page", page);
        return;
      }
      const child = new WebviewWindow("settings", {
        url: `index.html?settings=1&page=${encodeURIComponent(page)}`,
        title: "FormulaOCR 设置",
        width: 820,
        height: 500,
        minWidth: 760,
        minHeight: 420,
        resizable: true,
      });
      let created = false;
      void child.once("tauri://created", () => {
        created = true;
      });
      void child.once("tauri://error", () => onFallback?.());
      window.setTimeout(() => {
        if (!created) onFallback?.();
      }, 1200);
    } catch {
      onFallback?.();
    }
  })();
}

function LatexEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const internal = useRef(false);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);
  useEffect(() => {
    if (!host.current) return;
    const state = EditorState.create({
      doc: value,
      extensions: [
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged && !internal.current)
            onChangeRef.current(update.state.doc.toString());
        }),
      ],
    });
    view.current = new EditorView({ state, parent: host.current });
    return () => {
      view.current?.destroy();
      view.current = null;
    };
  }, []);
  useEffect(() => {
    if (!view.current || view.current.state.doc.toString() === value) return;
    internal.current = true;
    view.current.dispatch({
      changes: { from: 0, to: view.current.state.doc.length, insert: value },
    });
    internal.current = false;
  }, [value]);
  return <div ref={host} className="latex-editor" aria-label="LaTeX 编辑器" />;
}

function MathPreview({ latex }: { latex: string }) {
  const renderId = useRef(0);
  const [mathml, setMathml] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const currentId = ++renderId.current;
    if (!latex.trim()) {
      setMathml("");
      setError("");
      setLoading(false);
      return;
    }
    setMathml("");
    setError("");
    setLoading(true);
    const timer = window.setTimeout(() => {
      void callSidecar<{ mathml: string }>("conversion.toMathML", { latex })
        .then((result) => {
          if (renderId.current !== currentId) return;
          setMathml(result.mathml);
          setLoading(false);
        })
        .catch((caught) => {
          if (renderId.current !== currentId) return;
          setMathml("");
          setLoading(false);
          setError(caught instanceof Error ? caught.message : String(caught));
        });
    }, 120);
    return () => {
      window.clearTimeout(timer);
      renderId.current += 1;
    };
  }, [latex]);
  return (
    <div className="preview-surface">
      {mathml && (
        <div
          className="mathml-content"
          dangerouslySetInnerHTML={{ __html: mathml }}
        />
      )}
      {!latex && <span className="muted preview-message">公式将在这里预览</span>}
      {loading && <span className="muted preview-message">正在生成预览…</span>}
      {error && (
        <span className="preview-error preview-message">无法渲染公式：{error}</span>
      )}
    </div>
  );
}

function HotkeyRecorder({
  value,
  onChange,
  error,
  setError,
}: {
  value: string;
  onChange: (value: string) => void;
  error: string;
  setError: (value: string) => void;
}) {
  const [recording, setRecording] = useState(false);
  const modifierKeys = new Set(["Meta", "Control", "Alt", "Shift"]);
  useEffect(() => {
    if (!recording) return;
    const onKeyDown = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") {
        onChange("");
        setError("");
        setRecording(false);
        return;
      }
      if (modifierKeys.has(event.key)) return;
      const parts: string[] = [];
      if (event.ctrlKey) parts.push("ctrl");
      if (event.altKey) parts.push("alt");
      if (event.shiftKey) parts.push("shift");
      if (event.metaKey) parts.push("cmd");
      if (!parts.length) {
        setError("请使用至少一个修饰键和一个主键");
        return;
      }
      const key =
        event.key.length === 1
          ? event.key.toLowerCase()
          : event.key.toLowerCase().replace("arrow", "");
      if (!key || key === "unidentified") {
        setError("不支持的主键");
        return;
      }
      parts.push(key);
      onChange(parts.join("+"));
      setError("");
      setRecording(false);
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [recording, onChange, setError]);
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
    : "未设置";
  return (
    <div className="hotkey-recorder">
      <button
        className={recording ? "keycap recording" : "keycap"}
        onClick={() => {
          setRecording(true);
          setError("");
        }}
      >
        {recording ? "请按组合键…" : display}
      </button>
      <span className="field-help">点击后按组合键，Esc 清空</span>
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

function SettingsCenter({
  inline = false,
  initialPage,
  onClose,
}: {
  inline?: boolean;
  initialPage?: string;
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
  const [page, setPage] = useState(initialPage || params.get("page") || "常规");
  const [settings, setSettings] = useState<Settings>(defaults);
  const [savedSettings, setSavedSettings] = useState<Settings>(defaults);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [savedProfiles, setSavedProfiles] = useState<Profile[]>([]);
  const [apiEnabled, setApiEnabled] = useState(false);
  const [savedApiEnabled, setSavedApiEnabled] = useState(false);
  const [activeId, setActiveId] = useState("");
  const [savedActiveId, setSavedActiveId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [hotkeyError, setHotkeyError] = useState("");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const allowCloseRef = useRef(false);
  const selected = profiles.find((profile) => profile.id === selectedId);
  const settingsDirty =
    JSON.stringify(settings) !== JSON.stringify(savedSettings);
  const profilesDirty =
    apiEnabled !== savedApiEnabled ||
    activeId !== savedActiveId ||
    JSON.stringify(profiles) !== JSON.stringify(savedProfiles);
  const pageKeys: Record<string, (keyof Settings)[]> = {
    常规: ["auto_copy", "hide_dock_on_close", "default_recognition_mode"],
    界面与布局: ["layout_restore_mode"],
    快捷键: ["hotkey"],
    历史记录: ["history_limit"],
  };
  const currentSettingsDirty = (pageKeys[page] || []).some(
    (key) => settings[key] !== savedSettings[key],
  );
  useEffect(() => {
    void callSidecar<Settings>("settings.get")
      .then((value) => {
        setSettings({ ...defaults, ...value });
        setSavedSettings({ ...defaults, ...value });
        void invoke("set_global_hotkey", {
          shortcut: value.hotkey || "",
        }).catch(() => undefined);
      })
      .catch((caught) => setError(String(caught)));
    void callSidecar<{
      api_enabled: boolean;
      active_profile_id: string;
      profiles: Profile[];
    }>("profiles.list")
      .then((value) => {
        setApiEnabled(value.api_enabled);
        setSavedApiEnabled(value.api_enabled);
        setActiveId(value.active_profile_id);
        setSavedActiveId(value.active_profile_id);
        setProfiles(value.profiles);
        setSavedProfiles(value.profiles.map((profile) => ({ ...profile })));
        setSelectedId(value.active_profile_id || value.profiles[0]?.id || "");
      })
      .catch((caught) => setError(String(caught)));
  }, []);
  useEffect(() => {
    let stop: (() => void) | undefined;
    void listen<string>("formulaocr://settings-page", (event) =>
      setPage(event.payload),
    ).then((unlisten) => {
      stop = unlisten;
    });
    return () => stop?.();
  }, []);
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
          stop = unlisten;
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      stop?.();
    };
  }, [inline, page]);
  useEffect(() => {
    if (inline) return;
    let unlisten: (() => void) | undefined;
    void getCurrentWindow()
      .onCloseRequested((event) => {
        if (allowCloseRef.current) return;
        if (settingsDirty || profilesDirty) {
          event.preventDefault();
          setConfirmDiscard(true);
        }
      })
      .then((stop) => {
        unlisten = stop;
      });
    return () => unlisten?.();
  }, [inline, settingsDirty, profilesDirty]);
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
    if (inline) {
      onClose?.();
      return;
    }
    allowCloseRef.current = true;
    // Destroy bypasses a second close-request round-trip after the user has
    // explicitly confirmed discarding the draft.
    void getCurrentWindow().destroy();
  };
  const saved = (message = "✓ 已保存") => {
    void emit("formulaocr://settings-updated");
    setFeedback(message);
    window.setTimeout(() => setFeedback(""), 1500);
  };
  const saveSettings = async () => {
    if (hotkeyError) return;
    try {
      const persisted = await callSidecar<Settings>("settings.get");
      const values = { ...defaults, ...persisted };
      for (const key of pageKeys[page] || [])
        (values as Record<string, unknown>)[key] = settings[key];
      if (page === "快捷键")
        await invoke("set_global_hotkey", { shortcut: settings.hotkey });
      const value = await callSidecar<Settings>("settings.save", {
        values: { ...values, layout_version: 3 },
      });
      setSavedSettings((previous) => {
        const next = { ...previous };
        for (const key of pageKeys[page] || [])
          (next as Record<string, unknown>)[key] = value[key];
        return next;
      });
      if (page === "历史记录")
        await callSidecar("history.setLimit", {
          limit: settings.history_limit,
        });
      saved();
    } catch (caught) {
      setError(String(caught));
    }
  };
  const saveProfiles = async () => {
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
      setSelectedId(value.active_profile_id || value.profiles[0]?.id || "");
      saved();
    } catch (caught) {
      setError(String(caught));
    }
  };
  const patchProfile = (patch: Partial<Profile>) =>
    setProfiles((items) =>
      items.map((profile) =>
        profile.id === selectedId ? { ...profile, ...patch } : profile,
      ),
    );
  const fetchModels = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const result = await callSidecar<{ models: string[]; message?: string }>(
        "api.listModels",
        { profile_id: selected.id, profile: selected },
      );
      setModels(result.models);
      saved(result.message || `已获取 ${result.models.length} 个模型`);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };
  const testProfile = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const result = await callSidecar<{ message: string; models?: string[] }>(
        "api.testProfile",
        { profile_id: selected.id, profile: selected },
      );
      if (result.models) setModels(result.models);
      saved(result.message);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };
  const resetLayout = () => {
    localStorage.removeItem("formulaocr.layout.v2");
    saved("布局已重置");
  };
  const addProfile = () => {
    const profile: Profile = {
      id: crypto.randomUUID().replaceAll("-", ""),
      name: "新配置",
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
      <nav className="settings-tabs" aria-label="设置分类">
        {pages.map((item) => (
          <button
            key={item}
            className={
              page === item ? "settings-nav-item selected" : "settings-nav-item"
            }
            onClick={() => setPage(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      <section className="settings-page">
        <div className="page-heading">
          <h2>{page}</h2>
          <p>
            {page === "自定义模型与 API"
              ? "管理仅由你主动触发的远程重识别配置。"
              : "FormulaOCR 的本机行为与显示选项。"}
          </p>
        </div>
        <div className="settings-page-content">
          {page === "常规" && (
            <div className="settings-card">
              <Toggle
                checked={settings.auto_copy}
                onChange={(value) =>
                  setSettings({ ...settings, auto_copy: value })
                }
                title="识别完成后自动复制 Word 格式"
                description="本地或 API 识别完成后自动写入剪贴板。"
              />
              <Toggle
                checked={settings.hide_dock_on_close}
                onChange={(value) =>
                  setSettings({ ...settings, hide_dock_on_close: value })
                }
                title="关闭窗口时隐藏 Dock 图标"
                description="菜单栏继续运行，可从菜单栏重新打开主窗口。"
              />
              <label className="setting-field">
                <span>默认识别模式</span>
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
                  <option value="chemistry">化学</option>
                  <option value="math">数学</option>
                </select>
              </label>
            </div>
          )}
          {page === "界面与布局" && (
            <div className="settings-card">
              <p className="field-help">
                窗口尺寸通过拖动调整；这里控制下次启动如何恢复窗口和分隔比例。
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
                  <span>{label}</span>
                </label>
              ))}
              <button className="secondary-button" onClick={resetLayout}>
                <SlidersHorizontal size={17} />
                立即重置布局
              </button>
            </div>
          )}
          {page === "快捷键" && (
            <div className="settings-card">
              <label className="setting-field">
                <span>截图快捷键</span>
                <HotkeyRecorder
                  value={settings.hotkey}
                  onChange={(value) =>
                    setSettings({ ...settings, hotkey: value })
                  }
                  error={hotkeyError}
                  setError={setHotkeyError}
                />
              </label>
            </div>
          )}
          {page === "历史记录" && (
            <div className="settings-card">
              <label className="setting-field">
                <span>最多保存记录</span>
                <input
                  type="number"
                  min={20}
                  max={2000}
                  value={settings.history_limit}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      history_limit: Math.max(
                        20,
                        Math.min(2000, Number(event.target.value) || 200),
                      ),
                    })
                  }
                />
              </label>
              <p className="field-help">
                范围为 20–2000 条，降低上限后会删除最旧记录。
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
            />
          )}
        </div>
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
            disabled={
              page === "自定义模型与 API"
                ? !profilesDirty
                : !currentSettingsDirty || Boolean(hotkeyError)
            }
            onClick={() =>
              void (page === "自定义模型与 API"
                ? saveProfiles()
                : saveSettings())
            }
          >
            保存
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
            <h2 id="discard-title">放弃未保存的更改？</h2>
            <p id="discard-copy">
              设置中还有未保存的修改，关闭后这些修改将丢失。
            </p>
            <div className="settings-confirm-actions">
              <button
                className="secondary-button"
                onClick={() => setConfirmDiscard(false)}
              >
                取消
              </button>
              <button
                className="toolbar-button primary"
                onClick={discardAndClose}
              >
                放弃更改
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
}) {
  return (
    <div className="api-settings-shell">
      <div className="api-master-card">
        <Toggle
          checked={apiEnabled}
          onChange={setApiEnabled}
          title="启用 API 重识别"
          description="只有主动点击主窗口的 API 重识别按钮时才会上传当前图片。"
        />
      </div>
      <div className="api-workspace">
        <aside className="profile-list">
          <div className="profile-list-heading">
            <strong>配置</strong>
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
                <span>{profile.name || "未命名配置"}</span>
                <small>
                  {profile.provider_type === "mathpix"
                    ? "Mathpix"
                    : "OpenAI-compatible"}{" "}
                  · {profile.enabled ? "启用" : "停用"}
                </small>
              </button>
            ))}
          </div>
          <button className="secondary-button add-profile" onClick={addProfile}>
            ＋ 新增配置
          </button>
        </aside>
        <div className="profile-form">
          {selected ? (
            <>
              <div className="profile-form-heading">
                <div>
                  <strong>{selected.name || "未命名配置"}</strong>
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
                  <span>启用此配置</span>
                </label>
              </div>
              <section className="form-section">
                <h3>连接</h3>
                <div className="profile-form-grid">
                  <label className="setting-field">
                    <span>配置名称</span>
                    <input
                      value={selected.name}
                      onChange={(event) =>
                        patchProfile({ name: event.target.value })
                      }
                    />
                  </label>
                  <label className="setting-field">
                    <span>服务类型</span>
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
                      onChange={(event) =>
                        patchProfile({ base_url: event.target.value })
                      }
                    />
                  </label>
                </div>
              </section>
              {selected.provider_type === "openai_compatible" ? (
                <section className="form-section">
                  <h3>模型与凭据</h3>
                  <div className="profile-form-grid">
                    <label className="setting-field full-row">
                      <span>模型 ID</span>
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
                          {busy ? "获取中…" : "获取模型"}
                        </button>
                      </div>
                    </label>
                    <label className="setting-field full-row">
                      <span>
                        API Key{" "}
                        <small>留空将保留 Keychain 中已保存的密钥</small>
                      </span>
                      <input
                        type="password"
                        placeholder="Keychain 中已保存"
                        value={selected.api_key || ""}
                        onChange={(event) =>
                          patchProfile({ api_key: event.target.value })
                        }
                      />
                    </label>
                    <label className="setting-field full-row">
                      <span>
                        高级提示词 <small>留空使用内置公式转录提示</small>
                      </span>
                      <textarea
                        value={selected.prompt_override || ""}
                        onChange={(event) =>
                          patchProfile({ prompt_override: event.target.value })
                        }
                        placeholder="使用内置公式转录提示"
                      />
                    </label>
                  </div>
                </section>
              ) : (
                <section className="form-section">
                  <h3>Mathpix 凭据</h3>
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
                        App Key <small>留空保留已保存密钥</small>
                      </span>
                      <input
                        type="password"
                        placeholder="Keychain 中已保存"
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
                    <span>请求超时</span>
                    <input
                      type="number"
                      min={5}
                      max={120}
                      value={selected.timeout_s || 45}
                      onChange={(event) =>
                        patchProfile({
                          timeout_s: Math.max(
                            5,
                            Math.min(120, Number(event.target.value) || 45),
                          ),
                        })
                      }
                    />
                    <span>秒</span>
                  </label>
                  <span className="field-help">范围 5–120 秒</span>
                </div>
              </section>
              <div className="profile-actions">
                <button className="text-danger" onClick={removeProfile}>
                  <Trash2 size={16} />
                  删除配置
                </button>
                <span className="toolbar-spacer" />
                <button
                  className="secondary-button"
                  onClick={() => void testProfile()}
                  disabled={busy}
                >
                  <RefreshCw size={16} />
                  {busy ? "测试中…" : "测试配置"}
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setActiveId(selected.id)}
                  disabled={activeId === selected.id}
                >
                  {activeId === selected.id ? "当前配置" : "设为当前"}
                </button>
              </div>
            </>
          ) : (
            <div className="empty-state">请选择或新增一个 API 配置</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function MainApp() {
  const [drawer, setDrawer] = useState(false);
  const [settingsFallback, setSettingsFallback] = useState(false);
  const [settings, setSettings] = useState<Settings>(defaults);
  const [apiEnabled, setApiEnabled] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeId, setActiveId] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [selectedRecords, setSelectedRecords] = useState<string[]>([]);
  const [latex, setLatex] = useState("");
  const [localLatex, setLocalLatex] = useState("");
  const [apiLatex, setApiLatex] = useState("");
  const [localOriginal, setLocalOriginal] = useState("");
  const [apiOriginal, setApiOriginal] = useState("");
  const [localFormatted, setLocalFormatted] = useState("");
  const [apiFormatted, setApiFormatted] = useState("");
  const [mode, setMode] = useState<RecognitionMode>("chemistry");
  const [source, setSource] = useState<Source>("local");
  const [stacks, setStacks] = useState<
    Record<Source, { undo: string[]; redo: string[] }>
  >({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
  const [status, setStatus] = useState("正在后台准备离线模型…");
  const [busy, setBusy] = useState(false);
  const [layout, setLayout] = useState<Layout>(() => {
    try {
      const value = JSON.parse(
        localStorage.getItem("formulaocr.layout.v2") || "{}",
      );
      return {
        image: value.image || 42,
        result: value.result || 50,
        drawerWidth: value.drawerWidth || 320,
      };
    } catch {
      return { image: 42, result: 50, drawerWidth: 320 };
    }
  });
  const [reload, setReload] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const imageUrlRef = useRef<string | null>(null);
  const imageIdRef = useRef<string | null>(null);
  const requestId = useRef(0);
  const draftTimer = useRef<number | null>(null);
  const latexRef = useRef("");
  const editGroup = useRef<{ source: Source; lastAt: number }>({
    source: "local",
    lastAt: 0,
  });
  const captureInProgress = useRef(false);
  const workspace = useRef<HTMLElement>(null);
  const resultPane = useRef<HTMLElement>(null);
  const activeOriginal = source === "local" ? localOriginal : apiOriginal;
  const activeProfile = profiles.find((profile) => profile.id === activeId);
  useEffect(() => {
    latexRef.current = latex;
  }, [latex]);
  const resetEditGroup = (nextSource: Source = source) => {
    editGroup.current = { source: nextSource, lastAt: 0 };
  };
  const reloadSettings = useCallback(() => {
    void callSidecar<Settings>("settings.get")
      .then((value) => {
        setSettings({ ...defaults, ...value });
        void invoke("set_global_hotkey", {
          shortcut: value.hotkey || "",
        }).catch(() => undefined);
      })
      .catch(() => undefined);
    void callSidecar<{
      api_enabled: boolean;
      active_profile_id: string;
      profiles: Profile[];
    }>("profiles.list")
      .then((value) => {
        setApiEnabled(value.api_enabled);
        setActiveId(value.active_profile_id);
        setProfiles(value.profiles);
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    reloadSettings();
  }, [reloadSettings, reload]);
  useEffect(() => {
    let active = true;
    void callSidecar<{ loaded: boolean; elapsed_ms: number }>("ocr.preload")
      .then((result) => {
        if (!active) return;
        setStatus((current) =>
          current === "正在后台准备离线模型…"
            ? `离线模型已就绪 · ${Math.round(result.elapsed_ms)} ms`
            : current,
        );
      })
      .catch((error) => {
        if (!active) return;
        setStatus((current) =>
          current === "正在后台准备离线模型…"
            ? `离线模型加载失败：${error instanceof Error ? error.message : String(error)}`
            : current,
        );
      });
    return () => {
      active = false;
    };
  }, []);
  const showSettings = useCallback(
    (page = "常规") => openSettings(page, () => setSettingsFallback(true)),
    [],
  );
  useEffect(() => {
    let stop: (() => void) | undefined;
    void listen<string>("formulaocr://open-settings", (event) =>
      showSettings(event.payload || "常规"),
    ).then((unlisten) => {
      stop = unlisten;
    });
    return () => stop?.();
  }, [showSettings]);
  useEffect(() => {
    let stop: (() => void) | undefined;
    void listen("formulaocr://settings-updated", () =>
      setReload((value) => value + 1),
    ).then((unlisten) => {
      stop = unlisten;
    });
    return () => stop?.();
  }, []);
  useEffect(() => {
    let stop: (() => void) | undefined;
    void listen("formulaocr://window-close-requested", () => {
      void invoke("set_activation_policy", {
        accessory: settings.hide_dock_on_close,
      });
    }).then((unlisten) => {
      stop = unlisten;
    });
    return () => stop?.();
  }, [settings.hide_dock_on_close]);
  useEffect(() => {
    localStorage.setItem("formulaocr.layout.v2", JSON.stringify(layout));
    if (settings.layout_restore_mode === "restore_full_state")
      localStorage.setItem("formulaocr.layout.drawerOpen", drawer ? "1" : "0");
  }, [layout, drawer, settings.layout_restore_mode]);
  useEffect(() => {
    if (settings.layout_restore_mode === "optimized_default") {
      setLayout({ image: 42, result: 50, drawerWidth: 320 });
      setDrawer(false);
    } else if (settings.layout_restore_mode === "restore_full_state")
      setDrawer(localStorage.getItem("formulaocr.layout.drawerOpen") === "1");
  }, [settings.layout_restore_mode]);
  useEffect(() => {
    if (!drawer) return;
    void callSidecar<{ records: RecordItem[] }>("history.list")
      .then((value) => setRecords(value.records))
      .catch(() => setRecords([]));
  }, [drawer]);
  useEffect(() => {
    const listener = () => reloadSettings();
    window.addEventListener("focus", listener);
    return () => window.removeEventListener("focus", listener);
  }, [reloadSettings]);
  useEffect(
    () => () => {
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
      if (imageIdRef.current)
        void callSidecar("image.release", { image_id: imageIdRef.current });
    },
    [],
  );

  const openImage = async (blob: Blob, token: number, stagedPath?: string) => {
    const previousId = imageIdRef.current;
    imageIdRef.current = null;
    setImageId(null);
    if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    const url = URL.createObjectURL(blob);
    imageUrlRef.current = url;
    // Publish the image before any sidecar work.  The old flow waited for
    // image.open/model startup first, making paste and screenshot appear
    // frozen until OCR completed.
    setImageUrl(url);
    // A new image starts a completely new editing session.  Clear both
    // source histories immediately so Undo can never cross image boundaries
    // while the new OCR request is still running.
    setLatex("");
    setLocalLatex("");
    setApiLatex("");
    setLocalOriginal("");
    setApiOriginal("");
    setLocalFormatted("");
    setApiFormatted("");
    setSource("local");
    setHistoryId(null);
    setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
    latexRef.current = "";
    resetEditGroup("local");
    setStatus("图片已载入，正在识别…");
    if (previousId)
      void callSidecar("image.release", { image_id: previousId }).catch(
        () => undefined,
      );
    await new Promise<void>((resolve) => {
      let finished = false;
      const finish = () => {
        if (!finished) {
          finished = true;
          resolve();
        }
      };
      window.requestAnimationFrame(finish);
      // Global-shortcut captures can start while the main window is hidden;
      // WebKit may throttle animation frames in that state.
      window.setTimeout(finish, 32);
    });
    const path =
      stagedPath ||
      (await invoke<string>("stage_image_bytes", {
        bytes: Array.from(new Uint8Array(await blob.arrayBuffer())),
      }));
    const opened = await callSidecar<{ image_id: string }>("image.openPath", {
      path,
    });
    if (token !== requestId.current) {
      await callSidecar("image.release", { image_id: opened.image_id }).catch(
        () => undefined,
      );
      return null;
    }
    imageIdRef.current = opened.image_id;
    setImageId(opened.image_id);
    return opened.image_id;
  };
  const recognize = useCallback(
    async (blob: Blob) => {
      const token = ++requestId.current;
      setBusy(true);
      setStatus("正在载入图片…");
      try {
        const id = await openImage(blob, token);
        if (!id) return;
        const result = await callSidecar<{
          formatted_latex?: string;
          raw_latex?: string;
          elapsed_ms?: number;
          history_id?: string;
        }>("ocr.recognize", { image_id: id, mode });
        if (token !== requestId.current) return;
        const value = result.formatted_latex || result.raw_latex || "";
        const raw = result.raw_latex || value;
        setLatex(value);
        setLocalLatex(value);
        setApiLatex("");
        setLocalOriginal(raw);
        setLocalFormatted(value);
        setApiOriginal("");
        setApiFormatted("");
        setSource("local");
        setHistoryId(result.history_id || null);
        setStacks({
          local: { undo: [], redo: [] },
          api: { undo: [], redo: [] },
        });
        latexRef.current = value;
        resetEditGroup("local");
        setStatus(
          `识别完成${result.elapsed_ms ? ` · ${Math.round(result.elapsed_ms)} ms` : ""}`,
        );
        if (settings.auto_copy && value) await copyWord(value);
      } catch (error) {
        if (token === requestId.current)
          setStatus(
            `识别失败：${error instanceof Error ? error.message : String(error)}`,
          );
      } finally {
        if (token === requestId.current) setBusy(false);
      }
    },
    [settings.auto_copy, mode],
  );
  const recognizeStaged = useCallback(
    async (blob: Blob, stagedPath: string) => {
      const token = ++requestId.current;
      setBusy(true);
      try {
        const id = await openImage(blob, token, stagedPath);
        if (!id) return;
        const result = await callSidecar<{
          formatted_latex?: string;
          raw_latex?: string;
          elapsed_ms?: number;
          history_id?: string;
        }>("ocr.recognize", { image_id: id, mode });
        if (token !== requestId.current) return;
        const value = result.formatted_latex || result.raw_latex || "";
        const raw = result.raw_latex || value;
        setLatex(value);
        setLocalLatex(value);
        setLocalOriginal(raw);
        setLocalFormatted(value);
        setApiLatex("");
        setApiOriginal("");
        setApiFormatted("");
        setSource("local");
        setHistoryId(result.history_id || null);
        setStacks({
          local: { undo: [], redo: [] },
          api: { undo: [], redo: [] },
        });
        latexRef.current = value;
        resetEditGroup("local");
        setStatus(
          `识别完成${result.elapsed_ms ? ` · ${Math.round(result.elapsed_ms)} ms` : ""}`,
        );
        if (settings.auto_copy && value) await copyWord(value);
      } catch (error) {
        if (token === requestId.current)
          setStatus(
            `识别失败：${error instanceof Error ? error.message : String(error)}`,
          );
      } finally {
        if (token === requestId.current) setBusy(false);
      }
    },
    [settings.auto_copy, mode],
  );
  useEffect(() => {
    const paste = (event: ClipboardEvent) => {
      const image = Array.from(event.clipboardData?.items || [])
        .find((item) => item.type.startsWith("image/"))
        ?.getAsFile();
      if (image) {
        event.preventDefault();
        void recognize(image);
      }
    };
    window.addEventListener("paste", paste);
    return () => window.removeEventListener("paste", paste);
  }, [recognize]);
  const scheduleDraftSave = (
    value: string,
    nextSource: Source = source,
    nextHistoryId: string | null = historyId,
  ) => {
    if (draftTimer.current !== null) window.clearTimeout(draftTimer.current);
    if (!nextHistoryId) return;
    draftTimer.current = window.setTimeout(() => {
      draftTimer.current = null;
      void callSidecar("history.updateDraft", {
        id: nextHistoryId,
        source: nextSource,
        latex: value,
      });
    }, 500);
  };
  const updateLatex = (value: string) => {
    const now = performance.now();
    const previous = latexRef.current;
    if (value === previous) return;
    const startsNewGroup =
      editGroup.current.source !== source ||
      now - editGroup.current.lastAt > 600;
    setStacks((state) => ({
      ...state,
      [source]: {
        undo: startsNewGroup
          ? [...state[source].undo, previous].slice(-100)
          : state[source].undo,
        redo: [],
      },
    }));
    editGroup.current = { source, lastAt: now };
    latexRef.current = value;
    setLatex(value);
    if (source === "local") setLocalLatex(value);
    else setApiLatex(value);
    scheduleDraftSave(value);
  };
  const copyWord = async (value = latex) => {
    if (!value.trim()) return setStatus("没有可复制的 LaTeX");
    try {
      const mathml = (
        await callSidecar<{ mathml: string }>("conversion.toMathML", {
          latex: value,
        })
      ).mathml;
      await invoke("native_copy_word", { latex: value, mathml });
      setStatus("已复制 Word 格式");
    } catch (error) {
      setStatus(
        `复制 Word 失败：${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };
  const screenshot = useCallback(async () => {
    if (busy || captureInProgress.current) return;
    captureInProgress.current = true;
    setStatus("请拖动选择截图区域，Esc 取消");
    try {
      const path = await invoke<string>("native_screenshot");
      const response = await fetch(convertFileSrc(path));
      if (!response.ok) throw new Error("无法读取截图结果");
      const blob = await response.blob();
      // recognize() publishes the Blob URL first; the now-asynchronous Rust
      // bridge lets WebKit paint it while image.open and ONNX inference run.
      await recognizeStaged(blob, path);
    } catch (error) {
      setStatus(
        `截图失败：${error instanceof Error ? error.message : String(error)}`,
      );
    } finally {
      captureInProgress.current = false;
    }
  }, [busy, recognizeStaged]);
  useEffect(() => {
    let stop: (() => void) | undefined;
    void listen(
      "formulaocr://screenshot-requested",
      () => void screenshot(),
    ).then((unlisten) => {
      stop = unlisten;
    });
    return () => stop?.();
  }, [screenshot]);
  const apiRecognize = async () => {
    if (!imageId || !activeId) return setStatus("没有当前图片或可用 API 配置");
    setBusy(true);
    setStatus("正在进行 API 重识别…");
    try {
      const result = await callSidecar<{
        raw_latex: string;
        formatted_latex?: string;
        profile_name: string;
        history_id?: string;
      }>("api.recognize", { image_id: imageId, profile_id: activeId, mode });
      const value = result.formatted_latex || result.raw_latex;
      setStacks((state) => ({
        ...state,
        // The first API result is the baseline of the API source, not an edit
        // of the local source.  Its undo history therefore starts empty.
        api: { undo: [], redo: [] },
      }));
      setLatex(value);
      setApiLatex(value);
      setApiOriginal(result.raw_latex);
      setApiFormatted(value);
      setSource("api");
      latexRef.current = value;
      resetEditGroup("api");
      if (result.history_id) setHistoryId(result.history_id);
      setStatus(`API 完成 · ${result.profile_name}`);
      if (settings.auto_copy) await copyWord(value);
    } catch (error) {
      setStatus(
        `API 识别失败：${error instanceof Error ? error.message : String(error)}`,
      );
    } finally {
      setBusy(false);
    }
  };
  const restore = async (id: string) => {
    try {
      const [record, image] = await Promise.all([
        callSidecar<RecordItem>("history.get", { id }),
        callSidecar<{ png_base64: string }>("history.image", { id }),
      ]);
      if (!record) throw new Error("记录不存在");
      const blob = pngBase64ToBlob(image.png_base64);
      const token = ++requestId.current;
      await openImage(blob, token);
      setHistoryId(id);
      setMode(record.recognition_mode || "chemistry");
      setLocalLatex(record.local_draft_latex || "");
      setLocalOriginal(
        record.local_raw_latex || record.local_draft_latex || "",
      );
      setLocalFormatted(
        record.local_formatted_latex || record.local_draft_latex || "",
      );
      setApiLatex(record.api_draft_latex || "");
      setApiOriginal(record.api_raw_latex || record.api_draft_latex || "");
      setApiFormatted(
        record.api_formatted_latex || record.api_draft_latex || "",
      );
      const next =
        record.active_source === "api" && record.api_draft_latex
          ? "api"
          : "local";
      setSource(next);
      setLatex(
        next === "api"
          ? record.api_draft_latex || ""
          : record.local_draft_latex || "",
      );
      setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
      latexRef.current =
        next === "api"
          ? record.api_draft_latex || ""
          : record.local_draft_latex || "";
      resetEditGroup(next);
      setStatus("已恢复历史记录");
    } catch (error) {
      setStatus(
        `历史记录读取失败：${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };
  const switchMode = async (nextMode: RecognitionMode) => {
    if (nextMode === mode) return;
    const activeBaseline = source === "local" ? localFormatted : apiFormatted;
    if (
      latex &&
      activeBaseline &&
      latex !== activeBaseline &&
      !window.confirm("切换识别模式会重新排版当前结果，是否继续？")
    )
      return;
    try {
      const [local, api] = await Promise.all([
        localOriginal
          ? callSidecar<{ formatted_latex: string }>("ocr.format", {
              latex: localOriginal,
              mode: nextMode,
            })
          : Promise.resolve({ formatted_latex: "" }),
        apiOriginal
          ? callSidecar<{ formatted_latex: string }>("ocr.format", {
              latex: apiOriginal,
              mode: nextMode,
            })
          : Promise.resolve({ formatted_latex: "" }),
      ]);
      setMode(nextMode);
      setLocalFormatted(local.formatted_latex);
      setApiFormatted(api.formatted_latex);
      setLocalLatex(local.formatted_latex);
      setApiLatex(api.formatted_latex);
      setLatex(
        source === "local" ? local.formatted_latex : api.formatted_latex,
      );
      setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
      latexRef.current =
        source === "local" ? local.formatted_latex : api.formatted_latex;
      resetEditGroup(source);
      if (historyId)
        void callSidecar("history.setMode", { id: historyId, mode: nextMode });
      setStatus(
        nextMode === "chemistry" ? "已切换为化学排版" : "已切换为数学排版",
      );
    } catch (error) {
      setStatus(`切换模式失败：${String(error)}`);
    }
  };
  const resizeImage = (event: ReactPointerEvent) => {
    event.preventDefault();
    const startY = event.clientY;
    const start = layout.image;
    const height = workspace.current?.getBoundingClientRect().height || 600;
    const move = (next: PointerEvent) =>
      setLayout((value) => ({
        ...value,
        image: Math.max(
          25,
          Math.min(70, start + ((next.clientY - startY) / height) * 100),
        ),
      }));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  const resizeResult = (event: ReactPointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const start = layout.result;
    const width = resultPane.current?.getBoundingClientRect().width || 800;
    const move = (next: PointerEvent) =>
      setLayout((value) => ({
        ...value,
        result: Math.max(
          30,
          Math.min(70, start + ((next.clientX - startX) / width) * 100),
        ),
      }));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  const selectSource = (next: Source) => {
    const draft = next === "local" ? localLatex : apiLatex;
    setSource(next);
    setLatex(draft);
    latexRef.current = draft;
    resetEditGroup(next);
    if (historyId)
      void callSidecar("history.updateDraft", {
        id: historyId,
        source: next,
        latex: draft,
      }).catch(() => undefined);
  };
  const deleteRecord = async (id: string) => {
    const index = records.findIndex((item) => item.id === id);
    await callSidecar("history.delete", { id });
    const remaining = records.filter((item) => item.id !== id);
    setRecords(remaining);
    if (historyId !== id) return;
    const neighbor =
      remaining[Math.min(Math.max(index, 0), remaining.length - 1)];
    if (neighbor) await restore(neighbor.id);
    else {
      setHistoryId(null);
      setLatex("");
      setLocalLatex("");
      setApiLatex("");
      setImageUrl(null);
      setImageId(null);
      setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
      latexRef.current = "";
      resetEditGroup("local");
      setStatus("当前历史记录已删除");
    }
  };
  const undo = () => {
    const value = stacks[source].undo[stacks[source].undo.length - 1];
    if (value === undefined) return;
    setStacks((state) => ({
      ...state,
      [source]: {
        undo: state[source].undo.slice(0, -1),
        redo: [...state[source].redo, latex],
      },
    }));
    setLatex(value);
    latexRef.current = value;
    resetEditGroup(source);
    if (source === "local") setLocalLatex(value);
    else setApiLatex(value);
    scheduleDraftSave(value);
  };
  const redo = () => {
    const value = stacks[source].redo[stacks[source].redo.length - 1];
    if (value === undefined) return;
    setStacks((state) => ({
      ...state,
      [source]: {
        undo: [...state[source].undo, latex],
        redo: state[source].redo.slice(0, -1),
      },
    }));
    setLatex(value);
    latexRef.current = value;
    resetEditGroup(source);
    if (source === "local") setLocalLatex(value);
    else setApiLatex(value);
    scheduleDraftSave(value);
  };
  return (
    <main className="app-shell">
      <header className="toolbar">
        <button
          className="toolbar-button"
          onClick={() => setDrawer((value) => !value)}
        >
          <History size={18} />
          历史
        </button>
        <button
          className="toolbar-button primary"
          onClick={() => fileInput.current?.click()}
          disabled={busy}
        >
          <FolderOpen size={18} />
          打开图片
        </button>
        <input
          ref={fileInput}
          hidden
          type="file"
          accept="image/*"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void recognize(file);
            event.target.value = "";
          }}
        />
        <button
          className="toolbar-button"
          disabled={busy}
          onClick={async () => {
            try {
              const items = await navigator.clipboard.read();
              const item = items.find((entry) =>
                entry.types.some((type) => type.startsWith("image/")),
              );
              const type = item?.types.find((value) =>
                value.startsWith("image/"),
              );
              if (item && type) void recognize(await item.getType(type));
              else setStatus("剪贴板中没有图片");
            } catch {
              setStatus("无法读取剪贴板图片，请使用 Command–V");
            }
          }}
        >
          <ClipboardPaste size={18} />
          粘贴图片
        </button>
        <button
          className="toolbar-button"
          disabled={busy}
          onClick={() => void screenshot()}
        >
          <ImageUp size={18} />
          截图 OCR
        </button>
        <div className="mode-selector" aria-label="识别模式">
          <button
            className={mode === "chemistry" ? "active" : ""}
            onClick={() => void switchMode("chemistry")}
          >
            化学
          </button>
          <button
            className={mode === "math" ? "active" : ""}
            onClick={() => void switchMode("math")}
          >
            数学
          </button>
        </div>
        {apiEnabled && profiles.some((profile) => profile.enabled) && (
          <>
            <button
              className="toolbar-button"
              disabled={busy || !imageId}
              onClick={() => void apiRecognize()}
            >
              <Sparkles size={18} />
              API 重识别
            </button>
            <button
              className="profile-pill"
              onClick={() => showSettings("自定义模型与 API")}
            >
              {activeProfile?.name || "当前 API 配置"}
              <span className="pill-dot" />
            </button>
          </>
        )}
        <span className="toolbar-spacer" />
        <span className="status-pill">离线识别</span>
        <button
          className="icon-button"
          aria-label="设置"
          onClick={() => showSettings()}
        >
          <Settings size={18} />
        </button>
      </header>
      <section
        className="workspace"
        ref={workspace}
        style={{
          gridTemplateRows: `${layout.image}% 8px ${100 - layout.image}%`,
        }}
      >
        <div className="image-card">
          {imageUrl ? (
            <img className="source-image" src={imageUrl} alt="当前公式图片" />
          ) : (
            <div className="empty-state">
              <ImageUp size={32} />
              <span>打开、粘贴或截图一张公式</span>
            </div>
          )}
        </div>
        <div
          className="split-handle horizontal"
          onPointerDown={resizeImage}
          role="separator"
          aria-label="调整图片与结果比例"
        />
        <section className="result-card" ref={resultPane}>
          <div className="result-toolbar">
            <strong>识别结果</strong>
            {localLatex && (
              <button
                className={
                  source === "local"
                    ? "source-selector active"
                    : "source-selector"
                }
                onClick={() => selectSource("local")}
              >
                内置
              </button>
            )}
            {apiLatex && (
              <button
                className={
                  source === "api"
                    ? "source-selector active"
                    : "source-selector"
                }
                onClick={() => selectSource("api")}
              >
                API · {activeProfile?.name || "配置"}
              </button>
            )}
            <button
              className={`icon-button edit-history-button ${stacks[source].undo.length ? "is-active" : ""}`}
              aria-label="撤销"
              title="撤销"
              disabled={!stacks[source].undo.length}
              onClick={undo}
            >
              <Undo2 size={18} strokeWidth={2.2} />
            </button>
            <button
              className={`icon-button edit-history-button ${stacks[source].redo.length ? "is-active" : ""}`}
              aria-label="重做"
              title="重做"
              disabled={!stacks[source].redo.length}
              onClick={redo}
            >
              <Redo2 size={18} strokeWidth={2.2} />
            </button>
            <button
              className="secondary-button"
              disabled={!activeOriginal || latex === activeOriginal}
              onClick={() => {
                resetEditGroup(source);
                updateLatex(activeOriginal);
              }}
            >
              <RotateCcw size={16} />
              恢复原文
            </button>
            <span className="toolbar-spacer" />
            <button
              className="secondary-button"
              disabled={!latex.trim()}
              onClick={() => void copyWord()}
            >
              <Copy size={16} />
              复制 Word
            </button>
            <button
              className="secondary-button"
              disabled={!latex.trim()}
              onClick={() => {
                void navigator.clipboard.writeText(latex);
                setStatus("已复制 LaTeX");
              }}
            >
              <Copy size={16} />
              复制 LaTeX
            </button>
          </div>
          <div
            className="result-split"
            style={{
              gridTemplateColumns: `${layout.result}% 8px ${100 - layout.result}%`,
            }}
          >
            <section className="editor-pane">
              <h2>LaTeX</h2>
              <LatexEditor value={latex} onChange={updateLatex} />
            </section>
            <div
              className="split-handle vertical"
              onPointerDown={resizeResult}
              role="separator"
              aria-label="调整 LaTeX 与预览比例"
            />
            <section className="preview-pane">
              <h2>公式预览</h2>
              <MathPreview latex={latex} />
            </section>
          </div>
        </section>
      </section>
      <footer className="footer">
        <label>
          <input
            type="checkbox"
            checked={settings.auto_copy}
            onChange={(event) => {
              const value = { ...settings, auto_copy: event.target.checked };
              setSettings(value);
              void callSidecar("settings.save", { values: value });
              void emit("formulaocr://settings-updated");
            }}
          />
          识别完成后自动复制 Word 格式
        </label>
        <span>{status}</span>
      </footer>
      {drawer && (
        <>
          <div className="drawer-scrim" onClick={() => setDrawer(false)} />
          <aside
            className="history-drawer"
            style={{ width: layout.drawerWidth }}
          >
            <div className="drawer-header">
              <strong>识别历史</strong>
              <span className="toolbar-spacer" />
              {selectedRecords.length > 0 && (
                <button
                  className="text-danger"
                  onClick={async () => {
                    if (
                      !window.confirm(
                        `删除所选 ${selectedRecords.length} 条记录？`,
                      )
                    )
                      return;
                    await callSidecar("history.deleteMany", {
                      ids: selectedRecords,
                    });
                    setRecords((items) =>
                      items.filter(
                        (item) => !selectedRecords.includes(item.id),
                      ),
                    );
                    setSelectedRecords([]);
                  }}
                >
                  删除所选
                </button>
              )}
              {records.length > 0 && (
                <button
                  className="text-danger"
                  onClick={async () => {
                    if (!window.confirm("删除全部识别历史？")) return;
                    await callSidecar("history.deleteAll");
                    setRecords([]);
                    setSelectedRecords([]);
                  }}
                >
                  全部删除
                </button>
              )}
              <button
                className="icon-button"
                onClick={() => setDrawer(false)}
                aria-label="关闭"
              >
                <X size={17} />
              </button>
            </div>
            {records.length ? (
              <div className="history-list">
                {records.map((record) => (
                  <div className="history-item" key={record.id}>
                    <input
                      type="checkbox"
                      checked={selectedRecords.includes(record.id)}
                      onChange={(event) =>
                        setSelectedRecords((ids) =>
                          event.target.checked
                            ? [...ids, record.id]
                            : ids.filter((id) => id !== record.id),
                        )
                      }
                    />
                    <button
                      className="history-item-main"
                      onClick={() => void restore(record.id)}
                    >
                      {record.image_path && (
                        <img
                          className="history-thumb"
                          src={convertFileSrc(record.image_path)}
                          alt=""
                        />
                      )}
                      <span className="history-item-copy">
                      <span>
                        {new Date(record.updated_at * 1000).toLocaleString()} ·{" "}
                        {record.has_api ? "API" : "内置"}
                      </span>
                      <small>
                        {(record.active_source === "api"
                          ? record.api_draft_latex
                          : record.local_draft_latex) || "无 LaTeX 结果"}
                      </small>
                      </span>
                    </button>
                    <button
                      className="icon-button danger"
                      onClick={() => void deleteRecord(record.id)}
                      aria-label="删除历史记录"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="drawer-empty">暂无识别记录</div>
            )}
            <div
              className="drawer-resize"
              onPointerDown={(event) => {
                const startX = event.clientX;
                const start = layout.drawerWidth;
                const move = (next: PointerEvent) =>
                  setLayout((value) => ({
                    ...value,
                    drawerWidth: Math.max(
                      280,
                      Math.min(420, start + next.clientX - startX),
                    ),
                  }));
                const stop = () => {
                  window.removeEventListener("pointermove", move);
                  window.removeEventListener("pointerup", stop);
                };
                window.addEventListener("pointermove", move);
                window.addEventListener("pointerup", stop);
              }}
            />
          </aside>
        </>
      )}
      {settingsFallback && (
        <div className="settings-overlay">
          <SettingsCenter
            inline
            initialPage="常规"
            onClose={() => setSettingsFallback(false)}
          />
        </div>
      )}
    </main>
  );
}

export function App() {
  return new URLSearchParams(window.location.search).get("settings") === "1" ? (
    <SettingsCenter />
  ) : (
    <MainApp />
  );
}
