import { useCallback, useEffect, useState } from "react";
import {
  createCheckpoint,
  createTask,
  deleteCheckpoint,
  deleteTask,
  fetchCurrentUser,
  fetchTasks,
  fetchUsers,
  getStoredToken,
  loginWithDev,
  loginWithTelegram,
  setStoredToken,
  triggerAiGenerateCheckpoints,
  triggerAiImprove,
  updateCheckpoint,
  updateTask,
  updateTaskMentions,
} from "./api/client";
import { CreateTaskModal } from "./components/CreateTaskModal";
import { KanbanBoard } from "./components/KanbanBoard";
import { Navbar } from "./components/Navbar";
import { TelegramLoginView } from "./components/TelegramLoginView";
import { useTaskWebSocket } from "./hooks/useTaskWebSocket";
import type {
  DevAuthInput,
  Task,
  TaskCreateInput,
  TaskFilterMode,
  TaskPriority,
  TaskStatus,
  TaskUpdateInput,
  TelegramWidgetUser,
  User,
  WebSocketTaskEvent,
} from "./types";

export function App() {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [registeredUsers, setRegisteredUsers] = useState<User[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filterMode, setFilterMode] = useState<TaskFilterMode>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | "ALL">(
    "ALL",
  );
  const [collaboratorFilter, setCollaboratorFilter] = useState<string | null>(
    null,
  );
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const upsertTaskInState = useCallback((incoming: Task) => {
    setTasks((prev) => {
      const exists = prev.some((t) => t.id === incoming.id);
      if (exists) {
        return prev.map((t) => (t.id === incoming.id ? incoming : t));
      }
      return [incoming, ...prev];
    });
  }, []);

  const removeTaskFromState = useCallback((taskId: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
  }, []);

  const handleWebSocketEvent = useCallback(
    (event: WebSocketTaskEvent) => {
      if (
        (event.event === "task.created" || event.event === "task.updated") &&
        event.task
      ) {
        upsertTaskInState(event.task);
      } else if (event.event === "task.deleted" && event.task_id) {
        removeTaskFromState(event.task_id);
      }
    },
    [removeTaskFromState, upsertTaskInState],
  );

  const { isConnected } = useTaskWebSocket({
    token,
    onEvent: handleWebSocketEvent,
  });

  const loadTasksAndUsers = useCallback(async (mode: TaskFilterMode) => {
    try {
      const [list, usersList] = await Promise.all([
        fetchTasks(mode),
        fetchUsers(),
      ]);
      setTasks(list);
      setRegisteredUsers(usersList);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to load tasks",
      );
    }
  }, []);

  useEffect(() => {
    const tgWebApp = window.Telegram?.WebApp;
    if (tgWebApp) {
      tgWebApp.ready();
      tgWebApp.expand();
    }
  }, []);

  useEffect(() => {
    let active = true;
    const initAuth = async () => {
      if (!token) {
        setCurrentUser(null);
        setIsLoading(false);
        return;
      }
      try {
        const [me, list, usersList] = await Promise.all([
          fetchCurrentUser(),
          fetchTasks(filterMode),
          fetchUsers(),
        ]);
        if (!active) {
          return;
        }
        setCurrentUser(me);
        setTasks(list);
        setRegisteredUsers(usersList);
      } catch {
        if (active) {
          setStoredToken(null);
          setToken(null);
          setCurrentUser(null);
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };
    void initAuth();
    return () => {
      active = false;
    };
  }, [token, filterMode]);

  const handleTelegramAuth = async (widgetUser: TelegramWidgetUser) => {
    setErrorBanner(null);
    try {
      const res = await loginWithTelegram(widgetUser);
      setStoredToken(res.access_token);
      setToken(res.access_token);
      setCurrentUser(res.user);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Telegram login failed",
      );
    }
  };

  const handleDevAuth = async (devInput: DevAuthInput) => {
    setErrorBanner(null);
    try {
      const res = await loginWithDev(devInput);
      setStoredToken(res.access_token);
      setToken(res.access_token);
      setCurrentUser(res.user);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : "Dev login failed");
    }
  };

  const handleLogout = () => {
    setStoredToken(null);
    setToken(null);
    setCurrentUser(null);
    setTasks([]);
    setRegisteredUsers([]);
  };

  const handleCreateTask = async (payload: TaskCreateInput) => {
    setErrorBanner(null);
    try {
      const created = await createTask(payload);
      upsertTaskInState(created);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to create task",
      );
    }
  };

  const handleMoveTask = async (
    taskId: string,
    newStatus: TaskStatus,
    newPosition: number,
  ) => {
    setErrorBanner(null);
    const snapshot = [...tasks];
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId ? { ...t, status: newStatus, position: newPosition } : t,
      ),
    );
    try {
      const updated = await updateTask(taskId, {
        status: newStatus,
        position: newPosition,
      });
      upsertTaskInState(updated);
    } catch (err) {
      setTasks(snapshot);
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to move task",
      );
    }
  };

  const handleUpdateTask = async (
    taskId: string,
    payload: TaskUpdateInput,
  ) => {
    setErrorBanner(null);
    try {
      const updated = await updateTask(taskId, payload);
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to update task",
      );
    }
  };

  const handleUpdateMentions = async (
    taskId: string,
    usernames: string[],
  ) => {
    setErrorBanner(null);
    try {
      const updated = await updateTaskMentions(taskId, usernames);
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to update mentions",
      );
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    setErrorBanner(null);
    try {
      await deleteTask(taskId);
      removeTaskFromState(taskId);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to delete task",
      );
    }
  };

  const handleAiImprove = async (taskId: string) => {
    setErrorBanner(null);
    try {
      const updated = await triggerAiImprove(taskId);
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to trigger AI Improve",
      );
    }
  };

  const handleAiGenerateCheckpoints = async (taskId: string) => {
    setErrorBanner(null);
    try {
      const updated = await triggerAiGenerateCheckpoints(taskId);
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error
          ? err.message
          : "Failed to trigger AI Checkpoints",
      );
    }
  };

  const handleAddCheckpoint = async (taskId: string, title: string) => {
    setErrorBanner(null);
    try {
      const updated = await createCheckpoint(taskId, title);
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to add checkpoint",
      );
    }
  };

  const handleToggleCheckpoint = async (
    taskId: string,
    checkpointId: string,
    isCompleted: boolean,
  ) => {
    setErrorBanner(null);
    try {
      const updated = await updateCheckpoint(taskId, checkpointId, {
        is_completed: isCompleted,
      });
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to toggle checkpoint",
      );
    }
  };

  const handleDeleteCheckpoint = async (
    taskId: string,
    checkpointId: string,
  ) => {
    setErrorBanner(null);
    try {
      const updated = await deleteCheckpoint(taskId, checkpointId);
      upsertTaskInState(updated);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to delete checkpoint",
      );
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-sm text-slate-400">
        Loading workspace...
      </div>
    );
  }

  if (!currentUser) {
    return (
      <TelegramLoginView
        onTelegramAuth={handleTelegramAuth}
        onDevAuth={handleDevAuth}
        errorMessage={errorBanner}
      />
    );
  }

  const normalizedQuery = searchQuery.trim().toLowerCase();

  const visibleTasks = tasks.filter((task) => {
    if (filterMode === "private") {
      if (
        task.owner_id !== currentUser.id ||
        task.visibility !== "PRIVATE"
      ) {
        return false;
      }
    } else if (filterMode === "shared") {
      if (task.visibility !== "PUBLIC") {
        return false;
      }
    }

    if (priorityFilter !== "ALL" && (task.priority ?? "MEDIUM") !== priorityFilter) {
      return false;
    }

    if (collaboratorFilter) {
      const hasCollab = task.mentions.some(
        (m) => m.telegram_username.toLowerCase() === collaboratorFilter,
      );
      const isOwnerMatch =
        task.owner?.username?.toLowerCase() === collaboratorFilter;
      if (!hasCollab && !isOwnerMatch) {
        return false;
      }
    }

    if (tagFilter) {
      const hasTag = (task.tags ?? []).some(
        (t) => t.toLowerCase() === tagFilter,
      );
      if (!hasTag) {
        return false;
      }
    }

    if (normalizedQuery) {
      const inTitle = task.title.toLowerCase().includes(normalizedQuery);
      const inDesc = (task.description ?? "")
        .toLowerCase()
        .includes(normalizedQuery);
      const inMentions = task.mentions.some((m) =>
        m.telegram_username.toLowerCase().includes(normalizedQuery.replace(/^@/, "")),
      );
      const inTags = (task.tags ?? []).some((t) =>
        t.toLowerCase().includes(normalizedQuery),
      );
      if (!inTitle && !inDesc && !inMentions && !inTags) {
        return false;
      }
    }

    return true;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Navbar
        user={currentUser}
        registeredUsers={registeredUsers}
        tasks={tasks}
        isConnected={isConnected}
        filterMode={filterMode}
        searchQuery={searchQuery}
        priorityFilter={priorityFilter}
        collaboratorFilter={collaboratorFilter}
        tagFilter={tagFilter}
        onFilterChange={(mode) => setFilterMode(mode)}
        onSearchChange={setSearchQuery}
        onPriorityFilterChange={setPriorityFilter}
        onCollaboratorFilterChange={setCollaboratorFilter}
        onTagFilterChange={setTagFilter}
        onOpenCreateModal={() => setIsCreateModalOpen(true)}
        onRefresh={() => void loadTasksAndUsers(filterMode)}
        onLogout={handleLogout}
      />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {errorBanner && (
          <div className="mb-4 flex items-center justify-between rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-xs text-rose-200">
            <span>{errorBanner}</span>
            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              className="font-semibold underline"
            >
              Dismiss
            </button>
          </div>
        )}

        <KanbanBoard
          tasks={visibleTasks}
          currentUser={currentUser}
          registeredUsers={registeredUsers}
          onMoveTask={handleMoveTask}
          onUpdateTask={handleUpdateTask}
          onUpdateMentions={handleUpdateMentions}
          onDeleteTask={handleDeleteTask}
          onAiImprove={handleAiImprove}
          onAiGenerateCheckpoints={handleAiGenerateCheckpoints}
          onAddCheckpoint={handleAddCheckpoint}
          onToggleCheckpoint={handleToggleCheckpoint}
          onDeleteCheckpoint={handleDeleteCheckpoint}
        />
      </main>

      <CreateTaskModal
        isOpen={isCreateModalOpen}
        registeredUsers={registeredUsers}
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateTask}
      />
    </div>
  );
}
