// Calm "busy" state for rate limits: the API answers 429 with Retry-After (docs/SECURITY.md);
// the client waits and retries instead of showing an error. The UI shows "Busy, retrying in Ns".
import { create } from "zustand";

type BusyState = {
  /** epoch ms when the pending retry fires, or null when not waiting */
  until: number | null;
  set: (until: number | null) => void;
};

export const useBusy = create<BusyState>((set) => ({
  until: null,
  set: (until) => set({ until }),
}));

export const RETRY = { maxAttempts: 3, defaultS: 2, minS: 1, maxS: 30 } as const;

/** Seconds to wait from a Retry-After header (delta-seconds or HTTP date), clamped. */
export function retryAfterSeconds(h: string | null, now = Date.now()): number {
  let s: number = RETRY.defaultS;
  if (h) {
    const n = Number(h);
    if (Number.isFinite(n)) s = n;
    else {
      const t = Date.parse(h);
      if (Number.isFinite(t)) s = (t - now) / 1000;
    }
  }
  return Math.min(RETRY.maxS, Math.max(RETRY.minS, Math.ceil(s)));
}

export function sleep(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const id = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(id);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** fetch that waits out 429s (up to RETRY.maxAttempts retries), publishing the wait to useBusy. */
export async function fetchRetrying(
  url: string,
  init?: RequestInit,
  doFetch: typeof fetch = fetch,
): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    const r = await doFetch(url, init);
    if (r.status !== 429 || attempt >= RETRY.maxAttempts) return r;
    const s = retryAfterSeconds(r.headers.get("retry-after"));
    useBusy.getState().set(Date.now() + s * 1000);
    try {
      await sleep(s * 1000, init?.signal);
    } finally {
      useBusy.getState().set(null);
    }
  }
}
