# Statistical Route And Place Comparison

## What The App Can Claim

The app can say that one route or site has a statistically lower reported-incident rate than another route or site for the selected date range, geography, radius, offense filter, and method.
The app cannot say that a route is safe, unsafe, dangerous, risk-free, or that a route prevents crime.

## Why Raw Counts Are Not Enough

Raw incident counts do not account for route length, buffer size, or analysis period. The app compares exposure-adjusted rates.

## Exposure

Place exposure is buffer area in square kilometers multiplied by analysis days.
Route exposure is route corridor area in square kilometers multiplied by analysis days. Include this formula exactly:
`route_corridor_area_square_km = (route_length_km * 2 * radius_km) + pi * radius_km^2`

## Incident Inclusion

Coordinates, date range, offense filters, and selected place buffer/route corridor.

## Statistical Test

Default exact conditional Poisson comparison; if period counts are overdispersed, quasi-Poisson log-rate-ratio adjustment.

## Multiple Comparisons

Benjamini-Hochberg adjustment for more than two options; route recommended only when it passes conservative threshold against every relevant alternative.

## Recommendation Threshold

- adjusted p-value below 0.05
- adjusted rate ratio less than or equal to 0.80
- at least 30 analysis days
- positive exposure for every compared option
- combined incident count of at least 10
- no unhandled model warning

## Dashboard Modes

Overview is public summary. Analytical is audit view. Both modes read same backend result.

## Decision Classes

`statistically_lower` means one compared option has a statistically lower reported-incident rate under the selected filters and threshold.
`not_statistically_clear` means the comparison does not identify a statistically clear lower reported-incident rate.
`insufficient_data` means the selected inputs do not meet the minimum data requirements.
`model_warning` means the model produced a warning that should prevent a recommendation claim.
