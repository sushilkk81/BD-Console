"use client";
import { useState } from "react";

import { Message } from "@/lib/api";

export function MessageThread({
  messages,
  emptyLabel,
  onPost,
  posting = false,
  placeholder = "Write a message…",
}: {
  messages: Message[];
  emptyLabel: string;
  onPost?: (body: string) => Promise<void>;
  posting?: boolean;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  async function handleSend() {
    if (!onPost || !draft.trim()) return;
    await onPost(draft.trim());
    setDraft("");
  }

  return (
    <div className="flex flex-col gap-3">
      {messages.length === 0 ? (
        <p className="font-body text-sm text-ink-700/50">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {messages.map((m) => (
            <li key={m.id} className="rounded-lg border border-ink-700/10 bg-sand-50 px-3.5 py-2.5">
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <span className="font-body text-xs font-medium text-ink-700">{m.sender_name}</span>
                <span className="font-mono text-xs text-ink-700/50">{new Date(m.created_at).toLocaleString()}</span>
              </div>
              <p className="font-body text-sm text-ink-700">{m.body}</p>
            </li>
          ))}
        </ul>
      )}

      {onPost && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={placeholder}
            rows={2}
            className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={posting || !draft.trim()}
            className="rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
