export const DEFAULT_TEST_LOCATION_LABEL = "Test location";

export function labelOrDefault(label: string) {
  const trimmed = label.trim();
  return trimmed || DEFAULT_TEST_LOCATION_LABEL;
}
