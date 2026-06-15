import {
  SandpackCodeEditor,
  SandpackLayout,
  SandpackPreview,
  SandpackProvider,
  useSandpack,
} from "@codesandbox/sandpack-react";
import { nightOwl } from "@codesandbox/sandpack-themes";
import { useEffect, useRef, useState } from "react";
import {
  FiCheck,
  FiCode,
  FiCopy,
  FiDownload,
  FiEye,
  FiRefreshCw,
  FiX,
} from "react-icons/fi";
import * as api from "../api/client";
import type { Artifact } from "../types";

interface Props {
  artifactId: string;
  widthPct: number;
  onWidthChange: (pct: number) => void;
  onClose: () => void;
}

type Tab = "preview" | "code";

const DEPS = {
  recharts: "^2.12.0",
  "lucide-react": "^0.400.0",
};

const BODY_CSS = `html, body, #root {
  margin: 0;
  padding: 0;
  min-height: 100vh;
  background: #0c0a09;
  color: #fafaf9;
  -webkit-font-smoothing: antialiased;
}`;

const MIN_PCT = 30;
const MAX_PCT = 70;

function RefreshButton() {
  const { sandpack } = useSandpack();
  return (
    <button
      type="button"
      className="artifact-action"
      title="刷新预览"
      onClick={(e) => {
        e.stopPropagation();
        sandpack.runSandpack();
      }}
    >
      <FiRefreshCw size={13} />
    </button>
  );
}

export default function ArtifactPanel({
  artifactId,
  widthPct,
  onWidthChange,
  onClose,
}: Props) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("preview");
  const [copied, setCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const copyTimer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setArtifact(null);
    setError(null);
    setTab("preview");
    api
      .getArtifact(artifactId)
      .then((data) => {
        if (!cancelled) setArtifact(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  useEffect(
    () => () => {
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
    },
    [],
  );

  const handleCopy = async () => {
    if (!artifact) return;
    try {
      await navigator.clipboard.writeText(artifact.code);
      setCopied(true);
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be blocked */
    }
  };

  const handleDownload = () => {
    if (!artifact) return;
    const blob = new Blob([artifact.code], { type: "text/javascript" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.title || artifactId}.jsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDragStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    const startX = e.clientX;
    const startPct = widthPct;
    const vw = window.innerWidth;

    const onMove = (ev: MouseEvent) => {
      const dxPct = ((startX - ev.clientX) / vw) * 100;
      const next = Math.max(MIN_PCT, Math.min(MAX_PCT, startPct + dxPct));
      onWidthChange(next);
    };
    const onUp = () => {
      setDragging(false);
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  };

  const title = artifact?.title || "交互式可视化";

  return (
    <aside
      className={`artifact-panel ${dragging ? "dragging" : ""}`}
      style={{ width: `${widthPct}%` }}
    >
      <div
        className="artifact-drag-handle"
        onMouseDown={handleDragStart}
        title="拖动调整宽度"
      />
      {error ? (
        <>
          <div className="artifact-panel-header">
            <span className="artifact-panel-title">🧩 {title}</span>
            <button
              type="button"
              className="artifact-action"
              title="关闭"
              onClick={onClose}
            >
              <FiX size={14} />
            </button>
          </div>
          <div className="artifact-panel-error">加载失败: {error}</div>
        </>
      ) : !artifact ? (
        <>
          <div className="artifact-panel-header">
            <span className="artifact-panel-title">🧩 正在加载…</span>
            <button
              type="button"
              className="artifact-action"
              title="关闭"
              onClick={onClose}
            >
              <FiX size={14} />
            </button>
          </div>
          <div className="artifact-panel-loading">加载 artifact 中…</div>
        </>
      ) : (
        <SandpackProvider
          template="react"
          theme={nightOwl}
          files={{ "/App.js": artifact.code, "/styles.css": BODY_CSS }}
          customSetup={{ dependencies: DEPS }}
        >
          <div className="artifact-panel-header">
            <span className="artifact-panel-title" title={title}>
              🧩 {title}
            </span>
            <div className="artifact-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "preview"}
                className={`artifact-tab ${tab === "preview" ? "active" : ""}`}
                onClick={() => setTab("preview")}
              >
                <FiEye size={12} /> 预览
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "code"}
                className={`artifact-tab ${tab === "code" ? "active" : ""}`}
                onClick={() => setTab("code")}
              >
                <FiCode size={12} /> 代码
              </button>
            </div>
            <div className="artifact-actions">
              <RefreshButton />
              <button
                type="button"
                className="artifact-action"
                title={copied ? "已复制" : "复制代码"}
                onClick={handleCopy}
              >
                {copied ? <FiCheck size={13} /> : <FiCopy size={13} />}
              </button>
              <button
                type="button"
                className="artifact-action"
                title="下载 .jsx"
                onClick={handleDownload}
              >
                <FiDownload size={13} />
              </button>
              <button
                type="button"
                className="artifact-action artifact-close"
                title="关闭"
                onClick={onClose}
              >
                <FiX size={14} />
              </button>
            </div>
          </div>
          <SandpackLayout className="artifact-panel-layout">
            {tab === "preview" ? (
              <SandpackPreview
                showNavigator={false}
                showOpenInCodeSandbox={false}
                showRefreshButton={false}
                showRestartButton={false}
                style={{ height: "100%" }}
              />
            ) : (
              <SandpackCodeEditor
                showLineNumbers
                showTabs={false}
                showInlineErrors
                wrapContent
                style={{ height: "100%" }}
              />
            )}
          </SandpackLayout>
        </SandpackProvider>
      )}
    </aside>
  );
}
