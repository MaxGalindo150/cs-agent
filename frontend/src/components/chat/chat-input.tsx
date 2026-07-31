"use client";

import { useState, type KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  isStreaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

/** Message composer: a growing textarea plus a send/stop button.
 *  Enter sends, Shift+Enter inserts a newline. */
export function ChatInput({ isStreaming, onSend, onStop }: ChatInputProps) {
  const [value, setValue] = useState("");
  const canSend = value.trim().length > 0 && !isStreaming;

  function submit() {
    if (!canSend) return;
    onSend(value);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-2 transition-colors duration-150 focus-within:border-zinc-700">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Send a message…"
        rows={1}
        className="max-h-44 min-h-9 flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-sm text-zinc-100 shadow-none placeholder:text-zinc-500 focus-visible:border-0 focus-visible:ring-0 dark:bg-transparent"
      />
      {isStreaming ? (
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className="rounded-lg"
          onClick={onStop}
          aria-label="Stop generating"
        >
          <Square className="fill-current" />
        </Button>
      ) : (
        <Button
          type="button"
          size="icon"
          className="rounded-lg"
          onClick={submit}
          disabled={!canSend}
          aria-label="Send message"
        >
          <ArrowUp />
        </Button>
      )}
    </div>
  );
}
