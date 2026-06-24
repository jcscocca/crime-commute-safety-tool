# Map-First Public Dashboard Redesign Design

## Summary

Redesign the public dashboard as a map-first location workspace. The first screen should feel like a real location product, not a form-and-table prototype. Users can add locations by clicking the map to drop a pin by default, or by searching for a specific address or place and saving the resulting pin. The map remains the primary surface, while a tabbed bottom sheet holds the workflow for places, analysis, comparison, and export.

This redesign keeps the current backend concept: saved pins are saved places, analysis runs on selected place IDs, comparison runs on selected places, and exports use the current session summary. The main change is the frontend interaction model and presentation.

## Goals

- Make the public dashboard feel polished, spatial, and product-ready.
- Put a full interactive map at the center of the experience.
- Support click-to-drop pin creation as the default place-entry method.
- Support specific address/place search as an alternate place-entry method.
- Replace the current form/table-first layout with a tabbed bottom sheet.
- Show place markers, selected state, radius rings, and incident-count context after analysis.
- Avoid showing individual incident markers in the public launch version.
- Rewrite confusing comparison copy so it does not imply hidden route alternatives or a lower-incident recommendation when none is shown.
- Preserve the existing manual/bulk place capabilities as secondary paths inside the Places tab or an import modal.

## Non-Goals

- Do not build route-alternative UI in this pass.
- Do not display individual reported-incident dots on the map.
- Do not claim safety, risk, danger, or route/place recommendations.
- Do not require users to upload personal location history.
- Do not make production traffic depend permanently on a hardcoded public tile or geocoding service without an abstraction.

## Product Experience

The dashboard opens on a full-page map centered on Seattle. A compact top bar identifies the product and provides high-level status. The user’s primary interaction is spatial:

1. Click **Add pin**.
2. Click the map to drop an approximate location pin.
3. Fill a small marker popover with label, visit count, and optional dwell context.
4. Save the pin.
5. Select two or more saved pins.
6. Run analysis or comparison from the bottom sheet.

Search is available as a second path. The user can type a specific address or place, choose a result, review the resulting map position, adjust if needed, and save it as a pin. The saved object is still treated as a user-confirmed place, not as an authoritative address record.

After analysis, the map should show:

- Saved place markers.
- Selected markers with a distinct visual state.
- Radius rings for the active analysis radius.
- Incident-count badges or marker summaries for analyzed places.
- Map legend explaining selected places, analyzed radius, and reported-incident count context.

The map should not show individual incident markers for the public launch pass. Counts and radius rings are enough to provide context without creating a noisy or misleading crime-dot map.

## Layout

Use a full-map layout with a tabbed bottom sheet.

The bottom sheet has four tabs:

- **Places**: click-to-drop mode, search field, saved place list, selected-place state, edit/remove.
- **Analyze**: date range, radius, category filter, run analysis.
- **Compare**: selected places, comparison status, summary, caveats, and pairwise/detail area when the comparison payload includes pairwise results.
- **Export**: Tableau-ready CSV link and data limitation notes.

The sheet supports at least two visual states:

- **Half-open**: default working state. The map remains highly visible while the user manages pins or controls.
- **Expanded**: used for comparison details, longer place lists, and table-like content.

The design should avoid wizard-only navigation. Users should be able to jump between tabs because this tool will have repeat use after the first successful run.

## Frontend Architecture

Introduce focused frontend modules rather than continuing to grow `App.tsx`.

Recommended component boundaries:

- `MapWorkspace`: owns the page shell, map viewport, selected tab, bottom-sheet state, and high-level workflow state.
- `MapCanvas`: renders map tiles, markers, radius rings, selection state, and map click events.
- `PinDraftPopover`: captures label, visit count, and optional dwell information for a newly dropped or searched pin.
- `PlaceSearch`: wraps geocoding search behind a provider interface.
- `BottomSheet`: provides half-open/expanded states and tab navigation.
- `PlacesTab`: saved pins, selection controls, edit/remove, import/manual fallback entry.
- `AnalyzeTab`: date/radius/category controls and run-analysis action.
- `CompareTab`: comparison summary, caveats, selected place context, and future detail area.
- `ExportTab`: CSV export and data context.
- `MapLegend`: explains marker states, rings, and count badges.

The current components can be reused where they still fit:

- `AnalysisControls` logic can move into or be adapted for `AnalyzeTab`.
- `ComparisonPanel` should be rewritten for clearer language and richer map-first context.
- `ExportPanel` can be adapted into `ExportTab`.
- `PlaceTable` can become a compact selected/saved place list, not the primary screen.
- `BulkPlaceEntry` can remain as a secondary import path inside `PlacesTab` or a modal.

## Map And Search Providers

Use Leaflet with React bindings for the first implementation because it fits the current React stack and supports the needed primitives: map click handling, markers, circles, popups, and tile layers.

