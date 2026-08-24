use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::collections::HashMap;
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use tauri::menu::{Menu, MenuBuilder, MenuItemBuilder};
use tauri::tray::TrayIconBuilder;
use tauri::Manager;
use tauri::Emitter;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tauri::{RunEvent, WindowEvent};
use tauri::ActivationPolicy;

fn show_main_window<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    let _ = app.set_activation_policy(ActivationPolicy::Regular);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn tray_menu<R: tauri::Runtime>(app: &tauri::AppHandle<R>, language: &str) -> tauri::Result<Menu<R>> {
    let english = language == "en";
    let show = MenuItemBuilder::with_id("show", if english { "Show Main Window" } else { "显示主窗口" }).build(app)?;
    let screenshot = MenuItemBuilder::with_id("screenshot", if english { "Screenshot OCR" } else { "截图 OCR" }).build(app)?;
    let settings = MenuItemBuilder::with_id("settings", if english { "Settings…" } else { "设置…" }).build(app)?;
    let quit = MenuItemBuilder::with_id("quit", if english { "Quit FormulaOCR" } else { "退出 FormulaOCR" }).build(app)?;
    MenuBuilder::new(app)
        .item(&show)
        .item(&screenshot)
        .item(&settings)
        .separator()
        .item(&quit)
        .build()
}

#[tauri::command]
fn set_menu_language<R: tauri::Runtime>(app: tauri::AppHandle<R>, language: String) -> Result<(), String> {
    let menu = tray_menu(&app, &language).map_err(|error| error.to_string())?;
    let tray = app.tray_by_id("main").ok_or("FormulaOCR tray icon is unavailable")?;
    tray.set_menu(Some(menu)).map_err(|error| error.to_string())
}

fn stage_root() -> Result<std::path::PathBuf, String> {
    let root = std::env::temp_dir().join("formulaocr-stage");
    std::fs::create_dir_all(&root).map_err(|error| format!("无法建立图片暂存目录: {error}"))?;
    Ok(root)
}

fn staged_png_path(prefix: &str) -> Result<std::path::PathBuf, String> {
    Ok(stage_root()?.join(format!("{prefix}-{}-{}.png", std::process::id(), std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|value| value.as_nanos()).unwrap_or_default())))
}

#[tauri::command]
fn stage_image_bytes(bytes: Vec<u8>) -> Result<String, String> {
    if bytes.is_empty() { return Err("图片数据为空".into()); }
    let path = staged_png_path("input")?;
    std::fs::write(&path, bytes).map_err(|error| format!("无法暂存图片: {error}"))?;
    Ok(path.to_string_lossy().into_owned())
}

