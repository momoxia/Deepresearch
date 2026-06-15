import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { markdownRemarkPlugins, markdownRehypePlugins } from "../markdownPlugins";
import {
  FiSearch,
  FiGlobe,
  FiDatabase,
  FiCpu,
  FiChevronDown,
  FiChevronRight,
  FiExternalLink,
} from "react-icons/fi";
import type { ActivityCard } from "../types";

interface Props {
  activities: ActivityCard[];
  defaultExpanded?: boolean;
}

const KIND_ICON: Record<string, React.ReactNode> = {
  search: <FiSearch size={14} />,
  fetch: <FiGlobe size={14} />,
  cache: <FiDatabase size={14} />,
  agent: <FiCpu size={14} />,
  tool: <FiCpu size={14} />,
};

const KIND_COLOR: Record<string, string> = {
  search: "#6366f1",
  fetch: "#06b6d4",
  cache: "#22c55e",
  agent: "#f59e0b",
  tool: "#8b5cf6",
};

function CardItem({ card }: { card: ActivityCard }) {
  const isAgent = card.kind === "agent";
  const [open, setOpen] = useState(isAgent);
  const hasResult = !!card.summary;

  return (
    <div
      className={`activity-card kind-${card.kind} ${hasResult ? "has-result" : ""}`}
      style={{ borderLeftColor: KIND_COLOR[card.kind] || "#6366f1" }}
    >
      <div
        className="activity-card-header"
        onClick={() => hasResult && setOpen(!open)}
        style={{ cursor: hasResult ? "pointer" : "default" }}
      >
        <span className="activity-card-icon" style={{ color: KIND_COLOR[card.kind] }}>
          {KIND_ICON[card.kind] || <FiCpu size={14} />}
        </span>
        <span className="activity-card-label">{card.label}</span>
        <span className="activity-card-status">{card.detail}</span>
        {card.url && (
          <a
            className="activity-card-link"
            href={card.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
          >
            <FiExternalLink size={11} />
          </a>
        )}
        {hasResult && (
          <span className="activity-card-expand">
            {open ? <FiChevronDown size={12} /> : <FiChevronRight size={12} />}
          </span>
        )}
      </div>
      {!isAgent && card.detail && (
        <div className="activity-card-detail">{card.detail}</div>
      )}
      {open && card.summary && (
        <div className="activity-card-result-full">
          <ReactMarkdown
            remarkPlugins={markdownRemarkPlugins}
            rehypePlugins={markdownRehypePlugins}
          >
            {card.summary}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default function ActivityCards({ activities, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (!activities || activities.length === 0) return null;

  const searchCount = activities.filter((a) => a.kind === "search").length;
  const fetchCount = activities.filter((a) => a.kind === "fetch").length;
  const agentCount = activities.filter((a) => a.kind === "agent").length;

  const summaryParts: string[] = [];
  if (searchCount) summaryParts.push(`${searchCount} 次搜索`);
  if (fetchCount) summaryParts.push(`${fetchCount} 个网页`);
  if (agentCount) summaryParts.push(`${agentCount} 个子任务`);
  const withResults = activities.filter((a) => a.summary).length;

  return (
    <div className="activity-cards">
      <button
        className="activity-cards-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <FiChevronDown size={14} /> : <FiChevronRight size={14} />}
        <span className="activity-cards-summary">
          已完成 {summaryParts.join("、")}
          {withResults > 0 && !expanded && (
            <span className="activity-cards-hint">（点击展开查看详情）</span>
          )}
        </span>
        <span className="activity-cards-count">{activities.length}</span>
      </button>

      {expanded && (
        <div className="activity-cards-list">
          {activities.map((card) => (
            <CardItem key={card.id} card={card} />
          ))}
        </div>
      )}
    </div>
  );
}
