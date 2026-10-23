import { describe, expect, it, vi } from "vitest";
import { fetchRetrying, retryAfterSeconds, useBusy } from "./busy";

describe("retryAfterSeconds", () => {
  it("reads delta-seconds and HTTP dates, clamped", () => {
    expect(retryAfterSeconds("3")).toBe(3);
    expect(retryAfterSeconds(null)).toBe(2);
    expect(retryAfterSeconds("0")).toBe(1);
    expect(retryAfterSeconds("999")).toBe(30);
    const now = Date.parse("2026-10-23T22:00:00Z");
    expect(retryAfterSeconds("Fri, 23 Oct 2026 22:00:05 GMT", now)).toBe(5);
  });
});

describe("fetchRetrying", () => {
  it("waits out a 429 then returns the good response, publishing the busy state", async () => {
    vi.useFakeTimers();
    const seen: (number | null)[] = [];
    const unsub = useBusy.subscribe((s) => seen.push(s.until));
    const f = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 429, headers: { "retry-after": "2" } }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    const p = fetchRetrying("/api/route", undefined, f as unknown as typeof fetch);
    await vi.advanceTimersByTimeAsync(2100);
    const r = await p;
    expect(r.status).toBe(200);
    expect(f).toHaveBeenCalledTimes(2);
    expect(seen.some((x) => typeof x === "number")).toBe(true);
    expect(useBusy.getState().until).toBeNull();
    unsub();
    vi.useRealTimers();
  });
  it("gives up after the retry budget and returns the 429", async () => {
    vi.useFakeTimers();
    const f = vi.fn().mockImplementation(async () => new Response("", { status: 429, headers: { "retry-after": "1" } }));
    const p = fetchRetrying("/x", undefined, f as unknown as typeof fetch);
    await vi.advanceTimersByTimeAsync(5000);
    expect((await p).status).toBe(429);
    expect(f).toHaveBeenCalledTimes(4);
    vi.useRealTimers();
  });
});
