"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { GovernedTheme, ReviewQueue } from "@/lib/types";

type Decision = "" | "accept" | "edit" | "reject";

type Draft = {
  decision: Decision;
  corrected_theme: string;
  reason: string;
};

const CHOICES: { value: Decision; label: string }[] = [
  { value: "accept", label: "Accept" },
  { value: "edit", label: "Edit" },
  { value: "reject", label: "Reject" },
];

export function ReviewerPanel({ queue, themes }: { queue: ReviewQueue; themes: GovernedTheme[] }) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});

  const themeOptions = useMemo(
    () => [
      ...themes.map((theme) => ({ id: theme.theme_id, name: theme.name })),
      { id: "unclassified", name: "Unclassified" },
    ],
    [themes],
  );

  function draftFor(itemId: string): Draft {
    return drafts[itemId] ?? { decision: "", corrected_theme: "", reason: "" };
  }

  function update(itemId: string, patch: Partial<Draft>) {
    setDrafts((current) => {
      const prior = current[itemId] ?? { decision: "", corrected_theme: "", reason: "" };
      return { ...current, [itemId]: { ...prior, ...patch } };
    });
  }

  function download() {
    const payload = {
      version: 1,
      items: queue.items.map((item) => {
        const draft = draftFor(item.item_id);
        return {
          item_id: item.item_id,
          decision: draft.decision,
          corrected_theme: draft.corrected_theme,
          reason: draft.reason,
        };
      }),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "review_decisions.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  const reviewed = queue.items.filter((item) => draftFor(item.item_id).decision).length;

  return (
    <section id="review" className="scroll-mt-24 space-y-4">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Review</p>
        <h2 className="font-heading text-3xl text-balance">A person marks the queue. The file does not change the source.</h2>
        <p className="text-muted-foreground">
          {queue.item_count} items. Choices on this page stay in the browser until you download them. They are not saved on the server and they are not human labels. Use the Streamlit reviewer on port 43124 to save a decision into review_decisions.json. Accuracy stays N/A until that file has a real decision.
        </p>
        <p className="text-sm text-muted-foreground">
          Marked in this browser: {reviewed} of {queue.item_count}. Ambiguous means the top two theme scores are within {queue.ambiguous_margin} point.
        </p>
      </div>
      <Button type="button" onClick={download}>
        Download review decisions
      </Button>
      <ul className="space-y-3">
        {queue.items.map((item) => {
          const draft = draftFor(item.item_id);
          return (
            <li key={item.item_id} className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
              <details>
                <summary className="cursor-pointer text-sm font-medium">
                  {item.title}
                  <span className="mt-1 block font-normal text-muted-foreground">
                    {item.reasons.join(" · ") || item.item_type}
                    {item.predicted_theme_name ? ` · ${item.predicted_theme_name}` : ""}
                    {item.overlap_status ? ` · ${item.overlap_status}` : ""}
                    {draft.decision ? ` · ${draft.decision}` : ""}
                  </span>
                </summary>
                <div className="mt-3 space-y-3">
                  <p className="text-sm leading-6 text-muted-foreground">{item.evidence_excerpt}</p>
                  {item.original_labels.length > 0 ? (
                    <p className="text-xs text-muted-foreground">Labels: {item.original_labels.join(" · ")}</p>
                  ) : null}
                  <p className="text-xs text-muted-foreground">
                    Meeting {item.meeting_id || "—"}
                    {item.cited_meeting_ids.length > 1 ? ` · cites ${item.cited_meeting_ids.join(", ")}` : ""}
                  </p>
                  {item.finding ? <p className="text-sm leading-6">{item.finding}</p> : null}
                  <fieldset className="space-y-2">
                    <legend className="text-xs text-muted-foreground">Decision</legend>
                    <div className="flex flex-wrap gap-2">
                      {CHOICES.map((choice) => (
                        <Button
                          key={choice.value}
                          type="button"
                          size="sm"
                          variant={draft.decision === choice.value ? "default" : "outline"}
                          aria-pressed={draft.decision === choice.value}
                          onClick={() => update(item.item_id, { decision: choice.value })}
                        >
                          {choice.label}
                        </Button>
                      ))}
                    </div>
                  </fieldset>
                  {item.item_type === "meeting_classification" && draft.decision === "edit" ? (
                    <label className="flex flex-col gap-1 text-sm">
                      Corrected theme
                      <select
                        value={draft.corrected_theme}
                        onChange={(event) => update(item.item_id, { corrected_theme: event.target.value })}
                        className="h-8 rounded-lg border border-input bg-card px-2"
                      >
                        <option value="">Choose a theme</option>
                        {themeOptions.map((theme) => (
                          <option key={theme.id} value={theme.id}>
                            {theme.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <label className="flex flex-col gap-1 text-sm">
                    Reason
                    <textarea
                      value={draft.reason}
                      onChange={(event) => update(item.item_id, { reason: event.target.value })}
                      rows={2}
                      className="rounded-lg border border-input bg-card px-2 py-1"
                    />
                  </label>
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
