// Shared helpers for the Phase 9 recording tools (record-film, record-app, export-deck-assets).
// Owned by the OPS stream. Not imported by the app.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, renameSync, copyFileSync, rmSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";

export const ROOT = resolve(__dirname, "..", "..");
export const DECK_DIR = join(ROOT, "docs", "deck_assets");
export const VENV_PY = join(
  ROOT,
  "backend",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);

export const arg = (k: string, d?: string): string | undefined => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
export const flag = (k: string): boolean => process.argv.includes(`--${k}`);

export const BASE = arg("base", process.env.ZILL_BASE ?? "http://localhost:3000")!;

export const GPU_ARGS = [
  "--use-angle=d3d11",
  "--enable-gpu",
  "--ignore-gpu-blocklist",
  "--enable-unsafe-webgpu",
];
export const SWIFT_ARGS = [
  "--use-angle=swiftshader",
  "--enable-unsafe-swiftshader",
  "--ignore-gpu-blocklist",
];

export type Launched = { browser: Browser; gpu: "angle-d3d11" | "swiftshader" };

/** Launch Chromium with the GPU angle first and fall back to SwiftShader when WebGL is unavailable. */
export async function launch(forceSwift = false): Promise<Launched> {
  const tryLaunch = async (args: string[]): Promise<Browser> =>
    chromium.launch({ headless: true, args });
  if (!forceSwift) {
    try {
      const b = await tryLaunch(GPU_ARGS);
      const ctx = await b.newContext();
      const p = await ctx.newPage();
      const ok = await p.evaluate(() => {
        const c = document.createElement("canvas");
        return !!c.getContext("webgl2");
      });
      await ctx.close();
      if (ok) return { browser: b, gpu: "angle-d3d11" };
      await b.close();
    } catch {
      /* fall through to SwiftShader */
    }
  }
  return { browser: await tryLaunch(SWIFT_ARGS), gpu: "swiftshader" };
}

export async function rendererName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const c = document.querySelector("canvas");
    const gl = c?.getContext("webgl2") as WebGL2RenderingContext | null;
    if (!gl) return "unknown";
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : String(gl.getParameter(gl.RENDERER));
  });
}

export async function waitReady(page: Page, timeoutMs = 150_000): Promise<boolean> {
  try {
    await page.waitForFunction(() => (window as unknown as { __zillReady?: boolean }).__zillReady === true, undefined, {
      timeout: timeoutMs,
      polling: 250,
    });
    return true;
  } catch {
    return false;
  }
}

export function attachLogs(page: Page, logs: string[]): void {
  page.on("console", (m) => {
    if (m.type() === "error") logs.push(`[console.error] ${m.text().slice(0, 300)}`);
  });
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
}

export async function ensureServer(): Promise<void> {
  try {
    const r = await fetch(`${BASE}/api/health`);
    if (!r.ok) throw new Error(String(r.status));
  } catch (e) {
    console.error(
      `Cannot reach ${BASE}/api/health (${String(e)}). Start the servers first: python scripts/zill.py demo`,
    );
    process.exit(2);
  }
}

/** Move a file, falling back to copy + delete when src and dest are on different drives (EXDEV on Windows temp → D:). */
function moveFile(src: string, dest: string): void {
  try {
    renameSync(src, dest);
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "EXDEV") throw e;
    copyFileSync(src, dest);
    rmSync(src);
  }
}

/** Close the context (flushes the video) and move the single recorded .webm to `dest`. */
export async function finishVideo(ctx: BrowserContext, page: Page, tmpDir: string, dest: string): Promise<void> {
  const v = page.video();
  await ctx.close();
  const src = v ? await v.path() : null;
  mkdirSync(join(dest, ".."), { recursive: true });
  if (src && existsSync(src)) {
    if (existsSync(dest)) rmSync(dest);
    moveFile(src, dest);
  } else {
    const f = readdirSync(tmpDir).find((n) => n.endsWith(".webm"));
    if (!f) throw new Error("no video was recorded");
    moveFile(join(tmpDir, f), dest);
  }
  rmSync(tmpDir, { recursive: true, force: true });
  console.log(`video: ${dest} (${(statSync(dest).size / 1e6).toFixed(1)} MB)`);
}

/** H.264 crf 20 yuv420p via the ffmpeg binary bundled with imageio-ffmpeg (in the backend venv). */
export function toMp4(webm: string, mp4: string, crf = Number(arg("crf", "20"))): boolean {
  const q = spawnSync(
    VENV_PY,
    ["-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
    { encoding: "utf-8" },
  );
  const ffmpeg = (q.stdout ?? "").trim();
  if (q.status !== 0 || !ffmpeg) {
    console.error("imageio-ffmpeg not available: uv pip install --python backend/.venv imageio-ffmpeg");
    return false;
  }
  const r = spawnSync(
    ffmpeg,
    ["-y", "-i", webm, "-c:v", "libx264", "-crf", String(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4],
    { encoding: "utf-8" },
  );
  if (r.status !== 0) {
    console.error((r.stderr ?? "").slice(-600));
    return false;
  }
  console.log(`mp4: ${mp4} (${(statSync(mp4).size / 1e6).toFixed(1)} MB)`);
  return true;
}

export const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
