import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import WelcomePanel from "./components/WelcomePanel";
import SourcesPanel from "./components/SourcesPanel";
import MemoryPanel from "./components/MemoryPanel";
import ArtifactPanel from "./components/ArtifactPanel";
import OrganizeModal from "./components/OrganizeModal";
import * as api from "./api/client";
import type {
  Project,
  ChatMessage,
  ActivityCard,
  Source,
  ToolActivity,
  TaskActivity,
  SSEEvent,
  Folder,
} from "./types";

const DEFAULT_PROJECT_NAME = "新对话";

let toolIdCounter = 0;

function toolToKind(toolName: string): ActivityCard["kind"] {
  if (toolName.includes("web_search")) return "search";
  if (toolName.includes("web_fetch")) return "fetch";
  if (
    toolName.includes("pdf_parse") ||
    toolName.includes("pdf_read") ||
    toolName.includes("pdf_grep") ||
    toolName.includes("pdf_vision")
  ) {
    return "fetch";
  }
  if (toolName.includes("cache_school") || toolName.includes("search_schools")) return "cache";
  if (toolName.includes("Agent") || toolName.includes("agent")) return "agent";
  return "tool";
}

function buildActivityCards(
  tools: ToolActivity[],
  tasks: TaskActivity[],
): ActivityCard[] {
  const cards: ActivityCard[] = [];

  for (const t of tools) {
    const kind = toolToKind(t.tool);
    const detail =
      t.input.query ||
      t.input.url ||
      t.input.pattern ||
      t.input.summary ||
      t.input.doc_id ||
      t.input.school ||
      t.input.agent ||
      "";
    let url: string | undefined;
    if (kind === "fetch" && t.input.url) url = t.input.url;
    if (kind === "search" && t.input.query) {
      url = `https://www.google.com/search?q=${encodeURIComponent(t.input.query)}`;
    }
    cards.push({
      id: t.id,
      kind,
      label: t.label,
      detail,
      url,
      summary: t.result,
      timestamp: t.timestamp,
    });
  }

  for (const tk of tasks) {
    const statusLabel = tk.status === "done" ? "已完成" : "进行中";
    cards.push({
      id: `task-${tk.task_id}`,
      kind: "agent",
      label: tk.description,
      detail: statusLabel,
      summary: tk.summary,
      timestamp: Date.now(),
    });
  }

  return cards;
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [streamingText, setStreamingText] = useState("");
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [taskActivities, setTaskActivities] = useState<TaskActivity[]>([]);
  const [statusText, setStatusText] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [showSources, setShowSources] = useState(false);
  const [showMemory, setShowMemory] = useState(false);
  const [chatTitle, setChatTitle] = useState<string | null>(null);
  const [openArtifactId, setOpenArtifactId] = useState<string | null>(null);
  const [artifactWidth, setArtifactWidth] = useState<number>(() => {
    const v = Number(localStorage.getItem("artifactPanelWidth"));
    return v >= 30 && v <= 70 ? v : 50;
  });

  const openArtifact = useCallback((id: string) => {
    setShowMemory(false);
    setShowSources(false);
    setOpenArtifactId(id);
  }, []);

  const closeArtifact = useCallback(() => setOpenArtifactId(null), []);

  const toggleMemory = useCallback(() => {
    setShowMemory((v) => {
      const next = !v;
      if (next) setOpenArtifactId(null);
      return next;
    });
  }, []);

  const handleArtifactWidthChange = useCallback((pct: number) => {
    setArtifactWidth(pct);
    localStorage.setItem("artifactPanelWidth", String(pct));
  }, []);

  const abortRef = useRef<AbortController | null>(null);
  const activeIdRef = useRef<number | null>(activeId);
  const toolsRef = useRef<ToolActivity[]>([]);
  const tasksRef = useRef<TaskActivity[]>([]);
  const artifactsRef = useRef<string[]>([]);
  const activeProject = projects.find((p) => p.id === activeId);

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  useEffect(() => {
    if (showMemory || (showSources && sources.length > 0)) {
      setOpenArtifactId((id) => (id ? null : id));
    }
  }, [showMemory, showSources, sources.length]);

  useEffect(() => {
    api.listProjects().then(setProjects).catch(console.error);
    api.listFolders().then(setFolders).catch(console.error);
  }, []);

  const refreshFoldersAndProjects = useCallback(async () => {
    try {
      const [ps, fs] = await Promise.all([api.listProjects(), api.listFolders()]);
      setProjects(ps);
      setFolders(fs);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const selectProject = useCallback(async (id: number) => {
    // 不 abort：后台继续跑完并落库；仅断开本页面对该流的 AbortHandle，避免误杀其它项目请求
    if (abortRef.current) {
      abortRef.current = null;
    }
    setActiveId(id);
    setSessionId(null);
    setMessages([]);
    setLoading(false);
    setStreamingText("");
    setToolActivities([]);
    setTaskActivities([]);
    setStatusText("");
    setSources([]);
    setChatTitle(null);
    try {
      const history = await api.getChatHistory(id);
      setMessages(history);
      if (history.length > 0) {
        setSessionId(history[0].session_id ?? null);
        const titleMsg = history.find((m) => m.title);
        if (titleMsg?.title) {
          setChatTitle(titleMsg.title);
        }
      }
    } catch {
      /* no history */
    }
  }, []);

  const createProject = useCallback(async () => {
    try {
      const proj = await api.createProject({});
      setProjects((prev) => [proj, ...prev]);
      setActiveId(proj.id);
      setMessages([]);
      setSessionId(null);
      setSources([]);
      setChatTitle(null);
      setStreamingText("");
      setToolActivities([]);
      setTaskActivities([]);
      setStatusText("");
      setShowSources(false);
    } catch (e) {
      console.error(e);
      alert("创建失败，请检查后端是否运行");
    }
  }, []);

  const deleteProjectHandler = useCallback(
    async (id: number) => {
      try {
        await api.deleteProject(id);
        setProjects((prev) => prev.filter((p) => p.id !== id));
        if (activeId === id) {
          setActiveId(null);
          setMessages([]);
          setSessionId(null);
          setSources([]);
          setShowSources(false);
        }
      } catch (e) {
        console.error(e);
        alert("删除失败");
      }
    },
    [activeId],
  );

  const stopGeneration = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setLoading(false);
    const cards = buildActivityCards(toolsRef.current, tasksRef.current);
    const content = streamingText
      ? streamingText + "\n\n⏹ *已中止*"
      : "⏹ 已中止回复";
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content,
        activities: cards.length > 0 ? cards : undefined,
        _streamed: true,
      },
    ]);
    setStreamingText("");
    setToolActivities([]);
    setTaskActivities([]);
    toolsRef.current = [];
    tasksRef.current = [];
    artifactsRef.current = [];
    setStatusText("");
  }, [streamingText]);

  const sendMessage = useCallback(
    (text: string) => {
      if (!activeId) return;

      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const ownerProjectId = activeId;
      const streamDone = { current: false };

      const userMsg: ChatMessage = { role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);
      setStreamingText("");
      setToolActivities([]);
      setTaskActivities([]);
      setStatusText("");
      setSources([]);
      artifactsRef.current = [];

      const handleEvent = (event: SSEEvent) => {
        if (activeIdRef.current !== ownerProjectId) {
          if (event.type === "done") {
            streamDone.current = true;
          }
          return;
        }

        switch (event.type) {
          case "session":
            setSessionId(event.session_id);
            break;

          case "status":
            setStatusText(event.text);
            break;

          case "tool_start": {
            const id = `tool-${++toolIdCounter}`;
            setToolActivities((prev) => {
              const updated = prev.map((t) =>
                t.status === "running" ? { ...t, status: "done" as const } : t,
              );
              const next = [
                ...updated,
                {
                  id,
                  tool: event.tool,
                  label: event.label,
                  input: event.input,
                  status: "running" as const,
                  timestamp: Date.now(),
                },
              ];
              toolsRef.current = next;
              return next;
            });
            setStatusText("");

            if (event.tool.includes("web_fetch") && event.input.url) {
              setSources((prev) => {
                if (prev.some((s) => s.url === event.input.url)) return prev;
                const domain = new URL(event.input.url).hostname;
                return [...prev, { url: event.input.url, title: domain }];
              });
              setShowSources(true);
            }
            if (event.tool.includes("web_search") && event.input.query) {
              setSources((prev) => [
                ...prev,
                {
                  url: `https://www.google.com/search?q=${encodeURIComponent(event.input.query)}`,
                  title: `🔍 ${event.input.query.slice(0, 40)}`,
                },
              ]);
              setShowSources(true);
            }
            break;
          }

          case "task_start":
            setTaskActivities((prev) => {
              const next = [
                ...prev,
                {
                  task_id: event.task_id,
                  description: event.description,
                  status: "running" as const,
                },
              ];
              tasksRef.current = next;
              return next;
            });
            break;

          case "task_progress":
            setTaskActivities((prev) => {
              const next = prev.map((t) =>
                t.task_id === event.task_id
                  ? { ...t, description: event.description }
                  : t,
              );
              tasksRef.current = next;
              return next;
            });
            break;

          case "task_done":
            setTaskActivities((prev) => {
              const next = prev.map((t) =>
                t.task_id === event.task_id
                  ? { ...t, status: "done" as const, summary: event.summary }
                  : t,
              );
              tasksRef.current = next;
              return next;
            });
            break;

          case "tool_result": {
            setToolActivities((prev) => {
              const next = prev.map((t) => {
                if (t.tool === event.tool && t.status === "running") {
                  return { ...t, status: "done" as const, result: event.result };
                }
                if (t.tool === event.tool && !t.result && t.status === "done") {
                  const found = prev.filter((x) => x.tool === event.tool && !x.result);
                  if (found.length > 0 && found[0].id === t.id) {
                    return { ...t, result: event.result };
                  }
                }
                return t;
              });
              toolsRef.current = next;
              return next;
            });
            break;
          }

          case "artifact":
            if (!artifactsRef.current.includes(event.artifact_id)) {
              artifactsRef.current = [...artifactsRef.current, event.artifact_id];
            }
            break;

          case "text":
            setStreamingText((prev) => prev + event.content);
            setToolActivities((prev) => {
              const next = prev.map((t) =>
                t.status === "running" ? { ...t, status: "done" as const } : t,
              );
              toolsRef.current = next;
              return next;
            });
            break;

          case "done": {
            streamDone.current = true;
            let finalReply = event.reply || "";
            const missing = artifactsRef.current.filter(
              (id) => !finalReply.includes(`[artifact:${id}]`),
            );
            if (missing.length > 0) {
              const append = missing.map((id) => `\n\n[artifact:${id}]`).join("");
              finalReply = finalReply ? finalReply + append : append.trimStart();
            }
            setSessionId(event.session_id);
            if (event.sources?.length) {
              setSources((prev) => {
                const urls = new Set(prev.map((s) => s.url));
                const newSources = event.sources.filter((s) => !urls.has(s.url));
                return [...prev, ...newSources];
              });
              setShowSources(true);
            }
            const cards = buildActivityCards(toolsRef.current, tasksRef.current);
            if (finalReply) {
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: finalReply,
                  activities: cards.length > 0 ? cards : undefined,
                  _streamed: true,
                },
              ]);
            }
            setStreamingText("");
            setToolActivities([]);
            setTaskActivities([]);
            toolsRef.current = [];
            tasksRef.current = [];
            artifactsRef.current = [];
            setStatusText("");
            setLoading(false);
            if (abortRef.current === controller) abortRef.current = null;

            const pid = activeIdRef.current;
            if (event.session_id && pid && !chatTitle) {
              setTimeout(() => {
                api
                  .getSessionTitle(pid, event.session_id!)
                  .then((res) => {
                    if (res.title) {
                      setChatTitle(res.title);
                      setProjects((prev) =>
                        prev.map((p) =>
                          p.id === pid && p.name === DEFAULT_PROJECT_NAME
                            ? { ...p, name: res.title! }
                            : p,
                        ),
                      );
                    }
                  })
                  .catch(() => {});
              }, 3000);
            }
            break;
          }
        }
      };

      api.streamChat(activeId, text, sessionId, handleEvent, controller.signal, ({ aborted }) => {
        if (aborted) {
          if (abortRef.current === controller) abortRef.current = null;
          return;
        }
        if (activeIdRef.current !== ownerProjectId) {
          if (abortRef.current === controller) abortRef.current = null;
          return;
        }
        if (!streamDone.current) {
          setStreamingText((buf) => {
            if (buf.trim()) {
              const cards = buildActivityCards(toolsRef.current, tasksRef.current);
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: buf,
                  activities: cards.length > 0 ? cards : undefined,
                  _streamed: true,
                },
              ]);
            }
            return "";
          });
          setToolActivities([]);
          setTaskActivities([]);
          toolsRef.current = [];
          tasksRef.current = [];
          setStatusText("");
        }
        setLoading(false);
        if (abortRef.current === controller) abortRef.current = null;
      });
    },
    [activeId, sessionId, chatTitle],
  );

  const hasArtifact = !!openArtifactId;
  const hasRightPanel =
    hasArtifact || (showSources && sources.length > 0) || showMemory;

  return (
    <div
      className={`app-layout ${hasRightPanel ? "with-sources" : ""} ${
        hasArtifact ? "with-artifact" : ""
      }`}
    >
      <Sidebar
        projects={projects}
        folders={folders}
        activeId={activeId}
        onSelect={selectProject}
        onCreate={createProject}
        onDelete={deleteProjectHandler}
        onOrganize={() => setOrganizeOpen(true)}
      />
      <OrganizeModal
        open={organizeOpen}
        projects={projects}
        existingFolders={folders}
        onClose={() => setOrganizeOpen(false)}
        onApplied={refreshFoldersAndProjects}
      />
      {activeProject ? (
        <>
          <ChatPanel
            messages={messages}
            loading={loading}
            projectName={activeProject.name}
            streamingText={streamingText}
            toolActivities={toolActivities}
            taskActivities={taskActivities}
            statusText={statusText}
            onSend={sendMessage}
            onStop={stopGeneration}
            onToggleMemory={toggleMemory}
            showMemory={showMemory}
            openArtifactId={openArtifactId}
            onOpenArtifact={openArtifact}
          />
          {openArtifactId ? (
            <ArtifactPanel
              artifactId={openArtifactId}
              widthPct={artifactWidth}
              onWidthChange={handleArtifactWidthChange}
              onClose={closeArtifact}
            />
          ) : showMemory && activeId ? (
            <MemoryPanel projectId={activeId} visible={showMemory} />
          ) : (
            <SourcesPanel sources={sources} visible={showSources && sources.length > 0} />
          )}
        </>
      ) : (
        <WelcomePanel />
      )}
    </div>
  );
}
