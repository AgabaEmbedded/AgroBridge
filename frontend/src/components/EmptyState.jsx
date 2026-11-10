import { ArrowRight, Leaf, Phone, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const EXAMPLES = [
  "How well does Nigeria's seed policy match what smallholder maize farmers need?",
  "Where do extension and fertilizer commitments fall short for rice farmers?",
  "What budget or implementation evidence exists for irrigation and mechanization?",
  "Which crop-production needs are missing from current agricultural policy?",
];

const PHONE_DISPLAY = "+1 405 716 9054";
const PHONE_HREF = "tel:+14057169054";

export function EmptyState({ onExample }) {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          Multi-agent policy intelligence
        </span>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Where does crop-production policy meet practice?
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Ask a question about Nigerian crop-production policy. Two specialist agents compare
          what policy promises with what crop farmers actually need, then explain the gaps the
          evidence supports in plain language. Empty categories are valid; nothing is
          invented to fill a fixed number of findings.
        </p>
      </div>

      <Card>
        <CardContent className="space-y-3 p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Try an example
          </p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {EXAMPLES.map((example) => (
              <li key={example}>
                <Button
                  type="button"
                  variant="outline"
                  className="h-auto w-full justify-between gap-3 whitespace-normal py-2.5 text-left text-sm font-normal"
                  onClick={() => onExample?.(example)}
                >
                  <span>{example}</span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-muted-foreground">
            Analyses usually take 30–90 seconds: two analyst agents, one or more
            discussion rounds, then synthesis.
          </p>
        </CardContent>
      </Card>

      <Card className="border-primary/20 bg-primary/[0.03]">
        <CardContent className="flex flex-wrap items-center gap-4 p-5">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
            <Phone className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Need advice for a farm, not a policy?</p>
            <p className="text-xs text-muted-foreground">
              Farmer questions are handled by the telephone assistant — not by this page.
            </p>
          </div>
          <Button asChild variant="outline" className="rounded-full">
            <a href={PHONE_HREF} aria-label={`Call Farmer Assistant at ${PHONE_DISPLAY}`}>
              <Leaf className="h-4 w-4" aria-hidden="true" />
              Call Farmer Assistant
              <span className="text-xs text-muted-foreground">{PHONE_DISPLAY}</span>
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
