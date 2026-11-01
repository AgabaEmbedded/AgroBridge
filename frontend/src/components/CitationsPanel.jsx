import { useEffect, useMemo, useState } from "react";
import { Check, Copy, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export function CitationsPanel({
  open,
  onOpenChange,
  citations,
  selectedLabel,
}) {
  const [active, setActive] = useState(selectedLabel);
  const [copied, setCopied] = useState(null);

  useEffect(() => {
    setActive(selectedLabel);
    setCopied(null);
  }, [selectedLabel, open]);

  const selected = useMemo(
    () => citations.find((citation) => citation.label === active),
    [citations, active],
  );

  async function copy(label) {
    try {
      await navigator.clipboard.writeText(label);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      setCopied(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>Sources &amp; citations</DialogTitle>
          <DialogDescription>
            Citations returned with this analysis. Page text is not exposed by the current API.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-3">
          {citations.length ? (
            <ul className="space-y-2">
              {citations.map((citation) => (
                <li key={citation.label}>
                  <button
                    type="button"
                    onClick={() => setActive(citation.label)}
                    className={cn(
                      "w-full rounded-lg border p-3 text-left transition-colors hover:bg-accent/50",
                      active === citation.label && "border-primary bg-accent/60",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{citation.knowledgeBase || "KB"}</Badge>
                      <span className="text-sm font-medium">{citation.document}</span>
                      {citation.page ? (
                        <Badge variant="outline">page {citation.page}</Badge>
                      ) : null}
                      {citation.chunk ? (
                        <Badge variant="outline">chunk {citation.chunk}</Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">
                      {citation.label}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">
              No citations were returned for this analysis.
            </p>
          )}
        </div>

        {selected ? (
          <div className="border-t bg-muted/30 px-6 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <span className="text-xs text-muted-foreground">
                {selected.knowledgeBase} · {selected.document}
                {selected.page ? ` · page ${selected.page}` : ""}
                {selected.chunk ? ` · chunk ${selected.chunk}` : ""}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="ml-auto h-7 text-xs"
                onClick={() => copy(selected.label)}
              >
                {copied === selected.label ? (
                  <>
                    <Check className="h-3.5 w-3.5" /> Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" /> Copy citation
                  </>
                )}
              </Button>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              To read the cited page here, the backend needs a document endpoint
              (`GET /api/documents/:id?page=N`); it is not part of the current API.
            </p>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
