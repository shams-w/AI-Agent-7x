import { t } from "../i18n";

export default function ConfirmationCard({ lang, title, details, onConfirm, onCancel, loading }) {
  return (
    <div className="confirmation-card" dir="auto" data-testid="confirmation-card">
      <div className="confirmation-head">
        <div className="confirmation-icon">✓</div>
        <div><span className="eyebrow">{t(lang, "confirm_eyebrow")}</span><h3>{title}</h3></div>
      </div>
      <div className="confirmation-details">
        {details.map((item) => <div className="detail-row" key={item.label}><span>{item.label}</span><b dir="auto">{item.value}</b></div>)}
      </div>
      <div className="confirmation-actions">
        <button className="secondary-btn" onClick={onCancel} disabled={loading} data-testid="cancel-btn">{t(lang, "cancel")}</button>
        <button className="primary-btn" onClick={onConfirm} disabled={loading} data-testid="confirm-btn">{loading ? t(lang, "executing") : t(lang, "confirm")}</button>
      </div>
    </div>
  );
}
