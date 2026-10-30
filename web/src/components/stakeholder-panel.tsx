"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { callLabel, scoreText, stakeholderLabel } from "@/lib/format";
import type { Insight } from "@/lib/types";

const ORDER = ["support", "product", "engineering", "sales"];

export function StakeholderPanel({ insights }: { insights: Insight[] }) {
  const groups = ORDER.filter((id) => insights.some((insight) => insight.stakeholder === id));

  return (
    <section id="stakeholders" className="scroll-mt-24 space-y-4">
      <div className="max-w-3xl space-y-2">
        <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">Stakeholders</p>
        <h2 className="font-heading text-3xl text-balance">Four readers, one set of meetings</h2>
        <p className="text-muted-foreground">
          Each finding cites the meeting it came from. A sales quote and a support quote can be the same recording.
        </p>
      </div>

      <Tabs defaultValue={groups[0] ?? "support"}>
        <TabsList className="h-auto! w-full flex-wrap justify-start">
          {groups.map((id) => (
            <TabsTrigger key={id} value={id}>
              {stakeholderLabel(id)}
            </TabsTrigger>
          ))}
        </TabsList>
        {groups.map((id) => (
          <TabsContent key={id} value={id} className="space-y-4">
            {insights
              .filter((insight) => insight.stakeholder === id)
              .map((insight) => (
                <Card key={insight.insight_id}>
                  <CardHeader>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <CardTitle className="text-lg">{insight.title}</CardTitle>
                      <div className="text-right">
                        <p className="font-heading text-2xl tabular-nums">{insight.metric_value}</p>
                        <p className="text-xs text-muted-foreground">{insight.metric_label}</p>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm leading-6">{insight.finding}</p>
                    <p className="text-sm leading-6 text-muted-foreground">{insight.why_it_matters}</p>
                    <p className="text-sm leading-6">
                      <span className="font-medium">Do this. </span>
                      {insight.recommendation}
                    </p>
                    {insight.details.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Item</TableHead>
                            <TableHead>Value</TableHead>
                            <TableHead>Note</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {insight.details.map((detail, index) => (
                            <TableRow key={`${insight.insight_id}-${index}-${detail.label}`}>
                              <TableCell className="font-medium">{detail.label}</TableCell>
                              <TableCell className="tabular-nums">{detail.value}</TableCell>
                              <TableCell className="text-muted-foreground">{detail.note}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : null}
                    <ul className="space-y-3">
                      {insight.evidence.map((item, index) => (
                        <li key={`${insight.insight_id}-${item.meeting_id}-${index}`} className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <Badge variant="outline">{callLabel(item.call_type)}</Badge>
                            <span>{item.account_name || "Internal"}</span>
                            <span>{item.date}</span>
                            <span className="tabular-nums">{scoreText(item.sentiment_score)}</span>
                          </div>
                          <p className="text-sm font-medium">{item.title}</p>
                          <blockquote className="border-l-2 border-[#8c4a2f] pl-3 text-sm leading-6 text-muted-foreground">
                            {item.quote}
                          </blockquote>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              ))}
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}
