# Pivot plan: from "route through the shade" to "control your sun"

Status: **questions answered 2026-10-23, awaiting final go-ahead**. Decisions: name **Zill & Shams**
(Arabic: shade & sun); sun mode framed as **daylight and well-being**, vitamin D only with care; market figures
**researched with sources** ([TEAM TO FILL] only where no source exists); **no ask slide** (it is a hackathon). Nothing is recoded yet. After you approve this plan and answer the open
questions, I make (1) a Gamma prompt and (2) a PowerPoint deck. The code changes in section 6 are for a
later overnight session.

---

## 1. Where the project stands today (all real, all live)

- **Live product:** https://zill.itshamza.me. It redeploys itself within minutes of every push.
- **Engine on real open data:** the whole of Downtown Dubai from OpenStreetMap: 8,602 buildings,
  7,659 street segments and 744 trees. It computes where the sun's shadows fall every 10 minutes of the day.
- **Hero result (computed, not invented):** Burj Park → Business Bay Metro, summer, 15:30 walk.
  The coolest route takes **6.2 min less direct sun (−40%) for 2.2 extra minutes of walking**.
  A delivery rider's trip has 2.8 min less sun, and a work crew's shuttle walk 2.6 min less.
- **AI agent:** it plans with real tools, checks its own claims with a verifier, never invents a number,
  and replans when plans change. Today's sessions are scripted recordings because no live model key is set yet.
- **Film + app:** a 13-minute cinematic pitch film, the interactive app, plus fleet, crew and hotel views.
- **Quality:** 296 automated tests pass (222 engine + 74 frontend).

## 2. The new idea: one engine, two directions

Today the product only does one thing: *avoid* the sun. The new idea is that it **controls sun exposure
in both directions**:

| Mode | Who it is for | What the route optimises |
|---|---|---|
| **Shade** (today) | Hot cities: riders, workers, tourists, everyone in summer | least direct sun, coolest walk |
| **Sun** (new) | People who want more daylight: vitamin D, well-being, cold or dark winters | most direct sun or daylight on the way |

The engine already computes, for every street and every minute, how much of it is in sun. "Coolest"
minimises that number; "sunniest" maximises it. Technically the new mode is the same machinery with the
preference reversed. That makes it a credible pivot and not a rebuild, which is a good story for judges.

**New name: Zill & Shams** (ظل وشمس, "shade and sun"). It keeps the Dubai roots and names both
directions. The name stays in one config file, so changing it is a one-line change.

## 3. Honesty checks (these protect you in front of judges)

1. **Vitamin D only works when the sun is high.** The skin makes vitamin D from UVB light, which is weak
   when the sun is low in the sky. A common rule of thumb: if your shadow is longer than you are, you make
   little vitamin D. In Oslo or Toronto in December the sun stays very low, so a sunny route there helps
   **daylight, mood and well-being, not vitamin D**. The vitamin D story fits best in **sunny places where
   people avoid the sun**, like the Gulf, and in spring and summer up north. I will frame the deck this way
   and recommend you do too.
2. **Medical claims.** Position it as **well-being, not treatment**: "helps you get daylight safely",
   never "treats vitamin D deficiency". Add "not medical advice" and suggest working with clinicians as a
   future step.
3. **The far north in deep winter.** Oslo has about 6 hours of daylight in December, which matches what
   you said. Places like Tromsø have no sun at all for weeks (polar night). There the sun mode has nothing
   to work with, so we say so.
4. **Real company names.** Talabat, Deliveroo and Careem appear as **target customers**, never as
   partners or clients, unless that is true.
5. **Market numbers.** No invented statistics. Either I research real figures with sources (question 3),
   or they stay as visible `[TEAM TO FILL]` tags.

## 4. Business case (the core of the deck)

**Problem.** People cannot see or plan their sun exposure. In hot cities it is a heat and safety problem.
In dark or cold seasons it is a lack-of-daylight problem. Maps optimise only time and distance.

**Customers and what they buy** (prices are hypotheses to validate):

