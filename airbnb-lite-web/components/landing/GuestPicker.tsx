"use client";

import { useState, useRef, useEffect } from "react";

export type GuestCounts = { adults: number; children: number; infants: number };

const ROWS: { key: keyof GuestCounts; label: string; sub: string; min: number }[] = [
  { key: "adults", label: "Adults", sub: "Ages 13 or above", min: 1 },
  { key: "children", label: "Children", sub: "Ages 2\u201312", min: 0 },
  { key: "infants", label: "Infants", sub: "Under 2", min: 0 },
];

export function GuestPicker({ value, onChange }: { value: GuestCounts; onChange: (v: GuestCounts) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const total = value.adults + value.children;
  const summary = total > 0
    ? `${total} guest${total > 1 ? "s" : ""}${value.infants > 0 ? `, ${value.infants} infant${value.infants > 1 ? "s" : ""}` : ""}`
    : "Add guests";

  function bump(key: keyof GuestCounts, delta: number) {
    const min = ROWS.find((r) => r.key === key)!.min;
    onChange({ ...value, [key]: Math.max(min, Math.min(16, value[key] + delta)) });
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full flex-col items-start px-5 py-2 text-left"
      >
        <span className="text-xs font-medium text-[var(--lp-text)]">Who</span>
        <span className={`text-sm ${total > 0 ? "text-[var(--lp-text)]" : "text-[var(--lp-text-muted)]"}`}>{summary}</span>
      </button>

      {open && (
        <div className="fade-in absolute right-0 top-full z-20 mt-2 w-80 rounded-2xl border border-[var(--lp-border)] bg-[var(--lp-surface)] p-5 shadow-[0_8px_28px_rgba(34,32,27,0.14)]">
          {ROWS.map((row) => (
            <div key={row.key} className="flex items-center justify-between border-b border-[var(--lp-border)] py-3.5 last:border-b-0">
              <div>
                <p className="text-sm font-medium">{row.label}</p>
                <p className="text-xs text-[var(--lp-text-muted)]">{row.sub}</p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => bump(row.key, -1)}
                  disabled={value[row.key] <= row.min}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-[var(--lp-border)] text-[var(--lp-text-muted)] disabled:opacity-30"
                >
                  &minus;
                </button>
                <span className="w-4 text-center text-sm">{value[row.key]}</span>
                <button
                  type="button"
                  onClick={() => bump(row.key, 1)}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-[var(--lp-border)] text-[var(--lp-text)]"
                >
                  +
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
