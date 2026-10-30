import { EvaluationPanel, type HumanValidationReport } from "@/components/evaluation-panel";
import { MeetingsPanel } from "@/components/meetings-panel";
import { MethodologyPanel } from "@/components/methodology-panel";
import { QualityPanel } from "@/components/quality-panel";
import { ReviewerPanel } from "@/components/reviewer-panel";
import { SentimentPanel } from "@/components/sentiment-panel";
import { StakeholderPanel } from "@/components/stakeholder-panel";
import { TopicsPanel } from "@/components/topics-panel";
import { callLabel, formatDay, formatGenerated, scoreText } from "@/lib/format";
import type { Report } from "@/lib/types";
import reportJson from "@/data/report.json";
import validationJson from "@/data/human_validation_report.json";

const report = reportJson as unknown as Report;
const validation = validationJson as unknown as HumanValidationReport;

const NAV = [
  ["briefing", "Briefing"],
  ["sentiment", "Sentiment"],
  ["topics", "Topics"],
  ["stakeholders", "Stakeholders"],
  ["meetings", "Meetings"],
  ["methodology", "Methodology"],
  ["evaluation", "Evaluation"],
  ["review", "Review"],
  ["quality", "Quality"],
] as const;

export default function Page() {
  const { dataset, sentiment, quality, insights } = report;
  const byType = Object.fromEntries(sentiment.by_call_type.map((row) => [row.call_type, row]));
  const risk = insights.find((insight) => insight.insight_id === "sales-at-risk");
  const kpis = [
    ["Meetings", String(dataset.meeting_count), `${formatDay(dataset.start_date)} – ${formatDay(dataset.end_date)}`],
    ["Support", byType.support ? scoreText(byType.support.mean_score) : "—", byType.support ? `${byType.support.count} calls` : ""],
    ["External", byType.external ? scoreText(byType.external.mean_score) : "—", byType.external ? `${byType.external.count} calls` : ""],
    ["At-risk accounts", risk?.metric_value ?? "—", "Churn language on a recording"],
    ["Briefing quality", `${Math.round(quality.composite * 100)}%`, "Structure, not market truth"],
  ];

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <a href="#briefing" className="font-heading text-lg">
            Transcript Intelligence
          </a>
          <nav aria-label="Briefing sections" className="flex gap-4 overflow-x-auto text-sm">
            {NAV.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="shrink-0 text-muted-foreground hover:text-foreground">
                {label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-16 px-4 py-10">
        <section id="briefing" className="scroll-mt-24 space-y-8">
          <div className="max-w-3xl space-y-4">
            <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">
              Aegis Cloud · {formatDay(dataset.start_date)} – {formatDay(dataset.end_date)}
            </p>
            <h1 className="font-heading text-4xl leading-tight text-balance md:text-5xl">{report.headline}</h1>
            <p className="text-lg leading-7 text-muted-foreground">{report.subhead}</p>
            <p className="text-xs text-muted-foreground">
              Pipeline run {formatGenerated(report.generated_at)} Pacific time · {dataset.topic_model} ·{" "}
              {dataset.load_failures} load failures
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {kpis.map(([label, value, note]) => (
              <div key={label} className="rounded-xl bg-card px-3 py-3 ring-1 ring-foreground/10">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="font-heading text-3xl tabular-nums">{value}</dd>
                <dd className="text-xs text-muted-foreground">{note}</dd>
              </div>
            ))}
          </dl>

          <ol className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
            {[
              ["Ingest", "One folder becomes one meeting."],
              ["Canonical model", "Every analyzer reads the same object."],
              ["Pluggable engines", "Topics, sentiment, and insights share a contract."],
              ["Stakeholder views", "Support, product, engineering, sales."],
              ["This briefing", "A consumer of report.json, not of the raw files."],
            ].map(([title, text], index) => (
              <li key={title} className="border-t border-border pt-3">
                <p className="text-xs text-muted-foreground">0{index + 1}</p>
                <p className="font-medium">{title}</p>
                <p className="text-muted-foreground">{text}</p>
              </li>
            ))}
          </ol>

          <p className="text-sm text-muted-foreground">
            Call mix:{" "}
            {Object.entries(dataset.call_types)
              .map(([name, count]) => `${callLabel(name)} ${count}`)
              .join(" · ")}
            . Scores are the 1–5 values shipped with each summary.
          </p>
        </section>

        <SentimentPanel sentiment={sentiment} />
        <TopicsPanel topics={report.topics} />
        <StakeholderPanel insights={insights} />
        <MeetingsPanel meetings={report.meetings} themes={report.topics.themes} />
        <MethodologyPanel methodology={report.methodology} />
        <EvaluationPanel validation={validation} />
        <ReviewerPanel queue={report.review_queue} themes={report.topics.themes} />
        <QualityPanel quality={quality} method={report.method} />
      </main>
    </>
  );
}
