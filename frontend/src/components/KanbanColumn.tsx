import { useDroppable } from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import type { Task, TaskStatus, TaskUpdateInput, User } from "../types";
import { TaskCard } from "./TaskCard";

interface KanbanColumnProps {
  status: TaskStatus;
  title: string;
  accentColorClass: string;
  tasks: Task[];
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

export function KanbanColumn({
  status,
  title,
  accentColorClass,
  tasks,
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
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: status,
    data: { status },
  });

  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-[540px] flex-col rounded-2xl border bg-slate-900/50 p-4 transition ${
        isOver
          ? "border-indigo-500/70 bg-indigo-950/20"
          : "border-slate-800/90"
      }`}
    >
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${accentColorClass}`} />
          <h2 className="text-sm font-bold tracking-wide text-slate-100 uppercase">
            {title}
          </h2>
        </div>
        <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-semibold text-slate-300">
          {tasks.length}
        </span>
      </div>

      <SortableContext
        items={tasks.map((t) => t.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-1 flex-col gap-3">
          {tasks.length === 0 ? (
            <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-800 p-8 text-center text-xs text-slate-500">
              Drop tasks here
            </div>
          ) : (
            tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                currentUser={currentUser}
                registeredUsers={registeredUsers}
                onUpdateTask={onUpdateTask}
                onUpdateMentions={onUpdateMentions}
                onDeleteTask={onDeleteTask}
                onAiImprove={onAiImprove}
                onAiGenerateCheckpoints={onAiGenerateCheckpoints}
                onAddCheckpoint={onAddCheckpoint}
                onToggleCheckpoint={onToggleCheckpoint}
                onDeleteCheckpoint={onDeleteCheckpoint}
              />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
}
