import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Minus, Plus } from "lucide-react";
import { translate, type AppLanguage } from "./i18n";
import "./ImageViewer.css";

export type ImageViewerProps = { src: string; language: AppLanguage; alt?: string };
type Size = { width: number; height: number };
type Point = { x: number; y: number };
const origin: Point = { x: 0, y: 0 };

export function fitImageScale(image: Size, viewport: Size): number {
  if (image.width <= 0 || image.height <= 0 || viewport.width <= 0 || viewport.height <= 0) return 1;
  return Math.min(1, viewport.width / image.width, viewport.height / image.height);
}

export function constrainImagePan(pan: Point, image: Size, viewport: Size, scale: number): Point {
  const x = Math.max(0, (image.width * scale - viewport.width) / 2);
  const y = Math.max(0, (image.height * scale - viewport.height) / 2);
  return { x: Math.max(-x, Math.min(x, pan.x)), y: Math.max(-y, Math.min(y, pan.y)) };
}

// Keying the session also resets pan/zoom before a new image's first paint.
export function ImageViewer(props: ImageViewerProps) {
  return <ImageViewerSession key={props.src} {...props} />;
}

function ImageViewerSession({ src, language, alt }: ImageViewerProps) {
  const t = (key: string) => translate(language, key);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<Size>({ width: 0, height: 0 });
  const [natural, setNatural] = useState<Size | null>(null);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [pan, setPan] = useState<Point>(origin);
  const [dragging, setDragging] = useState(false);
  const [failed, setFailed] = useState(false);
  const drag = useRef<{ pointerId: number; start: Point; pan: Point } | null>(null);
  const fit = natural ? fitImageScale(natural, viewport) : 1;
  const scale = zoom === "fit" ? fit : zoom;
  const canPan = Boolean(natural && (natural.width * scale > viewport.width + 1 || natural.height * scale > viewport.height + 1));
  const bounded = natural ? constrainImagePan(pan, natural, viewport, scale) : origin;
  const changeZoom = (next: number) => setZoom(Math.max(Math.min(0.01, fit), Math.min(16, next)));
  const reset = () => { setZoom("fit"); setPan(origin); };

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const measure = () => {
      const { width, height } = element.getBoundingClientRect();
      setViewport({ width, height });
    };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    observer?.observe(element);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  useEffect(() => {
    if (natural) setPan(value => constrainImagePan(value, natural, viewport, scale));
  }, [natural, viewport, scale]);
  useEffect(() => {
    const element = viewportRef.current;
    if (!element || !natural) return;
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        changeZoom(scale * Math.exp(-event.deltaY * 0.002));
      } else if (canPan) {
        event.preventDefault();
        const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.height : 1;
        setPan(value => constrainImagePan({ x: value.x - event.deltaX * unit, y: value.y - event.deltaY * unit }, natural, viewport, scale));
      }
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [natural, viewport, scale, canPan, fit]);

  const finishDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return (
    <section className="image-viewer">
      <div className="image-viewer-toolbar" role="toolbar" aria-label={t("图片查看工具")}>
        <button type="button" disabled={!natural} aria-pressed={zoom === "fit"} onClick={reset}>{t("适合窗口")}</button>
        <button type="button" disabled={!natural} aria-label={t("实际大小")} title={t("实际大小")} aria-pressed={zoom === 1} onClick={() => { setZoom(1); setPan(origin); }}>100%</button>
        <span className="image-viewer-toolbar-spacer" />
        <button type="button" className="image-viewer-icon" disabled={!natural || scale <= Math.min(0.01, fit)} aria-label={t("缩小图片")} title={t("缩小图片")} onClick={() => changeZoom(scale / 1.25)}><Minus size={16} /></button>
        <output aria-label={t("图片缩放比例")}>{natural ? `${Math.round(scale * 100)}%` : "—"}</output>
        <button type="button" className="image-viewer-icon" disabled={!natural || scale >= 16} aria-label={t("放大图片")} title={t("放大图片")} onClick={() => changeZoom(scale * 1.25)}><Plus size={16} /></button>
      </div>
      <div
        ref={viewportRef}
        className={`image-viewer-viewport${canPan ? " can-pan" : ""}${dragging ? " is-dragging" : ""}`}
        tabIndex={0}
        role="region"
        aria-label={t("拖动或使用方向键平移图片")}
        onPointerDown={(event) => {
          if (!canPan || event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.focus();
          drag.current = { pointerId: event.pointerId, start: { x: event.clientX, y: event.clientY }, pan: bounded };
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const session = drag.current;
          if (!session || session.pointerId !== event.pointerId || !natural) return;
          setPan(constrainImagePan({ x: session.pan.x + event.clientX - session.start.x, y: session.pan.y + event.clientY - session.start.y }, natural, viewport, scale));
        }}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onLostPointerCapture={() => { drag.current = null; setDragging(false); }}
        onKeyDown={(event) => {
          if (!natural) return;
          const directions: Record<string, Point> = { ArrowLeft: { x: 40, y: 0 }, ArrowRight: { x: -40, y: 0 }, ArrowUp: { x: 0, y: 40 }, ArrowDown: { x: 0, y: -40 } };
          if (directions[event.key]) {
            event.preventDefault();
            const step = directions[event.key];
            setPan(value => constrainImagePan({ x: value.x + step.x, y: value.y + step.y }, natural, viewport, scale));
          } else if (event.key === "+" || event.key === "=") { event.preventDefault(); changeZoom(scale * 1.25); }
          else if (event.key === "-") { event.preventDefault(); changeZoom(scale / 1.25); }
          else if (event.key === "0" || event.key === "Escape") { event.preventDefault(); reset(); }
        }}
      >
        {failed ? <span className="image-viewer-error" role="status">{t("图片无法显示")}</span> : <img
          className={`source-image image-viewer-image${natural ? " is-loaded" : ""}`}
          src={src}
          alt={alt || t("当前公式图片")}
          draggable={false}
          onLoad={(event) => {
            const { naturalWidth: width, naturalHeight: height } = event.currentTarget;
            if (width > 0 && height > 0) setNatural({ width, height });
          }}
          onError={() => { setFailed(true); setNatural(null); }}
          style={natural ? { width: natural.width * scale, height: natural.height * scale, transform: `translate(-50%, -50%) translate(${bounded.x}px, ${bounded.y}px)` } : undefined}
        />}
      </div>
    </section>
  );
}
