// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "./ThemeToggle";

afterEach(cleanup);

describe("ThemeToggle", () => {
  it("labels the action it will take and reports pressed state", () => {
    const onChange = vi.fn();
    render(<ThemeToggle theme="light" onChange={onChange} />);
    const button = screen.getByRole("button", { name: "Switch to dark theme" });
    expect(button).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(button);
    expect(onChange).toHaveBeenCalledWith("dark");
  });

  it("inverts for dark", () => {
    const onChange = vi.fn();
    render(<ThemeToggle theme="dark" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(onChange).toHaveBeenCalledWith("light");
  });
});
