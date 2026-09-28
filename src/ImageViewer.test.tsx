// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImageViewer, constrainImagePan, fitImageScale } from "./ImageViewer";

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width:400, height:200, x:0, y:0, top:0, left:0, bottom:200, right:400, toJSON:() => ({}) });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const loadImage = (width = 800, height = 400) => {
  const image = screen.getByRole("img") as HTMLImageElement;
  Object.defineProperties(image, { naturalWidth:{ configurable:true, value:width }, naturalHeight:{ configurable:true, value:height } });
  fireEvent.load(image);
  return image;
};

describe("image inspection", () => {
  it("fits the image, shows actual size, zooms, and pans with keyboard without changing pixels", () => {
    render(<ImageViewer src="blob:formula" language="zh-CN" />);
    const image = loadImage();
    expect(image.style.width).toBe("400px");
    expect(screen.getByLabelText("图片缩放比例").textContent).toBe("50%");
    fireEvent.click(screen.getByRole("button", { name:"实际大小" }));
    expect(image.style.width).toBe("800px");
    const viewport = screen.getByRole("region");
    fireEvent.keyDown(viewport, { key:"ArrowRight" });
    expect(image.style.transform).toContain("-40px, 0px");
    fireEvent.click(screen.getByRole("button", { name:"放大图片" }));
    expect(image.style.width).toBe("1000px");
    fireEvent.click(screen.getByRole("button", { name:"适合窗口" }));
    expect(image.style.width).toBe("400px");
    expect(image.style.transform).toContain("0px, 0px");
    expect(image.getAttribute("src")).toBe("blob:formula");
  });
  it("resets fit and pan when the image changes", () => {
    const { rerender } = render(<ImageViewer src="blob:first" language="zh-CN" />);
    loadImage();
    fireEvent.click(screen.getByRole("button", { name:"实际大小" }));
    fireEvent.keyDown(screen.getByRole("region"), { key:"ArrowDown" });
    rerender(<ImageViewer src="blob:second" language="zh-CN" />);
    expect((screen.getByRole("button", { name:"实际大小" }) as HTMLButtonElement).disabled).toBe(true);
    const image = loadImage(1200, 600);
    expect(image.style.width).toBe("400px");
    expect(image.style.transform).toContain("0px, 0px");
    expect(screen.getByRole("button", { name:"适合窗口" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("supports wheel zoom and reports image failures without retaining stale controls", () => {
    render(<ImageViewer src="blob:formula" language="zh-CN" />);
    const image = loadImage();
    fireEvent.wheel(screen.getByRole("region"), { deltaY:-100, ctrlKey:true });
    expect(parseFloat(image.style.width)).toBeGreaterThan(400);
    fireEvent.error(image);
    expect(screen.getByText("图片无法显示").getAttribute("role")).toBe("status");
    expect((screen.getByRole("button", { name:"放大图片" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("bounds pan to image edges, preserves aspect ratio and does not upscale tiny images in fit mode", () => {
    expect(fitImageScale({ width:800, height:400 }, { width:400, height:300 })).toBe(.5);
    expect(fitImageScale({ width:80, height:40 }, { width:400, height:300 })).toBe(1);
    expect(constrainImagePan({ x:999, y:-999 }, { width:800, height:400 }, { width:400, height:200 }, 1)).toEqual({ x:200, y:-100 });
    expect(constrainImagePan({ x:999, y:999 }, { width:800, height:400 }, { width:400, height:200 }, .5)).toEqual({ x:0, y:0 });
  });
});
