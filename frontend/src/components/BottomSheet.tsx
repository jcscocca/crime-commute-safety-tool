import { useEffect, useRef } from "react";
import type { KeyboardEvent, PointerEvent, ReactNode } from "react";

import { clampWidth, DRAWER_DEFAULT, DRAWER_MIN, DRAWER_PEEK, DRAWER_RESIZE_STEP, DRAWER_WIDE, drawerMax, SHEET_SNAPS, snapHeightPx, type DrawerPreset } from "../lib/drawer";
import type { SheetSnap } from "../types";

const GRABBER_TAP_SLOP = 6;
// Fast flick past which the release biases one snap in the drag direction.
const GRABBER_FLICK = 0.5; // px/ms

type Props = {
  collapsed: boolean;
  widthPx: number;
  onToggleCollapsed: () => void;
  onResize: (px: number) => void;
  onPreset: (preset: DrawerPreset) => void;
  isMobile?: boolean;
  peekHeader?: ReactNode;
  /** Mobile-only: current sheet snap; defaults to bar/half from `collapsed` until wired. */
  snap?: SheetSnap;
  /** Mobile-only: commit a snap after a grabber drag. No-op on desktop. */
  onSnap?: (snap: SheetSnap) => void;
  children: ReactNode;
};

const PRESETS: { preset: DrawerPreset; label: string }[] = [
  { preset: "peek", label: "Peek" },
  { preset: "default", label: "Default" },
  { preset: "wide", label: "Wide" },
  { preset: "focus", label: "Focus" },
];

function activateWithKeyboard(event: KeyboardEvent<HTMLElement>, action: () => void) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    action();
  }
}

