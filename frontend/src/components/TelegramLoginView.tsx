import { Bot, ShieldCheck, Smartphone, Sparkles, Terminal } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import type { DevAuthInput, TelegramWidgetUser } from "../types";

interface TelegramLoginViewProps {
  onTelegramAuth: (user: TelegramWidgetUser) => Promise<void>;
  onTelegramWebAppAuth: (initData: string) => Promise<void>;
  onDevAuth: (input: DevAuthInput) => Promise<void>;
  errorMessage: string | null;
}

declare global {
  interface Window {
    onTelegramAuthCallback?: (user: TelegramWidgetUser) => void;
  }
}

export function TelegramLoginView({
  onTelegramAuth,
  onTelegramWebAppAuth,
  onDevAuth,
  errorMessage,
}: TelegramLoginViewProps) {
  const widgetContainerRef = useRef<HTMLDivElement | null>(null);
  const [devUsername, setDevUsername] = useState<string>("owner_alice");
  const [devFirstName, setDevFirstName] = useState<string>("Alice");
  const [devTelegramId, setDevTelegramId] = useState<string>("100001");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [webAppInitData, setWebAppInitData] = useState<string>("");
  const [webAppDisplayName, setWebAppDisplayName] = useState<string>("");

  const botUsername: string =
    (import.meta.env.VITE_TELEGRAM_BOT_USERNAME as string | undefined) ??
    "YourTaskBot";
  const allowDevAuth: boolean =
    ((import.meta.env.VITE_ALLOW_DEV_AUTH as string | undefined) ?? "true") ===
    "true";

  useEffect(() => {
    const tgWebApp = window.Telegram?.WebApp;
    if (tgWebApp) {
      tgWebApp.ready();
      tgWebApp.expand();
      if (tgWebApp.initData && tgWebApp.initData.trim().length > 0) {
        setWebAppInitData(tgWebApp.initData.trim());
      }
      const webAppUser = tgWebApp.initDataUnsafe?.user;
      if (webAppUser) {
        setDevTelegramId(String(webAppUser.id));
        if (webAppUser.username) {
          setDevUsername(webAppUser.username);
          setWebAppDisplayName(`@${webAppUser.username}`);
        } else if (webAppUser.first_name) {
          setWebAppDisplayName(webAppUser.first_name);
        }
        if (webAppUser.first_name) {
          setDevFirstName(webAppUser.first_name);
        }
      }
    }

    window.onTelegramAuthCallback = (user: TelegramWidgetUser) => {
      void onTelegramAuth(user);
    };

    const container = widgetContainerRef.current;
    if (!container) {
      return;
    }
    container.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "8");
    script.setAttribute("data-onauth", "onTelegramAuthCallback(user)");
    script.setAttribute("data-auth-url", window.location.origin);
    script.setAttribute("data-request-access", "write");
    container.appendChild(script);

    return () => {
      delete window.onTelegramAuthCallback;
    };
  }, [botUsername, onTelegramAuth]);

  const handleWebAppContinue = async () => {
    if (!webAppInitData) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onTelegramWebAppAuth(webAppInitData);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDevSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!devUsername.trim()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onDevAuth({
        telegram_id: Number.parseInt(devTelegramId, 10) || 100001,
        username: devUsername.trim().replace(/^@/, "").toLowerCase(),
        first_name: devFirstName.trim() || "Developer",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const applyPreset = (tgId: string, uname: string, fname: string) => {
    setDevTelegramId(tgId);
    setDevUsername(uname);
    setDevFirstName(fname);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-12">
      <div className="w-full max-w-md space-y-6 rounded-2xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/30">
            <Bot className="h-8 w-8" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Omni-Channel Task Manager
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Sync tasks across Telegram Voice/Text, AI Workflows, and a Real-Time
            Drag-and-Drop Kanban Board.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3 text-xs text-slate-300">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            <span>AI Improve & Checkpoints</span>
          </div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>@username Public ACLs</span>
          </div>
        </div>

        {errorMessage && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-xs text-rose-300">
            {errorMessage}
          </div>
        )}

        {webAppInitData && (
          <div className="flex flex-col items-center space-y-3 rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-5">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-300 uppercase">
              <Smartphone className="h-4 w-4" />
              Telegram Mini App Detected
            </span>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => void handleWebAppContinue()}
              className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-600/25 transition hover:bg-emerald-500 disabled:opacity-50"
            >
              {isSubmitting
                ? "Signing in..."
                : `Continue as ${webAppDisplayName || "Telegram User"}`}
            </button>
          </div>
        )}

        <div className="flex flex-col items-center space-y-3 rounded-xl border border-slate-800 bg-slate-950 p-5">
          <span className="text-xs font-medium tracking-wider text-slate-400 uppercase">
            {webAppInitData
              ? "Or Sign In via Browser Widget"
              : "Official Telegram Login Widget"}
          </span>
          <div ref={widgetContainerRef} className="min-h-[44px]" />
        </div>

        {allowDevAuth && (
          <form
            onSubmit={handleDevSubmit}
            className="space-y-4 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-5"
          >
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-300">
                <Terminal className="h-4 w-4" />
                Local Dev Login Helper
              </span>
              <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-medium text-indigo-300">
                VITE_ALLOW_DEV_AUTH=true
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => applyPreset("100001", "owner_alice", "Alice")}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
              >
                @owner_alice
              </button>
              <button
                type="button"
                onClick={() => applyPreset("200002", "collab_bob", "Bob")}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
              >
                @collab_bob
              </button>
              <button
                type="button"
                onClick={() => applyPreset("300003", "stranger_eve", "Eve")}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
              >
                @stranger_eve
              </button>
            </div>

            <div className="space-y-2.5">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-300">
                  Telegram @username
                </label>
                <input
                  type="text"
                  required
                  minLength={5}
                  maxLength={32}
                  value={devUsername}
                  onChange={(e) => setDevUsername(e.target.value)}
                  placeholder="owner_alice"
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300">
                    First Name
                  </label>
                  <input
                    type="text"
                    required
                    value={devFirstName}
                    onChange={(e) => setDevFirstName(e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300">
                    Telegram ID
                  </label>
                  <input
                    type="number"
                    required
                    value={devTelegramId}
                    onChange={(e) => setDevTelegramId(e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {isSubmitting
                ? "Signing in..."
                : `Sign in as @${devUsername.replace(/^@/, "")}`}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
