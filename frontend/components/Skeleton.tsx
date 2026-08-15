export function SkeletonRow() {
  return (
    <tr className="animate-pulse motion-reduce:animate-none">
      <td className="px-4 py-3">
        <span className="block h-4 w-10 rounded bg-ink-700/10" />
      </td>
      <td className="px-4 py-3">
        <span className="block h-4 w-24 rounded bg-ink-700/10" />
      </td>
      <td className="px-4 py-3">
        <span className="block h-4 w-16 rounded bg-ink-700/10" />
      </td>
      <td className="px-4 py-3">
        <span className="block h-4 w-28 rounded bg-ink-700/10" />
      </td>
    </tr>
  );
}

export function MobileSkeletonCard() {
  return (
    <div className="flex animate-pulse flex-col gap-2 px-4 py-3 motion-reduce:animate-none">
      <span className="block h-4 w-32 rounded bg-ink-700/10" />
      <span className="block h-4 w-20 rounded bg-ink-700/10" />
    </div>
  );
}
