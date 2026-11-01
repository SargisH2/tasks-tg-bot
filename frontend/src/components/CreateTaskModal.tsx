import {
  AlertTriangle,
  CheckCircle2,
  Globe,
  Lock,
  Plus,
  UserCheck,
  X,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import type {
  TaskCreateInput,
  TaskPriority,
  TaskStatus,
  TaskVisibility,
  User,
} from "../types";

interface CreateTaskModalProps {
  isOpen: boolean;
  registeredUsers: User[];
  onClose: () => void;
  onCreate: (payload: TaskCreateInput) => Promise<void>;
}

export function CreateTaskModal({
  isOpen,
  registeredUsers,
  onClose,
  onCreate,
}: CreateTaskModalProps) {
  const [title, setTitle] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [visibility, setVisibility] = useState<TaskVisibility>("PRIVATE");
  const [status, setStatus] = useState<TaskStatus>("PENDING");
  const [priority, setPriority] = useState<TaskPriority>("MEDIUM");
  const [tagsInput, setTagsInput] = useState<string>("");
  const [mentionDraft, setMentionDraft] = useState<string>("");
  const [mentions, setMentions] = useState<string[]>([]);
  const [showHints, setShowHints] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  if (!isOpen) {
    return null;
  }

  const registeredMap = new Map<string, User>();
  for (const u of registeredUsers) {
    if (u.username) {
      registeredMap.set(u.username.toLowerCase(), u);
    }
  }

  const cleanedDraft = mentionDraft.trim().replace(/^@/, "").toLowerCase();
  const matchingHints = registeredUsers.filter((u) => {
    if (!u.username) {
      return false;
    }
    const uname = u.username.toLowerCase();
    if (mentions.includes(uname)) {
      return false;
    }
    if (!cleanedDraft) {
      return true;
    }
    const fullName = `${u.first_name} ${u.last_name ?? ""}`.toLowerCase();
    return uname.includes(cleanedDraft) || fullName.includes(cleanedDraft);
  });

  const addMentionValue = (rawVal: string) => {
    const cleaned = rawVal.trim().replace(/^@/, "").toLowerCase();
    if (
      cleaned.length >= 5 &&
      cleaned.length <= 32 &&
      /^[a-z0-9_]+$/.test(cleaned)
    ) {
      if (!mentions.includes(cleaned)) {
        setMentions([...mentions, cleaned]);
      }
      setMentionDraft("");
      setShowHints(false);
    }
  };

  const removeMention = (uname: string) => {
    setMentions(mentions.filter((m) => m !== uname));
  };

  const unregisteredMentions = mentions.filter((m) => !registeredMap.has(m));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      return;
    }
    const parsedTags = tagsInput
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);

    setIsSubmitting(true);
    try {
      await onCreate({
        title: title.trim(),
        description: description.trim() || null,
        visibility,
        status,
        priority,
        tags: parsedTags,
        mentions,
      });
      setTitle("");
      setDescription("");
      setVisibility("PRIVATE");
      setStatus("PENDING");
      setPriority("MEDIUM");
      setTagsInput("");
      setMentions([]);
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white">Create New Task</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Task Title (supports inline @username mentions)
            </label>
            <input
              type="text"
              required
              maxLength={255}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Deploy payment webhook with @collab_bob"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Description (Optional)
            </label>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add context, links, or notes..."
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">
                Visibility
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => setVisibility("PRIVATE")}
                  className={`flex items-center justify-center gap-1 rounded-lg border px-2 py-2 text-[11px] font-medium transition ${
                    visibility === "PRIVATE"
                      ? "border-amber-500/50 bg-amber-500/15 text-amber-300"
                      : "border-slate-800 bg-slate-950 text-slate-400"
                  }`}
                >
                  <Lock className="h-3 w-3" />
                  Private
                </button>
                <button
                  type="button"
                  onClick={() => setVisibility("PUBLIC")}
                  className={`flex items-center justify-center gap-1 rounded-lg border px-2 py-2 text-[11px] font-medium transition ${
                    visibility === "PUBLIC"
                      ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                      : "border-slate-800 bg-slate-950 text-slate-400"
                  }`}
                >
                  <Globe className="h-3 w-3" />
                  Public
                </button>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as TaskPriority)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
              >
                <option value="LOW">🟢 Low</option>
                <option value="MEDIUM">🔵 Medium</option>
                <option value="HIGH">🟠 High</option>
                <option value="URGENT">🔴 Urgent</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">
                Initial Column
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as TaskStatus)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
              >
                <option value="PENDING">Pending</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="COMPLETED">Completed</option>
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Tags (comma-separated, optional)
            </label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="backend, release, urgent"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div className="relative">
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Mentioned Telegram Collaborators (@username hints)
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={mentionDraft}
                onFocus={() => setShowHints(true)}
                onBlur={() => {
                  window.setTimeout(() => setShowHints(false), 180);
                }}
                onChange={(e) => {
                  setMentionDraft(e.target.value);
                  setShowHints(true);
                }}
                placeholder="Type @username or pick from hints..."
                className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => addMentionValue(mentionDraft)}
                className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>

            {showHints && matchingHints.length > 0 && (
              <div className="absolute right-0 left-0 z-30 mt-1 max-h-36 overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-1 shadow-xl">
                <div className="px-2 py-0.5 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                  Registered Users (@username Hints)
                </div>
                {matchingHints.slice(0, 6).map((hintUser) => (
                  <button
                    key={hintUser.id}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (hintUser.username) {
                        addMentionValue(hintUser.username);
                      }
                    }}
                    className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs text-slate-200 hover:bg-indigo-600/30"
                  >
                    <span className="inline-flex items-center gap-1 font-medium text-indigo-300">
                      <UserCheck className="h-3.5 w-3.5 text-emerald-400" />@
                      {hintUser.username}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {hintUser.first_name} {hintUser.last_name ?? ""}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {mentions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {mentions.map((uname) => {
                  const isReg = registeredMap.has(uname);
                  return (
                    <span
                      key={uname}
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                        isReg
                          ? "border-indigo-500/30 bg-indigo-500/20 text-indigo-300"
                          : "border-amber-500/40 bg-amber-500/15 text-amber-300"
                      }`}
                    >
                      {isReg ? (
                        <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                      ) : (
                        <AlertTriangle className="h-3 w-3 text-amber-400" />
                      )}
                      @{uname}
                      <button
                        type="button"
                        onClick={() => removeMention(uname)}
                        className="ml-0.5 hover:text-white"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  );
                })}
              </div>
            )}

            {unregisteredMentions.length > 0 && (
              <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-200">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                <span>
                  User not available:{" "}
                  <strong>
                    {unregisteredMentions.map((u) => `@${u}`).join(", ")}
                  </strong>{" "}
                  is not registered yet. They will gain access once they send
                  /start to the bot or log in.
                </span>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {isSubmitting ? "Creating..." : "Create Task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
