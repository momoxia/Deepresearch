import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { JSX } from "react";
import { FiX, FiPlus, FiTrash2, FiLoader } from "react-icons/fi";
import * as api from "../api/client";
import type { Folder, Project, SuggestFolderSpec, SuggestTree } from "../types";

interface Props {
  open: boolean;
  projects: Project[];
  existingFolders: Folder[];
  onClose: () => void;
  onApplied: () => void;
}

const UNFILED = "__unfiled__";
let tmpCounter = 0;
const nextTmpId = () => `tmp${++tmpCounter}`;

function existingToTree(folders: Folder[], projects: Project[]): SuggestTree {
  const idToTmp = new Map<number, string>();
  const folderSpecs: SuggestFolderSpec[] = folders.map((f) => {
    const t = nextTmpId();
    idToTmp.set(f.id, t);
    return {
      tmp_id: t,
      name: f.name,
      parent_tmp_id: null,
      sort_order: f.sort_order,
    };
  });
  folderSpecs.forEach((spec, i) => {
    const origId = folders[i].parent_id;
    spec.parent_tmp_id = origId && idToTmp.has(origId) ? idToTmp.get(origId)! : null;
  });
  const assignments = projects.map((p) => ({
    project_id: p.id,
    folder_tmp_id: p.folder_id && idToTmp.has(p.folder_id) ? idToTmp.get(p.folder_id)! : null,
  }));
  return { folders: folderSpecs, assignments };
}

interface TreeEditorProps {
  tree: SuggestTree | null;
  projects: Project[];
  onAddFolder: (parentTmp: string | null) => void;
  onRenameFolder: (tmpId: string, name: string) => void;
  onDeleteFolder: (tmpId: string) => void;
  onAssignProject: (projectId: number, folderTmp: string | null) => void;
}