#[cfg(target_os = "macos")]
#[tauri::command]
fn native_copy_word(latex: String, mathml: String) -> Result<(), String> {
    use std::ffi::{c_char, c_void, CString};
    #[link(name = "objc", kind = "dylib")]
    extern "C" { fn objc_getClass(name: *const c_char) -> *mut c_void; fn sel_registerName(name: *const c_char) -> *mut c_void; fn objc_msgSend(); }
    unsafe fn sel(name: &[u8]) -> *mut c_void { sel_registerName(name.as_ptr().cast()) }
    unsafe fn ns_string(value: &str) -> Result<*mut c_void, String> {
        let value = CString::new(value).map_err(|_| "剪贴板文本包含无效字符")?;
        let class = objc_getClass(b"NSString\0".as_ptr().cast());
        let send: unsafe extern "C" fn(*mut c_void, *mut c_void, *const c_char) -> *mut c_void = std::mem::transmute(objc_msgSend as *const ());
        Ok(send(class, sel(b"stringWithUTF8String:\0"), value.as_ptr()))
    }
    unsafe {
        let pasteboard_class = objc_getClass(b"NSPasteboard\0".as_ptr().cast());
        let send0: unsafe extern "C" fn(*mut c_void, *mut c_void) -> *mut c_void = std::mem::transmute(objc_msgSend as *const ());
        let pasteboard = send0(pasteboard_class, sel(b"generalPasteboard\0"));
        let _ = send0(pasteboard, sel(b"clearContents\0"));
        let send2: unsafe extern "C" fn(*mut c_void, *mut c_void, *mut c_void, *mut c_void) -> bool = std::mem::transmute(objc_msgSend as *const ());
        let html = format!("<html><body><!--StartFragment-->{mathml}<!--EndFragment--></body></html>");
        let html_ok = send2(pasteboard, sel(b"setString:forType:\0"), ns_string(&html)?, ns_string("public.html")?);
        let text_ok = send2(pasteboard, sel(b"setString:forType:\0"), ns_string(&latex)?, ns_string("public.utf8-plain-text")?);
        if html_ok && text_ok { Ok(()) } else { Err("macOS 剪贴板拒绝写入公式".into()) }
    }
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn native_copy_word(_latex: String, _mathml: String) -> Result<(), String> { Err("Word 公式剪贴板仅支持 macOS".into()) }

/// Recreate the status item used by the original PySide app.
///
/// The old implementation used AppKit's SF Symbol named `function` as a
/// template image.  Keeping the symbol lookup in AppKit (rather than drawing
/// a glyph or shipping a second image) preserves the native menu-bar weight
/// and automatically follows light/dark menu-bar appearance.
#[cfg(target_os = "macos")]
fn original_function_tray_icon() -> Option<tauri::image::Image<'static>> {
    use std::ffi::{c_char, c_void};

    #[link(name = "objc", kind = "dylib")]
    extern "C" {
        fn objc_getClass(name: *const c_char) -> *mut c_void;
        fn sel_registerName(name: *const c_char) -> *mut c_void;
        fn objc_msgSend();
    }

    // The Rust Tauri shell intentionally has no AppKit binding dependency.
    // These small typed Objective-C calls keep the exact native SF Symbol
    // without adding a large GUI framework or another image asset.
    unsafe fn class(name: &[u8]) -> *mut c_void {
        objc_getClass(name.as_ptr().cast())
    }
    unsafe fn selector(name: &[u8]) -> *mut c_void {
        sel_registerName(name.as_ptr().cast())
    }
    unsafe fn msg0(receiver: *mut c_void, sel: *mut c_void) -> *mut c_void {
        let send: unsafe extern "C" fn(*mut c_void, *mut c_void) -> *mut c_void =
            std::mem::transmute(objc_msgSend as *const ());
        send(receiver, sel)
    }
    unsafe fn msg1(receiver: *mut c_void, sel: *mut c_void, arg: *mut c_void) -> *mut c_void {
        let send: unsafe extern "C" fn(*mut c_void, *mut c_void, *mut c_void) -> *mut c_void =
            std::mem::transmute(objc_msgSend as *const ());
        send(receiver, sel, arg)
    }
    unsafe fn msg2(
        receiver: *mut c_void,
        sel: *mut c_void,
        arg1: *mut c_void,
        arg2: *mut c_void,
    ) -> *mut c_void {
        let send: unsafe extern "C" fn(
            *mut c_void,
            *mut c_void,
            *mut c_void,
            *mut c_void,
        ) -> *mut c_void = std::mem::transmute(objc_msgSend as *const ());
        send(receiver, sel, arg1, arg2)
    }
    unsafe fn msg_bool(receiver: *mut c_void, sel: *mut c_void, value: bool) {
        let send: unsafe extern "C" fn(*mut c_void, *mut c_void, bool) =
            std::mem::transmute(objc_msgSend as *const ());
        send(receiver, sel, value)
    }
    unsafe fn msg_uinteger2(
        receiver: *mut c_void,
        sel: *mut c_void,
        value: usize,
        properties: *mut c_void,
    ) -> *mut c_void {
        let send: unsafe extern "C" fn(
            *mut c_void,
            *mut c_void,
            usize,
            *mut c_void,
        ) -> *mut c_void = std::mem::transmute(objc_msgSend as *const ());
        send(receiver, sel, value, properties)
    }
    unsafe fn data_to_vec(data: *mut c_void) -> Option<Vec<u8>> {
        if data.is_null() {
            return None;
        }
        let length: usize = {
            let send: unsafe extern "C" fn(*mut c_void, *mut c_void) -> usize =
                std::mem::transmute(objc_msgSend as *const ());
            send(data, selector(b"length\0"))
        };
        if length == 0 {
            return Some(Vec::new());
        }
        let bytes: *const u8 = {
            let send: unsafe extern "C" fn(*mut c_void, *mut c_void) -> *const u8 =
                std::mem::transmute(objc_msgSend as *const ());
            send(data, selector(b"bytes\0"))
        };
        if bytes.is_null() {
            return None;
        }
        Some(std::slice::from_raw_parts(bytes, length).to_vec())
    }

    unsafe {
        let ns_string = class(b"NSString\0");
        let make_string = selector(b"stringWithUTF8String:\0");
        let symbol = msg1(
            ns_string,
            make_string,
            (b"function\0".as_ptr() as *mut c_char).cast(),
        );
        let description = msg1(
            ns_string,
            make_string,
            (b"FormulaOCR\0".as_ptr() as *mut c_char).cast(),
        );
        if symbol.is_null() || description.is_null() {
            return None;
        }

        let image_class = class(b"NSImage\0");
        let image = msg2(
            image_class,
            selector(b"imageWithSystemSymbolName:accessibilityDescription:\0"),
            symbol,
            description,
        );
        if image.is_null() {
            return None;
        }
        msg_bool(image, selector(b"setTemplate:\0"), true);

        let tiff = msg0(image, selector(b"TIFFRepresentation\0"));
        let bitmap = msg1(class(b"NSBitmapImageRep\0"), selector(b"imageRepWithData:\0"), tiff);
        let properties = msg0(class(b"NSDictionary\0"), selector(b"dictionary\0"));
        if bitmap.is_null() || properties.is_null() {
            return None;
        }
        // NSBitmapImageFileTypePNG is the stable AppKit enum value 4.
        let png_data = msg_uinteger2(
            bitmap,
            selector(b"representationUsingType:properties:\0"),
            4,
            properties,
        );
        let png = data_to_vec(png_data)?;
        tauri::image::Image::from_bytes(&png).ok()
    }
}

