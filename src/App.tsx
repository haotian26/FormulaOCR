import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { ClipboardPaste, Copy, FolderOpen, History, ImageUp, Settings, Sparkles, Undo2, Redo2, RotateCcw } from 'lucide-react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { callSidecar } from './sidecar'

const emptyLatex = 'OCR 结果将在这里显示'
type HistoryItem = { id: string; updated_at: number; local_draft_latex: string; api_draft_latex?: string; has_api?: boolean }
type APIProfile = { id: string; name: string; enabled: boolean; provider_type: string; base_url?: string; model?: string; timeout_s?: number; prompt_override?: string; api_key?: string; app_id?: string; app_key?: string }

export function App() {
  const [drawer, setDrawer] = useState(false)
  const [latex, setLatex] = useState('')
  const [originalLatex, setOriginalLatex] = useState('')
  const [localLatex, setLocalLatex] = useState('')
  const [apiLatex, setApiLatex] = useState('')
  const [source, setSource] = useState<'内置' | 'API'>('内置')
  const [undoStack, setUndoStack] = useState<string[]>([])
  const [redoStack, setRedoStack] = useState<string[]>([])
  const [previewHtml, setPreviewHtml] = useState('')
  const [status, setStatus] = useState('请选择一张公式图片')
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [historyRecords, setHistoryRecords] = useState<HistoryItem[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsPage, setSettingsPage] = useState('常规')
  const [settings, setSettings] = useState({ auto_copy: false, hide_dock_on_close: true, hotkey: 'ctrl+alt+cmd+o', history_limit: 200 })
  const [savedSettings, setSavedSettings] = useState(settings)
  const fileInput = useRef<HTMLInputElement>(null)
  const [apiEnabled, setApiEnabled] = useState(false)
  const [apiProfiles, setApiProfiles] = useState<APIProfile[]>([])
  const [activeProfileId, setActiveProfileId] = useState('')
  const [selectedHistory, setSelectedHistory] = useState<string[]>([])
  const [layout, setLayout] = useState(() => { try { return JSON.parse(localStorage.getItem('formulaocr.layout.v1') || '{"image":42,"result":50}') } catch { return { image: 42, result: 50 } } })
  const [profileDrafts, setProfileDrafts] = useState<APIProfile[]>([])
  const [profilesDirty, setProfilesDirty] = useState(false)

  const recognizeBlob = useCallback(async (blob: Blob) => {
    setBusy(true)
    setStatus('正在识别…')
    setImageUrl(URL.createObjectURL(blob))
    try {
      const bytes = new Uint8Array(await blob.arrayBuffer())
      let binary = ''
      bytes.forEach(byte => { binary += String.fromCharCode(byte) })
      const opened = await callSidecar<{ image_id: string }>('image.open', { png_base64: btoa(binary) })
      const result = await callSidecar<{ formatted_latex?: string; raw_latex?: string; elapsed_ms?: number }>('ocr.recognize', { image_id: opened.image_id })
      const nextLatex = result.formatted_latex || result.raw_latex || ''
      setLatex(nextLatex); setLocalLatex(nextLatex); setApiLatex(''); setSource('内置')
      setOriginalLatex(nextLatex)
      setUndoStack([])
      setRedoStack([])
      setStatus(`识别完成${result.elapsed_ms ? ` · ${Math.round(result.elapsed_ms)} ms` : ''}`)
      if (settings.auto_copy && nextLatex) await copyLatexAsWord(nextLatex)
    } catch (error) {
      setStatus(`识别失败：${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    void callSidecar<typeof settings>('settings.get').then(value => { setSettings(value); setSavedSettings(value) }).catch(() => undefined)
    void callSidecar<{ api_enabled: boolean; active_profile_id: string; profiles: APIProfile[] }>('profiles.list').then(value => { setApiEnabled(value.api_enabled); setActiveProfileId(value.active_profile_id); setApiProfiles(value.profiles); setProfileDrafts(value.profiles.map(profile => ({...profile}))) }).catch(() => undefined)
  }, [])

  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const image = Array.from(event.clipboardData?.items ?? []).find(item => item.type.startsWith('image/'))?.getAsFile()
      if (!image) return
      event.preventDefault()
      void recognizeBlob(image)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [recognizeBlob])

  useEffect(() => {
    if (!drawer) return
    void callSidecar<{ records: HistoryItem[] }>('history.list').then(result => setHistoryRecords(result.records)).catch(() => setHistoryRecords([]))
  }, [drawer])

  useEffect(() => {
    void callSidecar<{ api_enabled: boolean; active_profile_id: string; profiles: APIProfile[] }>('profiles.list')
      .then(value => { setApiEnabled(value.api_enabled); setActiveProfileId(value.active_profile_id); setApiProfiles(value.profiles) })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!settingsOpen) return
    void callSidecar<typeof settings>('settings.get').then(value => { setSettings(value); setSavedSettings(value) }).catch(() => undefined)
  }, [settingsOpen])

  useEffect(() => {
    if (!settingsOpen) return
    const timer = window.setTimeout(() => { void invoke('set_global_hotkey', { shortcut: settings.hotkey }).catch(() => undefined) }, 250)
    return () => window.clearTimeout(timer)
  }, [settings.hotkey, settingsOpen])

  useEffect(() => {
    if (!latex.trim()) { setPreviewHtml(''); return }
    const timer = window.setTimeout(() => {
      void callSidecar<{ mathml: string }>('conversion.toMathML', { latex })
        .then(result => setPreviewHtml(result.mathml))
        .catch(() => setPreviewHtml('<span class="preview-error">无法渲染公式，请检查 LaTeX 语法</span>'))
    }, 120)
    return () => window.clearTimeout(timer)
  }, [latex])

  useEffect(() => { localStorage.setItem('formulaocr.layout.v1', JSON.stringify(layout)) }, [layout])

  const settingsDirty = JSON.stringify(settings) !== JSON.stringify(savedSettings)

  const saveProfiles = async () => {
    try {
      const value = await callSidecar<{ api_enabled: boolean; active_profile_id: string; profiles: APIProfile[] }>('profiles.save', { api_enabled: apiEnabled, active_profile_id: activeProfileId, profiles: profileDrafts })
      setApiEnabled(value.api_enabled); setActiveProfileId(value.active_profile_id); setApiProfiles(value.profiles); setProfileDrafts(value.profiles.map(profile => ({...profile}))); setProfilesDirty(false); setStatus('API 配置已保存')
    } catch (error) { setStatus(`API 配置保存失败：${error instanceof Error ? error.message : String(error)}`) }
  }

  const resizeImagePane = (event: ReactPointerEvent) => {
    event.preventDefault()
    const startY = event.clientY; const start = layout.image; const height = window.innerHeight
    const move = (next: PointerEvent) => setLayout((value: { image: number; result: number }) => ({...value, image: Math.max(25, Math.min(65, start + ((next.clientY - startY) / height) * 100))}))
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop)
  }

  const resizeResultPane = (event: ReactPointerEvent) => {
    event.preventDefault()
    const startX = event.clientX; const start = layout.result; const width = window.innerWidth
    const move = (next: PointerEvent) => setLayout((value: { image: number; result: number }) => ({...value, result: Math.max(30, Math.min(70, start + ((next.clientX - startX) / width) * 100))}))
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop)
  }

  const updateLatex = (next: string) => {
    setUndoStack(stack => [...stack, latex].slice(-100))
    setRedoStack([])
    setLatex(next)
    if (source === '内置') setLocalLatex(next); else setApiLatex(next)
  }

  const copyLatexAsWord = async (value = latex) => {
    if (!value.trim()) { setStatus('没有可复制的 LaTeX'); return }
    try {
      const mathml = (await callSidecar<{ mathml: string }>('conversion.toMathML', { latex: value })).mathml
      const html = `<div>${mathml}</div>`
      if ('ClipboardItem' in window && navigator.clipboard?.write) {
        await navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([value], { type: 'text/plain' }) })])
      } else await navigator.clipboard.writeText(value)
      setStatus('已复制 Word 格式')
    } catch (error) { setStatus(`复制 Word 失败：${error instanceof Error ? error.message : String(error)}`) }
  }

  const copyLatex = async () => {
    if (!latex.trim()) { setStatus('没有可复制的 LaTeX'); return }
    await navigator.clipboard.writeText(latex)
    setStatus('已复制 LaTeX')
  }

  const runScreenshot = async () => {
    setStatus('等待 macOS 截图选区…')
    try {
      await invoke('native_screenshot')
      const clipboard = await navigator.clipboard.read()
      for (const item of clipboard) {
        const type = item.types.find(value => value.startsWith('image/'))
        if (type) { await recognizeBlob(await item.getType(type)); return }
      }
      setStatus('未读取到截图')
    } catch (error) {
      setStatus(`截图失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  useEffect(() => {
    let stop: (() => void) | undefined
    void listen('formulaocr://screenshot-requested', () => { if (!busy) void runScreenshot() }).then(unlisten => { stop = unlisten })
    return () => { stop?.() }
  }, [busy])

  const restoreHistory = async (id: string) => {
    try {
      const [record, image] = await Promise.all([
        callSidecar<{ local_draft_latex: string; api_draft_latex?: string }>('history.get', { id }),
        callSidecar<{ png_base64: string }>('history.image', { id }),
      ])
      const nextLatex = record.local_draft_latex || ''
      setLatex(nextLatex); setLocalLatex(nextLatex); setApiLatex(record.api_draft_latex || ''); setSource(record.api_draft_latex ? 'API' : '内置')
      setOriginalLatex(nextLatex)
      setUndoStack([])
      setRedoStack([])
      setImageUrl(`data:image/png;base64,${image.png_base64}`)
      setStatus('已恢复历史记录')
    } catch (error) {
      setStatus(`历史记录读取失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const deleteHistory = async (id: string) => {
    try {
      await callSidecar('history.delete', { id })
      setHistoryRecords(records => records.filter(record => record.id !== id))
      setStatus('历史记录已删除')
    } catch (error) {
      setStatus(`历史记录删除失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const apiRecognize = async () => {
    if (!activeProfileId) { setStatus('没有可用的 API 配置'); return }
    setBusy(true)
    setStatus('正在进行 API 重识别…')
    try {
      const blob = imageUrl ? await (await fetch(imageUrl)).blob() : null
      if (!blob) throw new Error('当前没有图片')
      const bytes = new Uint8Array(await blob.arrayBuffer())
      let binary = ''
      bytes.forEach(byte => { binary += String.fromCharCode(byte) })
      const opened = await callSidecar<{ image_id: string }>('image.open', { png_base64: btoa(binary) })
      const result = await callSidecar<{ raw_latex: string; profile_name: string }>('api.recognize', { image_id: opened.image_id, profile_id: activeProfileId })
      setUndoStack(stack => [...stack, latex].slice(-100))
      setRedoStack([])
      setLatex(result.raw_latex); setApiLatex(result.raw_latex); setOriginalLatex(result.raw_latex); setSource('API')
      setStatus(`API 完成 · ${result.profile_name}`)
    } catch (error) {
      setStatus(`API 识别失败：${error instanceof Error ? error.message : String(error)}`)
    } finally { setBusy(false) }
  }

  return <main className="app-shell">
    <header className="toolbar">
      <button className="toolbar-button" onClick={() => setDrawer(v => !v)}><History size={17}/>历史</button>
      <button className="toolbar-button primary" onClick={() => fileInput.current?.click()} disabled={busy}><FolderOpen size={17}/>打开图片</button>
      <input ref={fileInput} hidden type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (file) void recognizeBlob(file); event.target.value = '' }}/>
      <button className="toolbar-button" onClick={async () => { try { const clipboard = await navigator.clipboard.read(); const item = clipboard.find(entry => entry.types.some(type => type.startsWith('image/'))); const type = item?.types.find(value => value.startsWith('image/')); if (item && type) await recognizeBlob(await item.getType(type)); else setStatus('剪贴板中没有图片'); } catch { setStatus('无法读取剪贴板图片，请使用 Command–V') } }} disabled={busy}><ClipboardPaste size={17}/>粘贴图片</button>
      <button className="toolbar-button" onClick={() => void runScreenshot()} disabled={busy}><ImageUp size={17}/>截图 OCR</button>
      {apiEnabled && apiProfiles.length > 0 && <><button className="toolbar-button" onClick={() => void apiRecognize()} disabled={busy}><Sparkles size={17}/>API 重识别</button><button className="profile-pill">{apiProfiles.find(profile => profile.id === activeProfileId)?.name || '当前 API 配置'}</button></>}
      <span className="toolbar-spacer" />
      <span className="status-pill">离线识别</span>
      <button className="icon-button" aria-label="设置" onClick={() => setSettingsOpen(true)}><Settings size={18}/></button>
    </header>

    <section className="workspace" style={{gridTemplateRows: `${layout.image}% 8px ${100 - layout.image}%`}}>
      <div className="image-card">{imageUrl ? <img className="source-image" src={imageUrl} alt="当前公式图片"/> : <div className="empty-state"><ImageUp size={32}/><span>打开、粘贴或截图一张公式</span></div>}</div>
      <div className="split-handle horizontal" onPointerDown={resizeImagePane} role="separator" aria-label="调整图片与结果比例" />
      <div className="result-card">
        <div className="result-toolbar"><strong>识别结果</strong>{localLatex && <button className={source === '内置' ? 'source-selector active' : 'source-selector'} onClick={() => { setSource('内置'); setLatex(localLatex); setOriginalLatex(localLatex) }}>内置</button>}{apiLatex && <button className={source === 'API' ? 'source-selector active' : 'source-selector'} onClick={() => { setSource('API'); setLatex(apiLatex); setOriginalLatex(apiLatex) }}>API</button>}<button className="icon-button" aria-label="撤销" disabled={!undoStack.length} onClick={() => { const previous = undoStack[undoStack.length - 1]; if (previous === undefined) return; setUndoStack(stack => stack.slice(0, -1)); setRedoStack(stack => [...stack, latex]); setLatex(previous) }}><Undo2 size={17}/></button><button className="icon-button" aria-label="重做" disabled={!redoStack.length} onClick={() => { const next = redoStack[redoStack.length - 1]; if (next === undefined) return; setRedoStack(stack => stack.slice(0, -1)); setUndoStack(stack => [...stack, latex]); setLatex(next) }}><Redo2 size={17}/></button><button className="secondary-button" onClick={() => updateLatex(originalLatex)}><RotateCcw size={15}/>恢复原文</button><span className="toolbar-spacer"/><button className="secondary-button" onClick={() => void copyLatexAsWord()}><Copy size={15}/>复制 Word</button><button className="secondary-button" onClick={() => void copyLatex()}><Copy size={15}/>复制 LaTeX</button></div>
        <div className="result-split" style={{gridTemplateColumns: `${layout.result}% 8px ${100 - layout.result}%`}}>
          <section className="editor-pane"><h2>LaTeX</h2><textarea value={latex} onChange={e => updateLatex(e.target.value)} placeholder={emptyLatex}/></section>
          <div className="split-handle vertical" onPointerDown={resizeResultPane} role="separator" aria-label="调整 LaTeX 与预览比例" />
          <section className="preview-pane"><h2>公式预览</h2><div className="preview-surface">{previewHtml ? <div className="mathml-content" dangerouslySetInnerHTML={{ __html: previewHtml }}/> : <span className="muted">{latex ? '正在渲染…' : '公式将在这里预览'}</span>}</div></section>
        </div>
      </div>
    </section>
    <footer className="footer"><label><input type="checkbox" checked={settings.auto_copy} onChange={event => setSettings({...settings, auto_copy: event.target.checked})}/>识别完成后自动复制 Word 格式</label><span>{status}</span></footer>
    {drawer && <aside className="history-drawer"><div className="drawer-header"><strong>识别历史</strong><span className="toolbar-spacer"/>{selectedHistory.length > 0 && <button className="text-danger" onClick={async () => { await callSidecar('history.deleteMany', { ids: selectedHistory }); setHistoryRecords(records => records.filter(record => !selectedHistory.includes(record.id))); setSelectedHistory([]); setStatus('已删除所选历史') }}>删除所选</button>}{historyRecords.length > 0 && <button className="text-danger" onClick={async () => { if (!window.confirm('删除全部识别历史？')) return; await callSidecar('history.deleteAll'); setHistoryRecords([]); setSelectedHistory([]); setStatus('识别历史已全部删除') }}>全部删除</button>}<button className="icon-button" onClick={() => setDrawer(false)} aria-label="关闭">×</button></div>{historyRecords.length ? <div className="history-list">{historyRecords.map(record => <div className="history-item" key={record.id}><input type="checkbox" checked={selectedHistory.includes(record.id)} onChange={event => setSelectedHistory(ids => event.target.checked ? [...ids, record.id] : ids.filter(id => id !== record.id))}/><button className="history-item-main" onClick={() => void restoreHistory(record.id)}><span>{new Date(record.updated_at * 1000).toLocaleString()}</span><small>{record.local_draft_latex || '无 LaTeX 结果'}</small></button><button className="icon-button danger" onClick={() => void deleteHistory(record.id)} aria-label="删除历史记录">×</button></div>)}</div> : <div className="drawer-empty">暂无识别记录</div>}</aside>}
    {settingsOpen && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSettingsOpen(false) }}><section className="settings-window" role="dialog" aria-label="FormulaOCR 设置"><header className="settings-header"><strong>设置</strong><button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="关闭">×</button></header><div className="settings-body"><nav className="settings-nav">{['常规', '界面与布局', '快捷键', '自定义模型与 API', '历史记录'].map(item => <button key={item} className={settingsPage === item ? 'settings-nav-item selected' : 'settings-nav-item'} onClick={() => setSettingsPage(item)}>{item}</button>)}</nav><section className="settings-content"><h2>{settingsPage}</h2>{settingsPage === '常规' && <><label className="setting-row"><input type="checkbox" checked={settings.auto_copy} onChange={event => setSettings({...settings, auto_copy: event.target.checked})}/>识别完成后自动复制 Word 格式</label><label className="setting-row"><input type="checkbox" checked={settings.hide_dock_on_close} onChange={event => setSettings({...settings, hide_dock_on_close: event.target.checked})}/>关闭窗口时隐藏 Dock 图标，保留菜单栏运行</label></>}{settingsPage === '快捷键' && <label className="setting-field">截图快捷键<input value={settings.hotkey} onChange={event => setSettings({...settings, hotkey: event.target.value})} placeholder="留空表示禁用"/></label>}{settingsPage === '历史记录' && <label className="setting-field">最多保存记录<input type="number" min={20} max={2000} value={settings.history_limit} onChange={event => setSettings({...settings, history_limit: Number(event.target.value)})}/></label>}{settingsPage === '界面与布局' && <p className="setting-help">窗口尺寸和分隔比例会在下次版本中按会话保存；当前版本不覆盖用户手动调整。</p>}{settingsPage === '自定义模型与 API' && <div className="api-settings"><label className="setting-row"><input type="checkbox" checked={apiEnabled} onChange={event => { setApiEnabled(event.target.checked); setProfilesDirty(true) }}/>启用 API 重识别</label>{profileDrafts.map((profile, index) => <div className="profile-editor" key={profile.id}><input value={profile.name} placeholder="配置名称" onChange={event => { const next = [...profileDrafts]; next[index] = {...profile, name: event.target.value}; setProfileDrafts(next); setProfilesDirty(true) }}/><input value={profile.base_url || ''} placeholder="HTTPS Base URL" onChange={event => { const next = [...profileDrafts]; next[index] = {...profile, base_url: event.target.value}; setProfileDrafts(next); setProfilesDirty(true) }}/><input value={profile.model || ''} placeholder="模型 ID" onChange={event => { const next = [...profileDrafts]; next[index] = {...profile, model: event.target.value}; setProfileDrafts(next); setProfilesDirty(true) }}/><input type="password" value={profile.api_key || ''} placeholder="API Key（写入 Keychain）" onChange={event => { const next = [...profileDrafts]; next[index] = {...profile, api_key: event.target.value}; setProfileDrafts(next); setProfilesDirty(true) }}/><button className="text-danger" onClick={() => { setProfileDrafts(profileDrafts.filter(item => item.id !== profile.id)); setProfilesDirty(true) }}>删除</button></div>)}<button className="secondary-button" onClick={() => { setProfileDrafts([...profileDrafts, {id: crypto.randomUUID().replaceAll('-', ''), name: '新配置', provider_type: 'openai_compatible', base_url: 'https://', model: '', enabled: true, timeout_s: 45}]); setProfilesDirty(true) }}>新增配置</button></div>}{<footer className="settings-footer"><button className="toolbar-button primary" disabled={settingsPage === '自定义模型与 API' ? !profilesDirty : !settingsDirty} onClick={settingsPage === '自定义模型与 API' ? () => void saveProfiles() : async () => { try { const value = await callSidecar<typeof settings>('settings.save', { values: settings }); setSettings(value); setSavedSettings(value) } catch { /* keep dirty */ } }}>保存</button>{!(settingsPage === '自定义模型与 API' ? profilesDirty : settingsDirty) && <span className="saved-hint">已保存</span>}</footer>}</section></div></section></div>}
  </main>
}
