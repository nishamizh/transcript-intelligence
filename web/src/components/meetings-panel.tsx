"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { callLabel, redactDisplay, scoreText, scoreTone } from "@/lib/format";
import type { GovernedTheme, MeetingRecord } from "@/lib/types";

const CALLS = ["all", "support", "external", "internal"] as const;

export function MeetingsPanel({
  meetings,
  themes,
}: {
  meetings: MeetingRecord[];
  themes: GovernedTheme[];
}) {
  const [query, setQuery] = useState("");
  const [callType, setCallType] = useState<(typeof CALLS)[number]>("all");
  const [theme, setTheme] = useState("all");
  const [polarity, setPolarity] = useState<"all" | "cold" | "warm">("all");
  const [openId, setOpenId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return meetings.filter((meeting) => {
      if (callType !== "all" && meeting.call_type !== callType) return false;
      if (theme !== "all" && meeting.primary_theme !== theme) return false;
      if (polarity === "cold" && meeting.sentiment_score >= 3) return false;
      if (polarity === "warm" && meeting.sentiment_score < 3) return false;
      if (!needle) return true;
      const haystack = [
        meeting.title,
        meeting.account_name,
        meeting.summary,
        meeting.primary_theme,
        meeting.generated_topic,
        ...meeting.topics,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [meetings, query, callType, theme, polarity]);

  const open = filtered.find((meeting) => meeting.meeting_id === openId) ?? null;
  const themeName = new Map(themes.map((item) => [item.theme_id, item.name]));

  return (
    <section id="meetings" className="scroll-mt-24 space-y-4">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Meetings</p>
        <h2 className="font-heading text-3xl text-balance">Every category has a transcript under it</h2>
        <p className="text-muted-foreground">
          Filter the corpus, then open a row for the summary, the provided labels, and the first lines of the transcript.
        </p>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search title, account, or topic"
          aria-label="Search meetings"
          className="lg:max-w-sm"
        />
        <div className="flex flex-wrap gap-2" role="group" aria-label="Call type">
          {CALLS.map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={callType === value ? "default" : "outline"}
              aria-pressed={callType === value}
              onClick={() => setCallType(value)}
            >
              {value === "all" ? "All types" : callLabel(value)}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Theme</span>
          <select
            value={theme}
            onChange={(event) => setTheme(event.target.value)}
            className="h-8 rounded-lg border border-input bg-card px-2 text-sm"
          >
            <option value="all">All themes</option>
            {themes.map((item) => (
              <option key={item.theme_id} value={item.theme_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Sentiment side">
          {(
            [
              ["all", "Any score"],
              ["cold", "Below 3"],
              ["warm", "3 and above"],
            ] as const
          ).map(([value, label]) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={polarity === value ? "default" : "outline"}
              aria-pressed={polarity === value}
              onClick={() => setPolarity(value)}
            >
              {label}
            </Button>
          ))}
        </div>
        <p className="text-sm text-muted-foreground sm:ml-auto">
          Showing {filtered.length} of {meetings.length}
        </p>
      </div>

      {open ? (
        <article className="space-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10" aria-live="polite">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{callLabel(open.call_type)}</Badge>
            <Badge variant="secondary">{themeName.get(open.primary_theme) ?? open.primary_theme}</Badge>
            <span className="text-sm text-muted-foreground">
              Generated topic: {open.generated_topic || "—"}
            </span>
            <span className="text-sm text-muted-foreground">
              Lexical overlap {open.lexical_topic_overlap.toFixed(2)} · {open.lexical_overlap_status}
            </span>
          </div>
          <h3 className="font-heading text-2xl text-balance">{open.title}</h3>
          <p className="text-sm leading-6">{redactDisplay(open.summary)}</p>
          <p className="text-xs text-muted-foreground">Provided labels: {open.topics.join(" · ")}</p>
          <p className="text-xs text-muted-foreground">
            Lexical overlap compares label words with the held-out topic terms. Review recommended means they share no content word. It is not an error score.
          </p>
          <pre className="font-sans text-sm leading-6 whitespace-pre-wrap text-muted-foreground">{redactDisplay(open.excerpt)}</pre>
          {open.action_items.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {open.action_items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </article>
      ) : (
        <p className="text-sm text-muted-foreground">Select a meeting to read its summary and the opening of the transcript.</p>
      )}

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center">
          <p className="font-medium">No meetings match this filter.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Clear the search or choose another theme. The corpus still has {meetings.length} meetings.
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            onClick={() => {
              setQuery("");
              setCallType("all");
              setTheme("all");
              setPolarity("all");
            }}
          >
            Reset filters
          </Button>
        </div>
      ) : (
        <div className="max-h-[32rem] overflow-auto rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Meeting</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Theme</TableHead>
                <TableHead className="text-right">Score</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((meeting) => (
                <TableRow
                  key={meeting.meeting_id}
                  data-state={openId === meeting.meeting_id ? "selected" : undefined}
                  className="cursor-pointer"
                  tabIndex={0}
                  aria-expanded={openId === meeting.meeting_id}
                  onClick={() =>
                    setOpenId((current) => (current === meeting.meeting_id ? null : meeting.meeting_id))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setOpenId((current) => (current === meeting.meeting_id ? null : meeting.meeting_id));
                    }
                  }}
                >
                  <TableCell className="whitespace-nowrap tabular-nums">{meeting.date}</TableCell>
                  <TableCell>
                    <span className="font-medium">{meeting.title}</span>
                    {meeting.account_name ? (
                      <span className="mt-0.5 block text-xs text-muted-foreground">{meeting.account_name}</span>
                    ) : null}
                  </TableCell>
                  <TableCell>{callLabel(meeting.call_type)}</TableCell>
                  <TableCell>{themeName.get(meeting.primary_theme) ?? meeting.primary_theme}</TableCell>
                  <TableCell className={`text-right tabular-nums ${scoreTone(meeting.sentiment_score)}`}>
                    {scoreText(meeting.sentiment_score)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

    </section>
  );
}
