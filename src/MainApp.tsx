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
  Settings as SettingsIcon,
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
import {
  localizeError,
  normalizeLanguage,
  translate,
  type AppLanguage,
} from "./i18n";

import { defaults, type Settings, type Source, type RecognitionMode, type Profile, type RecordItem, type Layout } from "./types";
import { SettingsCenter } from "./SettingsCenter";
import { useTauriEvent } from "./hooks";
import { DraftQueue, readLayout, DEFAULT_LAYOUT } from "./state";

function pngBase64ToBlob(value: string): Blob {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1)
    bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], { type: "image/png" });
}

function openSettings(
  page = "常规",
  language: AppLanguage = "zh-CN",
  onFallback?: () => void,
) {
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
        title: translate(language, "FormulaOCR 设置"),
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

    } catch {
      onFallback?.();
    }
  })();
}

function LatexEditor({
  value,
  onChange,
  language,
}: {
  value: string;
  onChange: (value: string) => void;
  language: AppLanguage;
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
  return (
    <div
      ref={host}
      className="latex-editor"
      aria-label={translate(language, "LaTeX 编辑器")}
    />
  );
}

function MathPreview({
  latex,
  language,
}: {
  latex: string;
  language: AppLanguage;
}) {
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
      {!latex && (
        <span className="muted preview-message">
          {translate(language, "公式将在这里预览")}
        </span>
      )}
      {loading && (
        <span className="muted preview-message">
          {translate(language, "正在生成预览…")}
        </span>
      )}
      {error && (
        <span className="preview-error preview-message">
          {translate(language, "无法渲染公式：{error}", { error })}
        </span>
      )}
    </div>
  );
}

