import { describe, expect, it } from "vitest";
import type { UTCTimestamp } from "lightweight-charts";
import {
  type Candle,
  aggregate,
  anchoredVwap,
  htfLevels,
  movingAverage,
  prevPeriodLevels,
  rsi,
  vwap,
} from "./indicators";

const c = (time: number, close: number, hi = close, lo = close, vol = 1): Candle => ({
  time: time as UTCTimestamp,
  open: close,
  high: hi,
  low: lo,
  close,
  volume: vol,
});

// Build a series of close-only candles spaced 60s apart from `start`.
const series = (vals: number[], start = 0, step = 60): Candle[] =>
  vals.map((v, i) => c(start + i * step, v));

const values = (pts: { value: number }[]) => pts.map((p) => p.value);

describe("moving averages", () => {
  const s = series([1, 2, 3, 4, 5]);

  it("SMA(3) is the trailing mean", () => {
    expect(values(movingAverage(s, 3, "SMA"))).toEqual([2, 3, 4]);
  });

  it("EMA(3) seeds on the SMA then smooths", () => {
    // seed = mean(1,2,3)=2; k=0.5; then 4*.5+2*.5=3; 5*.5+3*.5=4
    expect(values(movingAverage(s, 3, "EMA"))).toEqual([2, 3, 4]);
  });

  it("WMA(3) weights recent closes more", () => {
    const out = values(movingAverage(s, 3, "WMA"));
    expect(out).toHaveLength(3);
    expect(out[0]).toBeCloseTo(14 / 6, 6);
    expect(out[1]).toBeCloseTo(20 / 6, 6);
    expect(out[2]).toBeCloseTo(26 / 6, 6);
  });

  it("RMA(3) uses Wilder smoothing", () => {
    const out = values(movingAverage(s, 3, "RMA"));
    expect(out[0]).toBeCloseTo(2, 6);
    expect(out[1]).toBeCloseTo(2 + (4 - 2) / 3, 6); // 2.6667
    expect(out[2]).toBeCloseTo(2.6667 + (5 - 2.6667) / 3, 3); // 3.4444
  });

  it("HMA returns finite values aligned to the series tail", () => {
    const out = movingAverage(series([1, 2, 3, 4, 5, 6, 7, 8]), 4, "HMA");
    expect(out.length).toBeGreaterThan(0);
    expect(out.every((p) => Number.isFinite(p.value))).toBe(true);
  });
});

describe("RSI", () => {
  it("is 100 for a strictly rising series (all gains)", () => {
    const out = rsi(series([...Array(20)].map((_, i) => i + 1)), 14);
    expect(out.at(-1)?.value).toBeCloseTo(100, 6);
  });

  it("is 0 for a strictly falling series (all losses)", () => {
    const out = rsi(series([...Array(20)].map((_, i) => 20 - i)), 14);
    expect(out.at(-1)?.value).toBeCloseTo(0, 6);
  });
});

describe("VWAP", () => {
  it("is the cumulative volume-weighted typical price within a session", () => {
    const r = vwap(series([10, 20]), 1); // hlc3 == close, equal volume
    expect(values(r.vwap)).toEqual([10, 15]);
    // variance at bar 2 = mean(100,400) - 15^2 = 25 -> sd 5; bands at ±1σ
    expect(r.upper[1].value).toBeCloseTo(20, 6);
    expect(r.lower[1].value).toBeCloseTo(10, 6);
  });

  it("resets at the UTC day boundary", () => {
    const r = vwap([c(0, 10), c(60, 20), c(90_000, 100)], 1); // 3rd bar is a new day
    expect(r.vwap.at(-1)?.value).toBeCloseTo(100, 6); // fresh session -> just the new bar
  });
});

describe("anchored VWAP", () => {
  it("accumulates only from the anchor time onward", () => {
    const r = anchoredVwap(series([10, 20, 30]), 60); // anchor at 2nd bar
    expect(values(r)).toEqual([20, 25]); // (20), then (20+30)/2
  });
});

describe("aggregate", () => {
  it("rolls 1-minute bars into higher-timeframe OHLCV buckets", () => {
    // five 1-min bars (0,60,120,180,240); 5m bucket starts at 0 covers all five
    const bars = [
      c(0, 10, 12, 9, 100),
      c(60, 11, 15, 10, 100),
      c(120, 12, 13, 8, 100),
      c(180, 9, 11, 7, 100),
      c(240, 14, 16, 9, 100),
    ];
    const agg = aggregate(bars, 5);
    expect(agg).toHaveLength(1);
    expect(agg[0]).toMatchObject({
      time: 0,
      open: 10, // first open
      high: 16, // max high
      low: 7, // min low
      close: 14, // last close
      volume: 500, // summed
    });
  });

  it("returns the input unchanged for 1-minute timeframe", () => {
    const bars = series([1, 2, 3]);
    expect(aggregate(bars, 1)).toEqual(bars);
  });
});

describe("higher-timeframe levels", () => {
  it("plots the prior completed HTF bucket's high/low/close", () => {
    // 2-minute buckets over 1-min bars: bucket0 = bars[0,1], bucket1 = bars[2,3]
    const bars = [
      c(0, 10, 12, 8),
      c(60, 11, 15, 9), // bucket0: h=15, l=8, close=11
      c(120, 20, 21, 19),
      c(180, 22, 25, 18), // bucket1
    ];
    const lv = htfLevels(bars, 2);
    // bucket0 bars have no prior bucket; bucket1 bars carry bucket0's levels
    expect(values(lv.high)).toEqual([15, 15]);
    expect(values(lv.low)).toEqual([8, 8]);
    expect(values(lv.close)).toEqual([11, 11]);
  });
});

describe("previous-period levels", () => {
  it("plots the prior day's high/low on the current day's bars", () => {
    const bars = [
      c(0, 10, 12, 8), // day 0
      c(60, 11, 12, 9), // day 0
      c(90_000, 20, 21, 19), // day 1
      c(90_060, 22, 23, 18), // day 1
    ];
    const lv = prevPeriodLevels(bars);
    expect(values(lv.pdh)).toEqual([12, 12]); // day-0 high, on both day-1 bars
    expect(values(lv.pdl)).toEqual([8, 8]); // day-0 low
  });
});
