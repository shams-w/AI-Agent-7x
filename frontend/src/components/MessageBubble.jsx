import { t } from "../i18n";

export default function MessageBubble({ message, lang }) {
  if (message.kind === "system") {
    return (
      <div className={`system-card ${message.tone || ""}`} dir="auto" data-testid="system-card">
        {message.title && <strong>{message.title}</strong>}
        <div>{message.text}</div>
        {message.details && (
          <div className="system-details">
            {message.details.map((item) => (
              <div className="detail-row" key={item.label}>
                <span>{item.label}</span><b dir="auto">{item.value ?? "—"}</b>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  const isUser = message.role === "user";
  return (
    <div className={`message-row ${isUser ? "user" : "assistant"}`}>
      <div className="message-stack">
        <span className="role-label">{isUser ? t(lang, "ui_role_user") : "7X AI"}</span>
        <div className="message-bubble" dir="auto" data-testid={isUser ? "user-msg" : "assistant-msg"}>
          {message.text}
        </div>
      </div>
    </div>
  );
}