#[cfg(not(target_os = "macos"))]
fn original_function_tray_icon() -> Option<tauri::image::Image<'static>> {
    None
}

/// Replace tray-icon's rasterized image with the native SF Symbol after the
/// NSStatusItem has been created.  This preserves the vector-backed Retina
/// rendering used by the original PySide/AppKit implementation.
#[cfg(target_os = "macos")]
fn install_native_function_symbol<R: tauri::Runtime>(tray: &tauri::tray::TrayIcon<R>) {
    let _ = tray.with_inner_tray_icon(|inner| {
        use objc2::MainThreadMarker;
        use objc2_app_kit::NSImage;
        use objc2_foundation::NSString;

        let Some(status_item) = inner.ns_status_item() else {
            return false;
        };
        let Some(mtm) = MainThreadMarker::new() else {
            return false;
        };
        let name = NSString::from_str("function");
        let description = NSString::from_str("FormulaOCR");
        let Some(image) = NSImage::imageWithSystemSymbolName_accessibilityDescription(
            &name,
            Some(&description),
        ) else {
            return false;
        };
        image.setTemplate(true);
        if let Some(button) = status_item.button(mtm) {
            button.setImage(Some(&image));
            return true;
        }
        false
    });
}

#[cfg(not(target_os = "macos"))]
fn install_native_function_symbol<R: tauri::Runtime>(_tray: &tauri::tray::TrayIcon<R>) {}

struct Bridge {
    _child: Arc<Mutex<Child>>,
    stdin: Arc<Mutex<ChildStdin>>,
    pending: Arc<Mutex<HashMap<String, mpsc::Sender<Result<Value, String>>>>>,
}

impl Bridge {
    fn spawn() -> Result<Self, String> {
        let packaged_sidecar = std::env::current_exe()
            .ok()
            .and_then(|path| path.parent().map(|parent| parent.join("../Resources/formulaocr-sidecar/formulaocr-sidecar")))
            .filter(|path| path.is_file());
        let mut command = if let Ok(path) = std::env::var("FORMULAOCR_SIDECAR") {
            Command::new(path)
        } else if let Some(path) = packaged_sidecar {
            Command::new(path)
        } else {
            let mut c = Command::new("python3");
            c.args(["-m", "sidecar"]);
            c
        };
        if std::env::var_os("FORMULAOCR_KEYCHAIN_SERVICE").is_none() {
            command.env("FORMULAOCR_KEYCHAIN_SERVICE", "FormulaOCR API");
        }
        if std::env::var_os("FORMULAOCR_MODEL_PATH").is_none() {
            if let Ok(executable) = std::env::current_exe() {
                if let Some(parent) = executable.parent() {
                    let model = parent.join("../Resources/pp_formulanet_plus_l.onnx");
                    if model.is_file() { command.env("FORMULAOCR_MODEL_PATH", model); }
                }
            }
        }
        let stage_root = stage_root()?;
        command.env("FORMULAOCR_STAGE_ROOT", &stage_root);
        command.env(
            "FORMULAOCR_KEYCHAIN_SERVICE",
            if cfg!(debug_assertions) { "FormulaOCR API Dev" } else { "FormulaOCR API" },
        );
        if let Ok(data_root) = std::env::var("FORMULAOCR_DATA_ROOT") {
            command.env("FORMULAOCR_DATA_ROOT", data_root);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("无法启动 FormulaOCR sidecar: {error}"))?;
        let stdin = Arc::new(Mutex::new(child.stdin.take().ok_or("sidecar stdin unavailable")?));
        let stdout = child.stdout.take().ok_or("sidecar stdout unavailable")?;
        let pending: Arc<Mutex<HashMap<String, mpsc::Sender<Result<Value, String>>>>> = Arc::new(Mutex::new(HashMap::new()));
        let reader_pending = Arc::clone(&pending);
        thread::Builder::new().name("formulaocr-sidecar-reader".into()).spawn(move || {
            let mut stdout = BufReader::new(stdout);
            let mut line = String::new();
            loop {
                line.clear();
                match stdout.read_line(&mut line) {
                    Ok(0) | Err(_) => break,
                    Ok(_) => {
                        let parsed = serde_json::from_str::<Value>(line.trim()).map_err(|error| format!("sidecar 返回无效 JSON: {error}"));
                        let id = parsed.as_ref().ok().and_then(|value| value.get("id")).and_then(Value::as_str).unwrap_or("").to_string();
                        if let Ok(mut waiters) = reader_pending.lock() {
                            if let Some(waiter) = waiters.remove(&id) { let _ = waiter.send(parsed); }
                        }
                    }
                }
            }
            if let Ok(mut waiters) = reader_pending.lock() {
                for (_, waiter) in waiters.drain() { let _ = waiter.send(Err("sidecar 已退出".into())); }
            }
        }).map_err(|error| format!("无法启动 sidecar 响应线程: {error}"))?;
        Ok(Self { _child: Arc::new(Mutex::new(child)), stdin, pending })
    }

