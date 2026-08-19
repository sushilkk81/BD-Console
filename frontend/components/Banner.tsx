type BannerVariant = "error" | "success";

const VARIANTS: Record<BannerVariant, { wrap: string; text: string }> = {
  error: { wrap: "bg-orange-500/10", text: "text-orange-700" },
  success: { wrap: "bg-forest-600/10", text: "text-forest-900" },
};

export function Banner({
  message,
  onDismiss,
  variant = "error",
}: {
  message: string;
  onDismiss: () => void;
  variant?: BannerVariant;
}) {
  const styles = VARIANTS[variant];
  return (
    <div role="alert" className={`flex items-center justify-between gap-3 rounded-lg px-3.5 py-2.5 ${styles.wrap}`}>
      <p className={`font-body text-sm ${styles.text}`}>{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className={`shrink-0 rounded-md p-1 font-body text-sm hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-600 ${styles.text}`}
      >
        ×
      </button>
    </div>
  );
}
