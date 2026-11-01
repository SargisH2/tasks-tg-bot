import { CheckSquare, Plus, Square, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import type { TaskCheckpoint } from "../types";

interface CheckpointListProps {
  checkpoints: TaskCheckpoint[];
  onToggleCheckpoint: (
    checkpointId: string,
    isCompleted: boolean,
  ) => Promise<void>;
  onAddCheckpoint: (title: string) => Promise<void>;
  onDeleteCheckpoint: (checkpointId: string) => Promise<void>;
}

export function CheckpointList({
  checkpoints,
  onToggleCheckpoint,
  onAddCheckpoint,
  onDeleteCheckpoint,
}: CheckpointListProps) {
  const [newTitle, setNewTitle] = useState<string>("");
  const [isBusy, setIsBusy] = useState<boolean>(false);

  const sorted = [...checkpoints].sort((a, b) => a.position - b.position);
  const completedCount = sorted.filter((c) => c.is_completed).length;
  const totalCount = sorted.length;
  const progressPercent =
    totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) {
      return;
    }
    setIsBusy(true);
    try {
      await onAddCheckpoint(newTitle.trim());
      setNewTitle("");
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="space-y-2 rounded-lg border border-slate-800/80 bg-slate-950/50 p-2.5">
      <div className="flex items-center justify-between text-[11px] font-medium text-slate-400">
        <span>Checkpoints</span>
        <span>
          {completedCount} / {totalCount} ({progressPercent}%)
        </span>
      </div>

      {totalCount > 0 && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full bg-emerald-500 transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}

      {sorted.length > 0 && (
        <ul className="space-y-1">
          {sorted.map((ckpt) => (
            <li
              key={ckpt.id}
              className="group flex items-center justify-between gap-2 rounded px-1.5 py-1 hover:bg-slate-900"
            >
              <button
                type="button"
                onClick={() =>
                  void onToggleCheckpoint(ckpt.id, !ckpt.is_completed)
                }
                className="flex flex-1 items-start gap-2 text-left text-xs"
              >
                {ckpt.is_completed ? (
                  <CheckSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                ) : (
                  <Square className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                )}
                <span
                  className={
                    ckpt.is_completed
                      ? "text-slate-500 line-through"
                      : "text-slate-200"
                  }
                >
                  {ckpt.title}
                </span>
              </button>
              <button
                type="button"
                onClick={() => void onDeleteCheckpoint(ckpt.id)}
                title="Remove checkpoint"
                className="opacity-0 transition group-hover:opacity-100 hover:text-rose-400"
              >
                <Trash2 className="h-3 w-3 text-slate-500 hover:text-rose-400" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleAdd} className="flex items-center gap-1.5 pt-1">
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Add custom checkpoint..."
          disabled={isBusy}
          className="w-full rounded border border-slate-800 bg-slate-900 px-2 py-1 text-[11px] text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={isBusy || !newTitle.trim()}
          className="inline-flex items-center gap-0.5 rounded bg-slate-800 px-2 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
        >
          <Plus className="h-3 w-3" />
          Add
        </button>
      </form>
    </div>
  );
}