    fn request(&self, request: &Value) -> Result<Value, String> {
        let id = request.get("id").and_then(Value::as_str).ok_or("sidecar request id is missing")?.to_string();
        let (sender, receiver) = mpsc::channel();
        self.pending.lock().map_err(|_| "sidecar 请求表锁定失败")?.insert(id.clone(), sender);
        let line = serde_json::to_string(request).map_err(|e| e.to_string())?;
        let write_result = (|| {
            let mut stdin = self.stdin.lock().map_err(|_| "sidecar 输入锁定失败")?;
            writeln!(stdin, "{line}").map_err(|e| e.to_string())?;
            stdin.flush().map_err(|e| e.to_string())
        })();
        if let Err(error) = write_result {
            let _ = self.pending.lock().map(|mut waiters| waiters.remove(&id));
            return Err(error);
        }
        receiver.recv().map_err(|_| "sidecar 响应通道已关闭".to_string())?
    }
}

struct AppState(Arc<Mutex<Option<Arc<Bridge>>>>);
struct HotkeyState(Mutex<String>);

#[tauri::command]
async fn sidecar_request(state: tauri::State<'_, AppState>, request: Value) -> Result<Value, String> {
    // Model inference and JSON-lines reads are blocking work. Running them in
    // a blocking worker keeps the Tauri/WebKit event loop free so React can
    // paint the selected image while OCR is still running.
    let state = Arc::clone(&state.0);
    tauri::async_runtime::spawn_blocking(move || {
        let instance = {
            let mut bridge = state.lock().map_err(|_| "sidecar 状态锁定失败")?;
            if bridge.is_none() { *bridge = Some(Arc::new(Bridge::spawn()?)); }
            Arc::clone(bridge.as_ref().unwrap())
        };
        match instance.request(&request) {
            Ok(value) => Ok(value),
            Err(first_error) => {
                if let Ok(mut bridge) = state.lock() { *bridge = None; }
                Err(first_error)
            }
        }
    })
    .await
    .map_err(|error| format!("sidecar 工作线程失败: {error}"))?
}

#[tauri::command]
async fn native_screenshot<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<String, String> {
    // Read the selected region from a private temporary PNG instead of
    // immediately reading NSPasteboard from the WebView.  Clipboard reads
    // are permission-sensitive on macOS and, after a global shortcut, may
    // race the screencapture process; that was why the old flow opened the
    // selector but then required a second manual paste.
    let bytes = tauri::async_runtime::spawn_blocking(move || {
        let path = staged_png_path("capture")?;
        let status = std::process::Command::new("/usr/sbin/screencapture")
            .args(["-i", "-s"])
            .arg(&path)
            .status()
            .map_err(|error| format!("无法启动 macOS 截图: {error}"))?;
        if !status.success() {
            let _ = std::fs::remove_file(&path);
            return Err("截图已取消或未获屏幕录制权限".into());
        }
        if std::fs::metadata(&path).map(|value| value.len()).unwrap_or(0) == 0 {
            let _ = std::fs::remove_file(&path);
            return Err("截图结果为空".into());
        }
        Ok::<String, String>(path.to_string_lossy().into_owned())
    })
    .await
    .map_err(|error| format!("截图工作线程失败: {error}"))??;
    // A global shortcut may start capture while the app is hidden. Restore
    // the main window only after the selection overlay has gone away.
    show_main_window(&app);
    Ok(bytes)
}

