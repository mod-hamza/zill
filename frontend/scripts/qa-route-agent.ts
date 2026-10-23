// QA: route ribbons via the agent-proposal path. Opens /app with the agent panel, runs the tourist
// chip (replay), waits for the approval card, dumps route-ribbon state and saves a still.
//   npx tsx scripts/qa-route-agent.ts <out.png> [low|high]
import { chromium } from "@playwright/test";

void (async () => {
  const out = process.argv[2] ?? "agent-route.png";
  const q = process.argv[3] ?? "low";
  const swift = process.env.ZILL_SWIFT === "1";
  const b = await chromium.launch({
    args: swift
      ? ["--disable-gpu", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
      : ["--use-angle=d3d11", "--ignore-gpu-blocklist"],
  });
  const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
  p.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") console.log(`[${m.type()}]`, m.text().slice(0, 600));
  });
  await p.goto(`http://localhost:3000/app?qa=1&q=${q}&agent=1&agentSpeed=${process.env.ZILL_AGENT_SPEED ?? "20"}`, { timeout: 180000 });
  await p.waitForFunction("window.__zillReady === true", undefined, { timeout: 150000 });
  await p.getByTestId("chip-tourist_walk").click({ timeout: 30000 });
  await p.getByTestId("agent-approval").waitFor({ timeout: 90000 });
  await p.waitForTimeout(2500);
  const info = await p.evaluate(`(() => {
    const s = window.__zill.scene; const o = [];
    s.traverse((m) => { if (m.isMesh && m.material && m.material.uniforms && m.material.uniforms.uRevealD) {
      const u = m.material.uniforms; const pos = m.geometry.attributes.position.array;
      let nan = 0; for (let i = 0; i < pos.length; i++) if (!Number.isFinite(pos[i])) nan++;
      o.push({ ro: m.renderOrder, op: u.uOpacity.value, mul: u.uMulOpacity.value, rev: u.uRevealD.value, n: m.geometry.index.count, verts: pos.length / 3, nan, p0: [pos[0], pos[1], pos[2]] }); } });
    const r = window.__zill.useRoute.getState();
    const seg = r.result && r.result.coolest.segments[0];
    const c = window.__zill.gl.getContext(); const e = c.getExtension('WEBGL_debug_renderer_info');
    return { renderer: c.getParameter(e.UNMASKED_RENDERER_WEBGL), o, reveal: r.reveal, routeOpacity: r.routeOpacity, view: r.view, seg };
  })()`);
  console.log(JSON.stringify(info, null, 1).slice(0, 4000));
  if (process.env.ZILL_EXPR) {
    console.log("expr:", JSON.stringify(await p.evaluate(process.env.ZILL_EXPR)));
    await p.waitForTimeout(1500);
  }
  await p.screenshot({ path: out });
  await b.close();
})();
