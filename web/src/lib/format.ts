const CALL_LABELS: Record<string, string> = {
  support: "Support",
  external: "External",
  internal: "Internal",
};

export function callLabel(callType: string): string {
  return CALL_LABELS[callType] ?? callType;
}

export function scoreText(value: number): string {
  return value.toFixed(2);
}

export function percentText(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatDay(iso: string | null): string {
  if (!iso) return "—";
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatGenerated(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function scoreTone(score: number): string {
  if (score < 2.5) return "text-[#9a3412]";
  if (score < 3.2) return "text-[#8a5a12]";
  return "text-[#1f6b4a]";
}

export function stakeholderLabel(id: string): string {
  const labels: Record<string, string> = {
    support: "Support leader",
    product: "Product manager",
    engineering: "Engineering manager",
    sales: "Sales leader",
  };
  return labels[id] ?? id;
}
