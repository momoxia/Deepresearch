const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

import type {
  Project,
  ProjectCreate,
  ChatMessage,
  ChatResponse,
  SSEEvent,
  Artifact,
  Folder,
  SuggestTree,
} from "../types";

export const getArtifact = (artifactId: string) =>
  request<Artifact>(`/api/artifacts/${artifactId}`);

export const listProjects = () => request<Project[]>("/api/projects");

export const getProject = (id: number) => request<Project>(`/api/projects/${id}`);

export const createProject = (data: ProjectCreate) =>
  request<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const deleteProject = (id: number) =>
  request<void>(`/api/projects/${id}`, { method: "DELETE" });

export const listFolders = () => request<Folder[]>("/api/folders");

export const createFolder = (data: {
  name: string;
  parent_id?: number | null;
  sort_order?: number;
}) =>
  request<Folder>("/api/folders", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateFolder = (
  id: number,
  data: { name?: string; parent_id?: number | null; sort_order?: number },
) =>
  request<Folder>(`/api/folders/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteFolder = (id: number) =>
  request<void>(`/api/folders/${id}`, { method: "DELETE" });

export const assignProjectFolder = (projectId: number, folderId: number | null) =>
  request<{ id: number; folder_id: number | null }>(
    `/api/folders/assign/${projectId}`,
    { method: "POST", body: JSON.stringify({ folder_id: folderId }) },
  );

export const suggestFolders = (instruction: string) =>
  request<SuggestTree>("/api/folders/suggest", {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });

export const applyFolderTree = (tree: SuggestTree) =>
  request<{ folder_count: number; folders: Folder[] }>("/api/folders/apply", {
    method: "POST",
    body: JSON.stringify({ folders: tree.folders, assignments: tree.assignments }),
  });

export interface MemoryItem {
  id: number;
  category: string;
  key: string;
  value: string;
  importance: number;
  source: string;
  access_count: number;
  archived: boolean;
  last_accessed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const getProjectMemory = (id: number, includeArchived = false) =>
  request<MemoryItem[]>(
    `/api/projects/${id}/memory${includeArchived ? "?include_archived=true" : ""}`,
  );

export const addMemory = (
  projectId: number,
  data: { key: string; value: string; category?: string; importance?: number },
) =>
  request<{ id: number; key: string; category: string }>(`/api/projects/${projectId}/memory`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateMemory = (projectId: number, memoryId: number, data: Record<string, unknown>) =>
  request<{ id: number; key: string; updated: boolean }>(
    `/api/projects/${projectId}/memory/${memoryId}`,
    { method: "PATCH", body: JSON.stringify(data) },
  );

export const deleteMemory = (projectId: number, memoryId: number) =>
  request<void>(`/api/projects/${projectId}/memory/${memoryId}`, { method: "DELETE" });

export const sendMessage = (
  projectId: number,
  message: string,
  sessionId?: string | null,
  signal?: AbortSignal,
) =>
  request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      message,
      session_id: sessionId ?? undefined,
    }),
    signal,
  });

export const getChatHistory = (projectId: number, limit = 50) =>
  request<ChatMessage[]>(`/api/chat/${projectId}/history?limit=${limit}`);

export const getSessionTitle = (projectId: number, sessionId: string) =>
  request<{ title: string | null }>(
    `/api/chat/${projectId}/title?session_id=${encodeURIComponent(sessionId)}`,
  );

export const getSessions = (projectId: number) =>
  request<
    {
      session_id: string;
      title: string | null;
      message_count: number;
      last_message_at: string | null;
    }[]
  >(`/api/chat/${projectId}/sessions`);

export type StreamFinishedInfo = { aborted: boolean };

export function streamChat(
  projectId: number,
  message: string,
  sessionId: string | null,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
  onStreamFinished?: (info: StreamFinishedInfo) => void,
): void {
  fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      message,
      session_id: sessionId ?? undefined,
    }),
    signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      if (!res.body) {
        onStreamFinished?.({ aborted: false });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });

          const lines = buf.split("\n");
          buf = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6);
            if (payload === "[DONE]") return;
            try {
              const evt: SSEEvent = JSON.parse(payload);
              onEvent(evt);
            } catch {
              /* skip */
            }
          }
        }
      } finally {
        onStreamFinished?.({ aborted: false });
      }
    })
    .catch((e) => {
      if (e instanceof DOMException && e.name === "AbortError") {
        onStreamFinished?.({ aborted: true });
        return;
      }
      console.error("SSE stream error:", e);
      onStreamFinished?.({ aborted: false });
    });
}
