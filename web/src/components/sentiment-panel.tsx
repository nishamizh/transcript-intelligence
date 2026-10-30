import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendChart } from "@/components/trend-chart";
import { callLabel, percentText, scoreText } from "@/lib/format";
import type { SentimentReport } from "@/lib/types";

const BAR: Record<string, string> = {
  support: "#9a3412",
  external: "#1e4d6b",
  internal: "#3d5a45",
};

export function SentimentPanel({ sentiment }: { sentiment: SentimentReport }) {
  return (
    <section id="sentiment" className="scroll-mt-24 space-y-6">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Sentiment</p>
        <h2 className="font-heading text-3xl text-balance">The score, cut by who was on the call</h2>
        <p className="text-muted-foreground">{sentiment.scale}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Mean score by call type</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {sentiment.by_call_type.map((row) => (
              <div key={row.call_type} className="space-y-1.5">
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span>
                    {callLabel(row.call_type)}{" "}
                    <span className="text-muted-foreground">· {row.count} calls</span>
                  </span>
                  <span className="font-heading text-lg tabular-nums">{scoreText(row.mean_score)}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${((row.mean_score - 1) / 4) * 100}%`,
                      background: BAR[row.call_type] ?? "#8c4a2f",
                    }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  n={row.count} meetings. {percentText(row.negative_share)} on the negative side of the source label.
                  Turn polarity, n={row.turn_count} turns: {percentText(row.sentence_mix.negative ?? 0)} negative,{" "}
                  {percentText(row.sentence_mix.positive ?? 0)} positive. Turn polarity is not the 1–5 score.
                </p>
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              Corpus mean {scoreText(sentiment.overall_mean)} across n={sentiment.overall_count} meetings.
              Bars start at 1, the bottom of the source scale. No new model score.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Week by week</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart weeks={sentiment.by_week} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Where the number comes from</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm leading-6">
            <p>{sentiment.provenance.meeting_score_source}</p>
            <p>{sentiment.provenance.meeting_label_source}</p>
            <p>{sentiment.provenance.turn_polarity_source}</p>
            <p>{sentiment.provenance.inferred_model_note}</p>
            <p className="text-muted-foreground">{sentiment.provenance.causal_claims}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Cohort size</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              Incident titles: n={sentiment.incident.count}, mean {scoreText(sentiment.incident.mean_score)}. Other meetings: n=
              {sentiment.incident.rest_count}, mean {scoreText(sentiment.incident.rest_mean)}.
            </p>
            <p>
              Outage mentions: n={sentiment.outage_mention.count}, mean {scoreText(sentiment.outage_mention.mean_score)}. The rest: n=
              {sentiment.outage_mention.rest_count}, mean {scoreText(sentiment.outage_mention.rest_mean)}.
            </p>
            <ul className="space-y-1 text-muted-foreground">
              {sentiment.by_month.map((month) => (
                <li key={month.period}>
                  {month.period}: n={month.count}, mean {month.mean_score == null ? "—" : scoreText(month.mean_score)}
                  {" · "}
                  support n={month.by_call_type_n.support ?? 0}, external n={month.by_call_type_n.external ?? 0}, internal n=
                  {month.by_call_type_n.internal ?? 0}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {sentiment.interpretations.map((note) => (
          <article key={note.interpretation_id} className="space-y-2 border-t border-border pt-4">
            <h3 className="font-heading text-xl text-balance">{note.title}</h3>
            <p className="text-sm leading-6">{note.finding}</p>
            <p className="text-sm leading-6 text-muted-foreground">{note.why_it_matters}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
