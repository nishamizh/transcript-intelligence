"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { callLabel } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Rate = {
  value: number | null;
  display: string;
  numerator?: number | null;
  denominator?: number | null;
};

type Category = {
  theme: string;
  name: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  support: number;
};

type TopicBlock = {
  status: string;
  headline: string;
  warning: string;
  generalizes: boolean;
  assigned: number;
  reviewed: number;
  eligible: number;
  ambiguous: number;
  insufficient_evidence?: number;
  unadjudicated_conflicts?: number;
  unresolved: number;
  completion: Rate;
  reviewer_disagreement_rate?: Rate;
  accuracy_interval?: { display: string; caveat?: string };
  accuracy: Rate;
  macro_precision: Rate;
  macro_recall: Rate;
  macro_f1: Rate;
  weighted_precision: Rate;
  weighted_recall: Rate;
  weighted_f1: Rate;
  disagreement_rate: Rate;
  ambiguous_proportion: Rate;
  unresolved_proportion: Rate;
  per_category: Category[];
  confusion_matrix: {
    label_names: string[];
    counts: number[][];
  };
  population_estimates: {
    accuracy: Rate;
    macro_f1: Rate;
    note: string;
  } | null;
  note: string;
};

type StakeholderRow = {
  stakeholder: string;
  label: string;
  total: number;
  reviewed: number;
  accepted: number;
  rejected: number;
  needs_revision: number;
  needs_more_evidence: number;
  acceptance_rate: Rate;
};

export type HumanValidationReport = {
  data_gap: {
    resolved: boolean;
    topic_classification: string;
    insight_acceptance: string;
    finding_support?: string;
    reason: string;
  };
  sampling: {
    seed: number;
    target: number;
    method: string;
    population_meetings: number;
    representative_count: number;
    challenging_count: number;
    overlap_count: number;
    challenging_bias: string;
    pooling: string;
    coverage: {
      by_theme: { name: string; label: string; population: number; sampled: number; fraction: number | null }[];
      by_call_type: { name: string; label: string; population: number; sampled: number; fraction: number | null }[];
    };
  };
  topic_classification: {
    representative: TopicBlock;
    challenging: TopicBlock;
    pooling_note: string;
  };
  findings_verification?: {
    human_review_status: string;
    quotes_found: number;
    quotes_missing: number;
    human_reviewed: number;
    finding_count: number;
    note: string;
  };
  claims_audit?: {
    status: string;
    review_status: string;
    note: string;
    claims: {
      metric_name: string;
      computed_value: string | number | null;
      reported_value: string | number | null;
      source_count: number;
      check_status: string;
      review_status: string;
    }[];
  };
  readiness?: {
    implemented: string[];
    awaiting_review: string[];
    validated: string[];
    insufficient_evidence: string[];
    note: string;
  };
  business_insights: {
    total: number;
    awaiting_review: number;
    reviewed: number;
    accepted: number;
    rejected: number;
    needs_revision: number;
    needs_more_evidence: number;
    review_coverage: Rate;
    acceptance_rate: Rate;
    approval_coverage: Rate;
    mean_evidence_quality: { value: number | null; count: number; display: string };
    mean_business_usefulness: { value: number | null; count: number; display: string };
    by_stakeholder: StakeholderRow[];
    note: string;
  };
};

const SCORE_FIELDS: { key: keyof TopicBlock; label: string }[] = [
  { key: "accuracy", label: "Accuracy" },
  { key: "macro_precision", label: "Macro precision" },
  { key: "macro_recall", label: "Macro recall" },
  { key: "macro_f1", label: "Macro F1" },
  { key: "weighted_precision", label: "Weighted precision" },
  { key: "weighted_recall", label: "Weighted recall" },
  { key: "weighted_f1", label: "Weighted F1" },
];

