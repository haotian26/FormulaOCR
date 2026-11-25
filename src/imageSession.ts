type Transport = <T>(method: string, params?: Record<string, unknown>) => Promise<T>;
type ImageLease = { id: string; blob: Blob; session?: string; historyId?: string };

function base64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(reader.error || Error("Image could not be read"));
    reader.readAsDataURL(blob);
  });
}

/** The displayed image survives a backend process restart, never an API call. */
export class ImageSession {
  private current: ImageLease | null = null;
  constructor(private call: Transport) {}
  adopt(id: string, blob: Blob, session?: string, historyId?: string) {
    this.current = { id, blob, session, historyId };
  }
  setHistoryId(historyId?: string) { if (this.current) this.current.historyId = historyId; }
  invalidate() { if (this.current) this.current.session = undefined; }
  clear() { this.current = null; }
  async ensure(): Promise<string> {
    const image = this.current;
    if (!image) throw Error("请先载入图片");
    // Only health is safe to retry. OCR/history mutation and billable API
    // recognition are never replayed automatically after a transport failure.
    const health = () => this.call<{ session_id?: string }>("system.health");
    const backend = await health().catch(() => health());
    if (this.current !== image) throw Error("图片已切换，请重试");
    if (backend.session_id && backend.session_id !== image.session) {
      const png_base64 = await base64(image.blob);
      if (this.current !== image) throw Error("图片已切换，请重试");
      const restored = await this.call<{ image_id: string; session_id: string }>("image.open", {
        image_id: image.id, png_base64, history_id: image.historyId,
      });
      if (this.current !== image) {
        void this.call("image.release", { image_id: restored.image_id }).catch(() => undefined);
        throw Error("图片已切换，请重试");
      }
      image.id = restored.image_id;
      image.session = restored.session_id;
    }
    return image.id;
  }
}
