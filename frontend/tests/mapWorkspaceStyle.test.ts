// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../src/styles/mapWorkspace.css", import.meta.url), "utf8");

describe("map workspace styles", () => {
  it("keeps incident table data readable via semantic tokens", () => {
    expect(css).toMatch(/\.mc-incident-table\{[^}]*font-size:13px;[^}]*color:var\(--text-strong\);/);
    expect(css).toMatch(/\.mc-incident-table th,\.mc-incident-table td\{[^}]*color:var\(--text-strong\);/);
    expect(css).toMatch(/\.mc-incident-table th\{[^}]*font-size:11px;[^}]*color:var\(--text-strong\);[^}]*background:var\(--surface-sunken\);/);
    expect(css).toMatch(/\.mc-incident-count\{[^}]*color:var\(--text\);/);
    expect(css).toMatch(/\.mc-breakdown-head h5\{[^}]*color:var\(--text-strong\);/);
  });
});
