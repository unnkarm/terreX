"use client";

import { useEffect, useMemo, useState } from "react";
import { ChatContext, sendChatMessage, ChatCitation, getSystemStatus } from "@/lib/api";

interface Props {
  context: ChatContext;
  fallbackData?: {
    changeType?: string;
    confidence?: number;
    date1?: string;
    date2?: string;
    maskState?: string;
    sceneId?: string;
    sensor?: string;
  };
  onCitationClick?: (citationId: string) => void;
}

type ChatMessage = { role: "user" | "assistant"; content: string; citations?: ChatCitation[] };

function summaryFromData(data?: Props["fallbackData"]) {
  if (!data) return "No structured evidence is available for this context.";
  const confidence = typeof data.confidence === "number"
    ? `${data.confidence <= 1 ? (data.confidence * 100).toFixed(1) : data.confidence.toFixed(1)}%`
    : "unknown";
  return `This tile was flagged as ${data.changeType || "unclassified"} with ${confidence} confidence. Detected between ${data.date1 || "unknown"} and ${data.date2 || "unknown"}. Quality score: ${data.maskState || "unknown"}. Source: ${data.sceneId || "unknown"} (${data.sensor || "unknown"}).`;
}

export default function ChatPanel({ context, fallbackData, onCitationClick }: Props) {
  const summary = useMemo(() => summaryFromData(fallbackData), [fallbackData]);
  const contextKey = useMemo(() => JSON.stringify(context), [context]);
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: summary }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [chatState, setChatState] = useState<{ available: boolean; message?: string } | null>(null);
  const conversationId = useMemo(() => `terrex-${Date.now()}-${Math.random().toString(36).slice(2)}`, [contextKey]);

  useEffect(() => {
    setMessages([{ role: "assistant", content: summary }]);
    setInput("");
  }, [contextKey, summary]);

  useEffect(() => {
    let mounted = true;
    getSystemStatus()
      .then(status => mounted && setChatState({
        available: status.chat?.available ?? status.chat_available !== false,
        message: status.chat?.error || (status.chat?.ram_available === false ? "Local chat is paused while available RAM is below the safety threshold." : undefined),
      }))
      .catch(() => mounted && setChatState({ available: false, message: "Local Ollama status could not be reached." }));
    return () => { mounted = false; };
  }, []);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setLoading(true);
    try {
      const res = await sendChatMessage(userMsg, context, conversationId);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.response || summary,
        citations: res.citations,
      }]);
      if (res.fallback && res.status) setChatState({ available: false, message: res.status.error || "Showing structured evidence only." });
    } catch (err) {
      setMessages(prev => [...prev, { role: "assistant", content: `Unable to answer from the local evidence: ${String(err)}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[min(420px,calc(100vh-11rem))] min-h-64 flex-col overflow-hidden rounded-sm border border-neutral-800 bg-black/70">
      {chatState?.available === false && (
        <div className="border-b border-amber-900/50 bg-amber-950/20 px-3 py-2 text-[10px] text-amber-300">
          {chatState.message || "Local chat is unavailable. Showing structured evidence only."}
        </div>
      )}
      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
            <div className={`max-w-[90%] rounded-sm border px-3 py-2 text-[11px] leading-relaxed ${msg.role === "user" ? "border-blue-500/40 bg-blue-950/70 text-blue-50" : "border-neutral-800 bg-neutral-900 text-neutral-200"}`}>
              {msg.content}
            </div>
            {msg.citations && msg.citations.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {msg.citations.map((citation, idx) => (
                  <button
                    key={`${citation.type}-${citation.id}-${idx}`}
                    type="button"
                    onClick={() => onCitationClick?.(citation.id)}
                    className="rounded-sm border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 font-mono text-[9px] text-neutral-400 transition-colors hover:border-blue-500/60 hover:text-blue-300"
                    title={citation.field ? `Evidence field: ${citation.field}` : "Open evidence"}
                  >
                    {citation.type}:{citation.id.slice(0, 8)}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-blue-300"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" /> Thinking...</div>}
      </div>
      <div className="flex gap-2 border-t border-neutral-800 p-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleSend()}
          placeholder={chatState === null ? "Checking local Ollama..." : chatState.available === false ? "Structured summary mode" : "Ask about this evidence..."}
          disabled={chatState?.available !== true}
          className="min-w-0 flex-1 rounded-sm border border-neutral-700 bg-neutral-950 px-2.5 py-2 text-[11px] text-white outline-none placeholder:text-neutral-600 focus:border-blue-500/80 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={loading || !input.trim() || chatState?.available !== true}
          className="rounded-sm border border-blue-500/70 bg-blue-600/90 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
