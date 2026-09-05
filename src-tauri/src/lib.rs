use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::collections::HashMap;
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;
use tauri::menu::{Menu, MenuBuilder, MenuItemBuilder};
use tauri::tray::TrayIconBuilder;
use tauri::Manager;
use tauri::Emitter;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tauri::{RunEvent, WindowEvent};
use tauri::ActivationPolicy;

fn show_main_window<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if app.try_state::<Lifecycle>().map(|state| state.finished.load(Ordering::SeqCst)).unwrap_or(false) { return; }
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
    if bytes.is_empty() || bytes.len() > 32 * 1024 * 1024 { return Err("图片应小于 32 MB，且不能为空".into()); }
    let path = staged_png_path("input")?;
    std::fs::write(&path, bytes).map_err(|error| format!("无法暂存图片: {error}"))?;
    Ok(path.to_string_lossy().into_owned())
}

#[tauri::command]
fn native_copy_text(text: String) -> Result<(), String> {
    use objc2_app_kit::NSPasteboard;
    use objc2_foundation::NSString;
    let pasteboard = NSPasteboard::generalPasteboard();
    pasteboard.clearContents();
    if pasteboard.setString_forType(&NSString::from_str(&text), &NSString::from_str("public.utf8-plain-text")) { Ok(()) }
    else { Err("macOS 剪贴板拒绝写入".into()) }
}

#[tauri::command]
fn native_paste_image() -> Result<String, String> {
    use objc2_app_kit::{NSPasteboard, NSBitmapImageRep, NSBitmapImageFileType};
    use objc2_foundation::{NSString, NSDictionary};
    let pasteboard = NSPasteboard::generalPasteboard();
    let data = pasteboard.dataForType(&NSString::from_str("public.png"))
        .or_else(|| pasteboard.dataForType(&NSString::from_str("public.tiff")))
        .ok_or("剪贴板中没有图片")?;
    let image = NSBitmapImageRep::imageRepWithData(&data).ok_or("无法读取剪贴板图片")?;
    // An empty properties dictionary is valid for PNG encoding.
    let png = unsafe { image.representationUsingType_properties(NSBitmapImageFileType::PNG, &NSDictionary::new()) }.ok_or("无法转换剪贴板图片")?;
    stage_image_bytes(png.to_vec())
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
    child: Arc<Mutex<Child>>,
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
        } else if cfg!(debug_assertions) {
            command.env("FORMULAOCR_DATA_ROOT", std::env::temp_dir().join("formulaocr-development"));
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
        Ok(Self { child: Arc::new(Mutex::new(child)), stdin, pending })
    }

    fn request(&self, request: &Value) -> Result<Value, String> {
        let id = request.get("id").and_then(Value::as_str).ok_or("sidecar request id is missing")?.to_string();
        let (sender, receiver) = mpsc::channel();
        let mut pending = self.pending.lock().map_err(|_| "sidecar 请求表锁定失败")?;
        if pending.contains_key(&id) { return Err("duplicate sidecar request id".into()); }
        pending.insert(id.clone(), sender);
        drop(pending);
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
        let timeout = if request["method"] == "system.shutdown" { 3 } else { 260 };
        let result = receiver.recv_timeout(Duration::from_secs(timeout)).map_err(|_| "sidecar response timed out or disconnected".to_string());
        if result.is_err() { let _ = self.pending.lock().map(|mut waiters| waiters.remove(&id)); }
        result?
    }
}

impl Drop for Bridge {
    fn drop(&mut self) {
        if let Ok(mut child) = self.child.lock() {
            if child.try_wait().ok().flatten().is_none() { let _ = child.kill(); }
            let _ = child.wait();
        }
    }
}

struct AppState(Arc<Mutex<Option<Arc<Bridge>>>>);
struct HotkeyState(Mutex<String>);
#[derive(Default)]
struct Lifecycle { requested: AtomicBool, finished: AtomicBool, recording: AtomicBool, capturing: AtomicBool }

#[tauri::command]
fn set_hotkey_recording(state: tauri::State<'_, Lifecycle>, recording: bool) {
    state.recording.store(recording, Ordering::SeqCst);
}

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
                if let Ok(mut bridge) = state.lock() {
                    if bridge.as_ref().map(|value| Arc::ptr_eq(value, &instance)).unwrap_or(false) { *bridge = None; }
                }
                Err(first_error)
            }
        }
    })
    .await
    .map_err(|error| format!("sidecar 工作线程失败: {error}"))?
}

