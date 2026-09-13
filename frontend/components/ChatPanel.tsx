import { useEffect, useMemo, useState, useRef } from "react";
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

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations?: ChatCitation[];
  latencyMs?: number;
};

function summaryFromData(data?: Props["fallbackData"]) {
  if (!data) return "Terra ready. Ask any question about this target.";
  const confidence = typeof data.confidence === "number"
    ? `${data.confidence <= 1 ? (data.confidence * 100).toFixed(1) : data.confidence.toFixed(1)}%`
    : "unknown";
  return `Terra initialized. Target detected as ${data.changeType || "candidate"} (${confidence} confidence) from ${data.sensor || "Sentinel-2"}. Ask any question about anomalies, spectral indices, or observations.`;
}

const QUICK_PROMPTS = [
  { label: "Provenance & QA", query: "What is the sensor provenance, resolution, and data quality?" },
  { label: "Spectral Indices", query: "Calculate the physical NDVI, NDWI, and NDBI spectral indices for this tile." },
  { label: "Change Analysis", query: "Explain the detected change, confidence, and false alarm risk." },
];

export default function ChatPanel({ context, fallbackData, onCitationClick }: Props) {
  const summary = useMemo(() => summaryFromData(fallbackData), [fallbackData]);
  const storageKey = useMemo(() => {
    const id = context.tile_id || context.change_id || context.cluster_id || "global";
    return `terrex_terra_chat_${id}`;
  }, [context]);

  const conversationId = useMemo(() => {
    const id = context.tile_id || context.change_id || context.cluster_id || "global";
    return `terrex-conv-${id}`;
  }, [context]);

  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length > 0) return parsed;
        }
      } catch (e) {
        // fallback to initial message
      }
    }
    return [
      {
        id: "init-0",
        role: "assistant",
        content: summary,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ];
  });

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [chatState, setChatState] = useState<{ available: boolean; message?: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync / load saved messages whenever the targeted tile or context changes
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setMessages(parsed);
            setInput("");
            return;
          }
        }
      } catch (e) {
        // fallback
      }
    }
    setMessages([
      {
        id: `init-${Date.now()}`,
        role: "assistant",
        content: summary,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
    setInput("");
  }, [storageKey, summary]);

  // Persist conversation messages to localStorage on every update
  useEffect(() => {
    if (typeof window !== "undefined" && messages.length > 0) {
      try {
        localStorage.setItem(storageKey, JSON.stringify(messages));
      } catch (e) {
        // ignore quota errors
      }
    }
  }, [storageKey, messages]);

  useEffect(() => {
    let mounted = true;
    getSystemStatus()
      .then((status) => {
        if (mounted) {
          setChatState({
            available: status.chat?.available ?? status.chat_available !== false,
            message: status.chat?.error || undefined,
          });
        }
      })
      .catch(() => {
        if (mounted) {
          setChatState({ available: false, message: "Air-Gapped" });
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async (customQuery?: string) => {
    const textToSend = (customQuery || input).trim();
    if (!textToSend || loading) return;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: "user",
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    const startTime = performance.now();
    try {
      const res = await sendChatMessage(textToSend, context, conversationId);
      const elapsed = Math.round(performance.now() - startTime);

      setMessages((prev) => [
        ...prev,
        {
          id: `ast-${Date.now()}`,
          role: "assistant",
          content: res.response || summary,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          citations: res.citations,
          latencyMs: res.latency_ms || elapsed,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `Unable to complete query: ${err.message || String(err)}.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const clearChat = () => {
    if (typeof window !== "undefined") {
      try {
        localStorage.removeItem(storageKey);
      } catch (e) {
        // ignore
      }
    }
    setMessages([
      {
        id: `init-${Date.now()}`,
        role: "assistant",
        content: summary,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  };

  return (
    <div className="flex h-full min-h-[440px] flex-col overflow-hidden rounded border border-neutral-800 bg-neutral-950 font-mono select-none">
      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900/90 px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]"></span>
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-200">
            Terra Assistant
          </span>
          <span className="text-[9px] px-1.5 py-0.2 rounded bg-neutral-950 border border-neutral-800 text-emerald-400 font-mono font-bold">
            {chatState?.available ? "Grounded AI" : "Air-Gapped Local"}
          </span>
        </div>

        <button
          onClick={clearChat}
          className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 uppercase tracking-wider font-bold transition-colors"
          title="Reset conversation"
        >
          Reset
        </button>
      </div>

      {/* Quick Prompt Chips */}
      <div className="flex items-center gap-1.5 border-b border-neutral-800/80 bg-neutral-900/40 px-3 py-1.5 overflow-x-auto scrollbar-none">
        <span className="text-[9px] font-mono uppercase text-neutral-500 mr-0.5 flex-shrink-0 font-bold">
          Explore:
        </span>
        {QUICK_PROMPTS.map((p, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => handleSend(p.query)}
            disabled={loading}
            className="px-2 py-0.5 rounded bg-neutral-900 border border-neutral-800 text-[10px] text-neutral-300 hover:text-emerald-300 hover:border-neutral-700 transition-all font-mono whitespace-nowrap flex-shrink-0 font-medium"
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 space-y-3 overflow-y-auto p-3 text-xs">
        {messages.map((msg) => {
          const isUser = msg.role === "user";

          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isUser ? "items-end" : "items-start"} animate-fadeIn`}
            >
              {/* Sender & Timestamp Header */}
              <div className="flex items-center gap-1.5 mb-1 px-1 text-[9px] font-mono text-neutral-500">
                <span>{isUser ? "Analyst" : "Terra"}</span>
                <span>&middot;</span>
                <span>{msg.timestamp}</span>
                {msg.latencyMs !== undefined && (
                  <span className="text-neutral-500">({msg.latencyMs}ms)</span>
                )}
              </div>

              {/* Message Box */}
              <div
                className={`relative group max-w-[94%] rounded px-3 py-2 leading-relaxed font-sans ${
                  isUser
                    ? "border border-neutral-700 bg-neutral-800 text-neutral-100"
                    : "border border-neutral-800 bg-neutral-900/80 text-neutral-200"
                }`}
              >
                {/* Grounded Answer Text */}
                <div className="whitespace-pre-wrap text-[11px] select-text">
                  {msg.content}
                </div>

                {/* Copy Button */}
                <button
                  onClick={() => copyToClipboard(msg.content, msg.id)}
                  className="absolute right-1.5 top-1.5 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded bg-black/60 border border-neutral-700 text-neutral-400 hover:text-white text-[9px] font-mono"
                  title="Copy message"
                >
                  {copiedId === msg.id ? "✓" : "📋"}
                </button>

                {/* Citations & Evidence Links */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-2 pt-1.5 border-t border-neutral-800 flex flex-wrap gap-1">
                    <span className="text-[9px] font-mono uppercase text-neutral-500 self-center mr-0.5 font-bold">
                      Sources:
                    </span>
                    {msg.citations.map((citation, idx) => (
                      <button
                        key={`${citation.type}-${citation.id}-${idx}`}
                        type="button"
                        onClick={() => onCitationClick?.(citation.id)}
                        className="rounded px-1.5 py-0.5 font-mono text-[9px] bg-neutral-950 border border-neutral-800 text-emerald-400 hover:border-neutral-600 hover:text-white transition-all flex items-center gap-1 font-bold"
                        title={citation.field ? `Field: ${citation.field}` : "Jump to entity"}
                      >
                        <span className="text-neutral-500">{citation.type}:</span>
                        <span>{citation.id.slice(0, 8)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Minimal Clean Loading Indicator */}
        {loading && (
          <div className="flex items-center gap-2 p-2.5 rounded border border-neutral-800/80 bg-neutral-900/50 text-[10px] font-mono text-neutral-400">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
            <span>Terra is analyzing target evidence...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="flex items-center gap-2 border-t border-neutral-800 bg-neutral-900/80 p-2.5"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Terra about this target..."
          disabled={loading}
          className="flex-1 rounded bg-neutral-950 border border-neutral-800 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-500 focus:border-neutral-600 focus:outline-none font-sans"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded bg-neutral-800 px-3 py-1.5 font-mono text-[10px] font-bold text-neutral-200 hover:bg-neutral-700 disabled:opacity-40 transition-colors uppercase tracking-wider"
        >
          Send
        </button>
      </form>
    </div>
  );
}
