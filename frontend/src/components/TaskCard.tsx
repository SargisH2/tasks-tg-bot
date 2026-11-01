import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Edit3,
  Flag,
  Globe,
  GripVertical,
  Loader2,
  Lock,
  Sparkles,
  Tag,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";
import type { Task, TaskPriority, TaskUpdateInput, User } from "../types";
import { CheckpointList } from "./CheckpointList";
import { MentionInput } from "./MentionInput";

interface TaskCardProps {
  task: Task;
  currentUser: User;
  registeredUsers: User[];
  onUpdateTask: (taskId: string, payload: TaskUpdateInput) => Promise<void>;
  onUpdateMentions: (taskId: string, usernames: string[]) => Promise<void>;
  onDeleteTask: (taskId: string) => Promise<void>;
  onAiImprove: (taskId: string) => Promise<void>;
  onAiGenerateCheckpoints: (taskId: string) => Promise<void>;
  onAddCheckpoint: (taskId: string, title: string) => Promise<void>;
  onToggleCheckpoint: (
    taskId: string,
    checkpointId: string,
    isCompleted: boolean,
  ) => Promise<void>;
  onDeleteCheckpoint: (taskId: string, checkpointId: string) => Promise<void>;
}

const PRIORITY_ORDER: TaskPriority[] = ["LOW", "MEDIUM", "HIGH", "URGENT"];

const PRIORITY_STYLES: Record<
  TaskPriority,
  { label: string; className: string }
> = {
  LOW: {
    label: "🟢 Low",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  },
  MEDIUM: {
    label: "🔵 Medium",
    className: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  },
  HIGH: {
    label: "🟠 High",
    className: "border-amber-500/40 bg-amber-500/15 text-amber-300",
  },
  URGENT: {
    label: "🔴 Urgent",
    className: "border-rose-500/50 bg-rose-500/20 text-rose-300",
  },
};

