import { titleCase } from "../lib/addressLabel";
import { toCompareVerdict } from "../lib/compareVerdict";
import { countNoun, incidentNoun, REVISED_CAVEAT } from "../lib/layerCopy";
import { categoryLabel } from "../lib/offenseCategories";
import { aggregateHeadline } from "../lib/verdictCopy";
import type { AnalysisCardData, IncidentDetailsResponse, LayerKey } from "../types";
import { plotDomainMax } from "./BaselineIntervalPlot";
import { CompareRankedList } from "./CompareRankedList";
import { CompareRateNumberLine } from "./CompareRateNumberLine";
import { CompareVerdict } from "./CompareVerdict";
import { IncidentDetailsSection } from "./IncidentDetailsSection";
import { MethodsAppendix } from "./MethodsAppendix";
import { PlaceContextCard } from "./PlaceContextCard";
import { TrendSection } from "./TrendSection";

type Props = {
  card: AnalysisCardData;
  expanded: boolean;
  onExpandChange: (expanded: boolean) => void;
  exportHrefBase: string;
};

/** Aggregate the frozen incident list by offense category, mirroring the expanded
 * incident table's labeling (titleCase, null → "Uncategorized") so compact bars and
 * expanded rows agree. Descending by count; empty when there are no incidents. */
export function categoryCounts(incidents: IncidentDetailsResponse | null): { label: string; count: number }[] {
  if (!incidents || incidents.incidents.length === 0) return [];
  const counts = new Map<string, number>();
  for (const item of incidents.incidents) {
    const label = item.offense_category ? titleCase(item.offense_category) : "Uncategorized";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count);
}

function totalIncidentCount(card: AnalysisCardData): number | null {
  if (card.incidents) return card.incidents.total_count;
  if (card.comparison) return card.comparison.analytical.options.reduce((sum, o) => sum + o.incident_count, 0);
  if (card.neighborhood) return card.neighborhood.places.reduce((sum, p) => sum + p.place_incident_count, 0);
  return null;
}

export function AnalysisCard({ card, expanded, onExpandChange, exportHrefBase }: Props) {
  const layer: LayerKey = card.settings.layer ?? "reported";
  const noun = incidentNoun(layer);
  const category = card.settings.offense_category ?? null;
  const radiusM = card.settings.radius_m ?? 0;
  const { analysis_start_date: start, analysis_end_date: end } = card.settings;
  const windowLabel = start && end ? `${start} – ${end}` : "";

  const comparison = card.comparison;
  const neighborhood = card.neighborhood;
  const verdict = comparison ? toCompareVerdict(comparison) : null;

  // 911 calls carry no offense category — a single "Uncategorized" bar says nothing.
  const cats = layer === "calls" ? [] : categoryCounts(card.incidents);
  const maxCat = cats.reduce((m, c) => Math.max(m, c.count), 0);
  const total = totalIncidentCount(card);
  const capped = card.incidents !== null && card.incidents.returned_count < card.incidents.total_count;

  const showCategory = layer !== "calls";
  const subcategoryHeader = layer === "calls" ? "Call type" : layer === "arrests" ? "Charge" : "Subcategory";

  return (
    <div className={`mc-card${expanded ? " is-expanded" : ""}`}>
      <div className="mc-card-head">
        <span className="mc-card-kind">{card.kind === "compare" ? "Comparison" : "Analysis"}</span>
        <p className="mc-card-settings">
          {windowLabel ? `${windowLabel} · ` : ""}
          {radiusM} m · {categoryLabel(card.settings.offense_category ?? "")} · {noun.pluralCap}
        </p>
        {card.runId ? (
          <a className="mc-card-export" href={`${exportHrefBase}?run_id=${card.runId}`} download>
            Export CSV
          </a>
        ) : null}
        <button type="button" className="mc-card-expand" aria-expanded={expanded} onClick={() => onExpandChange(!expanded)}>
          {expanded ? "Collapse" : "Expand"}
        </button>
      </div>

      {verdict ? (
        <>
          <CompareVerdict callout={verdict.callout} noun={noun} />
          <CompareRateNumberLine rows={verdict.rows} noun={noun} radiusM={radiusM} />
        </>
      ) : neighborhood ? (
        neighborhood.places.map((place) => (
          <p className="mc-card-verdict" key={place.place_id}>
            {aggregateHeadline(place, noun)}
          </p>
        ))
      ) : null}

      {total !== null ? (
        <p className="mc-card-count">
          {total} {countNoun(noun, total)}
        </p>
      ) : null}

      {cats.length ? (
        <div className="mc-card-minibars">
          {cats.map((c) => (
            <div className="mc-card-minibar" key={c.label}>
              <span className="mc-card-minibar-label">{c.label}</span>
              <span className="mc-card-minibar-track" aria-hidden="true">
                <span className="mc-card-minibar-fill" style={{ width: `${Math.round((c.count / maxCat) * 100)}%` }} />
              </span>
              <span className="mc-card-minibar-count">{c.count}</span>
            </div>
          ))}
          {capped ? <p className="mc-card-minibar-note">of the {card.incidents!.returned_count} nearest</p> : null}
        </div>
      ) : null}

      {expanded ? (
        <div className="mc-card-expanded">
          {verdict ? <CompareRankedList rows={verdict.rows} noun={noun} radiusM={radiusM} /> : null}
          {neighborhood ? (
            <div className="mc-card-places">
              {neighborhood.places.map((place, index) => (
                <PlaceContextCard
                  key={place.place_id}
                  place={place}
                  index={index}
                  windowLabel={windowLabel}
                  noun={noun}
                  domainMax={plotDomainMax(neighborhood.places)}
                  locator={null}
                  coords={null}
                />
              ))}
            </div>
          ) : null}
          {neighborhood ? <TrendSection neighborhood={neighborhood} layer={layer} category={category} /> : null}
          <IncidentDetailsSection details={card.incidents} noun={noun} layout="table" showCategory={showCategory} subcategoryHeader={subcategoryHeader} />
          <div className="mc-caveat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
            {REVISED_CAVEAT}
          </div>
          <MethodsAppendix />
        </div>
      ) : null}
    </div>
  );
}
