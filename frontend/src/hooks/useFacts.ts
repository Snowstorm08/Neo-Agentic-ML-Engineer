import { useCallback, useState } from "react";
import type { FactRecord } from "../lib/facts";

export type FactAction = {
  type: "save" | "discard";
  factId: string;
  factText?: string;
};

export function useFacts() {
  const [facts, setFacts] = useState<FactRecord[]>([]);

  // Perform the action based on the provided type ("save" or "discard")
  const performAction = useCallback(async (action: FactAction) => {
    setFacts((currentFacts) => {
      if (action.type === "save") {
        const text = (action.factText ?? "").trim();
        // Return current state if the text is empty or the fact already exists
        if (!text || currentFacts.some((fact) => fact.id === action.factId)) {
          return currentFacts;
        }
        
        // Create a new fact object to add to the list
        const newFact: FactRecord = {
          id: action.factId,
          text,
          status: "saved",
          createdAt: new Date().toISOString(),
        };
        return [...currentFacts, newFact];
      }

      // Discard the fact by filtering it out based on factId
      return currentFacts.filter((fact) => fact.id !== action.factId);
    });
  }, []);

  const refresh = useCallback(() => {
    // No-op: facts are stored in memory, so there's no need to refresh externally
  }, []);

  return { facts, performAction, refresh };
}