#[tauri::command]
fn set_global_hotkey<R: tauri::Runtime>(app: tauri::AppHandle<R>, state: tauri::State<'_, HotkeyState>, shortcut: String) -> Result<(), String> {
    // Replace the binding only after the new accelerator has been validated.
    // The plugin-level handler installed in `run` handles dynamically registered shortcuts too.
    let previous = state.0.lock().map_err(|_| "快捷键状态锁定失败")?.clone();
    app.global_shortcut().unregister_all().map_err(|e| e.to_string())?;
    if !shortcut.trim().is_empty() {
        if let Err(error) = app.global_shortcut().register(shortcut.trim()) {
            if !previous.is_empty() { let _ = app.global_shortcut().register(previous.as_str()); }
            return Err(error.to_string());
        }
    }
    *state.0.lock().map_err(|_| "快捷键状态锁定失败")? = shortcut.trim().to_string();
    Ok(())
}

fn shutdown_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(state) = app.try_state::<AppState>() {
        if let Ok(mut bridge) = state.0.lock() {
            if let Some(instance) = bridge.as_ref() {
                let _ = instance.request(&serde_json::json!({"id":"shutdown","method":"system.shutdown","params":{}}));
            }
            *bridge = None;
        }
    }
    let _ = app.global_shortcut().unregister_all();
}

#[tauri::command]
fn quit_application<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<(), String> {
    shutdown_sidecar(&app);
    app.exit(0);
    Ok(())
}

#[tauri::command]
fn set_activation_policy<R: tauri::Runtime>(app: tauri::AppHandle<R>, accessory: bool) -> Result<(), String> {
    app.set_activation_policy(if accessory { ActivationPolicy::Accessory } else { ActivationPolicy::Regular }).map_err(|error| error.to_string())
}

#[tauri::command]
fn resize_settings_window<R: tauri::Runtime>(app: tauri::AppHandle<R>, width: f64, height: f64) -> Result<(), String> {
    let window = app.get_webview_window("settings").ok_or("设置窗口不存在")?;
    window
        .set_size(tauri::LogicalSize::new(width.max(760.0), height.max(420.0)))
        .map_err(|error| error.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcut("ctrl+alt+cmd+o")
                .expect("default screenshot shortcut is valid")
                .with_handler(|app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        let _ = app.emit("formulaocr://screenshot-requested", ());
                    }
                })
                .build(),
        )
        .manage(AppState(Arc::new(Mutex::new(None))))
        .manage(HotkeyState(Mutex::new("ctrl+alt+cmd+o".to_string())))
        .invoke_handler(tauri::generate_handler![sidecar_request, stage_image_bytes, native_copy_word, native_screenshot, set_global_hotkey, set_menu_language, quit_application, set_activation_policy, resize_settings_window])
        .setup(|app| {
            let menu = tray_menu(app.handle(), "zh-CN")?;
            let mut tray_builder = TrayIconBuilder::with_id("main")
                .menu(&menu)
                .tooltip("FormulaOCR");
            // This is the exact AppKit SF Symbol used by the original
            // `macos_status_item.py`, not a replacement text glyph.  The
            // fallback is retained only for systems where the symbol cannot
            // be rasterized by AppKit.
            if let Some(icon) = original_function_tray_icon() {
                tray_builder = tray_builder.icon(icon).icon_as_template(true);
            }
            let tray = tray_builder.on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        show_main_window(app);
                    }
                    "screenshot" => { let _ = app.emit("formulaocr://screenshot-requested", ()); }
                    "settings" => { let _ = app.emit("formulaocr://open-settings", "常规"); }
                    "quit" => { shutdown_sidecar(app); app.exit(0); }
                    _ => {}
                });
            let tray = tray.build(app)?;
            install_native_function_symbol(&tray);
            if let Some(window) = app.get_webview_window("main") {
                let close_window = window.clone();
                let _ = window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        // Keep the process and menu-bar item alive; the frontend controls
                        // whether the Dock icon is hidden according to the saved preference.
                        // Hiding instead of destroying the window makes menu-bar restoration reliable.
                        let _ = close_window.emit("formulaocr://window-close-requested", ());
                        let _ = close_window.hide();
                    }
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building FormulaOCR");
    app.run(|app, event| {
        #[cfg(target_os = "macos")]
        if let RunEvent::Reopen { .. } = event {
            show_main_window(app);
        }
    });
}
