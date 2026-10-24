# SPEAKER_NOTES

For the 12-14 minute pitch to the judges. The Film runs 13:00 at speed 1.0 (780 s). Talk over it; do not read the screen. The first bullet of each chapter is the opener (the presenter strip shows it as the "next" line). All numbers are from `data/scenarios/hero.json`, `data/cities/dubai_downtown/meta.json` and `data/test_results.json`; if you re-generate those, re-check the figures here. Anything in `[TEAM TO FILL]` has no source yet.

Format note: `frontend/scripts/sync-film-data.mjs` reads this file. Chapter headings are `## Chapter N`; bullets under them become the presenter's talking points. Do not start any other heading with a number.

Numbering: chapters 1-12 keep their original note ids. The three newer film chapters ("Two directions", "Winter in Oslo", "Safe and cheap to run") are note ids 13, 14 and 15; the Presenter finds them through the `notes` field in `frontend/src/film/master.ts` (currently unset for those three, so add `notes: 13`, `notes: 14`, `notes: 15`). Film order and times now: 1-7, Two directions (13), Winter in Oslo (14), 8, 9, 10, Safe and cheap to run (15), 11, 12; total 13:10. Start times printed on older headings predate the three new chapters.

## Chapter 1 — Dubai, 13:00 (0:00, 40 s)

- Dubai in summer is built for people who walk, and the sun decides where they can.
- Midday heat in these districts is routinely above 40 degrees [TEAM TO FILL — cite source].
- We are Abhamzay. This is Zill: the agent that routes you through the shade.
- Transition: "To see why that matters, let's stand in the street at one thirty."

## Chapter 2 — The problem (0:40, 50 s)

- Every map you use optimises time or distance. None of them optimises shade.
- This walker takes the fastest route from Burj Park to Business Bay Metro in July at 15:30: 23.9 minutes, 15.6 of them in direct sun.
- A static shady route cannot exist, because shade moves every minute and changes with the season.
- Transition: "So we asked: can we compute where the shade is, for any minute?"

## Chapter 3 — Shade moves (1:30, 55 s)

- This is Downtown on a July day, from early morning to evening. The Burj's shadow crosses the lake and rotates.
- At noon the shade is thin; by 16:00 tower shadows swallow whole streets.
- A shade map is only true for one minute, so Zill computes it for every ten minutes of the day.
- Transition: "Where does that map come from? From open data, and we can build it in front of you."

## Chapter 4 — A city, built in seconds (2:25, 90 s)

- We type "Downtown Dubai" and the pipeline pulls OpenStreetMap: 8,602 buildings in the shadow-casting area, 3,039 of them in the rendered scene.
- It builds a walking and cycling network of 7,659 street segments, 744 mapped trees, and finds covered and air-conditioned links, 15 segments tagged as enclosed bridges or passages.
- This is a cached build of the real bake, labelled as such. The pipeline takes only a name, a box and an origin, so another hot city is the same code.
- Be upfront: 79 % of building heights are not in OpenStreetMap and use sensible defaults. We say that on the validation page.
- Transition: "Now the engine that turns buildings into shade."

## Chapter 5 — The shade engine (3:55, 90 s)

- Sun position from a solar model, then a ray from every two-metre cell toward the sun; if a building top is higher than the ray, the cell is in shade.
- That gives a shade raster per ten-minute step, and an exposure number for every street segment.
- Routing is time-aware: a street's shade is looked up for the minute the walker arrives, not the minute they leave.
- It is tested: 470 automated tests pass (375 backend, 95 frontend, data/test_results.json 2026-10-24), including shadow-length geometry checks.
- Say the limits: buildings, mapped trees and covered links only. Awnings, unmapped trees and wind are not modelled.
- Transition: "Let's use it. A tourist at Burj Park wants to get to the metro."

## Chapter 6 — The route (5:25, 150 s)

- The user types a sentence. The agent resolves the places, checks the weather, compares routes, and a separate verifier checks its claims.
- Fastest versus Coolest, same start, same time: Coolest is 26.1 minutes against 23.9, so 2.2 minutes longer, but sun exposure drops from 15.6 to 9.4 minutes. That is 6.2 minutes less sun, about 40 percent, and our heat-load index falls 17.6 percent.
- Every number in the agent's sentence is a token filled in from the tool result. The model cannot invent a figure.
- These are model estimates, not measurements. We say so on the card.
- The agent session you see is a scripted recording against the real engine, not a live model, and the badge says so. [If a live key was added and sessions re-recorded, change this line.]
- Transition: "A better route is one answer. The other is to leave at a different time."

## Chapter 7 — Leave later (7:55, 70 s)

