interface SuggestionChipsProps {
  options: string[];
  /** Send the option as the user's next message. */
  onSelect: (text: string) => void;
  disabled?: boolean;
}

/** Follow-ups the agent offered (`suggest_replies`), as buttons to tap
 *  instead of typing. Rendered only under the latest reply. */
export function SuggestionChips({ options, onSelect, disabled }: SuggestionChipsProps) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(option)}
          className="rounded-full border border-border bg-background px-3 py-1.5 text-[13px] text-foreground transition-colors duration-150 hover:border-ring hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {option}
        </button>
      ))}
    </div>
  );
}