const TreeEditor = memo(function TreeEditor({
  tree,
  projects,
  onAddFolder,
  onRenameFolder,
  onDeleteFolder,
  onAssignProject,
}: TreeEditorProps) {
  const projectsById = useMemo(() => {
    const m = new Map<number, Project>();
    projects.forEach((p) => m.set(p.id, p));
    return m;
  }, [projects]);

  const folders = tree?.folders ?? [];
  const assignments = tree?.assignments ?? [];
  const assignedMap = useMemo(() => {
    const map = new Map<string, number[]>();
    assignments.forEach((a) => {
      const key = a.folder_tmp_id ?? UNFILED;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(a.project_id);
    });
    projects.forEach((p) => {
      if (!assignments.some((a) => a.project_id === p.id)) {
        if (!map.has(UNFILED)) map.set(UNFILED, []);
        map.get(UNFILED)!.push(p.id);
      }
    });
    return map;
  }, [assignments, projects]);

  const rootFolders = folders.filter((f) => !f.parent_tmp_id);
  const childrenOf = (tmpId: string) => folders.filter((f) => f.parent_tmp_id === tmpId);
  const unfiledIds = assignedMap.get(UNFILED) ?? [];

  const renderFolder = (spec: SuggestFolderSpec, depth: number): JSX.Element => {
    const pids = assignedMap.get(spec.tmp_id) ?? [];
    return (
      <div key={spec.tmp_id} className="org-folder" style={{ marginLeft: depth * 16 }}>
        <div className="org-folder-row">
          <span className="org-folder-icon">📁</span>
          <input
            className="org-folder-name"
            value={spec.name}
            onChange={(e) => onRenameFolder(spec.tmp_id, e.target.value)}
          />
          <button
            className="org-icon-btn"
            title="新增子文件夹"
            onClick={() => onAddFolder(spec.tmp_id)}
          >
            <FiPlus size={12} />
          </button>
          <button
            className="org-icon-btn danger"
            title="删除文件夹"
            onClick={() => onDeleteFolder(spec.tmp_id)}
          >
            <FiTrash2 size={12} />
          </button>
        </div>
        {pids.map((pid) => {
          const p = projectsById.get(pid);
          if (!p) return null;
          return (
            <div key={pid} className="org-project-row" style={{ marginLeft: 16 }}>
              <span className="org-project-icon">💬</span>
              <span className="org-project-name" title={p.name}>
                {p.name}
              </span>
              <select
                className="org-folder-select"
                value={spec.tmp_id}
                onChange={(e) =>
                  onAssignProject(pid, e.target.value === UNFILED ? null : e.target.value)
                }
              >
                <option value={UNFILED}>（未分类）</option>
                {folders.map((f) => (
                  <option key={f.tmp_id} value={f.tmp_id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
        {childrenOf(spec.tmp_id).map((c) => renderFolder(c, depth + 1))}
      </div>
    );
  };

  return (
    <div className="org-tree-editor">
      <div className="org-tree-header">
        <span>预览与编辑</span>
        <button className="btn-secondary" onClick={() => onAddFolder(null)}>
          <FiPlus size={12} /> 新建根文件夹
        </button>
      </div>

      {folders.length === 0 && projects.length > 0 && (
        <div className="org-hint">
          尚未生成或创建文件夹。输入整理方式 → 生成建议，或手动新建。
        </div>
      )}

      {rootFolders.map((f) => renderFolder(f, 0))}

      {unfiledIds.length > 0 && (
        <div className="org-unfiled">
          <div className="org-folder-row">
            <span className="org-folder-icon">📦</span>
            <span className="org-folder-name">（未分类）</span>
          </div>
          {unfiledIds.map((pid) => {
            const p = projectsById.get(pid);
            if (!p) return null;
            return (
              <div key={pid} className="org-project-row" style={{ marginLeft: 16 }}>
                <span className="org-project-icon">💬</span>
                <span className="org-project-name" title={p.name}>
                  {p.name}
                </span>
                <select
                  className="org-folder-select"
                  value={UNFILED}
                  onChange={(e) =>
                    onAssignProject(
                      pid,
                      e.target.value === UNFILED ? null : e.target.value,
                    )
                  }
                >
                  <option value={UNFILED}>（未分类）</option>
                  {folders.map((f) => (
                    <option key={f.tmp_id} value={f.tmp_id}>
                      {f.name}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});

export default function OrganizeModal({
  open,
  projects,
  existingFolders,
  onClose,
  onApplied,
}: Props) {
  const instructionRef = useRef<HTMLTextAreaElement>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tree, setTree] = useState<SuggestTree | null>(null);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState("");
  const [hasInput, setHasInput] = useState(false);

  useEffect(() => {
    if (!open) {
      setTree(null);
      setRationale("");
      setError("");
      setLoading(false);
      setSaving(false);
      setHasInput(false);
      if (instructionRef.current) instructionRef.current.value = "";
    } else if (existingFolders.length > 0 && !tree) {
      setTree(existingToTree(existingFolders, projects));
    }
  }, [open, existingFolders, projects, tree]);

  const handleSuggest = async () => {
    const instruction = instructionRef.current?.value.trim() ?? "";
    if (!instruction) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.suggestFolders(instruction);
      setTree({ folders: res.folders, assignments: res.assignments });
      setRationale(res.rationale ?? "");
    } catch (e: any) {
      setError(e?.message ?? "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const addFolder = useCallback(
    (parentTmp: string | null) => {
      setTree((prev) => {
        if (!prev) {
          return {
            folders: [
              { tmp_id: nextTmpId(), name: "新文件夹", parent_tmp_id: parentTmp, sort_order: 0 },
            ],
            assignments: projects.map((p) => ({ project_id: p.id, folder_tmp_id: null })),
          };
        }
        return {
          ...prev,
          folders: [
            ...prev.folders,
            { tmp_id: nextTmpId(), name: "新文件夹", parent_tmp_id: parentTmp, sort_order: 0 },
          ],
        };
      });
    },
    [projects],
  );

  const renameFolder = useCallback((tmpId: string, name: string) => {
    setTree((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        folders: prev.folders.map((f) => (f.tmp_id === tmpId ? { ...f, name } : f)),
      };
    });
  }, []);

  const deleteFolder = useCallback((tmpId: string) => {
    setTree((prev) => {
      if (!prev) return prev;
      const toDelete = new Set<string>();
      const collect = (id: string) => {
        toDelete.add(id);
        prev.folders.filter((f) => f.parent_tmp_id === id).forEach((c) => collect(c.tmp_id));
      };
      collect(tmpId);
      return {
        folders: prev.folders.filter((f) => !toDelete.has(f.tmp_id)),
        assignments: prev.assignments.map((a) =>
          a.folder_tmp_id && toDelete.has(a.folder_tmp_id)
            ? { ...a, folder_tmp_id: null }
            : a,
        ),
      };
    });
  }, []);

  const assignProject = useCallback(
    (projectId: number, folderTmp: string | null) => {
      setTree((prev) => {
        if (!prev) {
          return {
            folders: [],
            assignments: projects.map((p) =>
              p.id === projectId
                ? { project_id: p.id, folder_tmp_id: folderTmp }
                : { project_id: p.id, folder_tmp_id: null },
            ),
          };
        }
        const exists = prev.assignments.find((a) => a.project_id === projectId);
        const updated = exists
          ? prev.assignments.map((a) =>
              a.project_id === projectId ? { ...a, folder_tmp_id: folderTmp } : a,
            )
          : [...prev.assignments, { project_id: projectId, folder_tmp_id: folderTmp }];
        return { ...prev, assignments: updated };
      });
    },
    [projects],
  );

  const handleSave = async () => {
    if (!tree) return;
    setSaving(true);
    setError("");
    try {
      const fullAssignments = projects.map((p) => {
        const exist = tree.assignments.find((a) => a.project_id === p.id);
        return exist ?? { project_id: p.id, folder_tmp_id: null };
      });
      await api.applyFolderTree({ folders: tree.folders, assignments: fullAssignments });
      onApplied();
      onClose();
    } catch (e: any) {
      setError(e?.message ?? "保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="org-modal-backdrop" onClick={onClose}>
      <div className="org-modal" onClick={(e) => e.stopPropagation()}>
        <div className="org-header">
          <h3>🗂 懒人动态文件夹</h3>
          <button className="org-close" onClick={onClose}>
            <FiX size={18} />
          </button>
        </div>

        <div className="org-body">
          <div className="org-prompt-row">
            <textarea
              ref={instructionRef}
              placeholder="描述整理方式，例如：按研究主题分类；或：学习 / 工作 / 生活 三类"
              defaultValue=""
              onChange={(e) => {
                const next = e.target.value.trim().length > 0;
                if (next !== hasInput) setHasInput(next);
              }}
              rows={2}
            />
            <button
              className="btn-primary"
              disabled={loading || !hasInput}
              onClick={handleSuggest}
            >
              {loading ? <FiLoader className="spin" size={14} /> : "生成建议"}
            </button>
          </div>

          {error && <div className="org-error">⚠ {error}</div>}
          {rationale && <div className="org-rationale">💡 {rationale}</div>}

          <TreeEditor
            tree={tree}
            projects={projects}
            onAddFolder={addFolder}
            onRenameFolder={renameFolder}
            onDeleteFolder={deleteFolder}
            onAssignProject={assignProject}
          />
        </div>

        <div className="org-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={saving || !tree}
          >
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
