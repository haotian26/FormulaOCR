export type SidecarResponse<T> =
  | { id: string; ok: true; result: T }
  | { id: string; ok: false; error: { code: string; message: string; retryable: boolean } }


/** Transport seam. Tauri's Rust command attaches the JSON-lines process here. */
export async function callSidecar<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  const id = crypto.randomUUID()
  const response = await invoke<SidecarResponse<T>>('sidecar_request', { request: { id, method, params } })
  if (!response.ok) throw new Error(response.error.message)
  return response.result
}
import { invoke } from '@tauri-apps/api/core'
