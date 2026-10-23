# Gamma prompt: Zill & Shams pitch deck

Paste everything between the two lines below into Gamma ("Paste in text" → Presentation, 17 cards).
Recommended Gamma settings: theme **dark / elegant** (or a custom one with the colours below), image style
**photographic / architectural**, text density **brief**. Then replace the AI images on slides 1, 4, 5 and 6
with the real stills from `docs/deck_assets/stills/` (file names given per slide).

---

Create a 17-slide pitch deck for hackathon judges. The audience is business-minded; keep it easy to read, with no
jargon and no dense paragraphs: one idea per slide, short lines, large numbers.

VISUAL STYLE (follow strictly): premium, warm, cinematic, restrained, like an architecture film. Dark background
near-black warm ink (#0E0C0A) with panels in deep umber (#1A1511). Headlines in a high-contrast serif (Fraunces or
Cormorant Garamond), light weight, in champagne (#E9DCBC). Body text in a clean sans (Inter Tight or Manrope) in ivory
(#F4EEE1). Accents: brass (#C8A15A) for highlights and "the better option", ember (#D07A35) for sun/heat, deep
teal-slate (#22333A) for shade, muted sage (#5E8C7B) for cool/indoor, slate (#7C8A94) for neutral. Thin 1px hairline
rules, small caps labels with wide letter spacing. Imagery: warm desert light, long shadows, city at golden hour,
3D architectural city renders. NO neon, NO purple/blue AI gradients, NO glassy cards, NO robots, NO emoji, NO
circuit or hexagon patterns.

SLIDE 1: Title
Zill & Shams (ظل وشمس, "shade and sun")
Tagline: Shade when you need it. Sun when you want it.
Small line: An AI agent that plans every walk and ride around the sun.
Footer: Abhamzay, Team 13 · AI Agents Hackathon, American University in Dubai
[Image: dramatic 3D skyline of Downtown Dubai at dawn, Burj Khalifa silhouette, long light. Real still: 01_dubai-13-00.png]

SLIDE 2: The problem
Headline: Maps plan around time. Nobody plans around the sun.
Three short points:
- In hot cities, the route you pick decides how much direct sun you take, and in summer that is a health risk.
- In dark winters, people get too little daylight. Oslo has about 6 hours of daylight in late December.
- The sun and shade move every minute, so a static "shady street" or "sunny street" list is never right for long.

SLIDE 3: Why it matters (numbers, with sources in small text)
- 72% of 12,346 adults in an Abu Dhabi study were vitamin D deficient, and another 10% insufficient, in one of the
  sunniest places on earth. (BMC Research Notes, 2019)
- More than 70,000 delivery riders work across Dubai. (Dubai RTA)
- 18.72 million international overnight visitors came to Dubai in 2024. (Dubai DET via WAM)
- The UAE bans outdoor work in direct sun 12:30 to 15:00, from 15 June to 15 September, for the 21st year in 2025.
  (UAE Ministry of Human Resources and Emiratisation)

SLIDE 4: The product, one engine with two modes
Two columns side by side:
SHADE MODE (teal): for hot cities. Finds the coolest route: the most shade and the least direct sun, using
air-conditioned links such as the Dubai Metro to Dubai Mall walkway.
SUN MODE (ember): for daylight and well-being. Finds the sunniest route for people who want more daylight: winter
cities, office workers, anyone short on sun.
Line under: Same engine. The preference flips.
[Image: split-screen city: left half in deep shade, right half in warm sunlight. Real still: 06_the-route-compare.png]

SLIDE 5: How it works, in one picture
A simple 5-step flow with icons-free hairline arrows:
Open map data → 3D model of the city → where the sun and shadows fall, every 10 minutes → the best route for you →
an AI agent that plans, checks and adjusts.
Small line: Works for any city with OpenStreetMap data. Our first city: Downtown Dubai (8,602 buildings, 7,659
street segments, 744 trees).
[Image: 3D city rising out of a dark map grid. Real still: 04_a-city-built-in-seconds.png]

SLIDE 6: Proof it is real (big numbers)
A real walk computed by the engine: Burj Park → Business Bay Metro, a summer afternoon at 15:30.
Big numbers: 6.2 minutes less direct sun · 40% less sun · only 2.2 minutes longer.
Small line: Computed from real map data, not a mock-up. Live at zill.itshamza.me
Footnote: Model estimate; shade from buildings and mapped trees. Awnings and wind are not modelled yet.
[Image: real still 06_the-route-flythrough.png, street-level walk with a gold route line and an on-screen sun counter]

SLIDE 7: An agent, not just a map
Three short points:
- Plans: understands "I'm walking to the metro, I tire easily in the heat" and compares options.
- Checks itself: a second AI step verifies every claim; every number comes from the engine, never made up.
- Adapts: if you are delayed or a street is closed, it replans and asks before changing your plan.
[Image: real still 08_an-agent-not-a-map.png]

SLIDE 7: Proof, sun mode (real routes, clear-sky geometry, model estimates)
Dubai, 15 April 10:30, Business Bay Metro to Burj Park: +8.7 min more direct sun (+48%) for +4.5 min.
Oslo, 21 June 12:00, National Museum to Byporten Shopping: +11.3 min more sun (+110%) for +2.2 min.
Source: data/scenarios/hero.json.

SLIDE 8: Oslo, the second city
Built with the same city-agnostic pipeline: 13,841 buildings in the shadow ring, 10,082 street segments, 20,208 trees,
53 places. Sun is about 6.6 degrees at midwinter noon, so shadows run about 8.6x building height (tested). Honest note:
Oslo winter weather is a labelled stand-in; about 5 h 54 min of daylight at the solstice.

SLIDE 9: Well-being (NOT MEDICAL ADVICE)
UV index with WHO band; heat stress band (indicative); daylight window (sun high, UV 3+, cloud under 70%); hydration and
shade-break prompts. Well-being and daylight guidance only; clinicians are future partners. In Oslo winter, sun mode is
about daylight and mood, not vitamin D.

SLIDE 10: An agent, not just a map (Plans / Checks / Adapts, as before). Pluggable LLM providers with fallback.

SLIDE 11: Accuracy and update frequency
Sun position exact (within 0.5 deg of reference); shadows every 10 min on a 2 m grid; route timing every 5 min; weather
hourly; map data re-baked on demand (weekly job planned). Limits: 79% of Dubai heights estimated; trees/awnings only as
mapped; no field validation yet, so no accuracy percentage.

SLIDE 12: Security and privacy
No accounts, no stored user data, location per request only; per-IP rate limits, size caps, CORS allow-list, CSP/HSTS,
log scrubbing, key server-side. pip-audit clean; npm audit 2 findings (Next's PostCSS). PDPL/GDPR alignment is an aim, not
a certification; pen-test before B2B launch.

SLIDE 13: Who pays
Table: delivery fleets (targets Talabat, Deliveroo, Careem); hotels and tourism boards; outdoor-work employers; cities and
city planners (B2G planning analytics: where to plant trees or add shade); schools, elderly care, events, real estate;
corporate well-being and insurers. Prices are hypotheses, none quoted.

SLIDE 14: Freemium. No ads.
No ads because ads would put location into an ad pipeline. Free app; optional premium (saved routes, day plans); B2B and
B2G subscriptions as main revenue; pay-per-route API.

SLIDE 15: Costs to run
Server [TEAM TO FILL, Contabo price]; AI agent $10/month flat (OpenCode Go; about 3,630 conversations on glm-5.3-flash);
add a city $0 (Dubai data bake 7.5 s, shade bake 487.5 s); per 1,000 users [TEAM TO FILL]. Source: docs/COSTS.md.

SLIDE 16: How many users
Market (sourced): 70,000+ Dubai delivery riders; 18.72 million visitors in 2024. Capacity (measured): local machine 26.4
req/s at 20 users, p95 596 ms; live VM 16.9 req/s at 20 users, p95 1.6 s, 0 errors (capped at 20 users).

SLIDE 17: Closing and roadmap. No funding ask.
Headline: Zill & Shams. Team: Abhamzay, Team 13: Mohammed Hamza Ansari · Abhay Preethan. Try it: zill.itshamza.me
[Image: real still 12_the-ask.png]

Sources (put in small text on slide 3 or in speaker notes):
BMC Research Notes 2019, vitamin D in Abu Dhabi (n=12,346): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6693241/
Dubai RTA, delivery rider programmes (70,000+ riders): https://www.rta.ae/wps/portal/rta/ae/home/news-and-media/all-news/NewsDetails/23-temporary-rest-areas-to-protect-delivery-riders-from-heat-stress
Dubai DET via WAM, 18.72 million visitors in 2024: https://www.wam.ae/article/bi46kc8-dubai-welcomes-1872-million-international-visitors
MoHRE, Midday Break 2025: https://mohre.gov.ae/en/media-center/news/3/6/2025/mohre-to-implement-midday-break-for-the-21st-consecutive-year-from-15-june-to-15-september-2025
Oslo daylight at the December solstice (about 5 h 54 min): https://www.fjordtours.com/en/norway/people-and-culture/facts/winter-solstice

---
