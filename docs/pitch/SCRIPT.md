# Zill & Shams: 15-minute pitch script

**Cast:** Abhay (business lead), Hamza (technical lead). Swap lines freely; keep the timings.
**Screen:** https://zill.itshamza.me/film (6:45, scroll or press Space to play; arrow keys jump chapters).
Live demo: https://zill.itshamza.me/app. Backup: pendrive `E:\ZillShams-backup` (PDF deck, PPTX, backup videos).

| Clock | Part | Screen |
|---|---|---|
| 0:00–1:30 | Skit | Film paused on the title (dark skyline) |
| 1:30–8:15 | Pitch over the film | /film playing |
| 8:15–11:00 | Live demo: app + AI agent | /app |
| 11:00–11:30 | Close | /film "Try it" frame |
| 11:30–15:00 | Judge Q&A | /app open as backup |

Every number below comes from the engine or a cited source (docs/COSTS.md, docs/SECURITY.md,
data/scenarios/case_studies.json, hero.json). Do not round them up.

---

## 1. Skit (0:00–1:30)

*Hamza plays a tourist with a backpack, squinting. Abhay is the hotel receptionist.*

**Tourist (Hamza):** Hi! Could you book me a taxi to The Dubai Mall, please?

**Receptionist (Abhay):** Of course. That will be about fifty dirhams.

**Tourist:** Fifty? For the mall? It's a ten-minute walk, I can see it from here.

**Receptionist:** It is July, sir. It's over forty degrees out there.

**Tourist:** I came here to see the city, not the inside of a taxi. Everything is walking distance if you
put your mind to it.

**Receptionist:** Then put your phone to it. *(points to a QR code on the desk)* Scan this. It shows you
the walk that keeps you in the shade, right now, minute by minute. And if you were in Oslo in December,
it would do the opposite: find you the sun.

**Tourist:** *(scans, smiles)* Shade when I need it...

**Both, stepping forward, out of character:** ...sun when you want it.

**Hamza:** That QR code is our product. We are Abhay and Hamza, and this is **Zill & Shams**:
"shade and sun" in Arabic. An AI agent that plans every walk, run and ride around the sun.

*(Press Space: film starts.)*

---

## 2. Pitch over the film (1:30–8:15)

### Film 0:00–0:25 · "Zill & Shams" (Abhay)
- Maps optimise time and distance. Nobody plans around the sun.
- In Dubai that is a safety problem: the average July high at Dubai Airport is 41.5 °C (NOAA normals).
  In Oslo it is the opposite problem: about 6 hours of daylight in late December.

### Film 0:25–0:55 · "Shade moves" (Hamza) · TECHNICAL
- The key insight: shade is not a place, it is a time. Every building's shadow sweeps across the street all day.
- So a static "shady streets" list is wrong within minutes. We compute where every shadow falls,
  every 10 minutes, on a 2-metre grid.

### Film 0:55–1:30 · "A city, built in seconds" (Hamza) · TECHNICAL
- Built from open data: OpenStreetMap buildings, streets and trees, the exact sun position (pvlib),
  and live weather from Open-Meteo.
- Downtown Dubai: 8,602 buildings, 744 trees. We added Oslo overnight with the same pipeline:
  13,841 buildings, 10,082 street segments, 20,208 trees. No city-specific code: any city with map data.

### Film 1:30–2:10 · "Two directions" (Abhay)
- One engine, two modes. **Shade mode** for heat. **Sun mode** for daylight and well-being.
- The router simply flips the preference: least direct sun, or most direct sun.

### Film 2:10–4:25 · "Case studies" (Abhay, Hamza adds the tech note at the end)
- **Hotels → their guests.** Address Sky View to The Dubai Mall at 16:00 in July: the shade walk cuts direct sun
  by 40% for 2.8 extra minutes. A walk instead of a fifty-dirham cab. The hotel gets a happier guest.
