import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Menu, RefreshCw } from "lucide-react";
import { CallButton } from "@/components/CallButton";
import { CitationsPanel } from "@/components/CitationsPanel";
import { Composer } from "@/components/Composer";
import { EmptyState } from "@/components/EmptyState";
import { RunningState } from "@/components/RunningState";
import { Sidebar } from "@/components/Sidebar";
import { AnalysisMessage } from "@/components/AnalysisMessage";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { fetchHealth, runGapAnalysis } from "@/lib/api";
import { collectCitations } from "@/lib/citations";
import {
  createThread,
  loadThreads,
  saveThreads,
  threadTitle,
} from "@/lib/storage";

function makeMessageId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `m-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function ErrorNotice({ error, onRetry, onDismiss }) {
  return (
    <Card className="border-destructive/30 bg-destructive/[0.04]">
      <CardContent className="flex flex-wrap items-start gap-3 p-4">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{error.message}</p>
          {error.detail && error.detail !== error.message ? (
            <p className="mt-0.5 break-words text-xs text-muted-foreground">{error.detail}</p>
          ) : null}
        </div>
        <div className="flex gap-2">
          {error.retry ? (
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Retry
            </Button>
          ) : null}
          <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function App() {
  const [threads, setThreads] = useState(() => loadThreads());
  const [activeId, setActiveId] = useState(null);
  const [pending, setPending] = useState(null);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sources, setSources] = useState({ open: false, result: null, label: null });

  const abortRef = useRef(null);
  const bottomRef = useRef(null);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeId) || null,
    [threads, activeId],
  );

  useEffect(() => {
    saveThreads(threads);
  }, [threads]);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth({ signal: controller.signal })
      .then((data) => setHealth(data))
      .catch((err) => {
        if (err?.name !== "AbortError") setHealth({ status: "offline" });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeThread?.messages.length, pending]);

  const submit = useCallback(
    async (query, rounds, { appendUser = true } = {}) => {
      const clean = String(query || "").trim();
      if (!clean || pending) return;

      setError(null);
      const shouldAppend = appendUser || !activeId;
      let targetId = activeId;

      if (!targetId) {
        const thread = createThread();
        thread.title = threadTitle(clean);
        if (shouldAppend) {
          thread.messages = [{ id: makeMessageId(), role: "user", content: clean }];
        }
        setThreads((prev) => [thread, ...prev].slice(0, 20));
        setActiveId(thread.id);
        targetId = thread.id;
      } else if (shouldAppend) {
        const now = new Date().toISOString();
        setThreads((prev) =>
          prev.map((thread) =>
            thread.id === targetId
              ? {
                  ...thread,
                  title: thread.messages.length ? thread.title : threadTitle(clean),
                  updatedAt: now,
                  messages: [
                    ...thread.messages,
                    { id: makeMessageId(), role: "user", content: clean },
                  ],
                }
              : thread,
          ),
        );
      }

      const controller = new AbortController();
      abortRef.current = controller;
      setPending({ threadId: targetId, startedAt: Date.now(), query: clean, rounds });

      try {
        const result = await runGapAnalysis({
          query: clean,
          maxRounds: rounds,
          signal: controller.signal,
        });
        const now = new Date().toISOString();
        setThreads((prev) =>
          prev.map((thread) =>
            thread.id === targetId
              ? {
                  ...thread,
                  updatedAt: now,
                  messages: [
                    ...thread.messages,
                    {
                      id: makeMessageId(),
                      role: "assistant",
                      payload: result,
                      query: clean,
                    },
                  ],
                }
              : thread,
          ),
        );
      } catch (err) {
        if (err?.name === "AbortError") {
          setError({ message: "Analysis cancelled." });
        } else {
          setError({
            message: err?.message || "The analysis failed.",
            detail: err?.detail,
            retry: { query: clean, rounds },
          });
        }
      } finally {
        setPending(null);
        abortRef.current = null;
      }
    },
    [activeId, pending],
  );

  function handleNew() {
    if (pending) return;
    setActiveId(null);
    setError(null);
  }

  function handleSelect(id) {
    setActiveId(id);
    setError(null);
  }

  function handleDelete(id) {
    if (pending?.threadId === id) return;
    setThreads((prev) => prev.filter((thread) => thread.id !== id));
    if (activeId === id) {
      const remaining = threads.filter((thread) => thread.id !== id);
      setActiveId(remaining[0]?.id || null);
    }
  }

  function openSources(result) {
    setSources({ open: true, result, label: null });
  }

  function openCitation(result, label) {
    setSources({ open: true, result, label });
  }

  const sourceCitations = useMemo(
    () => (sources.result ? collectCitations(sources.result) : []),
    [sources.result],
  );

  const hasMessages = Boolean(activeThread?.messages.length);

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside className="hidden w-80 shrink-0 border-r lg:block">
        <Sidebar
          threads={threads}
          activeId={activeId}
          onSelect={handleSelect}
          onNew={handleNew}
          onDelete={handleDelete}
          health={health}
        />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b bg-background/80 px-4 py-3 backdrop-blur">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Open conversations"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">Policy Analyzer</p>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              Policy commitments vs. crop-production needs
            </p>
          </div>
          {health?.status !== "ok" ? (
            <span className="hidden text-[11px] text-destructive sm:inline">
              Backend offline
            </span>
          ) : null}
          <CallButton />
        </header>

        <main
          className="flex-1 overflow-y-auto scrollbar-thin"
          aria-live="polite"
          aria-busy={Boolean(pending)}
        >
          <div className="mx-auto w-full max-w-4xl space-y-8 px-4 py-6 sm:px-6">
            {hasMessages ? (
              activeThread.messages.map((message) => (
                <AnalysisMessage
                  key={message.id}
                  message={message}
                  onOpenSources={openSources}
                  onCitation={openCitation}
                />
              ))
            ) : (
              <EmptyState onExample={(example) => submit(example, 1)} />
            )}

            {pending && pending.threadId === activeThread?.id ? (
              <RunningState
                startedAt={pending.startedAt}
                onCancel={() => abortRef.current?.abort()}
              />
            ) : null}

            <div ref={bottomRef} />
          </div>
        </main>

        <div className="border-t bg-background/85 px-4 py-3 backdrop-blur sm:px-6">
          <div className="mx-auto w-full max-w-4xl space-y-2">
            {error ? (
              <ErrorNotice
                error={error}
                onRetry={() => {
                  const retry = error.retry;
                  setError(null);
                  if (retry) submit(retry.query, retry.rounds, { appendUser: false });
                }}
                onDismiss={() => setError(null)}
              />
            ) : null}
            <Composer
              onSubmit={(query, rounds) => submit(query, rounds)}
              pending={Boolean(pending)}
              hasMessages={hasMessages}
            />
          </div>
        </div>
      </div>

      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent className="h-[85vh] max-w-sm overflow-hidden p-0">
          <DialogTitle className="sr-only">Conversations</DialogTitle>
          <Sidebar
            threads={threads}
            activeId={activeId}
            onSelect={(id) => {
              handleSelect(id);
              setMobileOpen(false);
            }}
            onNew={() => {
              handleNew();
              setMobileOpen(false);
            }}
            onDelete={handleDelete}
            health={health}
          />
        </DialogContent>
      </Dialog>

      <CitationsPanel
        open={sources.open}
        onOpenChange={(open) => setSources((prev) => ({ ...prev, open }))}
        citations={sourceCitations}
        selectedLabel={sources.label}
      />
    </div>
  );
}
