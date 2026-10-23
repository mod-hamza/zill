// Streaming pass-through for the agent SSE endpoints. Next's built-in rewrite proxy gzips (and so
// buffers) event streams for browsers, which would turn live agent progress into one late burst.
// These route handlers forward the body untouched and mark it `no-transform` so nothing buffers it.
const BACKEND = process.env.ZILL_BACKEND_URL ?? "http://127.0.0.1:8000";

export async function proxyAgentStream(req: Request, action: "message" | "approve" | "simulate"): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/agent/${action}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: await req.text(),
      signal: req.signal,
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: { error: "backend_unreachable", message: "The backend is not reachable." } },
      { status: 502 },
    );
  }
  const headers = new Headers();
  headers.set("content-type", upstream.headers.get("content-type") ?? "text/event-stream");
  headers.set("cache-control", "no-cache, no-transform");
  headers.set("x-accel-buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers });
}
