import { cn } from "@/lib/utils";

function Separator({ className, ...props }) {
  return (
    <div
      role="separator"
      className={cn("shrink-0 bg-border", "h-px w-full", className)}
      {...props}
    />
  );
}

export { Separator };
