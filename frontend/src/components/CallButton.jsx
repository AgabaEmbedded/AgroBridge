import { Phone } from "lucide-react";
import { Button } from "@/components/ui/button";

const PHONE_DISPLAY = "+1 405 716 9054";
const PHONE_HREF = "tel:+14057169054";

export function CallButton({ className = "" }) {
  return (
    <Button asChild className={`rounded-full shadow-sm ${className}`}>
      <a
        href={PHONE_HREF}
        aria-label={`Call Farmer Assistant at ${PHONE_DISPLAY}`}
        title={`Call Farmer Assistant · ${PHONE_DISPLAY}`}
      >
        <Phone className="h-4 w-4" aria-hidden="true" />
        <span className="whitespace-nowrap">Call Farmer Assistant</span>
        <span className="hidden whitespace-nowrap text-xs font-normal text-primary-foreground/80 md:inline">
          {PHONE_DISPLAY}
        </span>
      </a>
    </Button>
  );
}
