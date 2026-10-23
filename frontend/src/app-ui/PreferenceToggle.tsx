"use client";
// Shade <-> Sun segmented control (restrained: hairline frame, the active side filled with its
// palette colour - shade #22333A / ember #D07A35 - no glow). Re-routes when A and B are set.
import { PREFERENCES } from "@/lib/preference";
import { useRoute } from "@/state/route";

export function PreferenceToggle() {
  const pref = useRoute((s) => s.preference);
  const setPreference = useRoute((s) => s.setPreference);
  const cur = PREFERENCES.find((p) => p.id === pref) ?? PREFERENCES[0]!;
  return (
    <div data-testid="preference-toggle">
      <div
        role="radiogroup"
        aria-label="Route preference"
        className="flex border border-[color:var(--zill-hairline)]"
      >
        {PREFERENCES.map((p) => {
          const on = pref === p.id;
          return (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setPreference(p.id)}
              title={p.hint}
              className={`flex-1 px-3 py-1.5 text-[13px] tracking-wide transition-colors ${
                on ? "text-ivory" : "text-ivory/55 hover:text-ivory/85"
              }`}
              style={on ? { background: p.color } : undefined}
            >
              {p.label}
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 text-[11px] text-ivory/45">{cur.hint}</p>
    </div>
  );
}
