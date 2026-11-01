import {
  closestCorners,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
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
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
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
      const columnTasks = tasks.filter((t) => t.status === destinationStatus);
      destinationPosition = columnTasks.length;
    } else {
      const overTask = tasks.find((t) => t.id === overId);
      if (overTask) {
        destinationStatus = overTask.status;
        const columnTasks = tasks
          .filter((t) => t.status === destinationStatus)
          .sort((a, b) => a.position - b.position);
        const targetIndex = columnTasks.findIndex((t) => t.id === overTask.id);
        destinationPosition = targetIndex >= 0 ? targetIndex : 0;
      }
    }

    if (
      destinationStatus === draggedTask.status &&
      destinationPosition === draggedTask.position
    ) {
      return;
    }

    void onMoveTask(activeTaskId, destinationStatus, destinationPosition);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
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
    </DndContext>
  );
}
