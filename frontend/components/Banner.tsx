export function Banner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 rounded-lg bg-orange-500/10 px-3.5 py-2.5"
    >
      <p className="font-body text-sm text-orange-700">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded-md p-1 font-body text-sm text-orange-700 hover:bg-orange-500/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-600"
      >
        ×
      </button>
    </div>
  );
}
