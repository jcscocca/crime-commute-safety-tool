import { useId, useState } from "react";

import { useAddressSearch } from "../lib/useAddressSearch";
import type { GeocodeResult } from "../types";

type Props = {
  search: (query: string, signal?: AbortSignal) => Promise<GeocodeResult[]>;
  onSelect: (result: GeocodeResult) => void;
  addPinMode: boolean;
  onToggleAddPin: () => void;
};

export function SearchPill({ search, onSelect, addPinMode, onToggleAddPin }: Props) {
  const { query, setQuery, results, status, rememberPlace } = useAddressSearch(search);
  const [open, setOpen] = useState(false);
  const listId = useId();

  function select(result: GeocodeResult) {
    rememberPlace(result);
    setQuery("");
    setOpen(false);
    onSelect(result);
  }

  return (
    <div className="mc-searchpill">
      <div className="mc-searchpill-row">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></svg>
        <input
          id="mc-search-input"
          role="combobox"
          aria-label="Search address or place"
          aria-expanded={open && results.length > 0}
          aria-controls={listId}
          placeholder="Search address or drop a pin"
          value={query}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
        />
        <button
          type="button"
          className={`mc-searchpill-pin${addPinMode ? " is-armed" : ""}`}
          aria-pressed={addPinMode}
          aria-label="Drop a pin on the map"
          onClick={onToggleAddPin}
        >
          <svg viewBox="0 0 24 32" width="13" height="16"><path d="M12 0C5.4 0 0 5.2 0 11.6 0 20 12 32 12 32s12-12 12-20.4C24 5.2 18.6 0 12 0z" fill="currentColor" /></svg>
        </button>
      </div>
      {open && results.length > 0 ? (
        <ul className="mc-searchpill-results" id={listId} role="listbox">
          {results.map((result) => (
            <li key={`${result.latitude},${result.longitude}`}>
              <button type="button" role="option" aria-selected={false} onClick={() => select(result)}>
                {result.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {status === "error" ? <p className="mc-searchpill-msg" role="status">Search is unavailable right now.</p> : null}
    </div>
  );
}
