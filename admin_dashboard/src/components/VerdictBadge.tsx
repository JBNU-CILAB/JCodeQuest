interface Props { verdict?: string; status?: string; }

export default function VerdictBadge({ verdict, status }: Props) {
  const v = verdict ?? status ?? "NONE";
  return (
    <span className={`badge verdict-${v}`}>{v}</span>
  );
}
