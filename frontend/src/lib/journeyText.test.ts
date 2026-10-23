import { describe, expect, it } from "vitest";
import { looksLikeJourney } from "./journeyText";

describe("looksLikeJourney", () => {
  it("recognises one-line journeys", () => {
    for (const t of [
      "from Burj Park to Dubai Mall",
      "Burj Park to Dubai Mall at 15:30",
      "Oslo S → Aker Brygge",
      "Oslo S -> Aker Brygge sunny",
      "Opera - Rådhuset",
      "من برج خليفة إلى دبي مول",
    ])
      expect(looksLikeJourney(t)).toBe(true);
  });
  it("leaves single place searches alone", () => {
    for (const t of ["Dubai Mall", "burj", "Aker Brygge", "Al-Manzil", "to", ""])
      expect(looksLikeJourney(t)).toBe(false);
  });
});