export function MainApp() {
  const [drawer, setDrawer] = useState(false);
  const [settingsFallback, setSettingsFallback] = useState(false);
  const [settings, setSettings] = useState<Settings>(defaults);
  const [layoutReady, setLayoutReady] = useState(false);
  const initialDrawer = useRef(localStorage.getItem("formulaocr.layout.drawerOpen") === "1");
  const geometryTimer = useRef<ReturnType<typeof setTimeout>>();

  const language = normalizeLanguage(settings.language);
  const t = useCallback(
    (text: string, values?: Record<string, string | number>) =>
      translate(language, text, values),
    [language],
  );
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
  const [apiResultName, setApiResultName] = useState("");
  const [profileMenu, setProfileMenu] = useState(false);
  const [mode, setMode] = useState<RecognitionMode>("chemistry");
  const [source, setSource] = useState<Source>("local");
  const [stacks, setStacks] = useState<
    Record<Source, { undo: string[]; redo: string[] }>
  >({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
  const [status, setStatus] = useState("正在后台准备离线模型…");
  const [busy, setBusy] = useState(false);
  const [layout, setLayout] = useState<Layout>(() => readLayout(localStorage.getItem("formulaocr.layout.v2")));
  const [reload, setReload] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const imageUrlRef = useRef<string | null>(null);
  const imageIdRef = useRef<string | null>(null);
  const requestId = useRef(0);
  const languageRef = useRef<AppLanguage>(language);
  const draftQueue = useRef<DraftQueue | null>(null);
  if (!draftQueue.current) draftQueue.current = new DraftQueue(
    (draft) => callSidecar("history.updateDraft", draft),
    (error) => setStatus(translate(languageRef.current, "历史保存失败：{error}", { error: localizeError(languageRef.current, error) })),
  );
  const bootstrapped = useRef(false);
  const hotkeyLoaded = useRef(false);
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
        const normalized = {
          ...defaults,
          ...value,
          language: normalizeLanguage(value.language),
        };
        setSettings(normalized);
        languageRef.current = normalized.language;
        if (!bootstrapped.current) {
          bootstrapped.current = true;
          setMode(normalized.default_recognition_mode);
          if (normalized.layout_restore_mode === "optimized_default") {
            setLayout({ ...DEFAULT_LAYOUT }); setDrawer(false);
            void invoke("restore_main_geometry", { geometry: {} }).catch(() => undefined);
          } else {
            if (normalized.layout_restore_mode === "restore_full_state") setDrawer(initialDrawer.current);
            try { void invoke("restore_main_geometry", { geometry: JSON.parse(localStorage.getItem("formulaocr.geometry.v1") || "{}") }).catch(() => undefined); } catch {}
          }
          setLayoutReady(true);
        }
        if (!hotkeyLoaded.current) {
          hotkeyLoaded.current = true;
          void invoke("set_global_hotkey", { shortcut: normalized.hotkey }).catch((error) =>
            setStatus(translate(normalized.language, "快捷键注册失败：{error}", { error: localizeError(normalized.language, error) })));
        }
        void invoke("set_menu_language", {
          language: normalized.language,
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
    document.documentElement.lang = language;
    document.title = "FormulaOCR";
    languageRef.current = language;
  }, [language]);
  useEffect(() => {
    let active = true;
    void callSidecar<{ loaded: boolean; elapsed_ms: number }>("ocr.preload")
      .then((result) => {
        if (!active) return;
        setStatus(translate(languageRef.current, "离线模型已就绪 · {ms} ms", {
          ms: Math.round(result.elapsed_ms),
        }));
      })
      .catch((error) => {
        if (!active) return;
        setStatus(translate(languageRef.current, "离线模型加载失败：{error}", {
          error: localizeError(languageRef.current, error),
        }));
      });
    return () => {
      active = false;
    };
  }, []);
  const showSettings = useCallback(
    (page = "常规") =>
      openSettings(page, language, () => setSettingsFallback(true)),
    [language],
  );
  useTauriEvent<string>("formulaocr://open-settings", (event) => showSettings(event.payload || "常规"));
  useTauriEvent("formulaocr://settings-updated", () => setReload((value) => value + 1));
  const saveGeometry = async () => {
    try { localStorage.setItem("formulaocr.geometry.v1", JSON.stringify(await invoke("main_geometry"))); } catch {}
  };
  useTauriEvent("formulaocr://window-close-requested", () => {
    void draftQueue.current!.flush(); void saveGeometry();
    void invoke("set_activation_policy", { accessory: settings.hide_dock_on_close });
  });
  const finishQuit = async () => {
    ++requestId.current;
    await draftQueue.current!.flush();
    await saveGeometry();
    await invoke("complete_quit");
  };
  useTauriEvent("formulaocr://quit-requested", () => { void finishQuit(); });
  useTauriEvent("formulaocr://flush-before-quit", () => { void finishQuit(); });
  useTauriEvent("formulaocr://reset-layout", () => {
    setLayout({ ...DEFAULT_LAYOUT }); setDrawer(false);
    localStorage.removeItem("formulaocr.geometry.v1");
    void invoke("restore_main_geometry", { geometry: {} });
  });
  useEffect(() => {
    if (!layoutReady) return;
    localStorage.setItem("formulaocr.layout.v2", JSON.stringify({ ...layout, version: 3 }));
    localStorage.setItem("formulaocr.layout.drawerOpen", drawer ? "1" : "0");
  }, [layout, drawer, layoutReady]);
  useEffect(() => {
    if (!layoutReady) return;
    let disposed = false;
    const stops: (() => void)[] = [];
    const save = () => { clearTimeout(geometryTimer.current); geometryTimer.current = setTimeout(() => void saveGeometry(), 250); };
    for (const subscribe of [getCurrentWindow().onResized(save), getCurrentWindow().onMoved(save)]) {
      void subscribe.then((stop) => { if (disposed) stop(); else stops.push(stop); });
    }
    return () => { disposed = true; stops.forEach((stop) => stop()); clearTimeout(geometryTimer.current); };
  }, [layoutReady]);
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
    const flushed = draftQueue.current!.flush();
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
    setApiResultName("");
    setSource("local");
    setHistoryId(null);
    setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
    latexRef.current = "";
    resetEditGroup("local");
    setStatus(t("图片已载入，正在识别…"));
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
    await flushed;
    if (token !== requestId.current) return null;
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
    async (blob: Blob, stagedPath?: string) => {
      const token = ++requestId.current;
      setBusy(true);
      setStatus(t("正在载入图片…"));
      try {
        const id = await openImage(blob, token, stagedPath);
        if (!id) return;
        const result = await callSidecar<{
          formatted_latex?: string;
          raw_latex?: string;
          elapsed_ms?: number;
          history_id?: string;
          history_error?: string;
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
        setStatus(t("识别完成{time}", {
          time: result.elapsed_ms ? ` · ${Math.round(result.elapsed_ms)} ms` : "",
        }));
        if (drawer) void callSidecar<{ records: RecordItem[] }>("history.list").then((value) => setRecords(value.records));
        if (result.history_error) setStatus(t("历史保存失败：{error}", { error: result.history_error }));
        if (settings.auto_copy && value) await copyWord(value, token, true);
      } catch (error) {
        if (token === requestId.current)
          setStatus(t("识别失败：{error}", {
            error: localizeError(language, error),
          }));
      } finally {
        if (token === requestId.current) setBusy(false);
      }
    },
    [settings.auto_copy, mode, t],
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
    if (!nextHistoryId) return;
    draftQueue.current!.schedule({ id: nextHistoryId, source: nextSource, latex: value });
  };
  const updateLatex = (value: string) => {
    const now = performance.now();
    const previous = latexRef.current;
    if (value === previous) return;
    const startsNewGroup =
      editGroup.current.lastAt === 0 ||
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
  const copyWord = async (value = latex, token = requestId.current, automatic = false) => {
    const isCurrent = () => token === requestId.current && (!automatic || latexRef.current === value);
    if (!isCurrent()) return;
    if (!value.trim()) return setStatus(t("没有可复制的 LaTeX"));
    try {
      const mathml = (
        await callSidecar<{ mathml: string }>("conversion.toMathML", {
          latex: value,
        })
      ).mathml;
      // Conversion is asynchronous. A newer image or edit must not have its
      // clipboard replaced by an automatic copy of the previous result.
      if (!isCurrent()) return;
      await invoke("native_copy_word", { latex: value, mathml });
      if (isCurrent()) setStatus(t("已复制 Word 格式"));
    } catch (error) {
      if (isCurrent()) setStatus(t("复制 Word 失败：{error}", {
        error: localizeError(language, error),
      }));
    }
  };
  const screenshot = useCallback(async () => {
    if (busy || captureInProgress.current) return;
    captureInProgress.current = true;
    setStatus(t("请拖动选择截图区域，Esc 取消"));
    try {
      const path = await invoke<string>("native_screenshot");
      const response = await fetch(convertFileSrc(path));
      if (!response.ok) throw new Error(t("无法读取截图结果"));
      const blob = await response.blob();
      // recognize() publishes the Blob URL first; the now-asynchronous Rust
      // bridge lets WebKit paint it while image.open and ONNX inference run.
      await recognize(blob, path);
    } catch (error) {
      setStatus(t("截图失败：{error}", {
        error: localizeError(language, error),
      }));
    } finally {
      captureInProgress.current = false;
    }
  }, [busy, recognize, t]);
  useTauriEvent("formulaocr://screenshot-requested", () => void screenshot());
  const apiRecognize = async () => {
    if (!imageId || !activeId) return setStatus(t("没有当前图片或可用 API 配置"));
    setBusy(true);
    setStatus(t("正在进行 API 重识别…"));
    const token = requestId.current;
    await draftQueue.current!.flush();
    try {
      const result = await callSidecar<{
        raw_latex: string;
        formatted_latex?: string;
        profile_name: string;
        history_id?: string;
        history_error?: string;
      }>("api.recognize", { image_id: imageId, profile_id: activeId, mode });
      if (token !== requestId.current) return;
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
      setApiResultName(result.profile_name);
      setSource("api");
      latexRef.current = value;
      resetEditGroup("api");
      if (result.history_id) setHistoryId(result.history_id);
      setStatus(t("API 完成 · {name}", { name: result.profile_name }));
      if (result.history_error) setStatus(t("历史保存失败：{error}", { error: result.history_error }));
      if (drawer) void callSidecar<{ records: RecordItem[] }>("history.list").then((value) => setRecords(value.records));
      if (settings.auto_copy) await copyWord(value, token, true);
    } catch (error) {
      if (token === requestId.current) setStatus(t("API 识别失败：{error}", {
        error: localizeError(language, error),
      }));
    } finally {
      if (token === requestId.current) setBusy(false);
    }
  };
  const restore = async (id: string) => {
    const token = ++requestId.current;
    setBusy(true);
    await draftQueue.current!.flush();
    try {
      const opened = await callSidecar<{ record: RecordItem; image_id: string; png_base64: string }>("history.open", { id });
      if (token !== requestId.current) {
        void callSidecar("image.release", { image_id: opened.image_id });
        return;
      }
      const record = opened.record;
      if (imageIdRef.current) void callSidecar("image.release", { image_id: imageIdRef.current });
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
      const url = URL.createObjectURL(pngBase64ToBlob(opened.png_base64));
      imageUrlRef.current = url;
      imageIdRef.current = opened.image_id;
      setImageUrl(url);
      setImageId(opened.image_id);
      setHistoryId(id);
      setMode(record.recognition_mode || "chemistry");
      setLocalLatex(record.local_draft_latex ?? "");
      setLocalOriginal(record.local_raw_latex);
      setLocalFormatted(record.local_formatted_latex ?? record.local_draft_latex);
      setApiLatex(record.api_draft_latex ?? "");
      setApiOriginal(record.api_raw_latex ?? "");
      setApiFormatted(record.api_formatted_latex ?? record.api_draft_latex ?? "");
      setApiResultName(record.api_profile_name ?? "");
      const next: Source = record.active_source === "api" && record.has_api ? "api" : "local";
      const draft = (next === "api" ? record.api_draft_latex : record.local_draft_latex) ?? "";
      setSource(next);
      setLatex(draft);
      setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
      latexRef.current = draft;
      resetEditGroup(next);
      setStatus(t("已恢复历史记录"));
    } catch (error) {
      if (token === requestId.current) setStatus(t("历史记录读取失败：{error}", { error: localizeError(language, error) }));
    } finally {
      if (token === requestId.current) setBusy(false);
    }
  };
  const switchMode = async (nextMode: RecognitionMode) => {
    if (nextMode === mode || busy) return;
    const token = requestId.current;
    if (
      ((localOriginal && localLatex !== localFormatted) || (apiOriginal && apiLatex !== apiFormatted)) &&
      !window.confirm(t("切换识别模式会重新排版当前结果，是否继续？"))
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
      if (token !== requestId.current) return;
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
      if (historyId) {
        await draftQueue.current!.flush();
        await callSidecar("history.setMode", { id: historyId, mode: nextMode });
        if (localOriginal) draftQueue.current!.schedule({ id: historyId, source: "local", latex: local.formatted_latex, activate: source === "local" });
        if (apiOriginal) draftQueue.current!.schedule({ id: historyId, source: "api", latex: api.formatted_latex, activate: source === "api" });
        await draftQueue.current!.flush();
      }
      setStatus(
        t(nextMode === "chemistry" ? "已切换为化学排版" : "已切换为数学排版"),
      );
    } catch (error) {
      setStatus(t("切换模式失败：{error}", { error: localizeError(language, error) }));
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
    void draftQueue.current!.flush();
    const draft = next === "local" ? localLatex : apiLatex;
    setSource(next);
    setLatex(draft);
    latexRef.current = draft;
    resetEditGroup(next);
    scheduleDraftSave(draft, next);
  };
  const clearWorkspace = () => {
    ++requestId.current;
    if (imageIdRef.current) void callSidecar("image.release", { image_id: imageIdRef.current });
    if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    imageIdRef.current = null;
    imageUrlRef.current = null;
    setHistoryId(null); setImageId(null); setImageUrl(null);
    setLatex(""); setLocalLatex(""); setApiLatex("");
    setLocalOriginal(""); setApiOriginal(""); setLocalFormatted(""); setApiFormatted(""); setApiResultName("");
    setSource("local"); setBusy(false);
    setStacks({ local: { undo: [], redo: [] }, api: { undo: [], redo: [] } });
    latexRef.current = ""; resetEditGroup("local");
  };
  const deleteRecords = async (ids: string[], all = false) => {
    await draftQueue.current!.flush();
    try {
      await callSidecar(all ? "history.deleteAll" : "history.deleteMany", { ids });
      const removed = new Set(ids);
      const remaining = all ? [] : records.filter((record) => !removed.has(record.id));
      const index = records.findIndex((record) => record.id === historyId);
      setRecords(remaining);
      setSelectedRecords((selected) => selected.filter((id) => !removed.has(id) && !all));
      if (all || (historyId && removed.has(historyId))) {
        const neighbor = remaining[Math.min(Math.max(index, 0), remaining.length - 1)];
        if (neighbor) await restore(neighbor.id);
        else clearWorkspace();
      }
      setStatus(t("当前历史记录已删除"));
    } catch (error) { setStatus(localizeError(language, error)); }
  };
  const deleteRecord = (id: string) => deleteRecords([id]);
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
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (settingsFallback) return;
      if (event.key === "Escape") { setDrawer(false); setProfileMenu(false); return; }
      if (!(event.metaKey || event.ctrlKey)) return;
      if (event.key === ",") { event.preventDefault(); showSettings(); return; }
      if (event.key.toLowerCase() === "z" && !(event.target instanceof HTMLInputElement)) {
        event.preventDefault(); event.stopPropagation();
        if (event.shiftKey) redo(); else undo();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });
  return (
    <main className="app-shell">
      <header className="toolbar">
        <button
          className="toolbar-button"
          onClick={() => setDrawer((value) => !value)}
        >
          <History size={18} />
          {t("历史")}
        </button>
        <button
          className="toolbar-button primary"
          onClick={() => fileInput.current?.click()}
          disabled={busy}
        >
          <FolderOpen size={18} />
          {t("打开图片")}
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
              const path = await invoke<string>("native_paste_image");
              const response = await fetch(convertFileSrc(path));
              if (!response.ok) throw new Error(t("无法读取截图结果"));
              await recognize(await response.blob(), path);
            } catch {
              setStatus(t("无法读取剪贴板图片，请使用 Command–V"));
            }
          }}
        >
          <ClipboardPaste size={18} />
          {t("粘贴图片")}
        </button>
        <button
          className="toolbar-button"
          disabled={busy}
          onClick={() => void screenshot()}
        >
          <ImageUp size={18} />
          {t("截图 OCR")}
        </button>
        <div className="mode-selector" aria-label={t("识别模式")}>
          <button
            disabled={busy}
            className={mode === "chemistry" ? "active" : ""}
            onClick={() => void switchMode("chemistry")}
          >
            {t("化学")}
          </button>
          <button
            disabled={busy}
            className={mode === "math" ? "active" : ""}
            onClick={() => void switchMode("math")}
          >
            {t("数学")}
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
              {t("API 重识别")}
            </button>
            <button
              className="profile-pill"
              title={activeProfile?.name || t("当前 API 配置")}
              aria-haspopup="menu"
              aria-expanded={profileMenu}
              onClick={() => setProfileMenu((open) => !open)}
            >
              <span className="profile-name">
                {activeProfile?.name || t("当前 API 配置")}
              </span>
              <span className="pill-dot" />
            </button>
          </>
        )}
        <span className="toolbar-spacer" />
        <span className="status-pill">{t("离线识别")}</span>
        <button
          className="icon-button"
          aria-label={t("设置")}
          title={t("设置")}
          onClick={() => showSettings()}
        >
          <SettingsIcon size={18} />
        </button>
      </header>
      {profileMenu && <><div className="profile-menu-dismiss" onClick={() => setProfileMenu(false)} />
        <div className="profile-menu" role="menu" aria-label={t("当前 API 配置")}>
          {profiles.filter((profile) => profile.enabled).map((profile) => <button key={profile.id} role="menuitemradio" aria-checked={profile.id === activeId} onClick={() => {
            setProfileMenu(false);
            void callSidecar("profiles.activate", { id: profile.id }).then(() => { setActiveId(profile.id); void emit("formulaocr://settings-updated"); })
              .catch((error) => setStatus(localizeError(language, error)));
          }}>{profile.id === activeId && <Check size={15}/>}<span>{profile.name}</span></button>)}
          <button role="menuitem" onClick={() => { setProfileMenu(false); showSettings("自定义模型与 API"); }}>{t("设置")}</button>
        </div></>}
      <section
        className="workspace"
        ref={workspace}
        style={{
          gridTemplateRows: `minmax(0, ${layout.image}fr) 8px minmax(0, ${100 - layout.image}fr)`,
        }}
      >
        <div className="image-card">
          {imageUrl ? (
            <img className="source-image" src={imageUrl} alt={t("当前公式图片")} />
          ) : (
            <div className="empty-state">
              <ImageUp size={32} />
              <span>{t("打开、粘贴或截图一张公式")}</span>
            </div>
          )}
        </div>
        <div
          className="split-handle horizontal"
          onPointerDown={resizeImage}
          role="separator"
          aria-label={t("调整图片与结果比例")}
        />
        <section className="result-card" ref={resultPane}>
          <div className="result-toolbar">
            <strong>{t("识别结果")}</strong>
            {localOriginal && (
              <button
                className={
                  source === "local"
                    ? "source-selector active"
                    : "source-selector"
                }
                onClick={() => selectSource("local")}
              >
                {t("内置")}
              </button>
            )}
            {apiOriginal && (
              <button
                className={
                  source === "api"
                    ? "source-selector active"
                    : "source-selector"
                }
                onClick={() => selectSource("api")}
              >
                {t("API · {name}", { name: apiResultName || t("配置") })}
              </button>
            )}
            <button
              className={`icon-button edit-history-button ${stacks[source].undo.length ? "is-active" : ""}`}
              aria-label={t("撤销")}
              title={t("撤销")}
              disabled={!stacks[source].undo.length}
              onClick={undo}
            >
              <Undo2 size={18} strokeWidth={2.2} />
            </button>
            <button
              className={`icon-button edit-history-button ${stacks[source].redo.length ? "is-active" : ""}`}
              aria-label={t("重做")}
              title={t("重做")}
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
              {t("恢复原文")}
            </button>
            <span className="toolbar-spacer" />
            <button
              className="secondary-button"
              disabled={!latex.trim()}
              onClick={() => void copyWord()}
            >
              <Copy size={16} />
              {t("复制 Word")}
            </button>
            <button
              className="secondary-button"
              disabled={!latex.trim()}
              onClick={() => {
                void invoke("native_copy_text", { text: latex }).then(() => setStatus(t("已复制 LaTeX")))
                  .catch((error) => setStatus(localizeError(language, error)));
              }}
            >
              <Copy size={16} />
              {t("复制 LaTeX")}
            </button>
          </div>
          <div
            className="result-split"
            style={{
              gridTemplateColumns: `minmax(0, ${layout.result}fr) 8px minmax(0, ${100 - layout.result}fr)`,
            }}
          >
            <section className="editor-pane">
              <h2>LaTeX</h2>
              <LatexEditor value={latex} onChange={updateLatex} language={language} />
            </section>
            <div
              className="split-handle vertical"
              onPointerDown={resizeResult}
              role="separator"
              aria-label={t("调整 LaTeX 与预览比例")}
            />
            <section className="preview-pane">
              <h2>{t("公式预览")}</h2>
              <MathPreview latex={latex} language={language} />
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
              const checked = event.target.checked;
              void callSidecar<Settings>("settings.save", { values: { auto_copy: checked } }).then((value) => {
                setSettings({ ...defaults, ...value });
                void emit("formulaocr://settings-updated");
              }).catch((error) => setStatus(localizeError(language, error)));
            }}
          />
          {t("识别完成后自动复制 Word 格式")}
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
              <strong>{t("识别历史")}</strong>
              <span className="toolbar-spacer" />
              {selectedRecords.length > 0 && (
                <button
                  className="text-danger"
                  onClick={async () => {
                    if (
                      !window.confirm(
                        t("删除所选 {count} 条记录？", { count: selectedRecords.length }),
                      )
                    )
                      return;
                    await deleteRecords(selectedRecords);
                  }}
                >
                  {t("删除所选")}
                </button>
              )}
              {records.length > 0 && (
                <button
                  className="text-danger"
                  onClick={async () => {
                    if (!window.confirm(t("删除全部识别历史？"))) return;
                    await deleteRecords(records.map((record) => record.id), true);
                  }}
                >
                  {t("全部删除")}
                </button>
              )}
              <button
                className="icon-button"
                onClick={() => setDrawer(false)}
                aria-label={t("关闭")}
              >
                <X size={17} />
              </button>
            </div>
            {records.length ? (
              <div className="history-list">
                {records.map((record) => (
                  <div className={historyId === record.id ? "history-item current" : "history-item"} key={record.id} onContextMenu={(event) => { event.preventDefault(); if (window.confirm(t("删除此历史记录？"))) void deleteRecord(record.id); }}>
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
                        {new Date(record.updated_at * 1000).toLocaleString(language === "en" ? "en-AU" : "zh-CN")} ·{" "}
                        {record.has_api ? "API" : t("内置")}
                      </span>
                      <small>
                        {(record.active_source === "api"
                          ? record.api_draft_latex
                          : record.local_draft_latex) || t("无 LaTeX 结果")}
                      </small>
                      </span>
                    </button>
                    <button
                      className="icon-button danger"
                      onClick={() => void deleteRecord(record.id)}
                      aria-label={t("删除历史记录")}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="drawer-empty">{t("暂无识别记录")}</div>
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
            initialLanguage={language}
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
