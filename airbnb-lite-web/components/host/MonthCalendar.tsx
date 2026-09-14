"use client";

import { useMemo, useState } from "react";
import { CalendarNight } from "@/lib/api";
import { effectiveGuestPrice } from "@/lib/pricing-display";
import { HOST_CALENDAR_DAYS } from "@/lib/api";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function toKey(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function MonthCalendar({
  nights,
  currency,
  selectedDate,
  onSelect,
}: {
  nights: CalendarNight[];
  currency: string;
  selectedDate: string | null;
  onSelect: (date: string) => void;
}) {
  const today = useMemo(() => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date;
  }, []);
  const calendarEnd = useMemo(() => {
    const date = new Date(today);
    date.setDate(date.getDate() + HOST_CALENDAR_DAYS);
    return date;
  }, [today]);

  const byDate = useMemo(() => {
    const m = new Map<string, CalendarNight>();
    nights.forEach((n) => {
      const date = new Date(`${n.date}T00:00:00`);
      if (date >= today && date <= calendarEnd) m.set(n.date, n);
    });
    return m;
  }, [nights, calendarEnd, today]);

  const availableNights = nights.filter((night) => byDate.has(night.date));
  const displayPrices = availableNights.map(effectiveGuestPrice);
  const min = displayPrices.length ? Math.min(...displayPrices) : 0;
  const max = displayPrices.length ? Math.max(...displayPrices) : 1;

  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());

  const monthStart = new Date(viewYear, viewMonth, 1);
  const gridStart = new Date(monthStart);
  gridStart.setDate(gridStart.getDate() - gridStart.getDay());

  const cells: Date[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart);
    d.setDate(gridStart.getDate() + i);
    cells.push(d);
  }

  function heatBackground(price: number, muted: boolean) {
    const t = max > min ? (price - min) / (max - min) : 0.5;
    const higherPrice = t >= 0.5;
    const base = higherPrice ? 22 : 33;
    const g = higherPrice ? 108 : 134;
    const b = higherPrice ? 220 : 122;
    const alpha = higherPrice
      ? (muted ? 0.1 : 0.16) + Math.abs(t - 0.5) * (muted ? 0.24 : 0.5)
      : (muted ? 0.05 : 0.09) + Math.abs(t - 0.5) * (muted ? 0.18 : 0.4);
    return `rgba(${base}, ${g}, ${b}, ${alpha.toFixed(2)})`;
  }

  function borderColor(night: CalendarNight) {
    if (night.status === "rejected") return "#e2604f";
    if (night.status === "host_override") return "#c9714a";
    if (night.status === "approved" || night.status === "auto_applied") return "#21867a";
    return "#c9c2b3"; // pending_approval - neutral warm gray, not yet decided
  }

  function canGoPrev() {
    return viewYear > today.getFullYear() || viewMonth > today.getMonth();
  }
  function canGoNext() {
    const nextMonthStart = new Date(viewYear, viewMonth + 1, 1);
    return nextMonthStart <= new Date(calendarEnd.getFullYear(), calendarEnd.getMonth(), 1);
  }

  function go(delta: number) {
    let m = viewMonth + delta;
    let y = viewYear;
    if (m < 0) { m = 11; y -= 1; }
    if (m > 11) { m = 0; y += 1; }
    setViewYear(y);
    setViewMonth(m);
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <button
          onClick={() => go(-1)}
          disabled={!canGoPrev()}
          className="rounded-md border border-[var(--lp-border)] px-2.5 py-1 text-sm text-[var(--lp-text-muted)] transition hover:text-[var(--lp-text)] disabled:opacity-30"
        >
          &larr;
        </button>
        <p className="font-display text-lg">{MONTH_NAMES[viewMonth]} {viewYear}</p>
        <button
          onClick={() => go(1)}
          disabled={!canGoNext()}
          className="rounded-md border border-[var(--lp-border)] px-2.5 py-1 text-sm text-[var(--lp-text-muted)] transition hover:text-[var(--lp-text)] disabled:opacity-30"
        >
          &rarr;
        </button>
      </div>

      <div className="mb-1 grid grid-cols-7 gap-1 text-center text-[10px] uppercase tracking-wide text-[var(--lp-text-muted)]">
        {WEEKDAYS.map((w) => <div key={w}>{w}</div>)}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {cells.map((d) => {
          const key = toKey(d);
          const night = byDate.get(key);
          const inMonth = d.getMonth() === viewMonth;
          const withinHorizon = d >= today && d <= calendarEnd;
          const selected = key === selectedDate;
          const pending = night?.status === "pending_approval";
          const rejected = night?.status === "rejected";
          const displayPrice = night ? effectiveGuestPrice(night) : null;

          return (
            <button
              key={key}
              disabled={!night || !withinHorizon}
              onClick={() => night && withinHorizon && onSelect(key)}
              className={`flex h-16 flex-col items-start justify-between rounded-md border p-1.5 text-left transition
                ${!inMonth ? "opacity-30" : ""}
                ${!night ? "cursor-default border-[var(--lp-border)]" : "hover:brightness-95"}
                ${pending ? "border-dashed" : "border-solid"}`}
              style={{
                background: night ? heatBackground(displayPrice!, pending || rejected) : "transparent",
                borderColor: night ? borderColor(night) : undefined,
                borderWidth: selected ? 2 : 1,
              }}
            >
              <span className="text-[10px] text-[var(--lp-text-muted)]">{d.getDate()}</span>
              {night && (
                <span
                  className={`font-mono text-[11px] leading-none ${rejected ? "text-[var(--lp-text-muted)] line-through" : ""}`}
                >
                  {displayPrice!.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-[var(--lp-text-muted)]">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border border-dashed" style={{ borderColor: "#c9c2b3" }} />
          Pending approval
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: "#21867a" }} />
          Approved / live
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: "#c9714a" }} />
          Host-set price
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: "#e2604f" }} />
          Rejected
        </span>
        <span className="ml-auto">{currency} {min.toLocaleString(undefined, { maximumFractionDigits: 0 })}&ndash;{max.toLocaleString(undefined, { maximumFractionDigits: 0 })} across the year</span>
      </div>
    </div>
  );
}
