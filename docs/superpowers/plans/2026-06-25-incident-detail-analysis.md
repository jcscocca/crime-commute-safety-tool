# Incident Detail Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add incident-detail rows to the Analyze tab and remove the misleading per-visit rate from primary comparison UI.

**Architecture:** The backend adds a small `/dashboard/incidents` route that reuses selected-place, date, category, and bounding-box filtering from dashboard analysis, then computes exact place-to-incident distances. The frontend fetches those details after Analyze succeeds, stores them in `MapWorkspace`, and renders a compact table in `AnalyzeTab`.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, Vitest, Testing Library.

---

### Task 1: Backend Incident Details Endpoint

**Files:**
- Modify: `app/api/routes_public_dashboard.py`
- Modify: `app/services/dashboard_analysis_service.py`
- Test: `tests/test_dashboard_analysis_api.py`

- [ ] **Step 1: Write the failing API test**

```python
def test_dashboard_incidents_returns_selected_place_rows(tmp_path):
    client = _client_with_places_and_crime(tmp_path)
    places = client.get("/places").json()["places"]

    response = client.post(
        "/dashboard/incidents",
        json={
            "place_ids": [places[0]["id"]],
            "analysis_start_date": "2024-01-01",
            "analysis_end_date": "2024-01-31",
            "radii_m": [250],
            "offense_category": "PROPERTY",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["radius_m"] == 250
    assert body["total_count"] == 1
    assert body["returned_count"] == 1
    assert body["incidents"][0]["place_id"] == places[0]["id"]
    assert body["incidents"][0]["incident_id"] == "incident-a"
    assert body["incidents"][0]["distance_m"] < 70
```

- [ ] **Step 2: Verify it fails**

Run: `pytest tests/test_dashboard_analysis_api.py::test_dashboard_incidents_returns_selected_place_rows -q`

Expected: FAIL with 404 for `/dashboard/incidents`.

- [ ] **Step 3: Implement the endpoint and service helper**

Add a `DashboardIncidentDetailsRequest` with the same fields as `DashboardAnalyzeRequest` plus `limit`. Add `incident_details_for_places(...)` that:

```python
clusters = [_cluster_data(row) for row in _selected_clusters(session, user_id_hash, place_ids)]
radius_m = radii_m[0]
incidents = _filtered_incidents(..., radii_m=[radius_m], ...)
```

For each cluster and incident, compute `haversine_m(cluster_lat, cluster_lon, incident.latitude, incident.longitude)`, keep rows within `radius_m`, sort by place label and distance, then return `incidents`, `returned_count`, `total_count`, `limit`, and `radius_m`.

- [ ] **Step 4: Verify it passes**

Run: `pytest tests/test_dashboard_analysis_api.py::test_dashboard_incidents_returns_selected_place_rows -q`

Expected: PASS.

### Task 2: Backend Filters and Limits

**Files:**
- Modify: `tests/test_dashboard_analysis_api.py`
- Modify: `app/services/dashboard_analysis_service.py`

- [ ] **Step 1: Write failing tests**

```python
def test_dashboard_incidents_respects_limit_and_total_count(tmp_path):
    client = _client_with_places_and_crime(tmp_path)
    places = client.get("/places").json()["places"]

    response = client.post(
        "/dashboard/incidents",
        json={
            "place_ids": [places[0]["id"], places[1]["id"]],
            "analysis_start_date": "2024-01-01",
            "analysis_end_date": "2024-01-31",
            "radii_m": [250],
            "offense_category": "PROPERTY",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["total_count"] == 2
    assert response.json()["returned_count"] == 1
    assert len(response.json()["incidents"]) == 1
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_dashboard_analysis_api.py::test_dashboard_incidents_respects_limit_and_total_count -q`

Expected: FAIL until limit accounting is implemented.

- [ ] **Step 3: Implement cap accounting**

Use `rows[:limit]` for returned rows and `len(rows)` for `total_count`. Clamp `limit` with Pydantic to `1..500`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_dashboard_analysis_api.py::test_dashboard_incidents_respects_limit_and_total_count -q`

Expected: PASS.

### Task 3: Frontend API and Analyze Table

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/AnalyzeTab.tsx`
- Test: `frontend/src/components/AnalyzeTab.test.tsx`

