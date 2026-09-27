export type ChatRole = "user" | "assistant";

export interface ChatHistoryMessage {
  role: ChatRole;
  content: string;
}

export interface EntityLink {
  type: "Site" | "HistoricalFigure" | "Entity";
  id: number;
  name: string;
  route: string;
}

export type ChatSseEvent =
  | { event: "token"; data: { text: string } }
  | { event: "status"; data: { tool: string; args: Record<string, unknown> } }
  | { event: "done"; data: { links: EntityLink[] } }
  | { event: "error"; data: { message: string } };

const AI_BASE_URL = "http://localhost:15423";

function parseSseChunk(raw: string): { event: string; data: string } | null {
  const lines = raw.split("\n");
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: dataLines.join("\n") };
}

function consumeSseText(text: string, onEvent: (event: ChatSseEvent) => void): void {
  for (const part of text.split("\n\n")) {
    const trimmed = part.trim();
    if (!trimmed) {
      continue;
    }
    const parsed = parseSseChunk(trimmed);
    if (!parsed) {
      continue;
    }
    try {
      const data = JSON.parse(parsed.data);
      onEvent({ event: parsed.event, data } as ChatSseEvent);
    } catch {
      // ignore malformed chunks
    }
  }
}

export async function streamChat(
  message: string,
  history: ChatHistoryMessage[],
  onEvent: (event: ChatSseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${AI_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, history }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `AI service error (${response.status})`);
  }

  if (!response.body) {
    throw new Error("AI service returned an empty body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      // Flush leftover (stream may end without a trailing blank line)
      if (buffer.trim()) {
        consumeSseText(buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n"), onEvent);
      }
      break;
    }

    // sse-starlette uses CRLF; normalize so "\n\n" framing works
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      consumeSseText(part, onEvent);
    }
  }
}

export async function checkAiHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${AI_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}