export function BottomSheet({
  collapsed,
  widthPx,
  onToggleCollapsed,
  onResize,
  onPreset,
  isMobile = false,
  peekHeader,
  snap,
  onSnap,
  children,
}: Props) {
  const panelRef = useRef<HTMLElement>(null);
  const dragging = useRef(false);
  const moved = useRef(false);
  const dragState = useRef<{ startY: number; startT: number; startHeight: number } | null>(null);

  const effectiveSnap: SheetSnap = snap ?? (collapsed ? "bar" : "half");

  function onGrabberPointerDown(event: PointerEvent<HTMLDivElement>) {
    const panel = panelRef.current;
    if (!panel) return;
    dragState.current = { startY: event.clientY, startT: performance.now(), startHeight: panel.getBoundingClientRect().height };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onGrabberPointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragState.current;
    const panel = panelRef.current;
    if (!drag || !panel) return;
    const dy = event.clientY - drag.startY;
    if (Math.abs(dy) <= GRABBER_TAP_SLOP) return;
    const height = Math.max(80, Math.min(window.innerHeight * 0.95, drag.startHeight - dy));
    panel.style.height = `${height}px`; // live drag, uncommitted
  }

  function onGrabberPointerUp(event: PointerEvent<HTMLDivElement>) {
    const drag = dragState.current;
    const panel = panelRef.current;
    dragState.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (!drag || !panel) return;
    panel.style.height = ""; // hand height back to the snap class
    const dy = event.clientY - drag.startY;
    if (Math.abs(dy) <= GRABBER_TAP_SLOP) {
      onToggleCollapsed(); // tap: bar ↔ last expanded (useDrawer owns the memory)
      return;
    }
    const dt = Math.max(1, performance.now() - drag.startT);
    const velocity = dy / dt; // px/ms; positive = downward
    const endHeight = drag.startHeight - dy;
    const vh = window.innerHeight;
    const candidates: { snap: SheetSnap; h: number }[] = SHEET_SNAPS.map((snap) => ({ snap, h: snapHeightPx(snap, vh) }));
    let nearest = candidates.reduce((a, b) => (Math.abs(b.h - endHeight) < Math.abs(a.h - endHeight) ? b : a));
    const index = candidates.findIndex((c) => c.snap === nearest.snap);
    if (velocity > GRABBER_FLICK) {
      nearest = candidates[Math.max(0, index - 1)]; // fast downward flick: one snap lower
    } else if (velocity < -GRABBER_FLICK) {
      nearest = candidates[Math.min(candidates.length - 1, index + 1)]; // fast upward flick: one snap higher
    }
    onSnap?.(nearest.snap);
  }

  function onGrabberPointerCancel(event: PointerEvent<HTMLDivElement>) {
    dragState.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (panelRef.current) panelRef.current.style.height = "";
  }

  useEffect(() => {
    if (!isMobile || typeof window === "undefined" || !window.visualViewport) return;
    const vv = window.visualViewport;
    const panel = panelRef.current;
    const update = () => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      panel?.style.setProperty("--kb-inset", `${inset}px`);
    };
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    update();
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      panel?.style.removeProperty("--kb-inset");
    };
  }, [isMobile]);

  function presetPressed(preset: DrawerPreset) {
    if (preset === "peek") return collapsed;
    if (collapsed) return false;
    if (preset === "default") return widthPx === clampWidth(DRAWER_DEFAULT);
    // On narrow viewports the clamped widths can collide (drawerMax === wide === default);
    // when they do the smaller preset wins and the larger ones suppress themselves, so a
    // segmented control only ever marks a single active option.
    if (preset === "wide") {
      return widthPx === clampWidth(DRAWER_WIDE) && clampWidth(DRAWER_WIDE) !== clampWidth(DRAWER_DEFAULT);
    }
    return (
      widthPx === drawerMax() &&
      drawerMax() !== clampWidth(DRAWER_WIDE) &&
      drawerMax() !== clampWidth(DRAWER_DEFAULT)
    );
  }

  function onHandlePointerDown(event: PointerEvent<HTMLDivElement>) {
    moved.current = false;
    if (collapsed) {
      dragging.current = false;
      return;
    }
    dragging.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onHandlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragging.current || !panelRef.current) return;
    moved.current = true;
    const right = panelRef.current.getBoundingClientRect().right;
    onResize(right - event.clientX);
  }

  function onHandlePointerUp(event: PointerEvent<HTMLDivElement>) {
    const wasDragging = dragging.current;
    dragging.current = false;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (collapsed) {
      onToggleCollapsed();
      return;
    }
    if (wasDragging && !moved.current) onToggleCollapsed();
  }

  function onHandleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggleCollapsed();
      return;
    }
    if (collapsed) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onResize(widthPx + DRAWER_RESIZE_STEP);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      onResize(widthPx - DRAWER_RESIZE_STEP);
    } else if (event.key === "Home") {
      event.preventDefault();
      onResize(drawerMax());
    } else if (event.key === "End") {
      event.preventDefault();
      onResize(DRAWER_MIN);
    }
  }

  return (
    <section
      ref={panelRef}
      className={`mc-workspace-panel ${isMobile ? `is-${effectiveSnap}` : collapsed ? "is-collapsed" : "is-open"}`}
      style={!isMobile && !collapsed ? { width: widthPx } : undefined}
      aria-label="Workspace panel"
    >
      {isMobile ? (
        <>
          <div
            className="mc-grabber"
            role="button"
            tabIndex={0}
            aria-label={collapsed ? "Expand panel" : "Collapse panel"}
            aria-expanded={!collapsed}
            onPointerDown={onGrabberPointerDown}
            onPointerMove={onGrabberPointerMove}
            onPointerUp={onGrabberPointerUp}
            onPointerCancel={onGrabberPointerCancel}
            onKeyDown={(event) => activateWithKeyboard(event, onToggleCollapsed)}
          >
            <b />
          </div>
          {peekHeader ? <div className="mc-sheet-head">{peekHeader}</div> : null}
        </>
      ) : (
        <>
          <div
            className="mc-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize workspace panel"
            aria-valuemin={DRAWER_PEEK}
            aria-valuemax={drawerMax()}
            aria-valuenow={collapsed ? DRAWER_PEEK : widthPx}
            tabIndex={0}
            onPointerDown={onHandlePointerDown}
            onPointerMove={onHandlePointerMove}
            onPointerUp={onHandlePointerUp}
            onPointerCancel={() => { dragging.current = false; }}
            onKeyDown={onHandleKeyDown}
          />
          <div className="mc-snaps" role="group" aria-label="Panel size">
            {PRESETS.map(({ preset, label }) => (
              <button
                key={preset}
                type="button"
                className={presetPressed(preset) ? "on" : undefined}
                aria-pressed={presetPressed(preset)}
                onClick={() => onPreset(preset)}
                onKeyDown={(event) => activateWithKeyboard(event, () => onPreset(preset))}
              >
                <span>{label}</span>
                <b />
              </button>
            ))}
          </div>
        </>
      )}
      <div className="mc-panels">{children}</div>
    </section>
  );
}