Create provider boundaries so tile and search services are not hardcoded throughout the UI:

- A map tile configuration module for tile URL, attribution, max zoom, and provider metadata.
- A geocoding provider module that exposes a search function returning label, latitude, longitude, and source metadata.

For local and demo work, OpenStreetMap-based tiles and Nominatim-style search are acceptable if used carefully. For public production traffic, the app should be ready to move to a provider that explicitly permits public web app traffic at the expected request volume. The design must preserve visible map attribution and avoid sending unnecessary user-entered data beyond what is needed for search.

References:

- React Leaflet documentation: https://react-leaflet.js.org/
- OpenStreetMap tile usage policy: https://operations.osmfoundation.org/policies/tiles/
- Nominatim usage policy: https://operations.osmfoundation.org/policies/nominatim/

## Data Flow

### Session Load

1. Start or resume a public dashboard session.
2. Fetch dashboard summary.
3. Render saved places as map markers and list entries.
4. Preserve selected place IDs in frontend state.

### Click-To-Drop Pin

1. User enters add-pin mode.
2. User clicks map.
3. Frontend creates a draft pin from clicked latitude/longitude.
4. User enters label and visit count in a pin popover or compact sheet panel.
5. Frontend calls the existing create-place endpoint.
6. Refresh summary.
7. Render the saved marker and keep the map centered where the user was working.

### Search-To-Pin

1. User enters a search query.
2. Frontend calls the geocoding provider.
3. User chooses a result.
4. Map moves to the result and creates a draft pin.
5. User may adjust the pin location before saving.
6. Frontend calls the existing create-place endpoint.
7. Refresh summary.

### Analyze

1. User selects one or more places.
2. User chooses date range, radius, and category.
3. Frontend calls the existing analyze endpoint with selected place IDs.
4. Refresh summary.
5. Map displays radius rings and count badges for analyzed places.

### Compare

1. User selects two or more places.
2. User chooses comparison controls.
3. Frontend calls the existing compare endpoint.
4. `CompareTab` renders the summary and caveats.
5. Map highlights compared places and their active radius rings.

## Copy And Content Rules

Use language that describes reported incident context, not safety advice.

Replace the confusing caveat:

> The app still shows alternatives, but it does not make a lower-incident recommendation.

With copy tailored to place comparison:

> The app still compares the selected places, but it does not identify one as statistically lower-incident.

For model warnings or insufficient data, explain the limitation plainly:

- “There is not enough data under these filters to make a statistical comparison.”
- “The selected data has limitations that require analytical review.”
- “Reported incidents can be incomplete, delayed, corrected, or geographically generalized.”

Do not use “safe,” “unsafe,” “dangerous,” “risk-free,” or “recommended route/place” language.

## Error Handling

- If map tiles fail, show a non-blocking map error state and keep the bottom-sheet workflows usable.
- If search fails, keep click-to-drop available and show a concise search error.
- If search returns no result, keep the query in the field and invite the user to drop a pin manually.
- If save fails, keep the draft pin and form values so the user can retry.
- If analysis fails, keep selected places and controls unchanged.
- If comparison fails, keep selected places and show retry copy.
- If export is unavailable, show the disabled export state with a short reason.

## Accessibility And Responsive Behavior

- The bottom sheet tabs must be keyboard reachable and expose selected state.
- Map actions must have non-map alternatives: saved place list selection, search result selection, and fallback manual entry.
- Marker selection must be reflected in the bottom sheet so keyboard users can operate the workflow without relying only on the map.
- Form inputs must have visible labels.
- Color cannot be the only way to distinguish selected, analyzed, warning, or inactive markers.
- On mobile, the bottom sheet should become the primary interaction surface and allow the map to remain visible behind it.

## Testing Strategy

Add focused tests around the public workflows:

- Renders the map-first dashboard shell and bottom-sheet tabs.
- Creates a draft pin from a map click.
- Saves a clicked pin through the existing create-place API.
- Searches for an address and creates a draft pin from the selected result.
- Selects places from markers and from the place list.
- Runs analysis with selected places and current controls.
- Renders radius/count context after analysis data is present.
- Compares selected places and renders revised comparison copy.
- Shows search failure and tile failure states without blocking click-to-drop/manual entry.
- Keeps export reachable from the Export tab.

Mock map/geocoding provider boundaries in tests rather than depending on live external services.

## Implementation Notes

The first implementation should prioritize the main happy path:

1. Map shell and bottom sheet.
2. Render existing saved places as markers.
3. Click-to-drop draft pin and save.
4. Address/place search to draft pin.
5. Selection sync between map and bottom sheet.
6. Analyze tab wired to existing endpoint.
7. Compare tab with revised copy.
8. Radius rings and count badges from existing summary data.
9. Export tab.

Route alternatives and individual incident marker overlays should remain future work.
