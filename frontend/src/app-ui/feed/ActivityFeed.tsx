// Shared agent activity timeline (PRD 12.6). Purely presentational: no fetching, no timers.
// Used by the /app agent panel and by the Film (which controls which events are visible).
import { colors } from "@/design/tokens";
import "./feed.css";
import {
  badgeFromEvents,
  badgeLabel,
  fmtOffset,
  FRESH_MS,
  mapEvents,
  type FeedRow,
} from "./mapEvents";
import type { FeedBadge, FeedProps } from "./types";

export type { AgentEvent, FeedBadge, FeedProps } from "./types";

export function SourceBadge({ badge }: { badge: FeedBadge }) {
  const tone = badge.source === "live" ? colors.oasis : colors.brass;
  return (
    <span
      className="smallcaps inline-block border px-2 py-[3px] text-[10px] leading-none"
      style={{ borderColor: `${tone}66`, color: tone, letterSpacing: "0.07em" }}
      data-testid="feed-badge"
      data-source={badge.source}
    >
      {badgeLabel(badge)}
    </span>
  );
}

function Row({ row, fresh, compact }: { row: FeedRow; fresh: boolean; compact: boolean }) {
  const secondary = row.kind === "result" || row.kind === "thought";
  const isMessage = row.kind === "message";
  return (
    <li
      className="zill-feed-row grid items-baseline gap-x-3"
      style={{
        gridTemplateColumns: "42px 8px 1fr",
        paddingBlock: compact ? 3 : row.kind === "result" ? 1 : 5,
        opacity: fresh ? 1 : undefined,
      }}
      data-kind={row.kind}
    >
      <span className="tabular text-right text-[10px] text-ivory/35">{fmtOffset(row.offsetMs)}</span>
      <span
        aria-hidden
        className="inline-block self-center"
        style={{
          width: row.kind === "result" ? 3 : 6,
          height: row.kind === "result" ? 3 : 6,
          marginInline: row.kind === "result" ? 1.5 : 0,
          borderRadius: "50%",
          background: row.marker,
        }}
      />
      <span className="min-w-0">
        {row.label ? (
          <span
            className="zill-feed-label mr-2 text-[12px]"
            style={{ color: row.kind === "tool" ? colors.sand : row.marker }}
          >
            {row.label}
          </span>
        ) : null}
        {row.text ? (
          <span
            className={[
              secondary ? "text-[12px] text-ivory/50" : "text-[13px] text-ivory/85",
              row.kind === "thought" ? "font-display italic text-ivory/55" : "",
              isMessage ? "leading-relaxed text-champagne" : "",
              row.failed ? "text-clay" : "",
              compact && isMessage ? "zill-feed-clamp" : "",
            ].join(" ")}
            style={fresh ? { color: colors.ivory } : undefined}
          >
            {row.text}
          </span>
        ) : null}
        {row.detail ? (
          <span className="ml-2 text-[12px] text-ivory/40">{row.detail}</span>
        ) : null}
      </span>
    </li>
  );
}

export function ActivityFeed({ events, badge, compact = false, now }: FeedProps) {
  const rows = mapEvents(events, compact);
  const b = badge ?? badgeFromEvents(events);
  return (
    <div data-testid="activity-feed">
      {b ? (
        <div className="mb-2">
          <SourceBadge badge={b} />
        </div>
      ) : null}
      <ol className="m-0 list-none p-0">
        {rows.map((r) => (
          <Row
            key={r.key}
            row={r}
            compact={compact}
            fresh={now !== undefined && Math.abs(now - r.offsetMs) <= FRESH_MS && now >= r.offsetMs}
          />
        ))}
      </ol>
    </div>
  );
}
