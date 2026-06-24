import { Trash2 } from "lucide-react";

import type { Place } from "../types";

type Props = {
  places: Place[];
  selectedIds: Set<string>;
  onToggle: (placeId: string) => void;
  onDelete: (placeId: string) => void;
};

function formatCoordinates(place: Place) {
  if (place.latitude === null || place.longitude === null) {
    return "Not provided";
  }

  return `${place.latitude.toFixed(3)}, ${place.longitude.toFixed(3)}`;
}

export function PlaceTable({
  places,
  selectedIds,
  onToggle,
  onDelete,
}: Props) {
  return (
    <section className="panel table-panel" aria-labelledby="places-title">
      <div className="panel-heading">
        <div>
          <p className="panel-label">Places</p>
          <h2 id="places-title">Places</h2>
        </div>
        <span className="count-pill">{places.length} entered</span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Select</th>
              <th scope="col">Place</th>
              <th scope="col">Visits</th>
              <th scope="col">Approx. coordinates</th>
              <th scope="col">Remove</th>
            </tr>
          </thead>
          <tbody>
            {places.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No places entered yet.
                </td>
              </tr>
            ) : (
              places.map((place) => (
                <tr key={place.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select ${place.display_label}`}
                      checked={selectedIds.has(place.id)}
                      onChange={() => onToggle(place.id)}
                    />
                  </td>
                  <td>{place.display_label}</td>
                  <td>{place.visit_count}</td>
                  <td>{formatCoordinates(place)}</td>
                  <td>
                    <button
                      className="icon-button"
                      type="button"
                      aria-label={`Remove ${place.display_label}`}
                      onClick={() => onDelete(place.id)}
                    >
                      <Trash2 size={17} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