export function EvaluationPanel({ validation }: { validation: HumanValidationReport }) {
  const gap = validation.data_gap;
  const insights = validation.business_insights;

  return (
    <section id="evaluation" className="scroll-mt-24 space-y-6">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Evaluation</p>
        <h2 className="font-heading text-3xl text-balance">Human review, then the score</h2>
        <p className="text-muted-foreground">
          A reviewer opens the review app, judges each transcript and each finding, and saves a decision.
          This page reads those decisions. It does not invent them.
        </p>
      </div>

      <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <p className="text-sm font-medium">
          Topic classification: {gap.topic_classification}. Insight acceptance: {gap.insight_acceptance}.
          {gap.finding_support ? ` Finding support: ${gap.finding_support}.` : ""}
        </p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{gap.reason}</p>
        <p className="mt-3 text-sm leading-6">
          Open the reviewer with{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">
            streamlit run src/review/app.py --server.port 43124 --server.address 0.0.0.0
          </code>
          . Enter a reviewer id, choose a decision, and save. The report regenerates from the saved file.
        </p>
      </div>

      <article className="space-y-3">
        <h3 className="font-heading text-2xl">How the 30 meetings were chosen</h3>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{validation.sampling.method}</p>
        <p className="text-sm text-muted-foreground">
          Seed {validation.sampling.seed}. Target {validation.sampling.target}. Representative sample{" "}
          {validation.sampling.representative_count} of {validation.sampling.population_meetings}. Challenging cases{" "}
          {validation.sampling.challenging_count}. Meetings in both lists: {validation.sampling.overlap_count}.
        </p>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{validation.sampling.pooling}</p>
        <div className="grid gap-4 lg:grid-cols-2">
          <CoverageTable
            title="Coverage by theme"
            rows={(validation.sampling.coverage.by_theme ?? []).map((row) => ({
              label: row.label,
              population: row.population,
              sampled: row.sampled,
              fraction: row.fraction,
            }))}
          />
          <CoverageTable
            title="Coverage by call type"
            rows={(validation.sampling.coverage.by_call_type ?? []).map((row) => ({
              label: callLabel(row.name),
              population: row.population,
              sampled: row.sampled,
              fraction: row.fraction,
            }))}
          />
        </div>
      </article>

      <Tabs defaultValue="representative">
        <TabsList className="h-auto! w-full flex-wrap justify-start">
          <TabsTrigger value="representative">Representative sample</TabsTrigger>
          <TabsTrigger value="challenging">Challenging cases</TabsTrigger>
        </TabsList>
        <TabsContent value="representative" className="space-y-4">
          <TopicScorecard block={validation.topic_classification.representative} />
        </TabsContent>
        <TabsContent value="challenging" className="space-y-4">
          <p className="max-w-3xl rounded-xl bg-card p-4 text-sm leading-6 ring-1 ring-foreground/10">
            {validation.sampling.challenging_bias} {validation.topic_classification.pooling_note}
          </p>
          <TopicScorecard block={validation.topic_classification.challenging} />
        </TabsContent>
      </Tabs>

      <article className="space-y-4">
        <h3 className="font-heading text-2xl">Business insight approval</h3>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{insights.note}</p>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Awaiting review" value={String(insights.awaiting_review)} note={`of ${insights.total}`} />
          <Stat label="Accepted" value={String(insights.accepted)} note="Resolved as accept" />
          <Stat label="Rejected" value={String(insights.rejected)} note="Resolved as reject" />
          <Stat label="Needs revision" value={String(insights.needs_revision)} note="Not accepted or rejected" />
          <Stat label="Needs more evidence" value={String(insights.needs_more_evidence)} note="Not accepted or rejected" />
          <Stat label="Review coverage" value={insights.review_coverage.display} note="Reviewed / all insights" />
          <Stat label="Resolved acceptance" value={insights.acceptance_rate.display} note="Accepted / (accepted + rejected)" />
          <Stat label="Accepted share of findings" value={insights.approval_coverage.display} note="Accepted / all insights" />
        </dl>
        <p className="text-sm text-muted-foreground">
          Average evidence quality: {insights.mean_evidence_quality.display}. Average business usefulness:{" "}
          {insights.mean_business_usefulness.display}.
        </p>
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stakeholder</TableHead>
                <TableHead>Reviewed</TableHead>
                <TableHead>Accepted</TableHead>
                <TableHead>Rejected</TableHead>
                <TableHead>Needs revision</TableHead>
                <TableHead>Needs more evidence</TableHead>
                <TableHead>Acceptance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {insights.by_stakeholder.map((row) => (
                <TableRow key={row.stakeholder}>
                  <TableCell>{row.label}</TableCell>
                  <TableCell>
                    {row.reviewed}/{row.total}
                  </TableCell>
                  <TableCell>{row.accepted}</TableCell>
                  <TableCell>{row.rejected}</TableCell>
                  <TableCell>{row.needs_revision}</TableCell>
                  <TableCell>{row.needs_more_evidence}</TableCell>
                  <TableCell>{row.acceptance_rate.display}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </article>

      <FindingsAndClaims validation={validation} />

      <p className="text-sm">
        <a className="underline" href="/human_validation_report.json">
          Download JSON
        </a>
        {" · "}
        <a className="underline" href="/human_validation_report.csv">
          Download CSV
        </a>
        {" · "}
        <a className="underline" href="/claims_audit.json">
          Claims audit
        </a>
        {" · "}
        <a className="underline" href="/evidence_verification.json">
          Evidence verification
        </a>
      </p>
    </section>
  );
}

function TopicScorecard({ block }: { block: TopicBlock }) {
  const matrixHasCounts = block.confusion_matrix.counts.some((row) => row.some((count) => count > 0));
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">{block.headline}</p>
      {block.warning ? (
        <p className="max-w-3xl rounded-xl bg-card p-4 text-sm leading-6 ring-1 ring-foreground/10">{block.warning}</p>
      ) : null}
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Review completion" value={block.completion.display} note="Reviewed / assigned" />
        <Stat label="Adjudicated" value={String(block.eligible)} note="Used in accuracy" />
        <Stat label="Ambiguous" value={`${block.ambiguous} · ${block.ambiguous_proportion.display}`} note="Excluded from accuracy" />
        <Stat label="Unresolved" value={`${block.unresolved} · ${block.unresolved_proportion.display}`} note="No decision saved" />
        <Stat
          label="Insufficient evidence"
          value={String(block.insufficient_evidence ?? 0)}
          note="Excluded from accuracy"
        />
        <Stat
          label="Unadjudicated conflicts"
          value={String(block.unadjudicated_conflicts ?? 0)}
          note="Excluded until adjudicated"
        />
        <Stat
          label="Reviewer disagreement"
          value={block.reviewer_disagreement_rate?.display ?? "N/A"}
          note="Items with two reviewers who differ"
        />
        {SCORE_FIELDS.map((field) => {
          const cell = block[field.key] as Rate;
          return <Stat key={field.key} label={field.label} value={shown(block, cell)} note="Eight-theme, single label" />;
        })}
        <Stat label="Disagreement" value={shown(block, block.disagreement_rate)} note="Predicted category differs" />
      </dl>
      <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
        Accuracy interval (Wilson 95% on labeled rows): {block.accuracy_interval?.display ?? "N/A"}.{" "}
        {block.accuracy_interval?.caveat ?? "No interval is shown until adjudicated labels exist."}
      </p>
      <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Category</TableHead>
              <TableHead>Precision</TableHead>
              <TableHead>Recall</TableHead>
              <TableHead>F1</TableHead>
              <TableHead>Labeled support</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {block.per_category.map((category) => (
              <TableRow key={category.theme}>
                <TableCell>{category.name}</TableCell>
                <TableCell>{shownPercent(block, category.precision)}</TableCell>
                <TableCell>{shownPercent(block, category.recall)}</TableCell>
                <TableCell>{shownPercent(block, category.f1)}</TableCell>
                <TableCell>{category.support}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {matrixHasCounts ? (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Human \ model</TableHead>
                {block.confusion_matrix.label_names.map((name) => (
                  <TableHead key={name}>{name}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {block.confusion_matrix.counts.map((row, index) => (
                <TableRow key={block.confusion_matrix.label_names[index]}>
                  <TableCell>{block.confusion_matrix.label_names[index]}</TableCell>
                  {row.map((count, column) => (
                    <TableCell key={`${index}-${column}`}>{count}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          The confusion matrix is empty until a reviewer approves or corrects a category. Rows will be the human
          category. Columns will be the model category.
        </p>
      )}
      {block.population_estimates ? (
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          Stratified population estimate — accuracy {shown(block, block.population_estimates.accuracy)}, macro F1{" "}
          {shown(block, block.population_estimates.macro_f1)}. {block.population_estimates.note}
        </p>
      ) : (
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          No population estimate is shown for this set. Challenging-case accuracy is unweighted and is not a sample of
          the whole book.
        </p>
      )}
    </div>
  );
}

function CoverageTable({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; population: number; sampled: number; fraction: number | null }[];
}) {
  return (
    <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{title}</TableHead>
            <TableHead>Population</TableHead>
            <TableHead>Sampled</TableHead>
            <TableHead>Fraction</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell>{row.label}</TableCell>
              <TableCell>{row.population}</TableCell>
              <TableCell>{row.sampled}</TableCell>
              <TableCell>{row.fraction == null ? "—" : row.fraction.toFixed(2)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function FindingsAndClaims({ validation }: { validation: HumanValidationReport }) {
  const findings = validation.findings_verification;
  const claims = validation.claims_audit;
  const readiness = validation.readiness;
  if (!findings && !claims && !readiness) return null;
  return (
    <article className="space-y-4">
      <h3 className="font-heading text-2xl">Findings and reproducibility</h3>
      {findings ? (
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          Quote location: {findings.quotes_found} found, {findings.quotes_missing} missing. Human support judgments:{" "}
          {findings.human_reviewed}/{findings.finding_count}. Status: {findings.human_review_status}. {findings.note}
        </p>
      ) : null}
      {claims?.claims?.length ? (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead>Computed</TableHead>
                <TableHead>Reported</TableHead>
                <TableHead>Check</TableHead>
                <TableHead>Human review</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.claims.map((row) => (
                <TableRow key={row.metric_name}>
                  <TableCell>{row.metric_name}</TableCell>
                  <TableCell>{String(row.computed_value)}</TableCell>
                  <TableCell>{String(row.reported_value)}</TableCell>
                  <TableCell>{row.check_status}</TableCell>
                  <TableCell>{row.review_status}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {claims?.note ? <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{claims.note}</p> : null}
      {readiness ? (
        <div className="grid gap-3 md:grid-cols-2">
          {(
            [
              ["Implemented", readiness.implemented],
              ["Awaiting review", readiness.awaiting_review],
              ["Validated", readiness.validated],
              ["Insufficient evidence", readiness.insufficient_evidence],
            ] as const
          ).map(([label, entries]) => (
            <div key={label} className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
              <h3 className="font-medium">{label}</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {(entries.length ? entries : ["None."]).map((entry) => (
                  <li key={entry}>{entry}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-xl bg-card px-3 py-3 ring-1 ring-foreground/10">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-heading text-2xl text-balance">{value}</dd>
      <dd className="text-xs text-muted-foreground">{note}</dd>
    </div>
  );
}

function shown(block: TopicBlock, cell: Rate): string {
  if (block.status !== "measured") {
    if (block.eligible > 0 && cell.value != null) {
      return `N/A · labeled rows ${cell.display}`;
    }
    return "N/A";
  }
  return cell.display;
}

function shownPercent(block: TopicBlock, value: number | null): string {
  if (value == null) return "N/A";
  const text = `${Math.round(value * 1000) / 10}%`;
  if (block.status !== "measured") return `N/A · ${text} on labeled rows`;
  return text;
}
