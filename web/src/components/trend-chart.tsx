import { callLabel, scoreText } from "@/lib/format";
import type { PeriodSentiment } from "@/lib/types";

function segments(
  values: (number | null)[],
  x: (index: number) => number,
  y: (value: number) => number,
): string[] {
  const parts: string[] = [];
  let current: string[] = [];
  values.forEach((value, index) => {
    if (value == null) {
      if (current.length > 0) parts.push(current.join(" "));
      current = [];
      return;
    }
    current.push(`${x(index)},${y(value)}`);
  });
  if (current.length > 0) parts.push(current.join(" "));
  return parts;
}

const COLORS: Record<string, string> = {
  all: "#1c1915",
  support: "#9a3412",
  external: "#1e4d6b",
  internal: "#3d5a45",
};

export function TrendChart({ weeks }: { weeks: PeriodSentiment[] }) {
  const width = 720;
  const height = 240;
  const pad = { left: 36, right: 12, top: 16, bottom: 42 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const min = 1;
  const max = 5;
  const y = (value: number) => pad.top + ((max - value) / (max - min)) * innerH;
  const x = (index: number) =>
    pad.left + (weeks.length <= 1 ? innerW / 2 : (index / (weeks.length - 1)) * innerW);

  const series: { key: string; values: (number | null)[] }[] = [
    { key: "all", values: weeks.map((week) => week.mean_score) },
    { key: "support", values: weeks.map((week) => week.by_call_type.support ?? null) },
    { key: "external", values: weeks.map((week) => week.by_call_type.external ?? null) },
    { key: "internal", values: weeks.map((week) => week.by_call_type.internal ?? null) },
  ];

  return (
    <figure className="space-y-3">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" className="h-auto w-full">
        <title>Weekly mean sentiment by call type</title>
        {[1, 2, 3, 4, 5].map((tick) => (
          <g key={tick}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="#e6dfd4"
            />
            <text x={pad.left - 8} y={y(tick) + 4} textAnchor="end" fontSize="11" fill="#5c564e">
              {tick}
            </text>
          </g>
        ))}
        {series.map((line) =>
          segments(line.values, x, y).map((points, index) => (
            <polyline
              key={`${line.key}-${index}`}
              fill="none"
              stroke={COLORS[line.key]}
              strokeWidth={line.key === "all" ? 2.4 : 1.4}
              strokeLinejoin="round"
              strokeLinecap="round"
              points={points}
            />
          )),
        )}
        {weeks.map((week, index) => (
          <text
            key={week.period}
            x={x(index)}
            y={height - 16}
            textAnchor="end"
            fontSize="10"
            fill="#5c564e"
            transform={`rotate(-40 ${x(index)} ${height - 16})`}
          >
            {week.period.slice(5)}
          </text>
        ))}
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((line) => (
          <span key={line.key} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-4 rounded-sm" style={{ background: COLORS[line.key] }} />
            {line.key === "all" ? "All calls" : callLabel(line.key)}
            {line.key === "all" && weeks.some((week) => week.mean_score != null)
              ? ` · low ${scoreText(Math.min(...weeks.flatMap((week) => (week.mean_score == null ? [] : [week.mean_score]))))}`
              : ""}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
