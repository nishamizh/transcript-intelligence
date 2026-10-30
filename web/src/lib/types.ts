export type CallType = "support" | "external" | "internal";

export type KeyMoment = {
  time_seconds: number;
  text: string;
  moment_type: string;
  speaker: string;
};

export type MeetingFeatures = {
  participant_count: number;
  invitee_count: number;
  topic_count: number;
  action_item_count: number;
  speaking_turns: number;
  sentiment_score: number;
  duration_minutes: number;
  transcript_words: number;
  negative_turn_share: number;
  positive_turn_share: number;
  late_join_count: number;
  talk_share_top_speaker: number;
  moment_counts: Record<string, number>;
};

export type MeetingRecord = {
  meeting_id: string;
  title: string;
  call_type: CallType | string;
  date: string;
  month: string;
  duration_minutes: number;
  sentiment: string;
  sentiment_score: number;
  topics: string[];
  primary_theme: string;
  governed_themes: string[];
  generated_topic: string;
  generated_terms: string[];
  topic_agreement: number;
  action_items: string[];
  account_name: string;
  customer_domains: string[];
  summary: string;
  excerpt: string;
  key_moments: KeyMoment[];
  features: MeetingFeatures;
};

export type CallTypeSentiment = {
  call_type: string;
  count: number;
  mean_score: number;
  negative_share: number;
  label_counts: Record<string, number>;
  sentence_mix: Record<string, number>;
};

export type PeriodSentiment = {
  period: string;
  count: number;
  mean_score: number | null;
  by_call_type: Record<string, number | null>;
};

export type CohortSentiment = {
  name: string;
  count: number;
  mean_score: number;
  rest_count: number;
  rest_mean: number;
};

export type Interpretation = {
  interpretation_id: string;
  title: string;
  finding: string;
  why_it_matters: string;
};

export type SentimentReport = {
  overall_mean: number;
  overall_count: number;
  scale: string;
  negative_threshold: number;
  by_call_type: CallTypeSentiment[];
  by_month: PeriodSentiment[];
  by_week: PeriodSentiment[];
  incident: CohortSentiment;
  outage_mention: CohortSentiment;
  label_counts: Record<string, number>;
  interpretations: Interpretation[];
};

export type ThemeExample = {
  meeting_id: string;
  title: string;
  call_type: string;
  date: string;
  sentiment: string;
  sentiment_score: number;
  account_name: string;
  provided_topics: string[];
  summary: string;
  excerpt: string;
};

export type GovernedTheme = {
  theme_id: string;
  name: string;
  description: string;
  meeting_count: number;
  by_call_type: Record<string, number>;
  mean_sentiment: number;
  examples: ThemeExample[];
};

export type GeneratedTopic = {
  topic_id: number;
  label: string;
  terms: string[];
  meeting_count: number;
  mean_sentiment: number;
  examples: ThemeExample[];
};

export type TopicComparison = {
  unique_provided_labels: number;
  hapax_labels: number;
  hapax_share: number;
  governed_coverage: number;
  label_mapping_coverage: number;
  mean_jaccard: number;
  weighted_purity: number;
  matrix: { theme_id: string; generated_topic: string; count: number }[];
  disagreements: ThemeExample[];
  commentary: string[];
};

export type TopicReport = {
  model_name: string;
  themes: GovernedTheme[];
  generated: GeneratedTopic[];
  comparison: TopicComparison;
  unclassified_count: number;
};

export type Evidence = {
  meeting_id: string;
  title: string;
  call_type: string;
  date: string;
  account_name: string;
  sentiment: string;
  sentiment_score: number;
  quote: string;
};

export type InsightDetail = {
  label: string;
  value: string;
  note: string;
};

export type Insight = {
  insight_id: string;
  stakeholder: string;
  title: string;
  finding: string;
  why_it_matters: string;
  recommendation: string;
  metric_label: string;
  metric_value: string;
  evidence: Evidence[];
  details: InsightDetail[];
};

export type QualityReport = {
  coverage: number;
  consistency: number;
  actionability: number;
  confidence: number;
  composite: number;
  notes: string[];
  next_evolution: string;
};

export type Report = {
  generated_at: string;
  headline: string;
  subhead: string;
  dataset: {
    meeting_count: number;
    load_failures: number;
    failures: { folder: string; message: string }[];
    start_date: string | null;
    end_date: string | null;
    call_types: Record<string, number>;
    internal_domain: string;
    topic_model: string;
  };
  meetings: MeetingRecord[];
  sentiment: SentimentReport;
  topics: TopicReport;
  insights: Insight[];
  quality: QualityReport;
  method: Record<string, string>;
};
