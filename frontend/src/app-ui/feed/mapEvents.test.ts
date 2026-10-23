import { describe, expect, it } from "vitest";
import { colors } from "@/design/tokens";
import { badgeFromEvents, mapEvents, summariseArgs, verifierText } from "./mapEvents";
import type { AgentEvent } from "./types";

const ev = (id: string, type: string, payload: Record<string, unknown>, ts = "2026-10-22T21:08:47.000+00:00"): AgentEvent => ({
  id,
  ts,
  type,
  payload,
});

describe("verifier text", () => {
  it("uses the real payload numbers", () => {
    expect(verifierText({ checked: 14, passed: 14, defects: [] })).toBe(
      "Verifier: 14 claims checked, 14 supported",
    );
    expect(verifierText({ checked: 12, passed: 11, defects: [{}] })).toBe(
      "Verifier: 12 claims checked, 11 supported, 1 flagged",
    );
  });
});

describe("mapEvents", () => {
  const events = [
    ev("1", "thought", { text: "Locating where you are starting." }),
    ev("2", "tool_call", { name: "resolve_place", args: { query: "Al Wasl Park 2", role: "origin", window: { a: 1 } } }, "2026-10-22T21:08:47.650+00:00"),
    ev("3", "tool_result", { name: "resolve_place", ok: true, summary: "Resolved 'Al Wasl Park 2'." }, "2026-10-22T21:08:48.100+00:00"),
    ev("4", "verifier", { checked: 12, passed: 12, defects: [] }, "2026-10-22T21:08:49.000+00:00"),
    ev("5", "replan", { reason: "Departure delayed.", kind: "delay" }, "2026-10-22T21:08:50.000+00:00"),
    ev("6", "approval_request", { reason: "Autonomy L2 asks before committing." }),
    ev("7", "message", { text: "Here is what I would do." }),
  ];

  it("maps markers to the brief's palette", () => {
    const rows = mapEvents(events);
    const byKind = Object.fromEntries(rows.map((r) => [r.kind, r]));
    expect(byKind.tool!.marker).toBe(colors.bronze);
    expect(byKind.verifier!.marker).toBe(colors.oasis);
    expect(byKind.replan!.marker).toBe(colors.ember);
    expect(byKind.message!.marker).toBe(colors.champagne);
    expect(byKind.approval!.marker).toBe(colors.brass);
  });

  it("humanises tool names and summarises scalar args only", () => {
    const tool = mapEvents(events).find((r) => r.kind === "tool")!;
    expect(tool.label).toBe("resolve place");
    expect(tool.detail).toBe("query Al Wasl Park 2 · role origin");
  });

  it("computes timestamp offsets from the first event", () => {
    const rows = mapEvents(events);
    expect(rows.find((r) => r.kind === "tool")!.offsetMs).toBe(650);
    expect(rows.find((r) => r.kind === "result")!.offsetMs).toBe(1100);
  });

  it("compact mode hides thoughts and result summaries", () => {
    const kinds = mapEvents(events, true).map((r) => r.kind);
    expect(kinds).not.toContain("thought");
    expect(kinds).not.toContain("result");
    expect(kinds).toContain("verifier");
  });

  it("marks failed tool results", () => {
    const row = mapEvents([ev("x", "tool_result", { ok: false, summary: "No route." })])[0]!;
    expect(row.failed).toBe(true);
    expect(row.marker).toBe(colors.clay);
  });

  it("tolerates unknown event types and empty payloads", () => {
    const rows = mapEvents([ev("u", "something_new", {})]);
    expect(rows[0]!.kind).toBe("other");
  });
});

describe("badges and args", () => {
  it("derives the badge from payload.replay", () => {
    const b = badgeFromEvents([
      ev("1", "thought", { text: "x", replay: { source: "scripted", label: "Scripted session (live model not connected)" } }),
    ]);
    expect(b).toEqual({ source: "scripted", label: "Scripted session (live model not connected)" });
    expect(badgeFromEvents([ev("1", "thought", { text: "x" })])).toBeUndefined();
  });

  it("caps long args", () => {
    expect(summariseArgs({ query: "x".repeat(200) }, 20).length).toBe(20);
  });
});
