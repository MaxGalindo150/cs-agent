"use client";

import {
  useCallback,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";
import { ArrowUp, Paperclip, Square, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { AttachedImage } from "@/lib/chat/types";

interface ChatInputProps {
  isStreaming: boolean;
  onSend: (text: string, images?: AttachedImage[]) => void;
  onStop: () => void;
}

// Mirrors agent-service's ImageInput validation (service/api/v1/chat.py) —
// checked here too so a bad attachment is rejected instantly instead of
// round-tripping to the server for a 422.
const ACCEPTED_MEDIA_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
]);
const MAX_IMAGES_PER_TURN = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** Strips the `data:<mime>;base64,` prefix FileReader adds — the API wants
 *  bare base64. */
function stripDataUrlPrefix(dataUrl: string): string {
  const comma = dataUrl.indexOf(",");
  return comma === -1 ? dataUrl : dataUrl.slice(comma + 1);
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(stripDataUrlPrefix(String(reader.result)));
    reader.onerror = () => reject(reader.error ?? new Error("failed to read file"));
    reader.readAsDataURL(file);
  });
}

/** Message composer: a growing textarea plus image attachments and a
 *  send/stop button. Enter sends, Shift+Enter inserts a newline. Images can
 *  be attached via the clip button or pasted directly (Ctrl+V) into the
 *  textarea — both funnel through the same validate-then-read pipeline. */
export function ChatInput({ isStreaming, onSend, onStop }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [images, setImages] = useState<AttachedImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canSend = value.trim().length > 0 && !isStreaming;

  const addFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;

      const room = MAX_IMAGES_PER_TURN - images.length;
      if (room <= 0) {
        setError(`You can attach up to ${MAX_IMAGES_PER_TURN} images.`);
        return;
      }

      const accepted: File[] = [];
      let rejected = false;
      for (const file of files) {
        if (!ACCEPTED_MEDIA_TYPES.has(file.type) || file.size > MAX_IMAGE_BYTES) {
          rejected = true;
          continue;
        }
        accepted.push(file);
        if (accepted.length >= room) break;
      }

      if (rejected) {
        setError("Some images were skipped (unsupported type or over 5MB).");
      } else if (accepted.length < files.length) {
        setError(`Only ${MAX_IMAGES_PER_TURN} images per message — extras were skipped.`);
      } else {
        setError(null);
      }

      const newImages = await Promise.all(
        accepted.map(async (file) => ({
          mediaType: file.type as AttachedImage["mediaType"],
          data: await readAsBase64(file),
          previewUrl: URL.createObjectURL(file),
        })),
      );
      setImages((prev) => [...prev, ...newImages]);
    },
    [images.length],
  );

  function removeImage(index: number) {
    setImages((prev) => {
      URL.revokeObjectURL(prev[index].previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }

  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // let the same file be picked again later
    void addFiles(files);
  }

  function handlePaste(e: ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(e.clipboardData.items)
      .filter((item) => item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (files.length === 0) return;
    // A pasted image is an attachment, not text — don't also let the browser
    // insert whatever placeholder text it associates with the clipboard item.
    e.preventDefault();
    void addFiles(files);
  }

  function submit() {
    if (!canSend) return;
    onSend(value, images.length > 0 ? images : undefined);
    setValue("");
    setImages([]);
    setError(null);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-2 transition-colors duration-150 focus-within:border-zinc-700">
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1 pt-1 pb-2">
          {images.map((img, i) => (
            <div key={img.previewUrl} className="group relative">
              {/* eslint-disable-next-line @next/next/no-img-element -- blob:
                  object URL preview, not a static/remote asset next/image optimizes */}
              <img
                src={img.previewUrl}
                alt="Attached"
                className="size-14 rounded-lg object-cover ring-1 ring-white/10"
              />
              <button
                type="button"
                onClick={() => removeImage(i)}
                aria-label="Remove image"
                className="absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full bg-zinc-800 text-zinc-300 opacity-0 ring-1 ring-white/10 transition-opacity group-hover:opacity-100"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {error && <p className="px-1 pb-1.5 text-xs text-destructive">{error}</p>}

      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept={Array.from(ACCEPTED_MEDIA_TYPES).join(",")}
          multiple
          onChange={handleFileInputChange}
          className="hidden"
        />
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="rounded-lg"
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming || images.length >= MAX_IMAGES_PER_TURN}
          aria-label="Attach images"
        >
          <Paperclip />
        </Button>
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
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
    </div>
  );
}
