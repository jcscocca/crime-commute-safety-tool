// Frontend half of docs/analysis/trend-indexing-method.md §8.
export const ANCHOR_MONTHS = 12;

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

export function anchorFactor(area: number[], city: number[]): number | null {
  if (area.length < ANCHOR_MONTHS + 1 || city.length !== area.length) return null;
  const a = sum(area.slice(0, ANCHOR_MONTHS));
  const c = sum(city.slice(0, ANCHOR_MONTHS));
  if (a === 0 || c === 0) return null;
  return a / c;
}

export function rollingMean12(series: number[]): (number | null)[] {
  return series.map((_, i) =>
    i < ANCHOR_MONTHS - 1 ? null : sum(series.slice(i - ANCHOR_MONTHS + 1, i + 1)) / ANCHOR_MONTHS,
  );
}

export function indexCitywide(city: number[], k: number): number[] {
  return city.map((v) => v * k);
}