- The agent also scans departures every five minutes from 15:30 to 17:00.
- For this trip, honestly, leaving later does not help enough: sun exposure of the balanced route falls from 594 s at 15:30 to 518 s at 16:30, about 76 seconds, for a one-hour wait. The optimiser recommends leaving now.
- That is the point of an optimiser: it can say "go now". On other trips and dates it will recommend a different time and show which streets turn to shade.
- The agent asks approval before committing the plan. Autonomy is a setting, not a surprise.
- Transition: "That was one traveller. Let's talk about what makes this an agent."

## Chapter 8 — An agent, not a map (9:05, 60 s)

- Same engine, three goals: a tourist, a delivery rider, an outdoor crew lead.
- The monitor watches a simulated clock. A 20-minute delay is injected, labelled a simulated event; it replans and shows the difference.
- At autonomy level 3 small changes are applied by itself and can be undone; larger ones need approval.
- Four roles: planner, verifier, monitor, narrator, with deterministic tools underneath.
- Transition: "Who would pay for this?"

## Chapter 9 — Who it's for (10:05, 60 s)

- Problem: heat costs real people time, comfort and safety, and nobody sells a shade-aware route.
- Buyers, our hypotheses to validate with mentors: hotels and tourism boards (per-property subscription or annual licence), delivery fleets (per active rider or per route call), outdoor-worker employers (per site). Individuals use it free.
- Our engine numbers for the wedges: rider route 38 percent less sun for 1.6 minutes more; crew shuttle 40 percent less sun for 0.7 minutes more. The crew policy pack for the UAE midday break is marked "verify".
- Market size [TEAM TO FILL — cite source]. Pricing [TEAM TO FILL — validate with mentors].
- Go-to-market: start with a few hotels in Downtown as a concierge widget, use the free app for distribution and data, then fleets.
- Why we win: real shade computed per minute from open data, an agent that verifies its own numbers, and a pipeline that is city-agnostic. [TEAM TO FILL — competitors, cite sources]
- Transition: "You should ask: does it actually work?"

## Chapter 10 — Does it work? (11:05, 40 s)

- What is real: open data with counts, a tested engine, a verifier that rejects invented numbers.
- What is not proven yet: field measurements. Our plan is shaded versus sunny surface readings on the Boulevard with an infrared thermometer. [If done, quote `data/validation/field_test.json`; if not, say the result is pending.]
- Limits again in one breath: heights, trees, awnings, and the air-conditioned link needs an on-site check.
- Transition: "And it is not only Dubai."

## Chapter 11 — Any hot city (11:45, 40 s)

- Only Downtown Dubai is baked. The others on the globe are the roadmap, shown hollow.
- Roadmap: Downtown prototype, then UAE cities, then a global open-data pipeline.
- The pipeline needs a name, a bounding box, an origin and a timezone; there is a test that bakes a tiny synthetic city to prove it.
- Transition: "To close."

## Chapter 12 — The ask (12:25, 35 s)

- Zill: the agent that routes you through the shade.
- What we want today: feedback on the buyer and the pricing, and introductions to a hotel group or fleet operator. [TEAM TO FILL — the specific ask]
- Press `A` and take any trip the judges want to try.

## Chapter 13 — Two directions (7:10, 50 s) [film order: after "Leave later", before "Winter in Oslo"]

- Same trip, same minute, two different needs: in a hot month you want shade, in a dark month you want sun.
- Shade mode shows the Burj Park to Business Bay Metro walk we just saw. Sun mode shows a real Dubai walk from the sun search in `data/scenarios/hero.json` (key `sun`): Business Bay Metro to Burj Park on 15 April at 10:30 gains 524 s of direct sun (+48 percent) for 269 s more walking.
- One engine; only the preference flips. The well-being card beside it shows the UV band and the daylight window as guidance, not medical advice.
- Say the limit: clear-sky geometry, model estimates, no field measurements yet.
- Transition: "Now the place where the sun is the scarce thing."

## Chapter 14 — Winter in Oslo (8:00, 56 s)

- Oslo is our second city, baked with the same pipeline and no city-specific code: 13,841 buildings in the shadow ring, 10,082 street segments, 20,208 trees, 53 places (`data/cities/oslo/meta.json`).
- At the December solstice the sun is about 6.6 degrees high, so shadows are about 8.6 times a building's height. The engine is tested at exactly that angle.
- The sunniest route is for daylight and mood. Be explicit: UV at midwinter is about 0.1, so this is not vitamin D, and it is not medical advice.
- Honest note: Oslo's winter weather in the app is a labelled stand-in (the 2025 solstice). Oslo has about 5 h 54 min of daylight at the solstice.
- Summer scenario for contrast: National Museum to Byporten Shopping at 12:00 on 21 June, 613 s to 1,288 s of direct sun (+110 percent) for 131 s more walking.
- Transition: "So who pays, and is it safe to run?"

## Chapter 15 — Safe and cheap to run (11:26, 42 s) [film order: after "Does it work?", before "Any city"]

