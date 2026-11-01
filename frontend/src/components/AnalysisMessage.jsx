import { GapReport } from "@/components/GapReport";
import { ExecutionTrace } from "@/components/ExecutionTrace";
import { cn } from "@/lib/utils";

export function AnalysisMessage({ message, onOpenSources, onCitation }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div
          className={cn(
            "max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm",
          )}
        >
          {message.content}
        </div>
      </div>
    );
  }

  const result = message.payload;
  if (!result) return null;

  return (
    <div className="animate-fade-in space-y-5">
      <GapReport
        result={result}
        onOpenSources={() => onOpenSources?.(result)}
        onCitation={(citation) => onCitation?.(result, citation)}
      />
      <ExecutionTrace
        result={result}
        onCitation={(citation) => onCitation?.(result, citation)}
      />
    </div>
  );
}
