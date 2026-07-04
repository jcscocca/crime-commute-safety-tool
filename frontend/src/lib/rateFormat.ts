// The compare payload carries rate as reported incidents per km²·day — a tiny fraction
// (~0.03) that reads as "0.0" once rounded. For display we express it as an intuitive
// expected count within the analysis buffer: rate × buffer area × days per year.

const DAYS_PER_YEAR = 365.25;

export function annualIncidentsWithin(ratePerKm2Day: number, radiusM: number): number {
  const areaKm2 = Math.PI * (radiusM / 1000) ** 2;
  return ratePerKm2Day * areaKm2 * DAYS_PER_YEAR;
}

export function formatPerYear(value: number): string {
  if (value < 0.05) return "0";
  if (value >= 10) return Math.round(value).toString();
  return value.toFixed(1);
}
