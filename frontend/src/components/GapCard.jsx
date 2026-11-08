import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfidenceBadge, EvidenceStatusBadge } from "@/components/StatusBadges";

function Field({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm leading-relaxed text-foreground/90">{value}</dd>
    </div>
  );
}

export function GapCard({ gap, onCitation }) {
  return (
    <Card className="animate-fade-in border-border/80">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="max-w-prose space-y-1">
            <p className="text-sm font-medium leading-snug">{gap.gap_description}</p>
            {gap.plain_explanation ? (
              <p className="text-sm leading-relaxed text-muted-foreground">
                {gap.plain_explanation}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <EvidenceStatusBadge status={gap.evidence_status} />
            <ConfidenceBadge confidence={gap.confidence} />
          </div>
        </div>

        <dl className="grid gap-3 sm:grid-cols-2">
          <Field label="What policy promised" value={gap.policy_commitment} />
          <Field label="What farmers need" value={gap.practical_need} />
          <Field label="What was delivered" value={gap.implementation_evidence} />
          <Field label="Who is responsible" value={gap.responsible_institution} />
        </dl>

        {gap.citations?.length ? (
          <div className="flex flex-wrap items-center gap-1.5 border-t pt-3">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Citations
            </span>
            {gap.citations.map((citation) => (
              <Button
                key={citation}
                type="button"
                variant="secondary"
                size="sm"
                className="h-7 max-w-full rounded-full px-2.5 text-xs font-normal"
                onClick={() => onCitation?.(citation)}
                title={`Inspect ${citation}`}
              >
                <Badge variant="outline" className="mr-1 px-1.5 py-0 text-[10px]">
                  {citation.split("/")[0]}
                </Badge>
                <span className="truncate">{citation.split("/").slice(1).join("/")}</span>
              </Button>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
