import StatusBadge from "./StatusBadge";
import AgentActivity from "./AgentActivity";
import { t, statusLabel } from "../i18n";

export default function ShipmentPanel({ lang, shipment, progressStep, activity }) {
  const steps = ["p_step1", "p_step2", "p_step3", "p_step4"].map((key) => t(lang, key));
  return (
    <aside className="shipment-panel" data-testid="shipment-panel">
      <section className="panel-card">
        <div className="panel-heading">
          <div dir="auto"><span className="eyebrow">{t(lang, "p_context")}</span><h2>{t(lang, "p_current")}</h2></div>
          {shipment?.status && <StatusBadge status={shipment.status} label={statusLabel(lang, shipment.status)} />}
        </div>
        {!shipment ? (
          <div className="empty-state"><div className="empty-icon">◎</div><p dir="auto">{t(lang, "p_empty")}</p></div>
        ) : (
          <div className="shipment-grid" dir="auto">
            <Field label={t(lang, "l_tracking_number")} value={shipment.tracking_number} />
            <Field label={t(lang, "p_customer")} value={shipment.customer_name} />
            <Field label={t(lang, "p_phone")} value={shipment.phone} />
            <Field label={t(lang, "l_emirate")} value={shipment.emirate} />
            <Field label={t(lang, "l_service")} value={shipment.service_type} />
            <Field label={t(lang, "p_shipment_date")} value={shipment.shipment_date} />
            <Field label={t(lang, "p_last_attempt")} value={shipment.last_attempt_date} />
            <Field label={t(lang, "p_attempts")} value={shipment.delivery_attempts} />
            <Field label={t(lang, "p_cod")} value={shipment.cod_amount_aed == null ? "—" : `${shipment.cod_amount_aed} AED`} />
            <Field label={t(lang, "p_weight")} value={shipment.weight_kg == null ? "—" : `${shipment.weight_kg} kg`} />
            <div className="full-field"><span>{t(lang, "p_address")}</span><b dir="auto" data-testid="panel-address">{shipment.delivery_address || "—"}</b></div>
            {shipment.scheduled_redelivery_date && <div className="full-field highlight-field"><span>{t(lang, "l_scheduled")}</span><b data-testid="panel-redelivery">{String(shipment.scheduled_redelivery_date).slice(0, 10)}</b></div>}
          </div>
        )}
      </section>
      <section className="panel-card">
        <span className="eyebrow">{t(lang, "p_timeline")}</span>
        <div className="timeline">
          {steps.map((step, index) => {
            const n = index + 1, active = progressStep >= n;
            return <div className={`timeline-item ${active ? "active" : ""}`} key={step}><div className="timeline-dot">{active ? "✓" : n}</div><span>{step}</span></div>;
          })}
        </div>
      </section>
      <AgentActivity items={activity} lang={lang} />
    </aside>
  );
}
function Field({ label, value }) {
  return <div className="field"><span>{label}</span><b dir="ltr" style={{ unicodeBidi: "isolate" }}>{value ?? "—"}</b></div>;
}
