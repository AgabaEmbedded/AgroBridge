import {
  BookOpen,
  Building2,
  ClipboardCheck,
  FileQuestion,
  Library,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { GapCard } from "@/components/GapCard";
import { collectCitations } from "@/lib/citations";
import { GAP_SECTIONS, STATUS_META, formatDuration } from "@/lib/gaps";

const SECTION_ICONS = {
  policy_coverage_gaps: BookOpen,
  implementation_gaps: ClipboardCheck,
  institutional_gaps: Building2,
  evidence_gaps: FileQuestion,
};

export function GapReport({ result, onOpenSources, onCitation }) {
  const report = result?.report || {};
  const citations = collectCitations(result);
  const totalGaps = GAP_SECTIONS.reduce(
    (sum, section) => sum + (report[section.key]?.length || 0),
    0,
  );
  const duration = formatDuration(
    Object.values(result?.timings || {}).reduce(
      (sum, value) => sum + (Number.isFinite(value) ? value : 0),
      0,
    ),
  );

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <CardContent className="space-y-3 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">Policy analysis</Badge>
            {result?.rounds != null ? (
              <Badge variant="outline">
                {result.rounds} discussion {result.rounds === 1 ? "round" : "rounds"}
              </Badge>
            ) : null}
            {duration ? <Badge variant="outline">{duration}</Badge> : null}
            <span className="text-xs text-muted-foreground">
              {totalGaps} identified {totalGaps === 1 ? "gap" : "gaps"}
            </span>
          </div>

          <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90">
            {report.summary || "The backend returned no summary for this analysis."}
          </p>
          {report.key_findings?.length ? (
            <div className="rounded-md bg-muted/50 p-3">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Key findings
              </p>
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {report.key_findings.map((finding, index) => (
                  <li key={index}>{finding}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onOpenSources}>
              <Library className="h-4 w-4" aria-hidden="true" />
              Sources & citations
              <Badge variant="secondary" className="ml-1">
                {citations.length}
              </Badge>
            </Button>
            {result?.audit_id ? (
              <span className="font-mono text-[11px] text-muted-foreground">
                audit {String(result.audit_id).slice(0, 10)}…
              </span>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2 border-t pt-3">
            {Object.entries(STATUS_META).map(([key, meta]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground"
                title={meta.description}
              >
                <Badge variant={meta.variant}>{meta.label}</Badge>
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      <Accordion
        type="multiple"
        defaultValue={GAP_SECTIONS.filter((section) => (report[section.key] || []).length).map(
          (section) => section.key,
        )}
        className="space-y-3"
      >
        {GAP_SECTIONS.filter((section) => (report[section.key] || []).length).map((section) => {
          const gaps = report[section.key] || [];
          const Icon = SECTION_ICONS[section.key];
          return (
            <AccordionItem
              key={section.key}
              value={section.key}
              className="rounded-lg border bg-card px-4"
            >
              <AccordionTrigger>
                <span className="flex items-center gap-2.5">
                  <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
                  <span>{section.title}</span>
                  <Badge variant={gaps.length ? "secondary" : "muted"}>{gaps.length}</Badge>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <p className="mb-3 text-xs text-muted-foreground">{section.description}</p>
                {gaps.length ? (
                  <div className="space-y-3">
                    {gaps.map((gap, index) => (
                      <GapCard
                        key={`${section.key}-${index}`}
                        gap={gap}
                        onCitation={onCitation}
                      />
                    ))}
                  </div>
                ) : null}
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>

      {totalGaps === 0 ? (
        <Card>
          <CardContent className="p-5 text-sm text-muted-foreground">
            No evidence-backed gaps were found in the supplied documents. That is a valid result;
            the documents may not contain enough implementation detail to support a finding.
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
