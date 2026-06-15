import { Fragment, memo, useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { markdownRemarkPlugins, markdownRehypePlugins } from "../markdownPlugins";
import { FiSend, FiSquare, FiDatabase } from "react-icons/fi";
import ToolActivityBar from "./ToolActivityBar";
import ActivityCards from "./ActivityCards";
import ArtifactCard from "./ArtifactCard";
import type { ChatMessage, ToolActivity, TaskActivity } from "../types";
import { formatZhWallClock } from "../time";

const ARTIFACT_MARKER = /\[artifact:([a-f0-9]{6,})\]/g;

function renderWithArtifacts(content: string) {
  ARTIFACT_MARKER.lastIndex = 0;
  const parts: Array<{ kind: "text"; text: string } | { kind: "artifact"; id: string }> = [];
  let cursor = 0;
  let m: RegExpExecArray | null;
  while ((m = ARTIFACT_MARKER.exec(content)) !== null) {
    if (m.index > cursor) {
      parts.push({ kind: "text", text: content.slice(cursor, m.index) });
    }
    parts.push({ kind: "artifact", id: m[1] });
    cursor = m.index + m[0].length;
  }
  if (cursor < content.length) {
    parts.push({ kind: "text", text: content.slice(cursor) });
  }
  if (parts.length === 0) parts.push({ kind: "text", text: content });
  return parts;
}

interface ContentWithArtifactsProps {
  content: string;
  openArtifactId: string | null;
  onOpenArtifact: (id: string) => void;
}

function ContentWithArtifacts({
  content,
  openArtifactId,
  onOpenArtifact,
}: ContentWithArtifactsProps) {
  const parts = renderWithArtifacts(content);
  return (
    <>
      {parts.map((p, i) =>
        p.kind === "artifact" ? (
          <ArtifactCard
            key={`a-${p.id}-${i}`}
            artifactId={p.id}
            isOpen={openArtifactId === p.id}
            onOpen={onOpenArtifact}
          />
        ) : (
          <Fragment key={`t-${i}`}>
            <ReactMarkdown
              remarkPlugins={markdownRemarkPlugins}
              rehypePlugins={markdownRehypePlugins}
            >
              {p.text || " "}
            </ReactMarkdown>
          </Fragment>
        ),
      )}
    </>
  );
}

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  projectName: string;
  streamingText: string;
  toolActivities: ToolActivity[];
  taskActivities: TaskActivity[];
  statusText: string;
  onSend: (text: string) => void;
  onStop: () => void;
  onToggleMemory?: () => void;
  showMemory?: boolean;
  openArtifactId: string | null;
  onOpenArtifact: (id: string) => void;
}

/**
 * Typewriter that only animates once when `content` first arrives,
 * then stays static. Tracks what's already been revealed so appending
 * new text doesn't restart the animation.
 */
function TypewriterMarkdown({
  content,
  animate,
  openArtifactId,
  onOpenArtifact,
}: {
  content: string;
  animate: boolean;
  openArtifactId: string | null;
  onOpenArtifact: (id: string) => void;
}) {
  const [displayed, setDisplayed] = useState(animate ? "" : content);
  const idxRef = useRef(animate ? 0 : content.length);

  useEffect(() => {
    if (!animate) {
      setDisplayed(content);
      idxRef.current = content.length;
      return;
    }
    if (idxRef.current >= content.length) {
      setDisplayed(content);
      return;
    }
    const timer = setInterval(() => {
      idxRef.current = Math.min(idxRef.current + 6, content.length);
      setDisplayed(content.slice(0, idxRef.current));
      if (idxRef.current >= content.length) clearInterval(timer);
    }, 10);
    return () => clearInterval(timer);
  }, [content, animate]);

  return (
    <ContentWithArtifacts
      content={displayed || " "}
      openArtifactId={openArtifactId}
      onOpenArtifact={onOpenArtifact}
    />
  );
}

