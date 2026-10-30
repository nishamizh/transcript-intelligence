import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { callLabel, percentText, scoreText } from "@/lib/format";
import type { TopicExemplar, TopicReport } from "@/lib/types";

export function TopicsPanel({ topics }: { topics: TopicReport }) {
  const comparison = topics.comparison;
  const stats = [
    ["Raw labels", String(comparison.unique_provided_labels)],
    ["Used once", percentText(comparison.hapax_share)],
    ["Theme coverage", percentText(comparison.governed_coverage)],
    ["Labels mapped", percentText(comparison.label_mapping_coverage)],
    ["Cluster purity", percentText(comparison.weighted_purity)],
    ["Lexical overlap", percentText(comparison.mean_jaccard)],
  ];

  return (
    <section id="topics" className="scroll-mt-24 space-y-6">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Topics</p>
        <h2 className="font-heading text-3xl text-balance">Publish a taxonomy. Audit it with a model that has not seen the labels.</h2>
        <p className="text-muted-foreground">
          Provided topic strings are evidence. The categories below are a governed map of those strings.
          The second column is {topics.model_name}, fit on summaries and transcripts with those labels held out.
          Lexical overlap is a word comparison, not classification accuracy.
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-card px-3 py-3 ring-1 ring-foreground/10">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-heading text-2xl tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Governed themes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {topics.themes
              .filter((theme) => theme.meeting_count > 0)
              .sort((a, b) => b.meeting_count - a.meeting_count)
              .map((theme) => (
                <div key={theme.theme_id} className="space-y-2 border-b border-border pb-4 last:border-0 last:pb-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <h3 className="font-medium">{theme.name}</h3>
                    <span className="text-sm tabular-nums text-muted-foreground">
                      {theme.meeting_count} · {scoreText(theme.mean_sentiment)}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{theme.description}</p>
                  {topics.topic_examples.examples
                    .filter((example) => example.assigned_theme === theme.theme_id)
                    .map((example) => (
                      <Example key={example.meeting_id} example={example} />
                    ))}
                </div>
              ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Generated topics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {topics.generated.map((topic) => (
              <div key={topic.topic_id} className="space-y-2 border-b border-border pb-4 last:border-0 last:pb-0">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="font-medium">{topic.label}</h3>
                  <span className="text-sm tabular-nums text-muted-foreground">
                    n={topic.meeting_count} · source {scoreText(topic.mean_sentiment)}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {topic.terms.map((term) => (
                    <Badge key={`${topic.topic_id}-${term}`} variant="secondary">
                      {term}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3">
        {comparison.commentary.map((paragraph) => (
          <p key={paragraph.slice(0, 48)} className="max-w-3xl text-sm leading-6">
            {paragraph}
          </p>
        ))}
      </div>

      <div className="space-y-3">
        <h3 className="font-heading text-xl">No shared words</h3>
        <p className="max-w-3xl text-sm text-muted-foreground">
          {topics.topic_examples.lexical_overlap_note}
        </p>
        <ul className="grid gap-3 md:grid-cols-2">
          {comparison.disagreements.map((meeting) => (
            <li key={meeting.meeting_id} className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
              <p className="text-sm font-medium">{meeting.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {callLabel(meeting.call_type)} · {meeting.date} · {scoreText(meeting.sentiment_score)}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{meeting.provided_topics.join(" · ")}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Example({ example }: { example: TopicExemplar }) {
  return (
    <figure className="space-y-1 rounded-lg bg-muted/70 px-3 py-2">
      <figcaption className="text-xs text-muted-foreground">
        {callLabel(example.call_type)} · {example.title}
      </figcaption>
      <p className="text-sm leading-5">{example.evidence_excerpt}</p>
      <p className="text-xs text-muted-foreground">
        {example.evidence_source === "transcript_turn" ? "Transcript sentence" : "Summary sentence"} · labels{" "}
        {example.original_labels.slice(0, 3).join(", ")} · model {example.generated_topic} · overlap{" "}
        {example.lexical_topic_overlap.toFixed(2)} · {example.overlap_status}
      </p>
      <p className="text-xs leading-5 text-muted-foreground">{example.classification_explanation}</p>
    </figure>
  );
}
