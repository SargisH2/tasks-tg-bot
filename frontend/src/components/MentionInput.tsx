import {
  AlertTriangle,
  AtSign,
  CheckCircle2,
  Plus,
  UserCheck,
  X,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import type { TaskMention, User } from "../types";

interface MentionInputProps {
  mentions: TaskMention[];
  isOwner: boolean;
  registeredUsers: User[];
  onUpdateMentions: (usernames: string[]) => Promise<void>;
}

export function MentionInput({
  mentions,
  isOwner,
  registeredUsers,
  onUpdateMentions,
}: MentionInputProps) {
  const [inputValue, setInputValue] = useState<string>("");
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [showHints, setShowHints] = useState<boolean>(false);

  const currentNames = mentions.map((m) => m.telegram_username.toLowerCase());
  const registeredMap = new Map<string, User>();
  for (const u of registeredUsers) {
    if (u.username) {
      registeredMap.set(u.username.toLowerCase(), u);
    }
  }

  const unregisteredMentions = currentNames.filter(
    (uname) => !registeredMap.has(uname),
  );

  const cleanedDraft = inputValue.trim().replace(/^@/, "").toLowerCase();
  const matchingHints = registeredUsers.filter((u) => {
    if (!u.username) {
      return false;
    }
    const uname = u.username.toLowerCase();
    if (currentNames.includes(uname)) {
      return false;
    }
    if (!cleanedDraft) {
      return true;
    }
    const fullName = `${u.first_name} ${u.last_name ?? ""}`.toLowerCase();
    return uname.includes(cleanedDraft) || fullName.includes(cleanedDraft);
  });

  const isDraftValidFormat =
    cleanedDraft.length >= 5 &&
    cleanedDraft.length <= 32 &&
    /^[a-z0-9_]+$/.test(cleanedDraft);
  const isDraftUnregistered =
    cleanedDraft.length >= 3 &&
    !registeredMap.has(cleanedDraft) &&
    matchingHints.length === 0;

  const addSpecificUsername = async (unameToAdd: string) => {
    const cleaned = unameToAdd.trim().replace(/^@/, "").toLowerCase();
    if (
      cleaned.length < 5 ||
      cleaned.length > 32 ||
      !/^[a-z0-9_]+$/.test(cleaned)
    ) {
      return;
    }
    if (currentNames.includes(cleaned)) {
      setInputValue("");
      setShowHints(false);
      return;
    }
    setIsUpdating(true);
    try {
      await onUpdateMentions([...currentNames, cleaned]);
      setInputValue("");
      setShowHints(false);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    await addSpecificUsername(inputValue);
  };

  const handleRemove = async (usernameToRemove: string) => {
    if (!isOwner) {
      return;
    }
    setIsUpdating(true);
    try {
      await onUpdateMentions(
        currentNames.filter((name) => name !== usernameToRemove.toLowerCase()),
      );
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="space-y-1.5 rounded-lg border border-slate-800/80 bg-slate-950/60 p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400">
          <AtSign className="h-3 w-3 text-indigo-400" />
          Collaborators:
        </span>
        {mentions.length === 0 ? (
          <span className="text-[11px] text-slate-500 italic">
            None mentioned
          </span>
        ) : (
          mentions.map((mention) => {
            const uname = mention.telegram_username.toLowerCase();
            const regUser = registeredMap.get(uname);
            const isRegistered = Boolean(regUser);
            return (
              <span
                key={mention.id}
                title={
                  regUser
                    ? `Registered user: ${regUser.first_name} ${regUser.last_name ?? ""}`.trim()
                    : `User @${uname} is not registered yet`
                }
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                  isRegistered
                    ? "border-indigo-500/30 bg-indigo-500/15 text-indigo-300"
                    : "border-amber-500/40 bg-amber-500/15 text-amber-300"
                }`}
              >
                {isRegistered ? (
                  <CheckCircle2 className="h-2.5 w-2.5 text-emerald-400" />
                ) : (
                  <AlertTriangle className="h-2.5 w-2.5 text-amber-400" />
                )}
                @{mention.telegram_username}
                {isOwner && (
                  <button
                    type="button"
                    disabled={isUpdating}
                    onClick={() => void handleRemove(mention.telegram_username)}
                    title="Remove collaborator"
                    className="ml-0.5 opacity-80 hover:text-rose-300 hover:opacity-100"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                )}
              </span>
            );
          })
        )}
      </div>

      {unregisteredMentions.length > 0 && (
        <div className="flex items-start gap-1.5 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-200">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
          <span>
            User not available:{" "}
            <strong>
              {unregisteredMentions.map((u) => `@${u}`).join(", ")}
            </strong>{" "}
            {unregisteredMentions.length === 1 ? "is" : "are"} not registered
            yet (must send /start to the bot or log in first).
          </span>
        </div>
      )}

      {isOwner && (
        <div className="relative pt-1">
          <form onSubmit={handleAdd} className="flex items-center gap-1.5">
            <input
              type="text"
              value={inputValue}
              onFocus={() => setShowHints(true)}
              onBlur={() => {
                window.setTimeout(() => setShowHints(false), 180);
              }}
              onChange={(e) => {
                setInputValue(e.target.value);
                setShowHints(true);
              }}
              placeholder="+ @username (type for hints)"
              disabled={isUpdating}
              className="w-full rounded border border-slate-800 bg-slate-900 px-2 py-1 text-[11px] text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={isUpdating || !isDraftValidFormat}
              className="inline-flex items-center gap-0.5 rounded bg-slate-800 px-2 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
            >
              <Plus className="h-3 w-3" />
              Add
            </button>
          </form>

          {showHints && matchingHints.length > 0 && (
            <div className="absolute right-0 left-0 z-30 mt-1 max-h-36 overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-1 shadow-xl">
              <div className="px-2 py-0.5 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                Registered @username Hints
              </div>
              {matchingHints.slice(0, 6).map((hintUser) => (
                <button
                  key={hintUser.id}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    if (hintUser.username) {
                      void addSpecificUsername(hintUser.username);
                    }
                  }}
                  className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-[11px] text-slate-200 hover:bg-indigo-600/30"
                >
                  <span className="inline-flex items-center gap-1 font-medium text-indigo-300">
                    <UserCheck className="h-3 w-3 text-emerald-400" />@
                    {hintUser.username}
                  </span>
                  <span className="truncate text-[10px] text-slate-400">
                    {hintUser.first_name} {hintUser.last_name ?? ""}
                  </span>
                </button>
              ))}
            </div>
          )}

          {isDraftUnregistered && (
            <div className="mt-1 flex items-center gap-1 text-[10px] text-amber-300">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              <span>
                @{cleanedDraft} — User not available (not registered yet)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