- **Responsible employers → their riders.** Companies like Talabat or Noon are exactly who we want to sell to
  (targets, not partners yet). For a rider at 14:00 in July, the shade route cuts sun 11% on one short trip.
  Small per trip, it adds up across a shift, and it is honest: we show what the engine finds.
- **Winter cities → residents.** Oslo, 21 December, Akershus Fortress to Oslo S: 13.5 more minutes of sun
  for 4.3 extra minutes. That is daylight and mood, not vitamin D: the sun is only 6 degrees high, and we say so.
- **Running clubs.** Dubai at 06:30, a 5.8 km loop: 71% less direct sun. Oslo winter lunch run:
  12.4 more minutes of sun.
- *(Hamza)* Every number on screen comes from the engine. None are typed in by hand.

### Film 4:25–5:10 · "An agent, not a map" (Hamza) · TECHNICAL, the core of the AI part
- Zill is not a route button. It is an **agent**: you say "I'm walking to the metro and I tire easily in
  the heat", and it plans.
- **Planner:** a language model chooses from **13 real tools**: find places, compare routes, find cool stops,
  optimise departure time, plan a day, check the sun and the weather.
- **Verifier:** a second check reads the answer and rejects any number that did not come from a tool.
  Numbers are inserted from tool results, so the model cannot invent a statistic.
- **Autonomy, with consent:** three levels. It suggests, it plans, or on autopilot it watches your trip.
  If you are delayed or a heat alert comes in, it replans, and it asks before it changes your plan. Every action can be undone.
- **Models:** provider-agnostic. Today it runs live on Google Gemini Flash with automatic fallback between
  models and providers, and replays labelled as recordings if the model is down.

### Film 5:10–5:50 · "Who pays" (Abhay) · MANAGERIAL
- **Free for people, no ads.** We never sell location, so ads are off the table.
- **B2B pays** (pricing hypotheses we are testing):
  hotels about $99 per property per month; delivery fleets about $1 per rider per month;
  outdoor employers about $49 per site per month; corporate well-being about $12 per employee per year;
  city and tourism licences about $15,000 per year. Consumer premium about $2.99 per month.
- **Market:** more than 70,000 delivery riders in Dubai (RTA); 19.59 million visitors to Dubai in 2025;
  over 154,000 hotel rooms. Plus municipalities planning where to plant trees and add shade.

### Film 5:50–6:25 · "Safe and cheap to run" (Hamza) · TECHNICAL RISK
- **Privacy by design:** no accounts, location used only to compute the route and never stored or logged,
  the AI key stays on the server. UAE PDPL and GDPR alignment is our aim.
- **Security:** rate limits, input limits, strict security headers, 16 security tests.
- **Cost:** about $17 a month today ($6.93 server + $10 AI). One small server handled 20 users at once with
  zero errors in our live test. Adding a city costs no money: open data, and minutes of compute.

### Film 6:25–6:45 · "Try it" (Abhay)
- Go-to-market: Dubai first, one hotel and one delivery fleet as pilots; then the Gulf; then a winter
  daylight pilot up north. The product is already live at zill.itshamza.me.
- "Let us show you." *(switch to /app)*

---

## 3. Live demo (8:15–11:00) · Hamza drives, Abhay narrates

1. **/app, Dubai.** Click **Summer** in the time bar first (the numbers below are for 15 July). Then type in the top bar: `from Burj Park to Business Bay Metro at 15:30`. Three routes appear:
   fastest, balanced, coolest. Point at the numbers: 6.2 minutes less direct sun (40%) for 2.2 extra minutes.
2. **Drag the time bar:** shadows sweep across the street. "This is why it has to be computed live."
3. **Toggle Sun.** The well-being card: UV level, heat stress, the daylight window, "not medical advice".
4. **Switch to Oslo** (top-left). Winter, Sun mode: long December shadows, the sunniest walk.
5. **Agent panel** (press A or click Agent). Type: `I'm walking from Burj Park to the metro, I tire easily in the heat`.
   Narrate as it works: "It is calling tools... comparing routes... the verifier is checking every number...
   now it asks me to approve." Approve.
   - **If the live model is slow** (free tier, about 10 requests a minute): open a recorded session from the
     agent panel's list. It is labelled "Recorded session"; say so.

