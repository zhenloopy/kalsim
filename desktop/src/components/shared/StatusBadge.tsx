interface StatusBadgeProps {
  flag: string;
}

export default function StatusBadge({ flag }: StatusBadgeProps) {
  let classes = "px-2 py-0.5 rounded text-[10px] font-semibold ";
  switch (flag) {
    case "CRITICAL":
      classes += "bg-red-900/40 text-accent-red";
      break;
    case "WATCH":
      classes += "bg-yellow-900/40 text-accent-yellow";
      break;
    case "NORMAL":
      classes += "bg-green-900/40 text-accent-green";
      break;
    default:
      classes += "bg-zinc-800 text-zinc-500";
  }
  return <span className={classes}>{flag}</span>;
}
