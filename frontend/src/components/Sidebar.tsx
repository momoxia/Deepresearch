import { useEffect, useState } from "react";
import {
  FiPlus,
  FiMessageSquare,
  FiSearch,
  FiTrash2,
  FiChevronsLeft,
  FiChevronsRight,
} from "react-icons/fi";
import FolderTree from "./FolderTree";
import type { Folder, Project } from "../types";

interface Props {
  projects: Project[];
  folders: Folder[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onCreate: () => void;
  onDelete: (id: number) => void;
  onOrganize?: () => void;
}

const STORAGE_KEY = "sidebar.collapsed";

export default function Sidebar({
  projects,
  folders,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  onOrganize,
}: Props) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    return localStorage.getItem(STORAGE_KEY) === "1";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const handleDelete = (e: React.MouseEvent, id: number, projectName: string) => {
    e.stopPropagation();
    if (confirm(`确定删除「${projectName}」及其对话与记忆吗？`)) {
      onDelete(id);
    }
  };

  const confirmAndDelete = (id: number, projectName: string) => {
    if (confirm(`确定删除「${projectName}」及其对话与记忆吗？`)) {
      onDelete(id);
    }
  };

  const hasFolders = folders.length > 0;

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-header">
        {!collapsed && <FiSearch size={18} />}
        {!collapsed && <h2>Deep Research</h2>}
        <button
          className="sidebar-toggle"
          onClick={() => setCollapsed((v) => !v)}
          title={collapsed ? "展开侧栏" : "收起侧栏"}
        >
          {collapsed ? <FiChevronsRight size={16} /> : <FiChevronsLeft size={16} />}
        </button>
      </div>

      <div className="sidebar-section">
        <button className="new-chat-btn" onClick={onCreate} title="新建对话">
          <FiPlus size={16} />
          <span>新建对话</span>
        </button>

        {onOrganize && (
          <button
            className="organize-btn"
            onClick={onOrganize}
            title="基于 AI 整理对话到文件夹"
          >
            <span>🗂</span>
            <span>智能整理</span>
          </button>
        )}

        {hasFolders ? (
          <FolderTree
            folders={folders}
            projects={projects}
            activeId={activeId}
            onSelect={onSelect}
            onDelete={confirmAndDelete}
          />
        ) : (
          <ul className="student-list">
            {projects.map((p) => (
              <li
                key={p.id}
                className={p.id === activeId ? "active" : ""}
                onClick={() => onSelect(p.id)}
              >
                <FiMessageSquare size={14} />
                <div className="student-info">
                  <span className="student-name">{p.name}</span>
                </div>
                <button
                  className="delete-btn"
                  onClick={(e) => handleDelete(e, p.id, p.name)}
                  title="删除对话"
                >
                  <FiTrash2 size={13} />
                </button>
              </li>
            ))}
            {projects.length === 0 && (
              <li className="empty">暂无对话，点击上方新建</li>
            )}
          </ul>
        )}
      </div>
    </aside>
  );
}