const MemoMarkdown = memo(function MemoMarkdown({
  content,
  openArtifactId,
  onOpenArtifact,
}: {
  content: string;
  openArtifactId: string | null;
  onOpenArtifact: (id: string) => void;
}) {
  return (
    <ContentWithArtifacts
      content={content}
      openArtifactId={openArtifactId}
      onOpenArtifact={onOpenArtifact}
    />
  );
});

export default function ChatPanel({
  messages,
  loading,
  projectName,
  streamingText,
  toolActivities,
  taskActivities,
  statusText,
  onSend,
  onStop,
  onToggleMemory,
  showMemory,
  openArtifactId,
  onOpenArtifact,
}: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastScrollRef = useRef(0);

  const scrollToBottom = useCallback(() => {
    const now = Date.now();
    if (now - lastScrollRef.current < 100) return;
    lastScrollRef.current = now;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages.length, loading, scrollToBottom]);

  useEffect(() => {
    if (streamingText || toolActivities.length > 0) scrollToBottom();
  }, [streamingText, toolActivities.length, scrollToBottom]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    onSend(text);
  };

  const lastMsgIdx = messages.length - 1;

  return (
    <main className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-titles">
          <h3>{projectName}</h3>
        </div>
        {onToggleMemory && (
          <button
            className={`memory-toggle-btn ${showMemory ? "active" : ""}`}
            onClick={onToggleMemory}
            title="记忆管理"
          >
            <FiDatabase size={16} />
            <span>记忆</span>
          </button>
        )}
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !loading && (
          <div className="empty-chat">
            <p>开始研究对话</p>
            <p className="hint">
              例如："总结近一年某某话题的主流观点并给出来源" 或 "对比 A 与 B 方案的公开数据"
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-avatar">
              {msg.role === "user" ? "👤" : "🤖"}
            </div>
            <div className="message-body">
              {msg.role === "assistant" && msg.activities && msg.activities.length > 0 && (
                <ActivityCards
                  activities={msg.activities}
                  defaultExpanded={i === lastMsgIdx && !msg.created_at}
                />
              )}
              {msg.role === "assistant" ? (
                i === lastMsgIdx && !loading && !msg.created_at && !msg._streamed ? (
                  <TypewriterMarkdown
                    content={msg.content}
                    animate
                    openArtifactId={openArtifactId}
                    onOpenArtifact={onOpenArtifact}
                  />
                ) : (
                  <MemoMarkdown
                    content={msg.content}
                    openArtifactId={openArtifactId}
                    onOpenArtifact={onOpenArtifact}
                  />
                )
              ) : (
                <p>{msg.content}</p>
              )}
              {msg.created_at && (
                <span className="message-time">
                  {formatZhWallClock(msg.created_at)}
                </span>
              )}
            </div>
          </div>
        ))}

        {/* Live streaming area — direct render, no typewriter */}
        {loading && (
          <div className="message assistant streaming-message">
            <div className="message-avatar">🤖</div>
            <div className="message-body">
              <ToolActivityBar
                tools={toolActivities}
                tasks={taskActivities}
                statusText={statusText}
              />
              {streamingText ? (
                <div className="streaming-text">
                  <ContentWithArtifacts
                    content={streamingText}
                    openArtifactId={openArtifactId}
                    onOpenArtifact={onOpenArtifact}
                  />
                  <span className="streaming-cursor" />
                </div>
              ) : (
                !statusText && toolActivities.length === 0 && taskActivities.length === 0 && (
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                    <em>正在思考...</em>
                  </div>
                )
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-bar">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={loading ? "AI 正在处理..." : "输入消息，Enter 发送，Shift+Enter 换行"}
          disabled={loading}
          rows={1}
        />
        {loading ? (
          <button className="stop-btn" onClick={onStop} title="停止生成">
            <FiSquare size={18} />
          </button>
        ) : (
          <button className="send-btn" onClick={handleSend} disabled={!input.trim()}>
            <FiSend size={18} />
          </button>
        )}
      </div>
    </main>
  );
}
