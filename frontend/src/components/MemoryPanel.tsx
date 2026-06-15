import { useCallback, useEffect, useState } from "react";
import {
  FiTrash2,
  FiEdit3,
  FiPlus,
  FiCheck,
  FiX,
  FiRefreshCw,
  FiChevronDown,
  FiChevronRight,
  FiDatabase,
  FiHeart,
  FiBookOpen,
  FiSettings,
  FiArchive,
} from "react-icons/fi";
import type { MemoryItem } from "../api/client";
import * as api from "../api/client";
import { formatZhDate } from "../time";

interface Props {
  projectId: number;
  visible: boolean;
}

const CATEGORY_META: Record<
  string,
  { label: string; icon: React.ReactNode; color: string }
> = {
  semantic: { label: "客观事实", icon: <FiDatabase size={13} />, color: "#3b82f6" },
  preference: { label: "个人偏好", icon: <FiHeart size={13} />, color: "#ec4899" },
  procedural: { label: "决策模式", icon: <FiSettings size={13} />, color: "#f59e0b" },
  episodic: { label: "对话摘要", icon: <FiBookOpen size={13} />, color: "#10b981" },
  long: { label: "长期记忆", icon: <FiDatabase size={13} />, color: "#6366f1" },
  medium: { label: "中期记忆", icon: <FiBookOpen size={13} />, color: "#8b5cf6" },
};

function getCategoryMeta(cat: string) {
  return CATEGORY_META[cat] || { label: cat, icon: <FiDatabase size={13} />, color: "#64748b" };
}

export default function MemoryPanel({ projectId, visible }: Props) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [adding, setAdding] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newCategory, setNewCategory] = useState("semantic");

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getProjectMemory(projectId, showArchived);
      setMemories(data);
      const cats = new Set(data.map((m) => m.category));
      setExpandedCats(cats);
    } catch (e) {
      console.error("Failed to load memories", e);
    } finally {
      setLoading(false);
    }
  }, [projectId, showArchived]);

  useEffect(() => {
    if (visible && projectId) loadMemories();
  }, [visible, projectId, loadMemories]);

  const handleDelete = async (memId: number) => {
    if (!confirm("确定删除这条记忆？")) return;
    try {
      await api.deleteMemory(projectId, memId);
      setMemories((prev) => prev.filter((m) => m.id !== memId));
    } catch (e) {
      console.error(e);
    }
  };

  const handleEditStart = (mem: MemoryItem) => {
    setEditingId(mem.id);
    setEditValue(typeof mem.value === "string" ? mem.value : JSON.stringify(mem.value));
  };

  const handleEditSave = async (memId: number) => {
    try {
      await api.updateMemory(projectId, memId, { value: editValue });
      setMemories((prev) =>
        prev.map((m) => (m.id === memId ? { ...m, value: editValue } : m)),
      );
      setEditingId(null);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAdd = async () => {
    if (!newKey.trim() || !newValue.trim()) return;
    try {
      await api.addMemory(projectId, {
        key: newKey.trim(),
        value: newValue.trim(),
        category: newCategory,
      });
      setAdding(false);
      setNewKey("");
      setNewValue("");
      await loadMemories();
    } catch (e) {
      console.error(e);
    }
  };

  const toggleCat = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  if (!visible) return null;

  const grouped: Record<string, MemoryItem[]> = {};
  for (const m of memories) {
    (grouped[m.category] ||= []).push(m);
  }

  const categoryOrder = ["semantic", "preference", "procedural", "episodic", "long", "medium"];
  const sortedCats = Object.keys(grouped).sort(
    (a, b) => (categoryOrder.indexOf(a) === -1 ? 99 : categoryOrder.indexOf(a)) -
              (categoryOrder.indexOf(b) === -1 ? 99 : categoryOrder.indexOf(b)),
  );

  return (
    <aside className="memory-panel">
      <div className="memory-panel-header">
        <h3>记忆管理</h3>
        <div className="memory-panel-actions">
          <button className="memory-btn-icon" onClick={loadMemories} title="刷新">
            <FiRefreshCw size={14} className={loading ? "spin" : ""} />
          </button>
          <button
            className={`memory-btn-icon ${showArchived ? "active" : ""}`}
            onClick={() => setShowArchived(!showArchived)}
            title="显示已归档"
          >
            <FiArchive size={14} />
          </button>
          <button className="memory-btn-icon" onClick={() => setAdding(!adding)} title="添加记忆">
            <FiPlus size={14} />
          </button>
        </div>
      </div>

      {adding && (
        <div className="memory-add-form">
          <select value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
            <option value="semantic">客观事实</option>
            <option value="preference">个人偏好</option>
            <option value="procedural">决策模式</option>
            <option value="episodic">对话摘要</option>
          </select>
          <input
            placeholder="Key (英文下划线)"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
          />
          <input
            placeholder="Value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
          />
          <div className="memory-add-btns">
            <button className="memory-btn-save" onClick={handleAdd}>
              <FiCheck size={12} /> 保存
            </button>
            <button className="memory-btn-cancel" onClick={() => setAdding(false)}>
              <FiX size={12} /> 取消
            </button>
          </div>
        </div>
      )}

      <div className="memory-panel-body">
        {memories.length === 0 && !loading && (
          <div className="memory-empty">暂无记忆数据</div>
        )}
        {sortedCats.map((cat) => {
          const meta = getCategoryMeta(cat);
          const items = grouped[cat];
          const expanded = expandedCats.has(cat);

          return (
            <div key={cat} className="memory-category">
              <div className="memory-category-header" onClick={() => toggleCat(cat)}>
                {expanded ? <FiChevronDown size={14} /> : <FiChevronRight size={14} />}
                <span className="memory-category-icon" style={{ color: meta.color }}>
                  {meta.icon}
                </span>
                <span className="memory-category-label">{meta.label}</span>
                <span className="memory-category-count">{items.length}</span>
              </div>

              {expanded && (
                <div className="memory-items">
                  {items.map((mem) => (
                    <div
                      key={mem.id}
                      className={`memory-item ${mem.archived ? "archived" : ""}`}
                    >
                      <div className="memory-item-header">
                        <span className="memory-item-key">{mem.key}</span>
                        <span
                          className="memory-item-importance"
                          style={{
                            backgroundColor: `hsl(${mem.importance * 120}, 70%, 90%)`,
                            color: `hsl(${mem.importance * 120}, 70%, 30%)`,
                          }}
                        >
                          {(mem.importance * 100).toFixed(0)}%
                        </span>
                      </div>

                      {editingId === mem.id ? (
                        <div className="memory-item-edit">
                          <input
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            autoFocus
                          />
                          <button onClick={() => handleEditSave(mem.id)}>
                            <FiCheck size={12} />
                          </button>
                          <button onClick={() => setEditingId(null)}>
                            <FiX size={12} />
                          </button>
                        </div>
                      ) : (
                        <div className="memory-item-value">
                          {typeof mem.value === "string" ? mem.value : JSON.stringify(mem.value)}
                        </div>
                      )}

                      <div className="memory-item-meta">
                        <span className="memory-item-source">{mem.source}</span>
                        <span className="memory-item-access">
                          访问 {mem.access_count}次
                        </span>
                        {mem.updated_at && (
                          <span className="memory-item-time">
                            {formatZhDate(mem.updated_at)}
                          </span>
                        )}
                        <div className="memory-item-actions">
                          <button onClick={() => handleEditStart(mem)} title="编辑">
                            <FiEdit3 size={12} />
                          </button>
                          <button onClick={() => handleDelete(mem.id)} title="删除">
                            <FiTrash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
