import type {
  DevAuthInput,
  Task,
  TaskCreateInput,
  TaskFilterMode,
  TaskUpdateInput,
  TelegramWidgetUser,
  TokenResponse,
  User,
} from "../types";

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

const TOKEN_STORAGE_KEY = "omni_task_manager_jwt";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody.detail) {
        errorDetail = errBody.detail;
      }
    } catch {
      errorDetail = response.statusText || errorDetail;
    }
    throw new Error(errorDetail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function loginWithTelegram(
  payload: TelegramWidgetUser,
): Promise<TokenResponse> {
  return requestJson<TokenResponse>("/auth/telegram", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginWithTelegramWebApp(
  initData: string,
): Promise<TokenResponse> {
  return requestJson<TokenResponse>("/auth/telegram-webapp", {
    method: "POST",
    body: JSON.stringify({ init_data: initData }),
  });
}

export async function loginWithDev(
  payload: DevAuthInput,
): Promise<TokenResponse> {
  return requestJson<TokenResponse>("/auth/dev", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCurrentUser(): Promise<User> {
  return requestJson<User>("/auth/me");
}

export async function fetchUsers(query?: string): Promise<User[]> {
  const qs = query ? `?q=${encodeURIComponent(query)}` : "";
  return requestJson<User[]>(`/users${qs}`);
}

export async function fetchTasks(
  filterMode: TaskFilterMode = "all",
): Promise<Task[]> {
  return requestJson<Task[]>(`/tasks?filter_mode=${filterMode}`);
}

export async function createTask(payload: TaskCreateInput): Promise<Task> {
  return requestJson<Task>("/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTask(
  taskId: string,
  payload: TaskUpdateInput,
): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function updateTaskMentions(
  taskId: string,
  mentions: string[],
): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}/mentions`, {
    method: "PUT",
    body: JSON.stringify({ mentions }),
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  await requestJson<void>(`/tasks/${taskId}`, {
    method: "DELETE",
  });
}

export async function triggerAiImprove(taskId: string): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}/improve`, {
    method: "POST",
  });
}

export async function triggerAiGenerateCheckpoints(
  taskId: string,
): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}/checkpoints/generate`, {
    method: "POST",
  });
}

export async function createCheckpoint(
  taskId: string,
  title: string,
): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}/checkpoints`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function updateCheckpoint(
  taskId: string,
  checkpointId: string,
  payload: { title?: string; is_completed?: boolean; position?: number },
): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}/checkpoints/${checkpointId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteCheckpoint(
  taskId: string,
  checkpointId: string,
): Promise<Task> {
  return requestJson<Task>(`/tasks/${taskId}/checkpoints/${checkpointId}`, {
    method: "DELETE",
  });
}
