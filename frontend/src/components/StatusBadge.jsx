export default function StatusBadge({ status, label }) {
  if (!status) return null;
  const s = String(status).toLowerCase();
  let tone = "neutral";
  if (s.includes("failed")) tone = "warning";
  else if (s.includes("redelivery")) tone = "info";
  else if (s.includes("delivered")) tone = "success";
  else if (s.includes("returned")) tone = "danger";
  return <span className={`status-badge ${tone}`} data-testid="status-badge">{label || status}</span>;
}
