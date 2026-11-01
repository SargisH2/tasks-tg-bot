declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
    readonly VITE_WS_URL?: string;
    readonly VITE_TELEGRAM_BOT_USERNAME?: string;
    readonly VITE_ALLOW_DEV_AUTH?: string;
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }

  interface TelegramWebApp {
    ready: () => void;
    expand: () => void;
    initData?: string;
    initDataUnsafe?: {
      user?: {
        id: number;
        first_name: string;
        last_name?: string;
        username?: string;
        photo_url?: string;
      };
    };
  }

  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export type TaskVisibility = "PRIVATE" | "PUBLIC";

export type TaskSource = "TELEGRAM_TEXT" | "TELEGRAM_VOICE" | "WEB";

export type TaskStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED";

export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export type TaskProcessingState =
  | "IDLE"
  | "TRANSCRIBING"
  | "IMPROVING"
  | "GENERATING_CHECKPOINTS"
  | "FAILED";

export type TaskFilterMode = "all" | "private" | "shared";

export interface User {
  id: string;
  telegram_id: number;
  username: string | null;
  first_name: string;
  last_name: string | null;
  photo_url: string | null;
  created_at: string;
}

export interface TaskMention {
  id: string;
  task_id: string;
  telegram_username: string;
  created_at: string;
}

export interface TaskCheckpoint {
  id: string;
  task_id: string;
  title: string;
  is_completed: boolean;
  position: number;
  created_at: string;
}

export interface Task {
  id: string;
  owner_id: string;
  owner: User | null;
  visibility: TaskVisibility;
  source: TaskSource;
  status: TaskStatus;
  priority: TaskPriority;
  tags: string[];
  processing_state: TaskProcessingState;
  title: string;
  description: string | null;
  raw_input: string;
  is_ai_improved: boolean;
  position: number;
  telegram_chat_id: number | null;
  telegram_message_id: number | null;
  telegram_voice_file_id: string | null;
  error_message: string | null;
  mentions: TaskMention[];
  checkpoints: TaskCheckpoint[];
  created_at: string;
  updated_at: string;
}

export interface TelegramWidgetUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export interface DevAuthInput {
  telegram_id: number;
  username: string;
  first_name: string;
  last_name?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface TaskCreateInput {
  title: string;
  description?: string | null;
  visibility: TaskVisibility;
  status: TaskStatus;
  priority?: TaskPriority;
  tags?: string[];
  mentions: string[];
}

export interface TaskUpdateInput {
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  tags?: string[];
  position?: number;
  visibility?: TaskVisibility;
  mentions?: string[];
}

export interface WebSocketTaskEvent {
  event:
    | "connection.established"
    | "task.created"
    | "task.updated"
    | "task.deleted"
    | "pong";
  task_id?: string;
  owner_id?: string;
  visibility?: TaskVisibility;
  allowed_usernames?: string[];
  actor_username?: string | null;
  task?: Task | null;
}
