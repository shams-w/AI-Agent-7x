import { t } from "../i18n";

export default function AgentActivity({ items, lang }) {
  return (
    <details className="activity-card" open>
      <summary>{t(lang, "p_activity")}</summary>
      <div className="activity-list" dir="auto">
        {items.length === 0 ? <p className="muted">{t(lang, "p_no_activity")}</p> :
          items.map((item, i) => <div className="activity-item" key={`${item}-${i}`}><span className="check">✓</span><span>{item}</span></div>)}
      </div>
    </details>
  );
}