- [ ] **Step 1: Write failing component tests**

```tsx
render(
  <AnalyzeTab
    selected={[home]}
    analysis={analysis}
    summary={analyzedSummary}
    availableRadii={[250]}
    running={false}
    incidentDetails={{
      incidents: [{ place_id: "p1", place_label: "Home", incident_id: "i1", external_incident_id: null, report_number: "R1", occurred_at: "2026-01-02T10:00:00Z", reported_at: null, offense_category: "PROPERTY", offense_subcategory: "THEFT", nibrs_group: "A", block_address: "100 BLOCK MAIN ST", distance_m: 42 }],
      returned_count: 1,
      total_count: 1,
      limit: 100,
      radius_m: 250,
    }}
    onChange={vi.fn()}
    onRun={vi.fn()}
  />,
);
expect(screen.getByText("Reported incidents near selected places")).toBeInTheDocument();
expect(screen.getByText("100 BLOCK MAIN ST")).toBeInTheDocument();
```

- [ ] **Step 2: Verify failure**

Run: `cd frontend && npm test -- src/components/AnalyzeTab.test.tsx`

Expected: FAIL because `incidentDetails` is not a prop and no table exists.

- [ ] **Step 3: Implement types, client, and table**

Add `IncidentDetail` and `IncidentDetailsResponse` in `types.ts`, add `getIncidentDetails(payload)` in `client.ts`, and render a table in `AnalyzeTab` when details are present.

- [ ] **Step 4: Verify pass**

Run: `cd frontend && npm test -- src/components/AnalyzeTab.test.tsx`

Expected: PASS.

### Task 4: Workspace Fetch and Invalidation

**Files:**
- Modify: `frontend/src/components/MapWorkspace.tsx`
- Test: `frontend/src/components/MapWorkspace.test.tsx`

- [ ] **Step 1: Write failing workspace test**

```tsx
vi.mocked(getIncidentDetails).mockResolvedValue({ incidents: [], returned_count: 0, total_count: 0, limit: 100, radius_m: 250 });
fireEvent.click(screen.getByRole("checkbox", { name: "Select Home" }));
fireEvent.click(screen.getByRole("tab", { name: /analyze/i }));
fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));
await waitFor(() => expect(getIncidentDetails).toHaveBeenCalledWith(expect.objectContaining({ place_ids: ["p1"] })));
```

- [ ] **Step 2: Verify failure**

Run: `cd frontend && npm test -- src/components/MapWorkspace.test.tsx`

Expected: FAIL because details are not fetched.

- [ ] **Step 3: Implement fetch and invalidation**

Add `incidentDetails` state, clear it when selection or analysis controls change, call `getIncidentDetails` after `analyzePlaces`, and pass the result to `AnalyzeTab`.

- [ ] **Step 4: Verify pass**

Run: `cd frontend && npm test -- src/components/MapWorkspace.test.tsx`

Expected: PASS.

### Task 5: Remove Per-Visit UI Rate

**Files:**
- Modify: `frontend/src/components/CompareTab.tsx`
- Test: `frontend/src/components/CompareTab.test.tsx`

- [ ] **Step 1: Write failing assertion**

```tsx
expect(screen.queryByText(/per expected visit/i)).not.toBeInTheDocument();
expect(screen.getByText(/nearest 42 m/i)).toBeInTheDocument();
```

- [ ] **Step 2: Verify failure**

Run: `cd frontend && npm test -- src/components/CompareTab.test.tsx`

Expected: FAIL while `rateText` is still rendered.

- [ ] **Step 3: Remove `rateText` from public comparison cards**

Render only nearest-distance metadata when counts exist.

- [ ] **Step 4: Verify pass**

Run: `cd frontend && npm test -- src/components/CompareTab.test.tsx`

Expected: PASS.

### Task 6: Full Verification

**Files:**
- No production edits.

- [ ] **Step 1: Run frontend tests**

Run: `cd frontend && npm test`

Expected: all Vitest tests pass.

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`

Expected: Vite build succeeds.

- [ ] **Step 3: Run backend tests**

Run: `make test`

Expected: pytest suite passes.
