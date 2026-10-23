import { fetchRetrying } from "./busy";

// Minimal SSE-over-fetch client (the agent endpoints are POST, so EventSource is not usable).
// Wire format (backend api/sse.py): `event: <name>\ndata: <json>\n\n`.

export type SSEMessage = { event: string; data: string };

/** Incremental SSE parser: feed chunks, get complete messages. Handles CRLF, split chunks,
 *  multi-line data, comments and unterminated trailing data (flushed by `flush()`). */
export class SSEParser {
  private buf = "";
  private event = "message";
  private data: string[] = [];

  private skipLF = false;

  push(chunk: string): SSEMessage[] {
    // Normalise line endings; a chunk ending in CR may be half of CRLF, so remember to drop a
    // leading LF on the next chunk.
    let text = chunk;
    if (this.skipLF && text.startsWith("\n")) text = text.slice(1);
    this.skipLF = text.endsWith("\r");
    text = text.replace(/\r\n?/g, "\n");
    this.buf += text;
    const out: SSEMessage[] = [];
    let idx: number;
    while ((idx = this.buf.indexOf("\n")) >= 0) {
      const line = this.buf.slice(0, idx);
      this.buf = this.buf.slice(idx + 1);
      const msg = this.line(line);
      if (msg) out.push(msg);
    }
    return out;
  }

  flush(): SSEMessage[] {
    const out: SSEMessage[] = [];
    if (this.buf) {
      const msg = this.line(this.buf);
      this.buf = "";
      if (msg) out.push(msg);
    }
    const last = this.dispatch();
    if (last) out.push(last);
    return out;
  }

  private dispatch(): SSEMessage | null {
    if (!this.data.length) {
      this.event = "message";
      return null;
    }
    const msg = { event: this.event, data: this.data.join("\n") };
    this.event = "message";
    this.data = [];
    return msg;
  }

  private line(line: string): SSEMessage | null {
    if (line === "") return this.dispatch();
    if (line.startsWith(":")) return null;
    const c = line.indexOf(":");
    const field = c < 0 ? line : line.slice(0, c);
    let value = c < 0 ? "" : line.slice(c + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }
}

export type StreamOptions = {
  signal?: AbortSignal;
  onMessage: (m: SSEMessage) => void;
};

/** POST JSON and stream the SSE response. Resolves when the stream ends; throws on HTTP errors. */
export async function postSSE(
  url: string,
  body: unknown,
  opts: StreamOptions,
): Promise<void> {
  const res = await fetchRetrying(url, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!res.ok || !res.body) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: { message?: string } };
      if (j?.detail?.message) detail = j.detail.message;
    } catch {
      /* body was not JSON */
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  const parser = new SSEParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const m of parser.push(dec.decode(value, { stream: true }))) opts.onMessage(m);
  }
  for (const m of parser.push(dec.decode())) opts.onMessage(m);
  for (const m of parser.flush()) opts.onMessage(m);
}
