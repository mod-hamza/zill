// Debug helper: open a URL, wait for readiness, evaluate an expression, optionally screenshot.
//   npx tsx scripts/qa-dbg.ts <url> <expr> [screenshot.png]
import { chromium } from "@playwright/test";

void (async () => {
  const b = await chromium.launch({
    args:
      process.env.ZILL_SWIFT === "1"
        ? ["--disable-gpu", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        : ["--use-angle=d3d11", "--ignore-gpu-blocklist"],
  });
  const [vw, vh] = (process.env.ZILL_VIEWPORT ?? "1920x1080").split("x").map(Number);
  const p = await b.newPage({ viewport: { width: vw!, height: vh! } });
  p.on("console", (m) => {
    if (m.type() === "error") console.log("ERR", m.text().slice(0, 400));
  });
  await p.goto(process.argv[2]!, { timeout: 180000 });
  await p.waitForFunction(
    () => (window as unknown as { __zillReady?: boolean }).__zillReady === true,
    undefined,
    { timeout: 120000 },
  );
  await p.waitForTimeout(1500);
  const out = await p.evaluate(process.argv[3]!);
  console.log(JSON.stringify(out, null, 1)?.slice(0, 6000));
  if (process.argv[4]) {
    await p.waitForTimeout(800);
    await p.screenshot({ path: process.argv[4] });
  }
  await b.close();
})();
