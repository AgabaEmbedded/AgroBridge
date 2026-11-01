import { Badge } from "@/components/ui/badge";
import { statusMeta } from "@/lib/gaps";

export function EvidenceStatusBadge({ status }) {
  const meta = statusMeta(status);
  return (
    <span title={meta.description}>
      <Badge variant={meta.variant}>{meta.label}</Badge>
    </span>
  );
}

export function ConfidenceBadge({ confidence }) {
  if (!confidence) return null;
  const variant =
    confidence === "high" ? "success" : confidence === "medium" ? "secondary" : "muted";
  return <Badge variant={variant}>Confidence: {confidence}</Badge>;
}