---

## 4. Close (11:00–11:30) · Abhay
- "Heat is getting worse, winters are still dark, and maps still ignore the sun. Zill & Shams is a working
  agent, on real data, live today, for about $17 a month. We are looking for our first hotel and our first
  fleet pilot. Thank you."

---

## 5. Judge Q&A (11:30–15:00), about 30 seconds per answer

**Q1 (technical): How accurate are the shadows?**
Hamza: The sun position matches the reference solar model within half a degree, and the shadow geometry
is unit-tested, including Oslo's 6-degree winter sun. The weak spot is building heights: about 79% of
Dubai's buildings have no height in OpenStreetMap, so we use typical heights by building type. Next step is a
field test with a light sensor on our hero routes. We make no accuracy percentage claim until then.

**Q2 (technical): Is the AI actually doing anything, or is it a wrapper?**
Hamza: The model decides which of 13 tools to call and in what order, and it can replan. But it never does the
maths. The engine computes, the model plans and explains, and a verifier blocks any number that did not come
from a tool. That split is what makes it reliable.

**Q3 (technical): What if the model hallucinates or goes down?**
Hamza: Numbers are filled in from tool results, never typed by the model, and the verifier rejects unsupported claims.
If a provider fails we fall back to another model or provider automatically; if all are down, the routes still
work without the agent.

**Q4 (technical): Does it scale?**
Hamza: The heavy work, the shadows, is precomputed per city and day and cached; routing is a fast graph search.
One worker handled about 26 requests per second locally; we scale by adding workers. A new city is an
automated bake from open data.

**Q5 (privacy): You handle location. Why should anyone trust you?**
Abhay: We don't keep it. No accounts, no location stored or logged, and no ads, so there is no one to sell it to.
B2B dashboards later get per-tenant keys. Security controls are tested in our suite.

**Q6 (managerial): Who pays first, and why would they?**
Abhay: Hotels: it turns "too hot to walk" into a concierge feature guests use at the door, for about $99 a month.
Delivery fleets: rider heat safety is a real duty in the UAE summer, and this is a cheap, measurable tool.

**Q7 (managerial): Your rider saving is only 11%. Is that worth paying for?**
Abhay: It's per trip, and we chose to show the honest number. Over a full shift in July those minutes
add up, and the departure optimiser and break prompts add more. Fleets also buy the reporting: heat exposure per rider.

**Q8 (managerial): Google Maps could add this tomorrow.**
Abhay: Maybe, but they optimise for time, and their model is ads. Ours is computed shade, both directions,
an agent that plans around your day, and privacy with no ads. We go where they don't sell: hotels, fleets, cities.

**Q9 (managerial): How do you make money from individuals if it's free?**
Abhay: Mostly we don't, by design. Individuals give us reach. A small premium (saved routes, day plans)
is optional. Revenue is B2B subscriptions and city licences.

**Q10 (well-being): Are you making medical claims about vitamin D?**
Abhay: No. We say "well-being, not medical advice". We only show a daylight or vitamin D window when the sun is
high enough and UV is at least 3. In Oslo in December we say clearly it's about daylight and mood, not vitamin D.

**Q11 (team): Can two people execute this?**
Hamza: We built the engine, two cities, the agent, the app and this film, with 480 automated tests and a
live deployment. Next we need one pilot partner and one field test, not a big team.

### Pacing notes
- If the skit runs long, drop the Oslo line in the skit.
- If the film is behind, skip "Safe and cheap to run" with the arrow key and cover it in one sentence.
- Hard stop for the demo at 11:00 even if the agent is mid-run: switch to the recorded session.
