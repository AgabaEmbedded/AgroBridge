import { Leaf, MessageSquarePlus, Phone, Trash2, Wifi, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/storage";

const PHONE_DISPLAY = "+234 201 350 2062";
const PHONE_HREF = "tel:+2342013502062";

export function Sidebar({
  threads,
  activeId,
  onSelect,
  onNew,
  onDelete,
  health,
  className = "",
}) {
  const sorted = [...threads].sort(
    (a, b) => new Date(b.updatedAt) - new Date(a.updatedAt),
  );
  const connected = health?.status === "ok";

  return (
    <div className={cn("flex h-full flex-col bg-card/60", className)}>
      <div className="flex items-center gap-3 px-5 py-5">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Leaf className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-base font-semibold leading-tight">AgroBridge</p>
          <p className="truncate text-xs text-muted-foreground">Gap Analysis</p>
        </div>
      </div>

      <div className="px-4">
        <Button type="button" className="w-full justify-start" onClick={onNew}>
          <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
          New analysis
        </Button>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto scrollbar-thin px-2 pb-2">
        <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          History
        </p>
        {sorted.length ? (
          <ul className="space-y-1">
            {sorted.map((thread) => (
              <li key={thread.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(thread.id)}
                  className={cn(
                    "w-full rounded-lg px-3 py-2 pr-9 text-left transition-colors hover:bg-accent/60",
                    activeId === thread.id && "bg-accent text-accent-foreground",
                  )}
                >
                  <span className="block truncate text-sm font-medium">{thread.title}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    {relativeTime(thread.updatedAt)} · {thread.messages.length} message
                    {thread.messages.length === 1 ? "" : "s"}
                  </span>
                </button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete analysis ${thread.title}`}
                  className="absolute right-1 top-1.5 h-7 w-7 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete(thread.id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-3 py-4 text-xs text-muted-foreground">
            No analyses yet. Ask a policy question to start.
          </p>
        )}
      </div>

      <div className="space-y-3 border-t px-5 py-4">
        <div className="flex items-center gap-2 text-xs">
          {connected ? (
            <Wifi className="h-3.5 w-3.5 text-success" aria-hidden="true" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
          )}
          <span className={connected ? "text-muted-foreground" : "text-destructive"}>
            {connected ? "Backend connected" : "Backend offline"}
          </span>
          {connected ? (
            <Badge variant="outline" className="ml-auto text-[10px]">
              KB1 {health.kb1_chunks} · KB2 {health.kb2_chunks}
            </Badge>
          ) : null}
        </div>

        <Separator />

        <a
          href={PHONE_HREF}
          className="flex items-start gap-2 rounded-lg p-1 transition-colors hover:bg-accent/50"
          aria-label={`Call Farmer Assistant at ${PHONE_DISPLAY}`}
        >
          <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
            <Phone className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="block text-xs font-medium">Call Farmer Assistant</span>
            <span className="block text-[11px] text-muted-foreground">{PHONE_DISPLAY}</span>
            <span className="block text-[10px] text-muted-foreground">
              Farmer questions are answered by phone.
            </span>
          </span>
        </a>
      </div>
    </div>
  );
}