export function TaskCard({
  task,
  currentUser,
  registeredUsers,
  onUpdateTask,
  onUpdateMentions,
  onDeleteTask,
  onAiImprove,
  onAiGenerateCheckpoints,
  onAddCheckpoint,
  onToggleCheckpoint,
  onDeleteCheckpoint,
}: TaskCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: task.id,
    data: {
      type: "Task",
      task,
      status: task.status,
    },
  });

  const [isMinimized, setIsMinimized] = useState<boolean>(false);
  const [showRawInput, setShowRawInput] = useState<boolean>(false);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editTitle, setEditTitle] = useState<string>(task.title);
  const [editDescription, setEditDescription] = useState<string>(
    task.description ?? "",
  );
  const [editPriority, setEditPriority] = useState<TaskPriority>(
    task.priority ?? "MEDIUM",
  );
  const [editTags, setEditTags] = useState<string>(
    (task.tags ?? []).join(", "),
  );

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
  };

  const isOwner = task.owner_id === currentUser.id;
  const ownerUsername =
    task.owner?.username ?? task.owner?.first_name ?? "owner";
  const msgSuffix = task.telegram_message_id
    ? ` \u0023${task.telegram_message_id}`
    : "";

  const sourceBadgeText =
    task.source === "TELEGRAM_VOICE"
      ? `🎙️ Voice${msgSuffix}`
      : task.source === "TELEGRAM_TEXT"
        ? `💬 Telegram${msgSuffix}`
        : "🖥️ Web";

  const isImproving = task.processing_state === "IMPROVING";
  const isGeneratingCheckpoints =
    task.processing_state === "GENERATING_CHECKPOINTS";
  const isTranscribing = task.processing_state === "TRANSCRIBING";

  const currentPriority: TaskPriority = task.priority ?? "MEDIUM";
  const priorityInfo =
    PRIORITY_STYLES[currentPriority] ?? PRIORITY_STYLES.MEDIUM;

  const completedCheckpointsCount = task.checkpoints.filter(
    (c) => c.is_completed,
  ).length;

  const handleToggleVisibility = async () => {
    if (!isOwner) {
      return;
    }
    const nextVis = task.visibility === "PRIVATE" ? "PUBLIC" : "PRIVATE";
    await onUpdateTask(task.id, { visibility: nextVis });
  };

  const handleCyclePriority = async () => {
    const idx = PRIORITY_ORDER.indexOf(currentPriority);
    const nextPriority = PRIORITY_ORDER[(idx + 1) % PRIORITY_ORDER.length];
    await onUpdateTask(task.id, { priority: nextPriority });
  };

  const handleSaveEdit = async () => {
    if (!editTitle.trim()) {
      return;
    }
    const parsedTags = editTags
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    await onUpdateTask(task.id, {
      title: editTitle.trim(),
      description: editDescription.trim() || null,
      priority: editPriority,
      tags: parsedTags,
    });
    setIsEditing(false);
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={`cursor-grab rounded-xl border bg-slate-900/95 p-3.5 shadow-lg transition select-none active:cursor-grabbing ${
        isDragging
          ? "z-40 border-indigo-500 opacity-40 ring-2 ring-indigo-500/40"
          : "border-slate-800 hover:border-slate-700"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            disabled={!isOwner}
            onClick={() => void handleToggleVisibility()}
            title={
              isOwner
                ? "Click to toggle Private / Public visibility"
                : "Only the task owner can change visibility"
            }
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold transition ${
              task.visibility === "PUBLIC"
                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                : "border-amber-500/40 bg-amber-500/15 text-amber-300"
            } ${isOwner ? "cursor-pointer hover:brightness-110" : "cursor-default"}`}
          >
            {task.visibility === "PUBLIC" ? (
              <>
                <Globe className="h-3 w-3" />
                🌐 Public
              </>
            ) : (
              <>
                <Lock className="h-3 w-3" />
                🔒 Private
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => void handleCyclePriority()}
            title="Click to cycle task priority"
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold transition hover:brightness-110 ${priorityInfo.className}`}
          >
            <Flag className="h-2.5 w-2.5" />
            {priorityInfo.label}
          </button>

          {!isMinimized && (
            <span className="rounded-md border border-slate-700/80 bg-slate-800/80 px-2 py-0.5 text-[11px] font-medium text-slate-300">
              {sourceBadgeText}
            </span>
          )}

          <span className="rounded-md bg-slate-800/50 px-2 py-0.5 text-[11px] text-slate-400">
            @{ownerUsername}
          </span>

          {isMinimized && task.checkpoints.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300">
              <CheckSquare className="h-2.5 w-2.5" />
              {completedCheckpointsCount}/{task.checkpoints.length}
            </span>
          )}

          {isMinimized && task.mentions.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
              <Users className="h-2.5 w-2.5" />
              {task.mentions.length}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setIsMinimized((prev) => !prev)}
            title={isMinimized ? "Expand task card" : "Minimize task card"}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            {isMinimized ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronUp className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            onClick={() => {
              setEditTitle(task.title);
              setEditDescription(task.description ?? "");
              setEditPriority(task.priority ?? "MEDIUM");
              setEditTags((task.tags ?? []).join(", "));
              setIsMinimized(false);
              setIsEditing(!isEditing);
            }}
            title="Edit task title, description, priority, and tags"
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <Edit3 className="h-3.5 w-3.5" />
          </button>
          {isOwner && (
            <button
              type="button"
              onClick={() => void onDeleteTask(task.id)}
              title="Delete task"
              className="rounded p-1 text-slate-400 hover:bg-rose-500/15 hover:text-rose-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          <span
            title="Drag card to move column"
            className="touch-none rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <GripVertical className="h-4 w-4" />
          </span>
        </div>
      </div>

      {isMinimized ? (
        <div className="mt-2 flex items-center justify-between gap-2">
          <h3 className="truncate text-sm font-semibold text-white">
            {task.title}
          </h3>
          {task.is_ai_improved && (
            <span className="shrink-0 rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-purple-300">
              ✨ AI
            </span>
          )}
        </div>
      ) : (
        <div className="mt-3">
          {isTranscribing && (
            <div className="mb-3 flex items-center gap-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Transcribing voice note via OpenAI Whisper...</span>
            </div>
          )}

          {task.processing_state === "FAILED" && task.error_message && (
            <div className="mb-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              Error: {task.error_message}
            </div>
          )}

          {isEditing ? (
            <div
              onPointerDown={(e) => e.stopPropagation()}
              className="mb-3 space-y-2 rounded-lg border border-slate-700 bg-slate-950 p-2.5"
            >
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
              />
              <textarea
                rows={2}
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Task description..."
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
              />
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={editPriority}
                  onChange={(e) =>
                    setEditPriority(e.target.value as TaskPriority)
                  }
                  className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white focus:border-indigo-500 focus:outline-none"
                >
                  <option value="LOW">🟢 Low</option>
                  <option value="MEDIUM">🔵 Medium</option>
                  <option value="HIGH">🟠 High</option>
                  <option value="URGENT">🔴 Urgent</option>
                </select>
                <input
                  type="text"
                  value={editTags}
                  onChange={(e) => setEditTags(e.target.value)}
                  placeholder="tags (comma separated)"
                  className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-1.5">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="rounded px-2.5 py-1 text-xs text-slate-400 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleSaveEdit()}
                  className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-500"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div className="mb-3 space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm leading-snug font-semibold text-white">
                  {task.title}
                </h3>
                {task.is_ai_improved && (
                  <span className="shrink-0 rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-purple-300">
                    ✨ AI Improved
                  </span>
                )}
              </div>
              {task.description && (
                <p className="text-xs leading-relaxed whitespace-pre-line text-slate-300">
                  {task.description}
                </p>
              )}
              {task.tags && task.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {task.tags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-300"
                    >
                      <Tag className="h-2.5 w-2.5 text-indigo-400" />
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {task.is_ai_improved && (
            <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/70">
              <button
                type="button"
                onClick={() => setShowRawInput(!showRawInput)}
                className="flex w-full items-center justify-between px-3 py-1.5 text-[11px] font-medium text-slate-400 hover:text-slate-200"
              >
                <span>Original Raw Input</span>
                {showRawInput ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>
              {showRawInput && (
                <div className="border-t border-slate-800 px-3 py-2 text-[11px] text-slate-400">
                  {task.raw_input}
                </div>
              )}
            </div>
          )}

          <div
            onPointerDown={(e) => e.stopPropagation()}
            className="mb-3"
          >
            <MentionInput
              mentions={task.mentions}
              isOwner={isOwner}
              registeredUsers={registeredUsers}
              onUpdateMentions={(usernames) =>
                onUpdateMentions(task.id, usernames)
              }
            />
          </div>

          <div className="mb-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={isImproving || isTranscribing}
              onClick={() => void onAiImprove(task.id)}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-500/15 px-2.5 py-1.5 text-[11px] font-semibold text-purple-200 transition hover:bg-purple-500/25 disabled:opacity-50"
            >
              {isImproving ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Improving...
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5" />✨ AI Improve Task
                </>
              )}
            </button>

            <button
              type="button"
              disabled={isGeneratingCheckpoints || isTranscribing}
              onClick={() => void onAiGenerateCheckpoints(task.id)}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-500/15 px-2.5 py-1.5 text-[11px] font-semibold text-indigo-200 transition hover:bg-indigo-500/25 disabled:opacity-50"
            >
              {isGeneratingCheckpoints ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Generating Checkpoints...
                </>
              ) : (
                <>
                  <CheckSquare className="h-3.5 w-3.5" />☑️ Generate Checkpoints
                </>
              )}
            </button>
          </div>

          <div onPointerDown={(e) => e.stopPropagation()}>
            <CheckpointList
              checkpoints={task.checkpoints}
              onAddCheckpoint={(title) => onAddCheckpoint(task.id, title)}
              onToggleCheckpoint={(checkpointId, isCompleted) =>
                onToggleCheckpoint(task.id, checkpointId, isCompleted)
              }
              onDeleteCheckpoint={(checkpointId) =>
                onDeleteCheckpoint(task.id, checkpointId)
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}
