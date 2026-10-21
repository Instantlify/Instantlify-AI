"use client";

import { useState } from "react";

const WIDTH = 240;
const HEIGHT = 56;
const PAD = 4;

/** A single-series trend line for a stat tile. Each day has a hover/focus target
 * that reads its exact value out below the line. */
export function Sparkline({
  points,
  label,
  format = String,
}: {
  points: { date: string; value: number }[];
  label: string;
  format?: (value: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (!points.length) return null;
  const max = Math.max(1, ...points.map((point) => point.value));
  const step = points.length > 1 ? (WIDTH - PAD * 2) / (points.length - 1) : 0;
  const x = (index: number) => PAD + index * step;
  const y = (value: number) =>
    HEIGHT - PAD - (value / max) * (HEIGHT - PAD * 2);
  const line = points
    .map((point, index) => `${x(index)},${y(point.value)}`)
    .join(" ");
  const area = `${PAD},${HEIGHT - PAD} ${line} ${x(points.length - 1)},${HEIGHT - PAD}`;
  const day = (date: string) =>
    new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  const shown = hover ?? points.length - 1;
  return (
    <figure className="sparkline">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${label}: ${points
          .map((point) => `${day(point.date)} ${format(point.value)}`)
          .join(", ")}`}
        onMouseLeave={() => setHover(null)}
      >
        <line
          x1={PAD}
          x2={WIDTH - PAD}
          y1={HEIGHT - PAD}
          y2={HEIGHT - PAD}
          className="sparkline-base"
        />
        <polygon points={area} className="sparkline-area" />
        <polyline points={line} className="sparkline-line" />
        {hover !== null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={PAD}
            y2={HEIGHT - PAD}
            className="sparkline-cross"
          />
        )}
        <circle
          cx={x(shown)}
          cy={y(points[shown].value)}
          r={4}
          className="sparkline-dot"
        />
        {points.map((point, index) => (
          <rect
            key={point.date}
            x={x(index) - Math.max(step, 8) / 2}
            y={0}
            width={Math.max(step, 8)}
            height={HEIGHT}
            fill="transparent"
            onMouseEnter={() => setHover(index)}
          />
        ))}
      </svg>
      <figcaption>
        {day(points[shown].date)} ·{" "}
        <strong>{format(points[shown].value)}</strong>
      </figcaption>
    </figure>
  );
}
