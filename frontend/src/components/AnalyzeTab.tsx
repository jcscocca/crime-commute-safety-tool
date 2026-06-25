import type { AnalysisSettings, CrimeSummary, DashboardSummary, Place } from "../types";

type Props = {
  selected: Place[];
  analysis: AnalysisSettings;
  summary: DashboardSummary | null;
  availableRadii: number[];
  running: boolean;
  onChange: (patch: Partial<AnalysisSettings>) => void;
  onRun: () => void;
};

const CATEGORIES: { value: string; label: string }[] = [
  { value: "", label: "All reported" },
  { value: "PROPERTY", label: "Property" },
  { value: "PERSON", label: "Person" },
  { value: "SOCIETY", label: "Society" },
];

function titleCase(value: string) {
  return value
    .toLowerCase()
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function incidentTypeLabel(summary: Pick<CrimeSummary, "offense_category" | "offense_subcategory" | "nibrs_group">) {
  const parts = [summary.offense_category, summary.offense_subcategory].filter((part): part is string => Boolean(part));
  if (parts.length > 0) return parts.map(titleCase).join(" / ");
  return summary.nibrs_group ? `NIBRS ${summary.nibrs_group}` : "All reported";
}

function findingEntries(summary: DashboardSummary | null, selected: Place[], radiusM: number) {
  const selectedIds = new Set(selected.map((place) => place.id));
  return (summary?.crime_summaries ?? []).filter(
    (entry) => selectedIds.has(entry.place_cluster_id) && entry.radius_m === radiusM,
  );
}

function buildFindings(summary: DashboardSummary | null, selected: Place[], radiusM: number) {
  if (selected.length === 0) {
    return ["Select one or more places to summarize reported incident patterns."];
  }

  const entries = findingEntries(summary, selected, radiusM);
  if (entries.length === 0) {
    return ["Run analysis to summarize reported incident patterns for the selected places."];
  }

  const selectedById = new Map(selected.map((place) => [place.id, place]));
  const placeTotals = new Map<string, number>();
  const typeTotals = new Map<string, { label: string; total: number }>();
  let hasAssault = false;

  for (const entry of entries) {
    placeTotals.set(entry.place_cluster_id, (placeTotals.get(entry.place_cluster_id) ?? 0) + entry.incident_count);

    const label = incidentTypeLabel(entry);
    const type = typeTotals.get(label) ?? { label, total: 0 };
    type.total += entry.incident_count;
    typeTotals.set(label, type);

    if (entry.offense_category === "PERSON" && entry.offense_subcategory === "ASSAULT") {
      hasAssault = true;
    }
  }

  const findings: string[] = [];
  const highestPlace = Array.from(placeTotals.entries())
    .map(([placeId, total]) => ({ place: selectedById.get(placeId), total }))
    .filter((entry): entry is { place: Place; total: number } => Boolean(entry.place))
    .sort((a, b) => b.total - a.total)[0];

  if (highestPlace) {
    findings.push(
      `${highestPlace.place.display_label} has the highest reported incident exposure in the selected radius (${highestPlace.total} reported incidents).`,
    );
  }

  const largestType = Array.from(typeTotals.values()).sort((a, b) => b.total - a.total)[0];
  if (largestType) {
    findings.push(`${largestType.label} is the largest reported incident type across the selected places.`);
  }

  if (hasAssault) {
    findings.push("Person / Assault appears in the selected places; use Compare for side-by-side context.");
  }

  return findings;
}

export function AnalyzeTab({ selected, analysis, summary, availableRadii, running, onChange, onRun }: Props) {
  const radii = availableRadii.length > 0 ? availableRadii : [250, 500, 1000];
  const canRun = selected.length >= 1 && !running;
  const findings = buildFindings(summary, selected, analysis.radiusM);

  return (
    <div className="mc-panel is-active" role="tabpanel" aria-label="Analyze">
      <section className="mc-findings" aria-label="Findings summary">
        <div className="mc-findings-head">
          <h4>Findings summary</h4>
          <span>{analysis.radiusM} m</span>
        </div>
        <ul>
          {findings.map((finding) => <li key={finding}>{finding}</li>)}
        </ul>
        <p>Reported incident patterns do not predict personal risk.</p>
      </section>

      <div className="mc-field">
        <label htmlFor="analysis-start-date">Date range</label>
        <div className="mc-inputs">
          <input id="analysis-start-date" type="date" className="mc-inp" value={analysis.startDate} aria-label="Start date" onChange={(event) => onChange({ startDate: event.target.value })} />
          <input id="analysis-end-date" type="date" className="mc-inp" value={analysis.endDate} aria-label="End date" onChange={(event) => onChange({ endDate: event.target.value })} />
        </div>
      </div>

      <div className="mc-field">
        <label id="radius-label">Search radius</label>
        <div className="mc-chips" role="group" aria-labelledby="radius-label">
          {radii.map((value) => (
            <button key={value} type="button" className={`mc-chip${analysis.radiusM === value ? " on" : ""}`} aria-pressed={analysis.radiusM === value} onClick={() => onChange({ radiusM: value })}>
              {value} m
            </button>
          ))}
        </div>
      </div>

      <div className="mc-field">
        <label id="category-label">Incident categories</label>
        <div className="mc-chips" role="group" aria-labelledby="category-label">
          {CATEGORIES.map((category) => (
            <button key={category.value || "all"} type="button" className={`mc-chip${analysis.offenseCategory === category.value ? " on" : ""}`} aria-pressed={analysis.offenseCategory === category.value} onClick={() => onChange({ offenseCategory: category.value })}>
              {category.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ height: 60 }} />
      <div className="mc-footer">
        <span className="note">{selected.length} place{selected.length === 1 ? "" : "s"} - {analysis.radiusM} m</span>
        <button type="button" className="mc-cta" disabled={!canRun} onClick={onRun}>{running ? "Running..." : "Run analysis"}</button>
      </div>
    </div>
  );
}
