import { FiExternalLink, FiGlobe, FiSearch } from "react-icons/fi";
import type { Source } from "../types";

interface Props {
  sources: Source[];
  visible: boolean;
}

export default function SourcesPanel({ sources, visible }: Props) {
  if (!visible) return null;

  return (
    <aside className="sources-panel">
      <div className="sources-header">
        <FiGlobe size={16} />
        <h3>浏览来源</h3>
        <span className="sources-count">{sources.length}</span>
      </div>

      {sources.length === 0 ? (
        <div className="sources-empty">暂无浏览记录</div>
      ) : (
        <ul className="sources-list">
          {sources.map((s, i) => (
            <li key={i} className="source-item">
              <div className="source-icon">
                {s.url.includes("google.com/search") ? (
                  <FiSearch size={14} />
                ) : (
                  <FiGlobe size={14} />
                )}
              </div>
              <div className="source-info">
                <a href={s.url} target="_blank" rel="noopener noreferrer">
                  {s.title}
                  <FiExternalLink size={10} style={{ marginLeft: 4 }} />
                </a>
                <span className="source-url">{s.url.length > 60 ? s.url.slice(0, 60) + "..." : s.url}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
