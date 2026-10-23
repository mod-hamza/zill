import { describe, expect, it } from "vitest";
import { SSEParser } from "./sseClient";

const frame = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

describe("SSEParser", () => {
  it("parses complete frames", () => {
    const p = new SSEParser();
    const out = p.push(frame("agent", { id: "a", type: "thought" }) + frame("agent", { id: "b", type: "message" }));
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ event: "agent", data: '{"id":"a","type":"thought"}' });
    expect(JSON.parse(out[1]!.data).id).toBe("b");
  });

  it("reassembles frames split across arbitrary chunks", () => {
    const whole = frame("agent", { id: "x", payload: { text: "héllo wörld" } }) + frame("agent", { id: "y" });
    for (const size of [1, 2, 3, 7, 13]) {
      const p = new SSEParser();
      const got: string[] = [];
      for (let i = 0; i < whole.length; i += size)
        for (const m of p.push(whole.slice(i, i + size))) got.push(JSON.parse(m.data).id);
      expect(got).toEqual(["x", "y"]);
    }
  });

  it("handles CRLF line endings, comments and multi-line data", () => {
    const p = new SSEParser();
    const out = p.push(": keep-alive\r\nevent: agent\r\ndata: a\r\ndata: b\r\n\r\n");
    expect(out).toEqual([{ event: "agent", data: "a\nb" }]);
  });

  it("defaults the event name to message and resets between frames", () => {
    const p = new SSEParser();
    const out = p.push("data: 1\n\nevent: x\ndata: 2\n\ndata: 3\n\n");
    expect(out.map((m) => m.event)).toEqual(["message", "x", "message"]);
  });

  it("flushes an unterminated trailing frame", () => {
    const p = new SSEParser();
    expect(p.push("event: agent\ndata: tail")).toEqual([]);
    expect(p.flush()).toEqual([{ event: "agent", data: "tail" }]);
  });

  it("ignores empty frames", () => {
    const p = new SSEParser();
    expect(p.push("\n\n\n")).toEqual([]);
  });
});
