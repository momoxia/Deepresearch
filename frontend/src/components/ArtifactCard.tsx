import { SandpackPreview, SandpackProvider } from "@codesandbox/sandpack-react";
import { nightOwl } from "@codesandbox/sandpack-themes";
import { useEffect, useRef, useState } from "react";
import { FiArrowUpRight } from "react-icons/fi";
import * as api from "../api/client";
import type { Artifact } from "../types";

interface Props {
  artifactId: string;
  isOpen: boolean;
  onOpen: (id: string) => void;
}

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

export default function ArtifactCard({ artifactId, isOpen, onOpen }: Props) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
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

  useEffect(() => {
    if (visible || !cardRef.current) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { rootMargin: "200px" },
    );
    obs.observe(cardRef.current);
    return () => obs.disconnect();
  }, [visible]);

  const title = artifact?.title || "交互式可视化";

  return (
    <div
      ref={cardRef}
      className={`artifact-card ${isOpen ? "active" : ""}`}
      onClick={() => onOpen(artifactId)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(artifactId);
        }
      }}
    >
      <div className="artifact-card-head">
        <span className="artifact-card-icon">🧩</span>
        <div className="artifact-card-meta">
          <div className="artifact-card-title">{title}</div>
          <div className="artifact-card-sub">
            交互式组件 · React · {artifactId.slice(0, 8)}
          </div>
        </div>
        <span className="artifact-card-open">
          打开 <FiArrowUpRight size={12} />
        </span>
      </div>
      <div className="artifact-card-preview">
        {error ? (
          <div className="artifact-card-placeholder error">
            加载失败: {error}
          </div>
        ) : !artifact || !visible ? (
          <div className="artifact-card-placeholder">正在加载预览…</div>
        ) : (
          <SandpackProvider
            template="react"
            theme={nightOwl}
            files={{ "/App.js": artifact.code, "/styles.css": BODY_CSS }}
            customSetup={{ dependencies: DEPS }}
            options={{ recompileMode: "delayed", recompileDelay: 500 }}
          >
            <div className="artifact-card-preview-inner">
              <SandpackPreview
                showNavigator={false}
                showOpenInCodeSandbox={false}
                showRefreshButton={false}
                showRestartButton={false}
                style={{ height: "100%", border: "none" }}
              />
            </div>
          </SandpackProvider>
        )}
      </div>
    </div>
  );
}
