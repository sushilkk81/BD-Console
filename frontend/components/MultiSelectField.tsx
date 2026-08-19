type Option = { value: string; label: string };

type MultiSelectFieldProps = {
  label: string;
  name: string;
  values: string[];
  onChange: (values: string[]) => void;
  options: Option[];
  error?: string;
};

/** Chip/pill toggle group for selecting any number of options — mirrors the strength-chip pattern. */
export function MultiSelectField({ label, name, values, onChange, options, error }: MultiSelectFieldProps) {
  function toggle(value: string) {
    onChange(values.includes(value) ? values.filter((v) => v !== value) : [...values, value]);
  }

  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="font-body text-sm font-medium text-ink-700">{label}</legend>
      <div className="flex flex-wrap gap-2" role="group" aria-label={label}>
        {options.map((opt) => (
          <label
            key={opt.value}
            className={`cursor-pointer rounded-full border px-3 py-1.5 font-body text-sm ${
              values.includes(opt.value)
                ? "border-forest-600 bg-forest-600/10 text-forest-900"
                : "border-ink-700/15 text-ink-700/70"
            }`}
          >
            <input
              type="checkbox"
              name={name}
              className="sr-only"
              checked={values.includes(opt.value)}
              onChange={() => toggle(opt.value)}
            />
            {opt.label}
          </label>
        ))}
      </div>
      {error && (
        <p id={`${name}-error`} className="font-body text-xs text-orange-700">
          {error}
        </p>
      )}
    </fieldset>
  );
}
