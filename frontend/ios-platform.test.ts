import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

describe("ios platform shape", () => {
  it("is an SPM project: CapApp-SPM package present, no Podfile", () => {
    expect(existsSync(join(here, "ios", "App", "CapApp-SPM", "Package.swift"))).toBe(true);
    expect(existsSync(join(here, "ios", "App", "Podfile"))).toBe(false);
  });
});
