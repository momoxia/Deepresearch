import { FiSearch, FiGlobe, FiDatabase, FiCpu, FiFileText, FiBookOpen, FiImage } from "react-icons/fi";
import type { ToolActivity, TaskActivity } from "../types";

interface Props {
  tools: ToolActivity[];
  tasks: TaskActivity[];
  statusText: string;
}

const TOOL_ICON: Record<string, React.ReactNode> = {
  "mcp__research-tools__web_search": <FiSearch size={14} />,
  "mcp__research-tools__web_search_scholar": <FiSearch size={14} />,
  "mcp__research-tools__web_fetch": <FiGlobe size={14} />,
  "mcp__research-tools__web_search_and_fetch": <FiSearch size={14} />,
  "mcp__research-tools__pdf_parse": <FiFileText size={14} />,
  "mcp__research-tools__pdf_read": <FiBookOpen size={14} />,
  "mcp__research-tools__pdf_grep": <FiSearch size={14} />,
  "mcp__research-tools__pdf_vision": <FiImage size={14} />,
  "mcp__research-tools__load_memory": <FiDatabase size={14} />,
  "mcp__research-tools__save_memory": <FiDatabase size={14} />,
  Agent: <FiCpu size={14} />,
};

export default function ToolActivityBar({ tools, tasks, statusText }: Props) {
  const hasActivity = tools.length > 0 || tasks.length > 0 || statusText;
  if (!hasActivity) return null;

  const runningTools = tools.filter((t) => t.status === "running");
  const recentDone = tools.filter((t) => t.status === "done").slice(-3);

  return (
    <div className="tool-activity-bar">
      {statusText && (
        <div className="activity-status">
          <span className="activity-pulse" />
          {statusText}
        </div>
      )}

      {runningTools.map((t) => (
        <div key={t.id} className="activity-item running">
          <span className="activity-spinner" />
          {TOOL_ICON[t.tool] || <FiCpu size={14} />}
          <span className="activity-label">{t.label}</span>
          <span className="activity-detail">
            {t.input.query ||
              t.input.url ||
              t.input.pattern ||
              t.input.summary ||
              t.input.doc_id ||
              t.input.agent ||
              t.input.school ||
              t.input.key ||
              ""}
          </span>
        </div>
      ))}

      {tasks
        .filter((tk) => tk.status === "running")
        .map((tk) => (
          <div key={tk.task_id} className="activity-item running task">
            <span className="activity-spinner" />
            <FiCpu size={14} />
            <span className="activity-label">{tk.description}</span>
          </div>
        ))}

      {recentDone.map((t) => (
        <div key={t.id} className="activity-item done">
          <span className="activity-check">✓</span>
          {TOOL_ICON[t.tool] || <FiCpu size={14} />}
          <span className="activity-label">{t.label}</span>
        </div>
      ))}
    </div>
  );
}
