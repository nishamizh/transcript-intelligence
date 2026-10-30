import type { Methodology } from "@/lib/types";
import { percentText } from "@/lib/format";

export function MethodologyPanel({ methodology }: { methodology: Methodology }) {
  const inventory = methodology.label_inventory;
  return (
    <section id="methodology" className="scroll-mt-24 space-y-4">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Methodology</p>
        <h2 className="font-heading text-3xl text-balance">Two views of the same meetings, kept apart</h2>
        <p className="text-muted-foreground">
          {inventory.distinct_labels} free-text labels shipped with the summaries. {percentText(inventory.hapax_share)} appear once.{" "}
          {inventory.note}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <article className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="font-medium">Governed map</h3>
          <p className="text-sm leading-6 text-muted-foreground">{methodology.governed_mapping}</p>
        </article>
        <article className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="font-medium">Held-out discovery</h3>
          <p className="text-sm leading-6 text-muted-foreground">{methodology.held_out_discovery}</p>
        </article>
        <article className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="font-medium">Why this fits a small corpus</h3>
          <p className="text-sm leading-6 text-muted-foreground">{methodology.why_this_corpus}</p>
        </article>
        <article className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="font-medium">What BERTopic changes</h3>
          <p className="text-sm leading-6 text-muted-foreground">{methodology.bertopic}</p>
        </article>
      </div>
      <div className="max-w-3xl space-y-2 text-sm leading-6 text-muted-foreground">
        <p>{methodology.lexical_overlap}</p>
        <p>{methodology.sentiment}</p>
        <p className="font-medium text-foreground">Not measured</p>
        <ul className="list-disc space-y-1 pl-5">
          {methodology.not_measured.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
