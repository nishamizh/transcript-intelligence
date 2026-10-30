import type { QualityReport } from "@/lib/types";

const METRICS: { key: keyof Pick<QualityReport, "coverage" | "consistency" | "actionability" | "confidence">; label: string; detail: string }[] = [
  {
    key: "coverage",
    label: "Coverage",
    detail: "Themes assigned, stakeholders served, and meetings actually cited.",
  },
  {
    key: "consistency",
    label: "Consistency",
    detail: "Sentiment labels two ranks apart do not invert the score.",
  },
  {
    key: "actionability",
    label: "Actionability",
    detail: "A number, a reason, a recommendation, and a cited meeting.",
  },
  {
    key: "confidence",
    label: "Confidence",
    detail: "Sample size, the smallest call-type cell, and how much evidence each finding carries.",
  },
];

export function QualityPanel({
  quality,
  method,
}: {
  quality: QualityReport;
  method: Record<string, string>;
}) {
  return (
    <section id="quality" className="scroll-mt-24 space-y-8">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Quality</p>
        <h2 className="font-heading text-3xl text-balance">Score the briefing, not just the calls</h2>
        <p className="text-muted-foreground">
          Composite {Math.round(quality.composite * 100)}%. This checks whether the briefing is structured well enough to review. It is not a claim that every conclusion is right.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {METRICS.map((metric) => {
          const value = quality[metric.key];
          return (
            <div key={metric.key} className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
              <div className="flex items-baseline justify-between">
                <h3 className="font-medium">{metric.label}</h3>
                <span className="font-heading text-2xl tabular-nums">{Math.round(value * 100)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-[#8c4a2f]" style={{ width: `${value * 100}%` }} />
              </div>
              <p className="text-sm text-muted-foreground">{metric.detail}</p>
            </div>
          );
        })}
      </div>

      <ul className="max-w-3xl space-y-2 text-sm leading-6">
        {quality.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>

      <blockquote className="max-w-3xl border-l-2 border-[#8c4a2f] pl-4 text-sm leading-6">
        {quality.next_evolution}
      </blockquote>

      <div className="space-y-4">
        <h3 className="font-heading text-2xl">How this is built</h3>
        <dl className="grid gap-4 md:grid-cols-2">
          {Object.entries(method).map(([key, text]) => (
            <div key={key} className="space-y-1">
              <dt className="text-sm font-medium capitalize">{key}</dt>
              <dd className="text-sm leading-6 text-muted-foreground">{text}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