#[tauri::command]
async fn native_screenshot<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<String, String> {
    if app.state::<Lifecycle>().capturing.swap(true, Ordering::SeqCst) { return Err("截图正在进行".into()); }
    // Read the selected region from a private temporary PNG instead of
    // immediately reading NSPasteboard from the WebView.  Clipboard reads
    // are permission-sensitive on macOS and, after a global shortcut, may
    // race the screencapture process; that was why the old flow opened the
    // selector but then required a second manual paste.
    let bytes = tauri::async_runtime::spawn_blocking(move || {
        let path = staged_png_path("capture")?;
        let status = std::process::Command::new("/usr/sbin/screencapture")
            .args(["-i", "-s", "-x"])
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
    .map_err(|error| format!("截图工作线程失败: {error}"));
    app.state::<Lifecycle>().capturing.store(false, Ordering::SeqCst);
    let bytes = bytes??;
    // A global shortcut may start capture while the app is hidden. Restore
    // the main window only after the selection overlay has gone away.
    show_main_window(&app);
    Ok(bytes)
}

#[tauri::command]
fn set_global_hotkey<R: tauri::Runtime>(app: tauri::AppHandle<R>, state: tauri::State<'_, HotkeyState>, shortcut: String) -> Result<(), String> {
    // Replace the binding only after the new accelerator has been validated.
    // The plugin-level handler installed in `run` handles dynamically registered shortcuts too.
    let mut binding = state.0.lock().map_err(|_| "快捷键状态锁定失败")?;
    let previous = binding.clone();
    if previous == shortcut.trim() { return Ok(()); }
    if !shortcut.trim().is_empty() {
        if let Err(error) = app.global_shortcut().register(shortcut.trim()) {
            return Err(error.to_string());
        }
    }
    if !previous.is_empty() {
        if let Err(error) = app.global_shortcut().unregister(previous.as_str()) {
            if !shortcut.trim().is_empty() { let _ = app.global_shortcut().unregister(shortcut.trim()); }
            return Err(error.to_string());
        }
    }
    *binding = shortcut.trim().to_string();
    Ok(())
}

fn shutdown_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    let instance = app.try_state::<AppState>().and_then(|state| state.0.lock().ok().and_then(|mut bridge| bridge.take()));
    if let Some(instance) = instance {
        let _ = instance.request(&serde_json::json!({"id":"shutdown","method":"system.shutdown","params":{}}));
        if let Ok(mut child) = instance.child.lock() {
            if child.try_wait().ok().flatten().is_none() { let _ = child.kill(); }
            let _ = child.wait();
        }
    }
}

fn begin_quit<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if app.state::<Lifecycle>().requested.swap(true, Ordering::SeqCst) { return; }
    let target = if app.get_webview_window("settings").is_some() { "settings" } else { "main" };
    let _ = app.emit_to(target, "formulaocr://quit-requested", ());
}

