import { useEffect, useRef } from "react";

import MessageBubble from "./MessageBubble";
import ConfirmationCard from "./ConfirmationCard";
import { t } from "../i18n";

export default function ChatPanel({
  lang,
  messages,
  quickActions,
  onQuickAction,
  onContextAction,
  state,
  input,
  setInput,
  onSubmit,
  onConfirm,
  onCancelConfirmation,
  confirmation,
  loading,
}) {
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, confirmation, loading]);

  const isDateState = state === "WAITING_FOR_RESCHEDULE_DATE";
  const isAddressState =
    state === "WAITING_FOR_NEW_ADDRESS" || state === "WAITING_FOR_PREREQ_ADDRESS";
  const showTrackingChoice = state === "WAITING_FOR_TRACKING_CHOICE";
  const showNoShipmentOptions = state === "NO_SHIPMENT_FOUND";
  const inputLocked = loading || state === "NO_SHIPMENT_FOUND" || state === "EXECUTING_ACTION";

  return (
    <main className="chat-panel">
      <div className="chat-header">
        <div dir="auto">
          <span className="eyebrow">{t(lang, "ui_conversation")}</span>
          <h2>{t(lang, "ui_support")}</h2>
        </div>

        <span className="secure-note">{t(lang, "ui_secure")}</span>
      </div>

      <div className="conversation" ref={scrollRef} data-testid="conversation">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} lang={lang} />
        ))}

        {loading && (
          <div className="message-row assistant">
            <div className="message-stack">
              <span className="role-label">7X AI</span>
              <div className="message-bubble typing">
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}

        {confirmation && (
          <ConfirmationCard
            lang={lang}
            title={confirmation.title}
            details={confirmation.details}
            onConfirm={onConfirm}
            onCancel={onCancelConfirmation}
            loading={loading}
          />
        )}
      </div>

      <div className="chat-composer">
        {quickActions && (
          <div className="quick-actions">
            <button onClick={() => onQuickAction("reschedule")} disabled={loading} data-testid="qa-reschedule">
              {t(lang, "user_reschedule")}
            </button>
            <button onClick={() => onQuickAction("address")} disabled={loading} data-testid="qa-address">
              {t(lang, "user_address")}
            </button>
          </div>
        )}

        {showTrackingChoice && (
          <div className="quick-actions">
            <button onClick={() => onContextAction("have_tracking")} disabled={loading}>
              {t(lang, "ui_yes_have")}
            </button>
            <button onClick={() => onContextAction("find_shipment")} disabled={loading}>
              {t(lang, "ui_no_find")}
            </button>
          </div>
        )}

        {showNoShipmentOptions && (
          <div className="quick-actions">
            <button onClick={() => onContextAction("try_another_phone")} disabled={loading}>
              {t(lang, "user_try_phone")}
            </button>
            <button onClick={() => onContextAction("enter_tracking")} disabled={loading}>
              {t(lang, "user_enter_tracking")}
            </button>
            <button onClick={() => onContextAction("transfer_support")} disabled={loading}>
              {t(lang, "user_transfer")}
            </button>
          </div>
        )}

        <form onSubmit={onSubmit} className="composer-form">
          {isAddressState ? (
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={t(lang, "ph_address")}
              disabled={inputLocked}
              rows={2}
              dir="auto"
              data-testid="chat-input"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
          ) : (
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={placeholderForState(lang, state)}
              disabled={inputLocked}
              autoComplete="off"
              dir="auto"
              data-testid="chat-input"
            />
          )}

          {isDateState && (
            <input
              type="date"
              className="date-picker"
              min={new Date().toISOString().slice(0, 10)}
              onChange={(event) => setInput(event.target.value)}
              disabled={loading}
              aria-label={t(lang, "l_new_date")}
            />
          )}

          <button
            className="send-btn"
            type="submit"
            disabled={inputLocked || !String(input).trim()}
            data-testid="send-btn"
          >
            {t(lang, "ui_send")}
          </button>
        </form>

        <div className="composer-foot" dir="auto">{t(lang, "ui_foot")}</div>
      </div>
    </main>
  );
}

function placeholderForState(lang, state) {
  const keys = {
    WAITING_FOR_TRACKING_CHOICE: "ph_tracking_choice",
    WAITING_FOR_TRACKING: "ph_tracking",
    WAITING_FOR_PHONE_LOOKUP: "ph_phone",
    WAITING_FOR_SHIPMENT_SELECTION: "ph_selection",
    WAITING_FOR_VERIFICATION: "ph_last4",
    WAITING_FOR_CONTACT_PHONE: "ph_contact",
    WAITING_FOR_RESCHEDULE_DATE: "ph_date",
    NO_SHIPMENT_FOUND: "ph_options",
  };
  return t(lang, keys[state] || "ph_default");
}
