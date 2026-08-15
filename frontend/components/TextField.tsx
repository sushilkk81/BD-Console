type TextFieldProps = {
  label: string;
  name: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  error?: string;
};

export function TextField({ label, name, type = "text", value, onChange, required, error }: TextFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="font-body text-sm font-medium text-ink-700">
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        aria-invalid={!!error}
        aria-describedby={error ? `${name}-error` : undefined}
        className={`rounded-lg border px-3.5 py-2.5 font-body text-sm text-ink-700 outline-none transition-colors focus-visible:border-forest-600 focus-visible:ring-2 focus-visible:ring-forest-600/30 ${
          error ? "border-orange-500" : "border-ink-700/15"
        }`}
      />
      {error && (
        <p id={`${name}-error`} className="font-body text-xs text-orange-700">
          {error}
        </p>
      )}
    </div>
  );
}
