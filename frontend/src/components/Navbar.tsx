import {
  AlertTriangle,
  CheckCircle2,
  Globe,
  Layers,
  Lock,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  Tag,
  Users,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useState } from "react";
import type { Task, TaskFilterMode, TaskPriority, User } from "../types";

interface NavbarProps {
  user: User;
  registeredUsers: User[];
  tasks: Task[];
  isConnected: boolean;
  filterMode: TaskFilterMode;
  searchQuery: string;
  priorityFilter: TaskPriority | "ALL";
  collaboratorFilter: string | null;
  tagFilter: string | null;
  onFilterChange: (mode: TaskFilterMode) => void;
  onSearchChange: (q: string) => void;
  onPriorityFilterChange: (p: TaskPriority | "ALL") => void;
  onCollaboratorFilterChange: (uname: string | null) => void;
  onTagFilterChange: (tag: string | null) => void;
  onOpenCreateModal: () => void;
  onRefresh: () => void;
  onLogout: () => void;
}

export function Navbar({
  user,
  registeredUsers,
  tasks,
  isConnected,
  filterMode,
  searchQuery,
  priorityFilter,
  collaboratorFilter,
  tagFilter,
  onFilterChange,
  onSearchChange,
  onPriorityFilterChange,
  onCollaboratorFilterChange,
  onTagFilterChange,
  onOpenCreateModal,
  onRefresh,
  onLogout,
}: NavbarProps) {
  const [showUsersPanel, setShowUsersPanel] = useState<boolean>(false);

  const registeredMap = new Map<string, User>();
  for (const reg of registeredUsers) {
    if (reg.username) {
      registeredMap.set(reg.username.toLowerCase(), reg);
    }
  }

  const allMentionedSet = new Set<string>();
  const allTagsSet = new Set<string>();
  for (const t of tasks) {
    for (const m of t.mentions) {
      allMentionedSet.add(m.telegram_username.toLowerCase());
    }
    for (const tg of t.tags ?? []) {
      allTagsSet.add(tg.toLowerCase());
    }
  }
  const allMentioned = Array.from(allMentionedSet).sort();
  const unregisteredMentioned = allMentioned.filter(
    (uname) => !registeredMap.has(uname),
  );
  const allTags = Array.from(allTagsSet).sort();

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-900/95 backdrop-blur-md">
      <div className="mx-auto max-w-7xl space-y-3 px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 font-bold text-white shadow-lg shadow-indigo-600/30">
              OM
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">
                Omni-Channel Task Manager
              </h1>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span>
                  Signed in as{" "}
                  <strong className="text-indigo-400">
                    @{user.username ?? user.first_name}
                  </strong>
                </span>
                <span>•</span>
                <span
                  className={`inline-flex items-center gap-1 font-medium ${
                    isConnected ? "text-emerald-400" : "text-amber-400"
                  }`}
                >
                  {isConnected ? (
                    <>
                      <Wifi className="h-3.5 w-3.5" />
                      Live WebSocket
                    </>
                  ) : (
                    <>
                      <WifiOff className="h-3.5 w-3.5" />
                      Reconnecting...
                    </>
                  )}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-slate-800 bg-slate-950 p-1">
              <button
                type="button"
                onClick={() => onFilterChange("all")}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  filterMode === "all"
                    ? "bg-indigo-600 text-white shadow"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                All Accessible
              </button>
              <button
                type="button"
                onClick={() => onFilterChange("private")}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  filterMode === "private"
                    ? "bg-indigo-600 text-white shadow"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Lock className="h-3.5 w-3.5" />
                My Private Tasks
              </button>
              <button
                type="button"
                onClick={() => onFilterChange("shared")}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  filterMode === "shared"
                    ? "bg-indigo-600 text-white shadow"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Globe className="h-3.5 w-3.5" />
                Shared Public Tasks
              </button>
            </div>

            <button
              type="button"
              onClick={() => setShowUsersPanel(!showUsersPanel)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition ${
                showUsersPanel
                  ? "border-indigo-500 bg-indigo-600/20 text-indigo-200"
                  : "border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800"
              }`}
            >
              <Users className="h-3.5 w-3.5 text-indigo-400" />
              Users ({registeredUsers.length})
              {unregisteredMentioned.length > 0 && (
                <span className="rounded-full bg-amber-500/20 px-1.5 py-0.2 text-[10px] text-amber-300">
                  {unregisteredMentioned.length} unavailable
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={onOpenCreateModal}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-500"
            >
              <Plus className="h-4 w-4" />+ New Task
            </button>

            <button
              type="button"
              onClick={onRefresh}
              title="Refresh tasks & users"
              className="rounded-lg border border-slate-800 bg-slate-900 p-2 text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              <RefreshCw className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={onLogout}
              title="Sign out"
              className="inline-flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300"
            >
              <LogOut className="h-3.5 w-3.5" />
              Logout
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute top-2.5 left-3 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search tasks by title, description, @username, or tag..."
              className="w-full rounded-lg border border-slate-800 bg-slate-950 py-1.5 pr-8 pl-8 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange("")}
                className="absolute top-2 right-2.5 text-slate-400 hover:text-white"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <select
            value={priorityFilter}
            onChange={(e) =>
              onPriorityFilterChange(e.target.value as TaskPriority | "ALL")
            }
            className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
          >
            <option value="ALL">All Priorities</option>
            <option value="URGENT">🔴 Urgent Only</option>
            <option value="HIGH">🟠 High Priority</option>
            <option value="MEDIUM">🔵 Medium Priority</option>
            <option value="LOW">🟢 Low Priority</option>
          </select>

          {allMentioned.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              {allMentioned.map((uname) => {
                const isSelected = collaboratorFilter === uname;
                const isReg = registeredMap.has(uname);
                return (
                  <button
                    key={uname}
                    type="button"
                    onClick={() =>
                      onCollaboratorFilterChange(isSelected ? null : uname)
                    }
                    title={
                      isReg
                        ? `Filter by registered user @${uname}`
                        : `@${uname} — User not available (not registered yet)`
                    }
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
                      isSelected
                        ? "border-indigo-400 bg-indigo-600 text-white"
                        : isReg
                          ? "border-slate-800 bg-slate-950 text-slate-300 hover:border-indigo-500/40"
                          : "border-amber-500/40 bg-amber-500/10 text-amber-300"
                    }`}
                  >
                    {isReg ? (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    ) : (
                      <AlertTriangle className="h-3 w-3 text-amber-400" />
                    )}
                    @{uname}
                  </button>
                );
              })}
            </div>
          )}

          {allTags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              {allTags.map((tg) => {
                const isSelected = tagFilter === tg;
                return (
                  <button
                    key={tg}
                    type="button"
                    onClick={() => onTagFilterChange(isSelected ? null : tg)}
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-medium transition ${
                      isSelected
                        ? "border-purple-400 bg-purple-600 text-white"
                        : "border-slate-800 bg-slate-950 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Tag className="h-2.5 w-2.5" />
                    {tg}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {showUsersPanel && (
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold tracking-wider text-slate-200 uppercase">
                  Workspace Users Directory & Availability Status
                </h3>
                <p className="text-[11px] text-slate-400">
                  Click any @username below to filter tasks shared with them.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowUsersPanel(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2 rounded-lg border border-slate-800/90 bg-slate-900/60 p-3">
                <div className="flex items-center justify-between text-xs font-semibold text-emerald-400">
                  <span className="inline-flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Registered Users ({registeredUsers.length})
                  </span>
                </div>
                {registeredUsers.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    No registered users found.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {registeredUsers.map((regUser) => {
                      const uname = regUser.username?.toLowerCase() ?? "";
                      const isSelected =
                        uname !== "" && collaboratorFilter === uname;
                      return (
                        <button
                          key={regUser.id}
                          type="button"
                          onClick={() => {
                            if (uname) {
                              onCollaboratorFilterChange(
                                isSelected ? null : uname,
                              );
                            }
                          }}
                          className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition ${
                            isSelected
                              ? "border-indigo-400 bg-indigo-600 text-white"
                              : "border-slate-800 bg-slate-950 text-slate-200 hover:border-indigo-500/40"
                          }`}
                        >
                          <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                          <span className="font-semibold text-indigo-300">
                            @{regUser.username ?? "no_username"}
                          </span>
                          <span className="text-[11px] text-slate-400">
                            ({regUser.first_name} {regUser.last_name ?? ""})
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="space-y-2 rounded-lg border border-slate-800/90 bg-slate-900/60 p-3">
                <div className="flex items-center justify-between text-xs font-semibold text-amber-400">
                  <span className="inline-flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Mentioned Users Not Registered Yet (
                    {unregisteredMentioned.length})
                  </span>
                </div>
                {unregisteredMentioned.length === 0 ? (
                  <p className="text-xs text-slate-400">
                    All mentioned @username collaborators are registered and
                    available!
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {unregisteredMentioned.map((uname) => (
                      <div
                        key={uname}
                        className="flex items-center justify-between rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-200"
                      >
                        <span className="font-semibold">@{uname}</span>
                        <span className="text-[11px] text-amber-300">
                          ⚠️ User not available (not registered yet)
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
