"""Build Zill-and-Shams-pitch.pptx from the rendered slide PNGs (docs/pitch/qa/slide-NN.png) with speaker notes.
Run render.mjs first (from frontend/): node ../docs/pitch/deck/render.mjs ../docs/pitch/qa
Then: backend/.venv/Scripts/python.exe docs/pitch/deck/build_pptx.py"""
import io, glob, os
from PIL import Image
from pptx import Presentation
from pptx.util import Emu
here = os.path.dirname(os.path.abspath(__file__))
qa = os.path.join(here, '..', 'qa')
NOTES = [
"Zill & Shams (ظل وشمس, shade and sun). An AI agent that plans walks and rides around the sun. Team Abhamzay, Team 13. Live at zill.itshamza.me.",
"Maps optimise time. Hot cities: route choice decides sun exposure. Dark winters: too little daylight (Oslo about 6 h at the December solstice). Sun and shade move every minute, so static lists go stale.",
"Sourced figures only. 72% of 12,346 Abu Dhabi adults vitamin D deficient (BMC Research Notes 2019); 70,000+ riders (Dubai RTA); 18.72 M visitors 2024 (Dubai DET via WAM); UAE midday break 12:30-15:00, 15 Jun-15 Sep (MoHRE 2025).",
"One engine, two modes. Shade mode = least direct sun (includes AC links like Metro to Dubai Mall). Sun mode = most direct sun for daylight and well-being. The preference flips.",
"Open map data, 3D model, sun and shadows every 10 minutes, best route, agent. Dubai: 8,602 buildings, 7,659 street segments, 744 trees. Oslo is the second city, built by the same pipeline.",
"Shade mode proof: Burj Park to Business Bay Metro, summer 15:30. 6.2 min less direct sun, 40% less, 2.2 min longer. Model estimate; awnings and wind not modelled. Source: data/scenarios/hero.json.",
"Sun mode proof, real routes from the documented search (hero.json 'sun'). Dubai 15 Apr 10:30: sun 1,101 s to 1,625 s (+524 s, +48%) for +269 s. Oslo 21 Jun 12:00: 613 s to 1,288 s (+675 s, +110%) for +131 s. Clear-sky geometry, model estimates.",
"Oslo: 13,841 buildings in the shadow ring, 10,082 edges, 20,208 trees, 53 POIs (meta.json). Sun ~6.6 deg at midwinter noon, shadows ~8.6x height, tested. Winter weather in the app is a labelled stand-in. Images are shade-bake masks.",
"Well-being: WHO UV band, indicative heat stress, daylight window (sun high, UV >= 3, cloud < 70%), break prompts. Not medical advice. In Oslo winter, sun mode is about daylight and mood, not vitamin D (UV 0.1 in the solstice scenario).",
"Agent plans, checks (verifier; numbers come from engine tokens), and adapts. Pluggable LLM chain OpenCode Go then Voke. Without a live key, sessions are labelled recorded replays.",
"Accuracy and freshness (docs/ACCURACY.md): sun within 0.5 deg of pvlib on 20 samples; shadows 10 min / 2 m; weather hourly; map re-bake on demand, weekly job planned. About 79% of Dubai heights are estimates. No field validation yet, so no accuracy percentage claimed. 373 backend tests passed.",
"Security (docs/SECURITY.md): no accounts or stored user data; location per request only; per-IP rate limits, size caps, CORS allow-list, CSP/HSTS, log scrubbing, key server-side. pip-audit clean; npm audit 2 findings in Next's PostCSS. PDPL/GDPR alignment is an aim, not certification. Pen-test comes before B2B launch.",
"Who pays. Target customers (not partners): Talabat, Deliveroo, Careem. Expanded scope: city planners (B2G planning analytics: where to plant trees or add shade), schools, elderly care, events, real estate. Prices are hypotheses; none quoted.",
"Freemium, no ads. Reason: ads would put location data into an ad pipeline; no ads keeps the privacy story clean. Free app, optional premium (saved routes, day plans), B2B/B2G subscriptions as main revenue, pay-per-route API.",
"Costs (docs/COSTS.md). Contabo price and per-1,000-user cost are [TEAM TO FILL]. OpenCode Go $10/month flat: ~3,630 conversations on glm-5.3-flash, ~56 on kimi-k3 (page request estimates, 8.7 requests per conversation measured). Bake timings on a dev laptop, not the VM.",
"Users. Market: 70,000+ riders, 18.72 M visitors (sourced; context, not a forecast). Capacity measured with scripts/loadtest.py: local machine peaks ~26 req/s at 20 users (p95 596 ms), 40 users p95 2.6 s; live VM at 20 users 16.9 req/s, p95 1.6 s, 0 errors (run capped at 20 users, did not saturate). VM CPU count [TEAM TO FILL].",
"Roadmap: Dubai and Oslo now; UAE and Gulf next with city planners as first B2G pilot; northern cities winter daylight pilot. No funding ask. Team Abhamzay: Mohammed Hamza Ansari, Abhay Preethan. Try it at zill.itshamza.me.",
]
fs = sorted(glob.glob(os.path.join(qa, 'slide-*.png')))
assert len(fs) == len(NOTES), (len(fs), len(NOTES))
prs = Presentation(); prs.slide_width = Emu(12191695); prs.slide_height = Emu(6858000)
blank = prs.slide_layouts[6]
for f, n in zip(fs, NOTES):
    s = prs.slides.add_slide(blank)
    buf = io.BytesIO(); Image.open(f).convert('RGB').save(buf, 'JPEG', quality=90); buf.seek(0)
    s.shapes.add_picture(buf, 0, 0, prs.slide_width, prs.slide_height)
    s.notes_slide.notes_text_frame.text = n
prs.save(os.path.join(here, '..', 'Zill-and-Shams-pitch.pptx'))
print('ok', len(fs))
