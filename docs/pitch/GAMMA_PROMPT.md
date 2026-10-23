# Gamma prompt: Zill & Shams pitch deck

Paste everything between the two lines below into Gamma ("Paste in text" → Presentation, 13 cards).
Recommended Gamma settings: theme **dark / elegant** (or a custom one with the colours below), image style
**photographic / architectural**, text density **brief**. Then replace the AI images on slides 1, 4, 5 and 6
with the real stills from `docs/deck_assets/stills/` (file names given per slide).

---

Create a 13-slide pitch deck for hackathon judges. The audience is business-minded; keep it easy to read, with no
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

SLIDE 8: Who pays
A clean table with 5 rows (segment / what they get / how they pay):
- Delivery fleets (targets such as Talabat, Deliveroo, Careem): heat-aware routes and shift pacing for riders /
  per rider per month.
- Hotels and tourism boards: "walk there in the shade, or in the sun" guest concierge, so guests walk short distances
  instead of booking a cab / per hotel per month.
- Employers of outdoor workers: shift planner that respects the midday break / per site per month.
- Corporate well-being and insurers: daylight-walk programmes for staff / per employee per year.
- Cities with dark winters (Nordics, Canada): sunniest-route mode for residents / city licence.
Footer: Free for individuals, which builds reach and data. Prices are hypotheses we are validating.

SLIDE 9: Four people, one product
Four small cards:
- Rider in Dubai, July 14:00: the coolest route, plus a rest stop in air conditioning.
- Hotel guest at Burj Park: a 25-minute walk in the shade instead of a cab.
- Office worker in Dubai, winter: a 15-minute sunny walk at lunch for daylight.
- Resident of Oslo, December: the sunniest path during the few daylight hours.
Small note: Sun mode is about daylight and well-being, not medical advice.

SLIDE 10: Business model
- B2B software subscriptions (fleets, hotels, employers) as the main revenue.
- A pay-per-route API for delivery and mobility apps.
- City and tourism-board licences.
- A free consumer app for reach.
Line: Low cost to add a city: it is built from open data automatically.

SLIDE 11: Go-to-market and roadmap
A three-step timeline:
1) Dubai: a pilot with one delivery fleet and one hotel. The prototype is already live.
2) UAE and Gulf: Abu Dhabi, Doha, Riyadh; the sun mode for winter well-being.
3) Northern cities: a winter daylight pilot in a city like Oslo or Toronto.
[Image: real still 11_any-hot-city.png, dark globe with brass city points]

SLIDE 12: What already works
- A live prototype at zill.itshamza.me: 3D city, shade engine, routing and an AI agent.
- Real data for Downtown Dubai and real sun calculations; 296 automated tests pass.
- Honest limits: shade comes from buildings and mapped trees; field measurements are the next step.
[Image: real still 05_the-shade-engine.png]

SLIDE 13: Closing
Headline: Zill & Shams
Line: Shade when you need it. Sun when you want it.
Team: Abhamzay: Mohammed Hamza Ansari · Abhay Preethan
Small: Try it: zill.itshamza.me
[Image: Burj Khalifa at golden hour with long shadows. Real still: 12_the-ask.png]

Sources (put in small text on slide 3 or in speaker notes):
BMC Research Notes 2019, vitamin D in Abu Dhabi (n=12,346): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6693241/
Dubai RTA, delivery rider programmes (70,000+ riders): https://www.rta.ae/wps/portal/rta/ae/home/news-and-media/all-news/NewsDetails/23-temporary-rest-areas-to-protect-delivery-riders-from-heat-stress
Dubai DET via WAM, 18.72 million visitors in 2024: https://www.wam.ae/article/bi46kc8-dubai-welcomes-1872-million-international-visitors
MoHRE, Midday Break 2025: https://mohre.gov.ae/en/media-center/news/3/6/2025/mohre-to-implement-midday-break-for-the-21st-consecutive-year-from-15-june-to-15-september-2025
Oslo daylight at the December solstice (about 5 h 54 min): https://www.fjordtours.com/en/norway/people-and-culture/facts/winter-solstice

---
