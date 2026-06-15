// Pure indicator math, computed client-side from the candle series. Provider-agnostic:
// these work unchanged whether bars come from the demo feed or a real market-data provider.

import type { UTCTimestamp } from "lightweight-charts";

export interface Candle {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Point {
  time: UTCTimestamp;
  value: number;
}

export type MaType = "SMA" | "EMA" | "WMA" | "RMA" | "HMA";

const SECONDS_PER_DAY = 86_400;

// --- moving-average kernels: number[] -> (number | null)[] aligned to input ---

function smaArr(v: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(v.length).fill(null);
  let sum = 0;
  for (let i = 0; i < v.length; i++) {
    sum += v[i];
    if (i >= n) sum -= v[i - n];
    if (i >= n - 1) out[i] = sum / n;
  }
  return out;
}

function emaArr(v: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(v.length).fill(null);
  if (v.length < n) return out;
  const k = 2 / (n + 1);
  let seed = 0;
  for (let j = 0; j < n; j++) seed += v[j];
  let prev = seed / n;
  out[n - 1] = prev;
  for (let i = n; i < v.length; i++) {
    prev = v[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

function wmaArr(v: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(v.length).fill(null);
  const denom = (n * (n + 1)) / 2;
  for (let i = n - 1; i < v.length; i++) {
    let s = 0;
    for (let j = 0; j < n; j++) s += v[i - j] * (n - j); // most recent gets weight n
    out[i] = s / denom;
  }
  return out;
}

// Wilder's smoothing (RMA) — also the basis for RSI.
function rmaArr(v: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(v.length).fill(null);
  if (v.length < n) return out;
  let seed = 0;
  for (let j = 0; j < n; j++) seed += v[j];
  let prev = seed / n;
  out[n - 1] = prev;
  const a = 1 / n;
  for (let i = n; i < v.length; i++) {
    prev = (v[i] - prev) * a + prev;
    out[i] = prev;
  }
  return out;
}

function hmaArr(v: number[], n: number): (number | null)[] {
  const half = Math.max(1, Math.floor(n / 2));
  const sq = Math.max(1, Math.round(Math.sqrt(n)));
  const wHalf = wmaArr(v, half);
  const wFull = wmaArr(v, n);
  const diff: (number | null)[] = v.map((_, i) =>
    wHalf[i] != null && wFull[i] != null ? 2 * (wHalf[i] as number) - (wFull[i] as number) : null,
  );
  const out: (number | null)[] = new Array(v.length).fill(null);
  const denom = (sq * (sq + 1)) / 2;
  for (let i = sq - 1; i < v.length; i++) {
    let ok = true;
    let s = 0;
    for (let j = 0; j < sq; j++) {
      const x = diff[i - j];
      if (x == null) {
        ok = false;
        break;
      }
      s += x * (sq - j);
    }
    if (ok) out[i] = s / denom;
  }
  return out;
}

function kernel(type: MaType): (v: number[], n: number) => (number | null)[] {
  switch (type) {
    case "SMA":
      return smaArr;
    case "WMA":
      return wmaArr;
    case "RMA":
      return rmaArr;
    case "HMA":
      return hmaArr;
    default:
      return emaArr;
  }
}

function toPoints(candles: Candle[], arr: (number | null)[]): Point[] {
  const out: Point[] = [];
  for (let i = 0; i < candles.length; i++) {
    const val = arr[i];
    if (val != null && Number.isFinite(val)) out.push({ time: candles[i].time, value: val });
  }
  return out;
}

// --- public indicators ---

export function movingAverage(candles: Candle[], length: number, type: MaType): Point[] {
  const closes = candles.map((c) => c.close);
  return toPoints(candles, kernel(type)(closes, length));
}

export interface VwapBands {
  vwap: Point[];
  upper: Point[];
  lower: Point[];
}

// Session VWAP (resets each UTC day) with volume-weighted std-dev bands.
export function vwap(candles: Candle[], mult = 1): VwapBands {
  const out: VwapBands = { vwap: [], upper: [], lower: [] };
  let day = Number.NaN;
  let cumPV = 0;
  let cumV = 0;
  let cumPV2 = 0;
  for (const c of candles) {
    const d = Math.floor(c.time / SECONDS_PER_DAY);
    if (d !== day) {
      day = d;
      cumPV = 0;
      cumV = 0;
      cumPV2 = 0;
    }
    const tp = (c.high + c.low + c.close) / 3;
    cumPV += tp * c.volume;
    cumV += c.volume;
    cumPV2 += tp * tp * c.volume;
    if (cumV > 0) {
      const v = cumPV / cumV;
      const variance = Math.max(0, cumPV2 / cumV - v * v);
      const sd = Math.sqrt(variance);
      out.vwap.push({ time: c.time, value: v });
      out.upper.push({ time: c.time, value: v + mult * sd });
      out.lower.push({ time: c.time, value: v - mult * sd });
    }
  }
  return out;
}

// VWAP anchored to a fixed start time (defaults to the first bar if anchor precedes it).
export function anchoredVwap(candles: Candle[], anchorTime: number): Point[] {
  const out: Point[] = [];
  let cumPV = 0;
  let cumV = 0;
  for (const c of candles) {
    if (c.time < anchorTime) continue;
    const tp = (c.high + c.low + c.close) / 3;
    cumPV += tp * c.volume;
    cumV += c.volume;
    if (cumV > 0) out.push({ time: c.time, value: cumPV / cumV });
  }
  return out;
}

export function rsi(candles: Candle[], length: number): Point[] {
  const closes = candles.map((c) => c.close);
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i === 0) {
      gains.push(0);
      losses.push(0);
      continue;
    }
    const ch = closes[i] - closes[i - 1];
    gains.push(Math.max(0, ch));
    losses.push(Math.max(0, -ch));
  }
  const avgGain = rmaArr(gains, length);
  const avgLoss = rmaArr(losses, length);
  const out: Point[] = [];
  for (let i = 0; i < closes.length; i++) {
    const g = avgGain[i];
    const l = avgLoss[i];
    if (g == null || l == null) continue;
    const value = l === 0 ? (g === 0 ? 50 : 100) : 100 - 100 / (1 + g / l);
    out.push({ time: candles[i].time, value });
  }
  return out;
}

export interface PrevLevels {
  pdh: Point[];
  pdl: Point[];
  pwh: Point[];
  pwl: Point[];
}

// Previous-day and previous-week high/low, as step lines (the level in effect at each bar).
export function prevPeriodLevels(candles: Candle[]): PrevLevels {
  const dayKey = (t: number) => Math.floor(t / SECONDS_PER_DAY);
  // Monday-aligned week index (epoch day 0 is a Thursday).
  const weekKey = (t: number) => {
    const d = Math.floor(t / SECONDS_PER_DAY);
    return d - ((d + 3) % 7);
  };

  const aggregate = (keyFn: (t: number) => number) => {
    const hl = new Map<number, { h: number; l: number }>();
    const order: number[] = [];
    for (const c of candles) {
      const k = keyFn(c.time);
      const e = hl.get(k);
      if (!e) {
        hl.set(k, { h: c.high, l: c.low });
        order.push(k);
      } else {
        if (c.high > e.h) e.h = c.high;
        if (c.low < e.l) e.l = c.low;
      }
    }
    const prior = new Map<number, { h: number; l: number }>();
    for (let i = 1; i < order.length; i++) {
      prior.set(order[i], hl.get(order[i - 1]) as { h: number; l: number });
    }
    return { keyFn, prior };
  };

  const d = aggregate(dayKey);
  const w = aggregate(weekKey);
  const out: PrevLevels = { pdh: [], pdl: [], pwh: [], pwl: [] };
  for (const c of candles) {
    const pd = d.prior.get(d.keyFn(c.time));
    if (pd) {
      out.pdh.push({ time: c.time, value: pd.h });
      out.pdl.push({ time: c.time, value: pd.l });
    }
    const pw = w.prior.get(w.keyFn(c.time));
    if (pw) {
      out.pwh.push({ time: c.time, value: pw.h });
      out.pwl.push({ time: c.time, value: pw.l });
    }
  }
  return out;
}
