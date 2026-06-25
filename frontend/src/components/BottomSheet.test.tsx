// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomSheet } from "./BottomSheet";

afterEach(cleanup);

describe("BottomSheet", () => {
  it("renders four tabs and marks the active one", () => {
    render(
      <BottomSheet activeTab="places" onTabChange={vi.fn()} sheetState="half" onSheetStateChange={vi.fn()}>
        <div>panel</div>
      </BottomSheet>,
    );
    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(screen.getByRole("tab", { name: /places/i })).toHaveAttribute("aria-selected", "true");
  });

  it("calls onTabChange when another tab is clicked", () => {
    const onTabChange = vi.fn();
    render(
      <BottomSheet activeTab="places" onTabChange={onTabChange} sheetState="half" onSheetStateChange={vi.fn()}>
        <div>panel</div>
      </BottomSheet>,
    );
    fireEvent.click(screen.getByRole("tab", { name: /analyze/i }));
    expect(onTabChange).toHaveBeenCalledWith("analyze");
  });

  it("activates tabs and snap controls from the keyboard", () => {
    const onTabChange = vi.fn();
    const onSheetStateChange = vi.fn();
    render(
      <BottomSheet activeTab="places" onTabChange={onTabChange} sheetState="half" onSheetStateChange={onSheetStateChange}>
        <div>panel</div>
      </BottomSheet>,
    );

    fireEvent.keyDown(screen.getByRole("tab", { name: /analyze/i }), { key: "Enter" });
    expect(onTabChange).toHaveBeenCalledWith("analyze");

    fireEvent.keyDown(screen.getByRole("button", { name: /peek/i }), { key: " " });
    expect(onSheetStateChange).toHaveBeenCalledWith("peek");
  });

  it("renders a docked workspace panel with open and peek controls", () => {
    const onSheetStateChange = vi.fn();
    const { container } = render(
      <BottomSheet activeTab="places" onTabChange={vi.fn()} sheetState="half" onSheetStateChange={onSheetStateChange}>
        <div>panel</div>
      </BottomSheet>,
    );
    expect(container.querySelector(".mc-workspace-panel")).toHaveClass("is-half");
    expect(container.querySelector(".mc-sheet")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: /full/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /half/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /peek/i }));
    expect(onSheetStateChange).toHaveBeenCalledWith("peek");
  });

  it("cycles the handle between collapsed and open panel states", () => {
    const onSheetStateChange = vi.fn();
    render(
      <BottomSheet activeTab="places" onTabChange={vi.fn()} sheetState="half" onSheetStateChange={onSheetStateChange}>
        <div>panel</div>
      </BottomSheet>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Toggle panel width" }));

    expect(onSheetStateChange).toHaveBeenCalledWith("peek");
  });
});
