export interface Project {
  id: number;
  name: string;
  description: string | null;
  folder_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Folder {
  id: number;
  name: string;
  parent_id: number | null;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface SuggestFolderSpec {
  tmp_id: string;
  name: string;
  parent_tmp_id: string | null;
  sort_order: number;
}

export interface SuggestAssignment {
  project_id: number;
  folder_tmp_id: string | null;
}

export interface SuggestTree {
  folders: SuggestFolderSpec[];
  assignments: SuggestAssignment[];
  rationale?: string;
}

export interface ProjectCreate {
  name?: string;
  description?: string;
}

export interface ActivityCard {
  id: string;
  kind: "search" | "fetch" | "cache" | "agent" | "tool";
  label: string;
  detail: string;
  url?: string;
  summary?: string;
  timestamp: number;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  session_id?: string | null;
  title?: string | null;
  created_at?: string;
  activities?: ActivityCard[];
  _streamed?: boolean;
}

export interface ChatResponse {
  project_id: number;
  session_id: string | null;
  reply: string;
}

export interface Source {
  url: string;
  title: string;
}

export interface ToolActivity {
  id: string;
  tool: string;
  label: string;
  input: Record<string, string>;
  status: "running" | "done";
  timestamp: number;
  result?: string;
}

export interface TaskActivity {
  task_id: string;
  description: string;
  status: "running" | "done";
  summary?: string;
}

export type SSEEvent =
  | { type: "session"; session_id: string }
  | { type: "status"; text: string }
  | { type: "tool_start"; tool: string; label: string; input: Record<string, string> }
  | { type: "tool_result"; tool: string; tool_use_id: string; result: string }
  | { type: "source"; url: string; title: string }
  | { type: "task_start"; task_id: string; description: string }
  | { type: "task_progress"; task_id: string; description: string; last_tool?: string }
  | { type: "task_done"; task_id: string; status: string; summary: string }
  | { type: "text"; content: string }
  | { type: "artifact"; artifact_id: string; preview_url: string }
  | { type: "done"; session_id: string | null; reply: string; sources: Source[] };

export interface Artifact {
  artifact_id: string;
  project_id: number;
  session_id: string | null;
  title: string | null;
  code: string;
  viz_hint: string | null;
  created_at: string | null;
}
