export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[11px] uppercase tracking-wide text-text-faint">{label}</span>
      <div className="flex rounded-md border border-border bg-surface p-0.5">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              className={`rounded px-2.5 py-1 text-xs transition-colors ${
                active ? "bg-surface-2 text-text" : "text-text-muted hover:text-text"
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
