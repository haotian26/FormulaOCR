// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AboutPanel } from "./AboutPanel";
const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
afterEach(() => { cleanup(); invoke.mockReset(); });
describe("manual update checks", () => {
  it("does not contact a server when rendered or expanded", () => {
    render(<AboutPanel language="en"/>);
    fireEvent.click(screen.getByText("About FormulaOCR"));
    expect(invoke).not.toHaveBeenCalled();
  });
  it("only checks and opens a release after explicit clicks", async () => {
    invoke.mockResolvedValue({ current:"0.4.2", latest:"0.4.3", update_available:true, url:"https://github.com/haotian26/FormulaOCR/releases/tag/v0.4.3" });
    render(<AboutPanel language="en"/>);
    fireEvent.click(screen.getByText("About FormulaOCR"));
    fireEvent.click(screen.getByText("Check for Updates"));
    await screen.findByText("New version 0.4.3 is available");
    expect(invoke).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("View New Version"));
    expect(invoke).toHaveBeenCalledWith("open_release_page", { url:"https://github.com/haotian26/FormulaOCR/releases/tag/v0.4.3" });
  });
  it("shows failure and allows another manual attempt", async () => {
    invoke.mockRejectedValue(Error("Offline")); render(<AboutPanel language="en"/>);
    fireEvent.click(screen.getByText("About FormulaOCR"));
    fireEvent.click(screen.getByText("Check for Updates"));
    await screen.findByRole("alert");
    expect((screen.getByText("Check for Updates").closest("button") as HTMLButtonElement).disabled).toBe(false);
  });
});
