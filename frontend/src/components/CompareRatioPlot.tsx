import type { CompareVerdictRow } from "../lib/compareVerdict";

// Positions on the "× the lowest" axis. Domain starts at the same-rate line (1×) with a small
// left margin so a marker at ~1× is visible, up to the largest interval end (padded).
function makeScale(rows: CompareVerdictRow[]) {
  const highs = rows.map((r) => r.plotCiHigh).filter((v): v is number => v != null);
  const mults = rows.map((r) => r.multipleOfLowest).filter((v): v is number => v != null);
  const domainMax = Math.max(1.5, ...highs, ...mults) * 1.05;
  const domainMin = 0.9;
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - domainMin) / (domainMax - domainMin)) * 100));
  return { pos };
}

export function CompareRatioPlot({ rows }: { rows: CompareVerdictRow[] }) {
  const lowest = rows.find((r) => r.relationship === "lowest");
  const others = rows.filter((r) => r.relationship !== "lowest");
  const { pos } = makeScale(rows);
  const onePct = pos(1);
  const floorPct = pos(1.25);

  return (
    <div className="mc-plot" data-testid="compare-plot">
      <p className="mc-label">Each address vs the lowest rate — 95% interval</p>
      <div className="mc-plot-chart">
        <span className="mc-plot-line same" style={{ left: `${onePct}%` }} aria-hidden />
        <span className="mc-plot-line floor" style={{ left: `${floorPct}%` }} aria-hidden />
        <div className="mc-plot-row ref">
          <span className="name">{lowest ? lowest.label : "lowest"}</span>
          <div className="track"><span className="dot ref" style={{ left: `${onePct}%` }} /></div>
          <span className="val">1× · same rate</span>
        </div>
        {others.map((r) => {
          const hasBar = r.relationship !== "limited" && r.plotCiLow != null && r.plotCiHigh != null;
          const left = hasBar ? pos(r.plotCiLow as number) : 0;
          const width = hasBar ? Math.max(1, pos(r.plotCiHigh as number) - left) : 0;
          const dot = r.multipleOfLowest != null ? pos(r.multipleOfLowest) : onePct;
          return (
            <div className={`mc-plot-row ${r.relationship}`} key={r.optionId}>
              <span className="name">{r.label}</span>
              <div className="track">
                {hasBar ? <span className="bar" style={{ left: `${left}%`, width: `${width}%` }} /> : null}
                <span className="dot" style={{ left: `${dot}%` }} />
              </div>
              <span className="val">{r.multipleOfLowest != null ? `${r.multipleOfLowest.toFixed(1)}×` : "—"}</span>
            </div>
          );
        })}
      </div>
      <p className="mc-plot-foot">Bar is the raw 95% interval; the “clearly higher / similar” label is the corrected verdict and is authoritative. Dashed line marks the lowest’s rate.</p>
    </div>
  );
}
