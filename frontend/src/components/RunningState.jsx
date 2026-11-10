import { useEffect, useState } from "react";
import { Loader2, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const STEPS = ["Policy review", "Farmer needs", "Discussion", "Synthesis"];

export function RunningState({ startedAt, onCancel }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setElapsed(Math.max(0, Math.round((Date.now() - startedAt) / 1000)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  return (
    <Card className="animate-fade-in border-primary/20">
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Running policy analysis…</p>
            <p className="text-xs text-muted-foreground">
              {elapsed}s elapsed · the backend processes this run as one request
            </p>
          </div>
          {onCancel ? (
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              <Square className="h-3.5 w-3.5" aria-hidden="true" />
              Cancel
            </Button>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {STEPS.map((step, index) => (
            <span key={step} className="flex items-center gap-1.5">
              <span className="rounded-full border bg-muted/40 px-2.5 py-1 text-[11px] text-muted-foreground">
                {step}
              </span>
              {index < STEPS.length - 1 ? (
                <span className="text-muted-foreground" aria-hidden="true">
                  →
                </span>
              ) : null}
            </span>
          ))}
        </div>

        <p className="text-[11px] text-muted-foreground">
          Live stage events are not streamed by the current API, so no step is marked
          complete until the result arrives.
        </p>
      </CardContent>
    </Card>
  );
}