#[tauri::command]
fn cancel_quit(state: tauri::State<'_, Lifecycle>) { state.requested.store(false, Ordering::SeqCst); }

#[tauri::command]
fn continue_quit<R: tauri::Runtime>(app: tauri::AppHandle<R>) {
    let _ = app.emit_to("main", "formulaocr://flush-before-quit", ());
}

#[tauri::command]
async fn complete_quit<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<(), String> {
    if app.state::<Lifecycle>().finished.swap(true, Ordering::SeqCst) { return Ok(()); }
    let _ = app.global_shortcut().unregister_all();
    let _ = app.remove_tray_by_id("main");
    let cleanup = app.clone();
    tauri::async_runtime::spawn_blocking(move || shutdown_sidecar(&cleanup)).await.map_err(|error| error.to_string())?;
    app.exit(0);
    Ok(())
}

#[tauri::command]
fn quit_application<R: tauri::Runtime>(app: tauri::AppHandle<R>) { begin_quit(&app); }

#[tauri::command]
fn main_geometry<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<Value, String> {
    let window = app.get_webview_window("main").ok_or("main window unavailable")?;
    let scale = window.scale_factor().map_err(|error| error.to_string())?;
    let position = window.outer_position().map_err(|error| error.to_string())?.to_logical::<f64>(scale);
    let size = window.inner_size().map_err(|error| error.to_string())?.to_logical::<f64>(scale);
    Ok(serde_json::json!({"x":position.x, "y":position.y, "width":size.width, "height":size.height}))
}

#[tauri::command]
fn restore_main_geometry<R: tauri::Runtime>(app: tauri::AppHandle<R>, geometry: Value) -> Result<(), String> {
    let window = app.get_webview_window("main").ok_or("main window unavailable")?;
    let monitor = window.current_monitor().map_err(|e| e.to_string())?.or(window.primary_monitor().map_err(|e| e.to_string())?).ok_or("display unavailable")?;
    let scale = monitor.scale_factor();
    let size = monitor.size().to_logical::<f64>(scale);
    let origin = monitor.position().to_logical::<f64>(scale);
    let valid = |key: &str, fallback: f64| geometry[key].as_f64().filter(|value| value.is_finite()).unwrap_or(fallback);
    let width = valid("width", 1120.0).clamp(900.0, size.width.max(900.0));
    let height = valid("height", 760.0).clamp(650.0, (size.height - 80.0).max(650.0));
    let x = valid("x", origin.x + (size.width - width) / 2.0).clamp(origin.x, origin.x + (size.width - width).max(0.0));
    let y = valid("y", origin.y + 40.0).clamp(origin.y + 30.0, origin.y + (size.height - height - 40.0).max(30.0));
    window.set_size(tauri::LogicalSize::new(width, height)).map_err(|e| e.to_string())?;
    window.set_position(tauri::LogicalPosition::new(x, y)).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_activation_policy<R: tauri::Runtime>(app: tauri::AppHandle<R>, accessory: bool) -> Result<(), String> {
    if app.state::<Lifecycle>().requested.load(Ordering::SeqCst) { return Ok(()); }
    app.set_activation_policy(if accessory { ActivationPolicy::Accessory } else { ActivationPolicy::Regular }).map_err(|error| error.to_string())
}

#[tauri::command]
fn resize_settings_window<R: tauri::Runtime>(app: tauri::AppHandle<R>, width: f64, height: f64) -> Result<(), String> {
    let window = app.get_webview_window("settings").ok_or("设置窗口不存在")?;
    if !width.is_finite() || !height.is_finite() { return Err("Invalid window size".into()); }
    let monitor = window.current_monitor().map_err(|e| e.to_string())?.ok_or("display unavailable")?;
    let scale = monitor.scale_factor();
    let screen = monitor.size().to_logical::<f64>(scale);
    let origin = monitor.position().to_logical::<f64>(scale);
    let width = width.clamp(760.0, screen.width.max(760.0));
    let height = height.clamp(420.0, (screen.height - 90.0).max(420.0));
    let position = window.outer_position().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    window
        .set_size(tauri::LogicalSize::new(width, height))
        .map_err(|error| error.to_string())?;
    window.set_position(tauri::LogicalPosition::new(
        position.x.clamp(origin.x, origin.x + (screen.width - width).max(0.0)),
        position.y.clamp(origin.y + 30.0, origin.y + (screen.height - height - 40.0).max(30.0)),
    )).map_err(|error| error.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed && !app.state::<Lifecycle>().recording.load(Ordering::SeqCst) && !app.state::<Lifecycle>().requested.load(Ordering::SeqCst) {
                        let _ = app.emit("formulaocr://screenshot-requested", ());
                    }
                })
                .build(),
        )
        .manage(AppState(Arc::new(Mutex::new(None))))
        .manage(HotkeyState(Mutex::new(String::new())))
        .manage(Lifecycle::default())
        .invoke_handler(tauri::generate_handler![sidecar_request, stage_image_bytes, native_copy_word, native_screenshot, set_global_hotkey, set_menu_language, quit_application, set_activation_policy, resize_settings_window, native_copy_text, native_paste_image, set_hotkey_recording, cancel_quit, continue_quit, complete_quit, main_geometry, restore_main_geometry])
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
                    "quit" => begin_quit(app),
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
        match event {
            RunEvent::ExitRequested { api, .. } if !app.state::<Lifecycle>().finished.load(Ordering::SeqCst) => {
                api.prevent_exit();
                begin_quit(app);
            }
            RunEvent::Reopen { .. } => show_main_window(app),
            RunEvent::Exit => shutdown_sidecar(app),
            _ => {}
        }
    });
}
