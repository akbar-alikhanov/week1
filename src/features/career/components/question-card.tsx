"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/shared/lib/cn";

export function QuestionCard({ question, answer }: { question: string; answer: string }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium transition-colors hover:bg-accent"
      >
        <span>{question}</span>
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            isOpen && "rotate-180",
          )}
        />
      </button>
      {isOpen ? (
        <div className="border-t border-border px-4 py-3 text-sm text-muted-foreground">
          {answer}
        </div>
      ) : null}
    </div>
  );
}
