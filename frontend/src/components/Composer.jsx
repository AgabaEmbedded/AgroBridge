import { useState } from "react";
import { Loader2, Send, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const MAX_LENGTH = 2000;

export function Composer({ onSubmit, pending, hasMessages }) {
  const [query, setQuery] = useState("");
  const [rounds, setRounds] = useState(1);
  const [focused, setFocused] = useState(false);

  function submit(event) {
    event?.preventDefault();
    const clean = query.trim();
    if (!clean || pending) return;
    onSubmit(clean, rounds);
    setQuery("");
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div
        className={`rounded-xl border bg-card shadow-sm transition-shadow ${
          focused ? "ring-2 ring-ring ring-offset-2 ring-offset-background" : ""
        }`}
      >
        <label htmlFor="gap-question" className="sr-only">
          Gap analysis question
        </label>
        <Textarea
          id="gap-question"
          value={query}
          onChange={(event) => setQuery(event.target.value.slice(0, MAX_LENGTH))}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          rows={3}
          maxLength={MAX_LENGTH}
          placeholder="Ask about a policy area, e.g. livestock disease control, extension services, fertilizer subsidies…"
          className="resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
          disabled={pending}
        />
        <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
            Discussion rounds
            <select
              value={rounds}
              onChange={(event) => setRounds(Number(event.target.value))}
              disabled={pending}
              className="rounded-md border bg-background px-1.5 py-0.5 text-xs text-foreground"
              aria-label="Number of agent discussion rounds"
            >
              {[0, 1, 2, 3].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <span className="hidden text-[11px] text-muted-foreground sm:inline">
            Enter to send · Shift+Enter for a new line
          </span>
          <Button
            type="submit"
            className="ml-auto"
            disabled={pending || !query.trim()}
          >
            {pending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Running
              </>
            ) : (
              <>
                <Send className="h-4 w-4" aria-hidden="true" />
                Run analysis
              </>
            )}
          </Button>
        </div>
      </div>

      {hasMessages ? (
        <p className="text-[11px] text-muted-foreground">
          Follow-ups start a new, independent analysis run. This thread keeps earlier
          results for reference; the backend does not carry agent context between runs.
        </p>
      ) : null}
      {query.length > 1600 ? (
        <p className="text-right text-[11px] text-muted-foreground">
          {query.length}/{MAX_LENGTH}
        </p>
      ) : null}
    </form>
  );
}
