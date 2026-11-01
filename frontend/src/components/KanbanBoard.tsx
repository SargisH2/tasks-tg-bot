import {
  type CollisionDetection,
  closestCorners,
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  KeyboardSensor,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { useState } from "react";
import type { Task, TaskStatus, TaskUpdateInput, User } from "../types";
import { KanbanColumn } from "./KanbanColumn";

interface KanbanBoardProps {
  tasks: Task[];
  currentUser: User;
  registeredUsers: User[];
  onMoveTask: (
    taskId: string,
    newStatus: TaskStatus,
    newPosition: number,
  ) => Promise<void>;
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

const COLUMNS: Array<{
  status: TaskStatus;
  title: string;
  accentColorClass: string;
}> = [
  {
    status: "PENDING",
    title: "Pending",
    accentColorClass: "bg-amber-400",
  },
  {
    status: "IN_PROGRESS",
    title: "In Progress",
    accentColorClass: "bg-indigo-400",
  },
  {
    status: "COMPLETED",
    title: "Completed",
    accentColorClass: "bg-emerald-400",
  },
];

const VALID_STATUSES: TaskStatus[] = ["PENDING", "IN_PROGRESS", "COMPLETED"];

const collisionDetectionStrategy: CollisionDetection = (args) => {
  const pointerCollisions = pointerWithin(args);
  if (pointerCollisions.length > 0) {
    const taskCollision = pointerCollisions.find(
      (c) => !VALID_STATUSES.includes(String(c.id) as TaskStatus),
    );
    if (taskCollision) {
      return [taskCollision];
    }
    return pointerCollisions;
  }
  const rectCollisions = rectIntersection(args);
  if (rectCollisions.length > 0) {
    return rectCollisions;
  }
  return closestCorners(args);
};

export function KanbanBoard({
  tasks,
  currentUser,
  registeredUsers,
  onMoveTask,
  onUpdateTask,
  onUpdateMentions,
  onDeleteTask,
  onAiImprove,
  onAiGenerateCheckpoints,
  onAddCheckpoint,
  onToggleCheckpoint,
  onDeleteCheckpoint,
}: KanbanBoardProps) {
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 150, tolerance: 5 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragStart = (event: DragStartEvent) => {
    const found = tasks.find((t) => t.id === String(event.active.id)) ?? null;
    setActiveTask(found);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveTask(null);
    const { active, over } = event;
    if (!over) {
      return;
    }

    const activeTaskId = String(active.id);
    const overId = String(over.id);

    const draggedTask = tasks.find((t) => t.id === activeTaskId);
    if (!draggedTask) {
      return;
    }

    let destinationStatus: TaskStatus = draggedTask.status;
    let destinationPosition = draggedTask.position;

    if (VALID_STATUSES.includes(overId as TaskStatus)) {
      destinationStatus = overId as TaskStatus;
      const columnTasks = tasks.filter(
        (t) => t.status === destinationStatus && t.id !== activeTaskId,
      );
      destinationPosition = columnTasks.length;
    } else {
      const overTask = tasks.find((t) => t.id === overId);
      if (!overTask) {
        return;
      }
      destinationStatus = overTask.status;
      const columnTasks = tasks
        .filter((t) => t.status === destinationStatus)
        .sort((a, b) => a.position - b.position);
      const targetIndex = columnTasks.findIndex((t) => t.id === overTask.id);
      destinationPosition = targetIndex >= 0 ? targetIndex : 0;

      if (
        destinationStatus === draggedTask.status &&
        overTask.id === draggedTask.id
      ) {
        return;
      }
    }

    if (
      destinationStatus === draggedTask.status &&
      VALID_STATUSES.includes(overId as TaskStatus)
    ) {
      return;
    }

    void onMoveTask(activeTaskId, destinationStatus, destinationPosition);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisionDetectionStrategy}
      onDragStart={handleDragStart}
      onDragCancel={() => setActiveTask(null)}
      onDragEnd={handleDragEnd}
    >
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {COLUMNS.map((column) => {
          const columnTasks = tasks
            .filter((t) => t.status === column.status)
            .sort((a, b) => a.position - b.position);

          return (
            <KanbanColumn
              key={column.status}
              status={column.status}
              title={column.title}
              accentColorClass={column.accentColorClass}
              tasks={columnTasks}
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
          );
        })}
      </div>

      <DragOverlay>
        {activeTask ? (
          <div className="w-full max-w-sm rotate-1 rounded-xl border-2 border-indigo-500 bg-slate-900/95 p-3.5 shadow-2xl">
            <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px] font-semibold text-indigo-300">
              <span>
                {activeTask.visibility === "PUBLIC"
                  ? "🌐 Public"
                  : "🔒 Private"}
              </span>
              <span>Moving card...</span>
            </div>
            <h3 className="truncate text-sm font-semibold text-white">
              {activeTask.title}
            </h3>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
