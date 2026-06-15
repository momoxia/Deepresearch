import { useEffect, useState } from "react";
import type { JSX } from "react";
import {
  FiFolder,
  FiMessageSquare,
  FiChevronRight,
  FiChevronDown,
  FiTrash2,
} from "react-icons/fi";
import type { Folder, Project } from "../types";

interface Props {
  folders: Folder[];
  projects: Project[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onDelete: (id: number, name: string) => void;
}

interface Node {
  folder: Folder;
  children: Node[];
  projects: Project[];
}

const EXPAND_KEY = "sidebar.expandedFolders";

function buildTree(
  folders: Folder[],
  projects: Project[],
): { roots: Node[]; unfiled: Project[] } {
  const byId = new Map<number, Node>();
  folders.forEach((f) => byId.set(f.id, { folder: f, children: [], projects: [] }));
  const roots: Node[] = [];
  folders.forEach((f) => {
    const node = byId.get(f.id)!;
    if (f.parent_id && byId.has(f.parent_id)) {
      byId.get(f.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  const unfiled: Project[] = [];
  projects.forEach((p) => {
    if (p.folder_id && byId.has(p.folder_id)) {
      byId.get(p.folder_id)!.projects.push(p);
    } else {
      unfiled.push(p);
    }
  });
  const sortRec = (n: Node) => {
    n.children.sort((a, b) => a.folder.sort_order - b.folder.sort_order);
    n.children.forEach(sortRec);
  };
  roots.sort((a, b) => a.folder.sort_order - b.folder.sort_order);
  roots.forEach(sortRec);
  return { roots, unfiled };
}

export default function FolderTree({
  folders,
  projects,
  activeId,
  onSelect,
  onDelete,
}: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(() => {
    try {
      const raw = localStorage.getItem(EXPAND_KEY);
      if (raw) return new Set(JSON.parse(raw));
    } catch {
      /* noop */
    }
    return new Set<number>();
  });

  useEffect(() => {
    localStorage.setItem(EXPAND_KEY, JSON.stringify(Array.from(expanded)));
  }, [expanded]);

  const toggle = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const { roots, unfiled } = buildTree(folders, projects);

  const renderProject = (p: Project, depth: number) => (
    <li
      key={`p-${p.id}`}
      className={`tree-project ${p.id === activeId ? "active" : ""}`}
      style={{ paddingLeft: 10 + depth * 14 }}
      onClick={() => onSelect(p.id)}
    >
      <FiMessageSquare size={13} />
      <span className="tree-name">{p.name}</span>
      <button
        className="delete-btn"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(p.id, p.name);
        }}
        title="删除对话"
      >
        <FiTrash2 size={12} />
      </button>
    </li>
  );

  const renderFolder = (n: Node, depth: number): JSX.Element => {
    const isOpen = expanded.has(n.folder.id);
    const count =
      n.projects.length +
      n.children.reduce((acc, c) => acc + countRecursive(c), 0);
    return (
      <li key={`f-${n.folder.id}`} className="tree-folder-group">
        <div
          className="tree-folder"
          style={{ paddingLeft: 10 + depth * 14 }}
          onClick={() => toggle(n.folder.id)}
        >
          {isOpen ? <FiChevronDown size={12} /> : <FiChevronRight size={12} />}
          <FiFolder size={13} />
          <span className="tree-name">{n.folder.name}</span>
          <span className="tree-count">{count}</span>
        </div>
        {isOpen && (
          <>
            {n.children.map((c) => renderFolder(c, depth + 1))}
            {n.projects.map((p) => renderProject(p, depth + 1))}
          </>
        )}
      </li>
    );
  };

  return (
    <ul className="folder-tree">
      {roots.map((n) => renderFolder(n, 0))}
      {unfiled.length > 0 && roots.length > 0 && (
        <li className="tree-divider">未分类</li>
      )}
      {unfiled.map((p) => renderProject(p, 0))}
      {roots.length === 0 && unfiled.length === 0 && (
        <li className="empty">暂无对话</li>
      )}
    </ul>
  );
}

function countRecursive(n: Node): number {
  return n.projects.length + n.children.reduce((a, c) => a + countRecursive(c), 0);
}
