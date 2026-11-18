import { apiRequest } from "./api";
import type { KnowledgeQueryResponse } from "./types";

export async function askKnowledge(
  question: string,
  token?: string | null,
): Promise<KnowledgeQueryResponse> {
  return apiRequest<KnowledgeQueryResponse>("/api/knowledge/query", {
    method: "POST",
    body: JSON.stringify({ question }),
    token: token ?? undefined,
  });
}
