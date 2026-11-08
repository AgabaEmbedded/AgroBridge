import { ArrowLeftRight, ClipboardList, Gauge, MessagesSquare, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { collectCitations } from "@/lib/citations";
import { formatDuration, timingEntries } from "@/lib/gaps";

function ListBlock({ label, items }) {
  if (!items?.length) return null;
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-foreground/90">
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function CitationButtons({ citations, onCitation }) {
  if (!citations?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {citations.map((citation) => (
        <Button
          key={citation}
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 rounded-full px-2.5 text-xs font-normal"
          onClick={() => onCitation?.(citation)}
        >
          {citation}
        </Button>
      ))}
    </div>
  );
}

function FindingsBlock({ findings, onCitation }) {
  if (!findings || !Object.keys(findings).length) {
    return <p className="text-sm text-muted-foreground">No findings returned.</p>;
  }
  return (
    <div className="space-y-3">
      <dl className="space-y-3">
        <ListBlock label="Policy commitments" items={findings.policy_commitments} />
        <ListBlock label="Responsible institutions" items={findings.responsible_institutions} />
        <ListBlock label="Implementation targets" items={findings.implementation_targets} />
        <ListBlock label="Implementation evidence" items={findings.implementation_evidence} />
        <ListBlock label="Identified policy gaps" items={findings.identified_policy_gaps} />
        <ListBlock label="Crop-production challenges" items={findings.agricultural_challenges} />
        <ListBlock label="Practical crop-production needs" items={findings.practical_farmer_needs} />
        <ListBlock label="Technical requirements" items={findings.technical_requirements} />
        <ListBlock label="Evidence of challenges" items={findings.evidence_of_challenges} />
        <ListBlock
          label="Policy coverage observations"
          items={findings.policy_coverage_observations}
        />
      </dl>
      <CitationButtons citations={findings.citations} onCitation={onCitation} />
    </div>
  );
}

function CommunicationBlock({ messages, onCitation }) {
  if (!messages?.length) {
    return <p className="text-sm text-muted-foreground">No agent messages were exchanged.</p>;
  }
  return (
    <div className="space-y-3">
      {messages.map((message, index) => (
        <div key={index} className="rounded-md border bg-muted/30 p-3">
          <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs">
            <Badge variant="outline">{message.sender}</Badge>
            <ArrowLeftRight className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
            <Badge variant="outline">{message.recipient}</Badge>
            <Badge variant="secondary">{message.intent}</Badge>
          </div>
          {message.claims?.length ? (
            <ul className="list-disc space-y-1 pl-4 text-sm">
              {message.claims.map((claim, i) => (
                <li key={i}>{claim}</li>
              ))}
            </ul>
          ) : null}
          {message.questions?.length ? (
            <ul className="mt-2 space-y-1 text-sm">
              {message.questions.map((question, i) => (
                <li key={i} className="font-medium">
                  Q: {question}
                </li>
              ))}
            </ul>
          ) : null}
          {message.notes ? (
            <p className="mt-2 text-xs text-muted-foreground">{message.notes}</p>
          ) : null}
          {message.citations?.length ? (
            <div className="mt-2">
              <CitationButtons citations={message.citations} onCitation={onCitation} />
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function ExecutionTrace({ result, onCitation }) {
  const report = result?.report || {};
  const timings = result?.timings || {};
  const citations = collectCitations(result);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Agent execution trace</h3>
        <span className="text-[11px] text-muted-foreground">
          Structured output from this run · live streaming not enabled
        </span>
      </div>

      <Accordion type="multiple" className="rounded-lg border bg-card px-4">
        <AccordionItem value="pa">
          <AccordionTrigger>
            <span className="flex items-center gap-2">
              <Search className="h-4 w-4 text-primary" aria-hidden="true" />
              PA · Policy Analyst (KB2)
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <FindingsBlock findings={result?.policy_findings} onCitation={onCitation} />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="cpa">
          <AccordionTrigger>
            <span className="flex items-center gap-2">
              <ClipboardList className="h-4 w-4 text-primary" aria-hidden="true" />
              CPA · Crop Production Analyst (KB1)
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <FindingsBlock findings={result?.needs_findings} onCitation={onCitation} />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="communication">
          <AccordionTrigger>
            <span className="flex items-center gap-2">
              <MessagesSquare className="h-4 w-4 text-primary" aria-hidden="true" />
              Agent-to-agent communication
              <Badge variant="secondary">{result?.communication?.length || 0}</Badge>
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <CommunicationBlock
              messages={result?.communication}
              onCitation={onCitation}
            />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="synthesis" className="border-b-0">
          <AccordionTrigger>
            <span className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-primary" aria-hidden="true" />
              Synthesis &amp; timing
            </span>
          </AccordionTrigger>
          <AccordionContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {timingEntries(timings).map((timing) => (
                <div key={timing.key} className="rounded-md bg-muted/50 p-2">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {timing.label}
                  </p>
                  <p className="text-sm font-medium">{formatDuration(timing.value)}</p>
                </div>
              ))}
            </div>
            {report.summary ? (
              <p className="text-sm leading-relaxed">{report.summary}</p>
            ) : null}
            {report.limitations?.length ? (
              <ListBlock label="Limitations" items={report.limitations} />
            ) : null}
            <div>
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Retrieved evidence ({citations.length})
              </p>
              <CitationButtons
                citations={citations.map((citation) => citation.label)}
                onCitation={onCitation}
              />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