- Privacy by design: no accounts, no stored user data, location used per request and discarded, logs scrub coordinates and keys, no ads.
- Controls on the live site: per-IP rate limits (tightest on the agent), 64 KB request cap, CORS allow-list, CSP and HSTS. pip-audit is clean; npm audit has 2 findings inside Next's build-time PostCSS. UAE PDPL and GDPR alignment is an aim, not a certification; a penetration test comes before any B2B launch (`docs/SECURITY.md`).
- Costs: the AI agent is $10 a month flat on OpenCode Go (about 3,630 conversations a month on glm-5.3-flash). Adding a city costs no money: Dubai data bake 7.5 s and shade bake 487.5 s for four dates. The Contabo price and cost per 1,000 users are [TEAM TO FILL] (`docs/COSTS.md`).
- Capacity, measured: local machine about 26 requests per second at 20 users (p95 596 ms); live VM 16.9 requests per second at 20 users, p95 1.6 s, 0 errors, run capped at 20 users.
- Transition: "And it is not only Dubai and Oslo."

## Managerial story

- Problem: in hot cities the route you choose decides how much direct sun you take, and existing maps ignore it.
- Buyer: hospitality and tourism first (guests avoid walking in heat), delivery fleets (rider heat stress and productivity), outdoor employers (heat-illness risk and the midday break rule). Individuals free for acquisition and data.
- Pricing hypotheses (unvalidated): per property per month; per active rider per month or per call; per site per month; annual licence for a tourism board. [TEAM TO FILL — validate with Dr Maria Haynes' session]
- Go-to-market: a free consumer app and an embeddable hotel widget; pilot with one or two Downtown hotels; then a fleet pilot using the rider scenario.
- Why we win: it is computed, not guessed (real sun, real buildings, tested); it is an agent that owns a goal over time and checks itself; the pipeline is city-agnostic so each new city is a bake, not a rewrite.
- Execution: what exists is working software with tests, honest limits and a field-test plan; what is unproven is stated, not hidden.

## Judge Q&A

### How is the shade computed?
Open building footprints and heights go into a two-metre height grid. For every cell and every ten minutes we cast a ray toward the sun and check whether a building is taller than the ray. Trees add partial shade. The result is sampled along every street segment.

### How accurate is it?
The geometry is tested (shadow lengths, directions, symmetry, sun position against a reference library to within half a degree). We have not yet validated against street measurements; that is the field test. The biggest error source is building heights: 79 percent come from defaults because OpenStreetMap lacks them.

### What about trees and awnings?
Only mapped trees count (744, none with crown data), and awnings and canopies not in OpenStreetMap are ignored. So the model tends to under-estimate shade. We say it on screen: "Model v1: buildings, mapped trees, covered links".

### Why an agent and not just a map?
The map answers one question. The agent plans a goal over time: compares options, searches departure times, orders stops, adds cool-down breaks, replans when something changes, and asks approval at the right moment. A verifier checks every claim and numbers come only from tool results.

### What if OpenStreetMap is wrong?
Then the model is wrong in that place. Heights and links can be overridden by curated files (we did that for the Burj Khalifa, 828 m against 760 m in OpenStreetMap). Better sources such as Overture heights are on the roadmap.

### Is the air-conditioned link verified?
No. OpenStreetMap tags the Metro to Dubai Mall link as covered and indoor; it is on our list to walk it on site. Until then we call it unverified.

### How do you make money, and who pays first?
Hypothesis: hospitality and tourism pay per property or by licence; fleets pay per rider; outdoor employers pay per site. First paying customers are most likely a Downtown hotel group. None of this is validated yet. [TEAM TO FILL — evidence from mentors or interviews]

### Who are the competitors?
[TEAM TO FILL — cite sources.] We do not claim to know that nobody else does this; we claim existing mainstream routing products we have used optimise time and distance.

### Why would a hotel use it?
A concierge widget turns "it is too hot to walk" into three shade-safe walks from the entrance with real stats. [TEAM TO FILL — hotel interview evidence]

### What is simulated or recorded?
The agent sessions in the film and the offline app are scripted recordings against the real engine (badged); the proactive-replan delay is a labelled simulated event; the fleet and crew views are scenario simulations; weather files are real recorded Open-Meteo data; the film's build log is a cached build. Route numbers, shade rasters and statistics are computed live by the engine.

### What happens with no internet?
Everything runs: the film, the app, replay, recorded weather. Only a live model call and live weather need a network.

### Is this medical advice?
No. It reduces sun exposure and labels the heat index a model estimate. The crew policy pack for the UAE midday break is unverified and not legal advice.

### Why is the saving only about 40 percent, and why is the late-departure gain small?
Because the real engine said so on the best trip we found by search, and we did not tune parameters to inflate it. The detour is 2.2 minutes. For this trip, waiting does not pay.

### What did you build in this time?
Data bake, shade engine, router, departure optimiser, agent with verifier and monitor, a 13-minute film, the live app, tests and docs. What we did not build: accounts, payments, traffic, a mobile app.
