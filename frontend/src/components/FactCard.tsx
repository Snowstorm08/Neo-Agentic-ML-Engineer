import { ChevronRight } from "lucide-react";
import type { FactRecord } from "../lib/facts";

interface FactCardProps {
  fact: FactRecord;
}

export function FactCard({ fact }: FactCardProps) {
  return (
    <li
      className="group flex items-start gap-1 text-sm font-medium
                 text-slate-600 dark:text-slate-300"
    >
      <ChevronRight
        className="mt-0.5 h-5 w-5 shrink-0
                   text-slate-800 dark:text-slate-200
                   transition-transform group-hover:translate-x-0.5"
        aria-hidden="true"
      />
      <span className="leading-relaxed">{fact.text}</span>
    </li>
  );
}
