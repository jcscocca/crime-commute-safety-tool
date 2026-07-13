// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import { clampWidth, drawerMax, DRAWER_DEFAULT, DRAWER_MIN } from "./drawer";

function setViewport(width: number) {
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true, writable: true });
}

afterEach(() => setViewport(1024));

describe("drawer math", () => {
  it("exposes the expected default expanded width", () => {
    expect(DRAWER_DEFAULT).toBe(400);
    expect(DRAWER_MIN).toBe(340);
  });

  it("drawerMax leaves a 96px map strip, floored at DRAWER_MIN", () => {
    setViewport(800);
    expect(drawerMax()).toBe(704);
    setViewport(2000);
    expect(drawerMax()).toBe(1904);
  });

  it("clamps width into [DRAWER_MIN, drawerMax]", () => {
    setViewport(1200);
    expect(clampWidth(100)).toBe(DRAWER_MIN);
    expect(clampWidth(5000)).toBe(drawerMax());
    expect(clampWidth(512.6)).toBe(513);
  });
});

describe("focus preset geometry", () => {
  it("drawerMax leaves a 96px map strip", () => {
    // jsdom window.innerWidth defaults to 1024
    expect(drawerMax()).toBe(1024 - 96);
  });

  it("clampWidth allows widths up to drawerMax", () => {
    expect(clampWidth(1024 - 96)).toBe(1024 - 96);
    expect(clampWidth(5000)).toBe(1024 - 96);
  });

  it("drawerMax never drops below DRAWER_MIN on narrow windows", () => {
    const original = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { value: 400, configurable: true });
    expect(drawerMax()).toBe(DRAWER_MIN);
    Object.defineProperty(window, "innerWidth", { value: original, configurable: true });
  });
});
