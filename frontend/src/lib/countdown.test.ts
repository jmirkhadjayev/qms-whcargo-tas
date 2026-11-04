import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { formatCountdown, useSecondsLeft } from "./countdown";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-04T10:00:00Z"));
});
afterEach(() => vi.useRealTimers());

describe("formatCountdown", () => {
  it.each([
    [0, "00:00"],
    [59, "00:59"],
    [60, "01:00"],
    [605, "10:05"],
  ])("%i seconds -> %s", (seconds, text) => {
    expect(formatCountdown(seconds)).toBe(text);
  });
});

describe("useSecondsLeft", () => {
  it("counts down once a second and stops at zero", () => {
    const { result } = renderHook(() => useSecondsLeft("2026-11-04T10:00:03Z"));
    expect(result.current).toBe(3);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(2);
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current).toBe(0);
  });

  it("is null without a deadline", () => {
    const { result } = renderHook(() => useSecondsLeft(null));
    expect(result.current).toBeNull();
  });

  it("is already zero for a deadline in the past", () => {
    const { result } = renderHook(() => useSecondsLeft("2026-11-04T09:00:00Z"));
    expect(result.current).toBe(0);
  });
});