| Segment | Pain | Product | Revenue model |
|---|---|---|---|
| Delivery & quick-commerce fleets (e.g. Talabat, Deliveroo, Careem, Noon as targets) | rider heat stress, heat-illness incidents, lost productivity | heat-aware routing + shift pacing API, fleet dashboard | per active rider / month or per API call |
| Hotels & tourism boards | guests avoid walking in heat, taxis for short hops are costly and slow to book | "walk in the shade or sun" concierge widget, white-label | per property / month; tourism-board licence |
| Employers of outdoor workers | heat illness, compliance with the UAE midday work break | crew shift planner with policy checks | per site / month |
| Corporate well-being & insurers (new) | employee well-being, daylight-poor winters | "daylight walks" programme + reports | per employee / year |
| Cold and dark cities (new: Nordics, Canada) | short winter days, low mood | sunniest-route mode in the consumer app, city partnerships | city licence; free consumer app |
| Individuals | comfort, health | free app (acquisition + data) | free |

**Why us:**
1. It is real: computed shadows from open data, not a static "shady streets" list.
2. It is time-aware, because shade moves every minute.
3. It runs on an AI agent that plans, checks itself and replans.
4. It works for any city: open data in, any city out.
5. It works in both directions: heat and daylight are one product.

**Go-to-market:** start with Dubai (hot climate and a dense delivery market), with a pilot with one
fleet and one hotel. Then other UAE and Gulf cities, then a winter "sun mode" pilot in one northern city.

No funding ask (it is a hackathon); the deck closes on the vision and the team.

## 5. The deck (Gamma prompt and my own PowerPoint follow this outline)

Business-first, easy to read, the same look as the film: dark ink background, warm stone and brass,
Fraunces serif headings, real stills from the 3D film. About 12–14 slides:

1. Title: Zill & Shams, with a tagline such as "Shade when you need it. Sun when you want it."
2. The problem: heat in hot cities, daylight-poor winters
3. The insight: sun and shade move every minute; maps ignore them
4. The product: one engine, two modes (Shade / Sun)
5. How it works, simply: open data → 3D city → sun & shadow → best route → AI agent (one picture)
6. Proof it is real: the Dubai hero result and the live link
7. The AI agent: plans, checks itself, replans (honest note: live model being connected)
8. Who pays: the customer table above
9. Use cases: rider, hotel guest, office worker in the Gulf, winter walker in the north
10. Business model + pricing hypotheses
11. Go-to-market + roadmap (Dubai → Gulf → northern pilot)
12. Traction / validation so far (tests, live site; field test pending)
13. Closing: vision + team (Abhamzay, Team 13: Mohammed Hamza Ansari · Abhay Preethan)
14. Appendix: technical summary and honest limits

## 6. Engineering plan for the overnight recoding session (not now)

1. **Rename:** a single brand file on each side (`brand.ts` / `brand.py`), then copy, film titles and the domain.
2. **Sun mode:** reverse the preference so the router finds the sunniest route; app toggle "Shade ⇄ Sun";
   new agent persona ("daylight seeker").
3. **UV and clouds:** sunny routes only matter when the sun is out. Add cloud cover and a
   UV-index-aware "vitamin D window" indicator, worded carefully and labelled "not medical advice".
4. **A second, northern city:** bake Oslo (or Toronto) with the same pipeline. Check that very low
   winter sun angles behave correctly (long shadows), and add a test.
5. **Film:** update the chapter titles, add a "two directions" chapter, a winter-city chapter and the new business slides.
6. **Hero scenarios:** let the search pick the best real "sunniest walk" examples, as it already does for shade.
7. **Docs, tests and deploy:** every change ships automatically through the existing CD.

## 7. Deliverables after approval

- `docs/pitch/GAMMA_PROMPT.md`: a single prompt to paste into Gamma, with slide-by-slide notes.
- `docs/pitch/<name>_pitch.pptx`: a deck I build myself in the project theme, using the real film
  stills. I check it visually, then send it to you.
- Both use the same outline (section 5) and the same honest numbers.
