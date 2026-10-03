import { useEffect, useMemo, useRef, useState } from "react";
import Header from "./components/Header";
import ChatPanel from "./components/ChatPanel";
import ShipmentPanel from "./components/ShipmentPanel";
import {
  t,
  reasonMessage,
  issueTitle,
  statusLabel,
  toAsciiDigits,
  inferLanguage,
} from "./i18n";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const STATES = {
  WELCOME: "WELCOME",
  WAITING_FOR_TRACKING_CHOICE: "WAITING_FOR_TRACKING_CHOICE",
  WAITING_FOR_TRACKING: "WAITING_FOR_TRACKING",
  WAITING_FOR_PHONE_LOOKUP: "WAITING_FOR_PHONE_LOOKUP",
  WAITING_FOR_SHIPMENT_SELECTION: "WAITING_FOR_SHIPMENT_SELECTION",
  NO_SHIPMENT_FOUND: "NO_SHIPMENT_FOUND",
  SHIPMENT_LOOKUP: "SHIPMENT_LOOKUP",
  WAITING_FOR_VERIFICATION: "WAITING_FOR_VERIFICATION",
  WAITING_FOR_CONTACT_PHONE: "WAITING_FOR_CONTACT_PHONE",
  WAITING_FOR_PREREQ_ADDRESS: "WAITING_FOR_PREREQ_ADDRESS",
  WAITING_FOR_REVIEW: "WAITING_FOR_REVIEW",
  VERIFIED: "VERIFIED",
  WAITING_FOR_RESCHEDULE_DATE: "WAITING_FOR_RESCHEDULE_DATE",
  WAITING_FOR_NEW_ADDRESS: "WAITING_FOR_NEW_ADDRESS",
  WAITING_FOR_CONFIRMATION: "WAITING_FOR_CONFIRMATION",
  EXECUTING_ACTION: "EXECUTING_ACTION",
  SUCCESS: "SUCCESS",
  ESCALATED: "ESCALATED",
  ERROR: "ERROR",
  ACTION_BLOCKED: "ACTION_BLOCKED",
};

// States in which a new free-text message starts a new request.
const NEW_REQUEST_STATES = new Set([
  STATES.WELCOME,
  STATES.SUCCESS,
  STATES.ACTION_BLOCKED,
  STATES.ESCALATED,
  STATES.ERROR,
]);

const EMPTY_ENTITIES = { tracking_number: null, delivery_date: null, address: null };

function welcomeMessage(lang) {
  return { id: `welcome-${lang}`, role: "assistant", text: t(lang, "welcome") };
}

export default function App() {
  const [lang, setLangState] = useState("en");
  const [state, setStateValue] = useState(STATES.WELCOME);
  const [selectedIntent, setSelectedIntent] = useState(null);
  const [trackingNumber, setTrackingNumberState] = useState("");
  const [shipment, setShipment] = useState(null);
  const [verified, setVerifiedState] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [pendingValue, setPendingValue] = useState("");
  const [messages, setMessages] = useState([welcomeMessage("en")]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [activity, setActivity] = useState([]);
  const [toast, setToast] = useState("");

  // Refs mirror the values async handlers depend on, so a single customer
  // message can carry intent + tracking number + date through several awaits
  // without reading stale React state.
  const langRef = useRef("en");
  const stateRef = useRef(STATES.WELCOME);
  const intentRef = useRef(null);
  const trackingRef = useRef("");
  const shipmentRef = useRef(null);
  const verifiedRef = useRef(false);
  const tokenRef = useRef("");
  const entitiesRef = useRef({ ...EMPTY_ENTITIES });
  const needsAddressRef = useRef(false);
  const discoveredRef = useRef([]);
  const lookupPhoneRef = useRef("");
  const pendingRef = useRef({ action: null, value: "" });

  const tr = (key, params) => t(langRef.current, key, params);

  function setLang(value) {
    langRef.current = value;
    setLangState(value);
  }
  function setState(value) {
    stateRef.current = value;
    setStateValue(value);
  }
  function setIntent(value) {
    intentRef.current = value;
    setSelectedIntent(value);
  }
  function setTracking(value) {
    trackingRef.current = value;
    setTrackingNumberState(value);
  }
  function setShipmentValue(value) {
    shipmentRef.current = value;
    setShipment(value);
  }
  function setVerification(isVerified, token = "") {
    verifiedRef.current = isVerified;
    tokenRef.current = token;
    setVerifiedState(isVerified);
  }
  function setPending(action, value) {
    pendingRef.current = { action, value };
    setPendingAction(action);
    setPendingValue(value);
  }

  const quickActions = state === STATES.WELCOME;

  const progressStep = useMemo(() => {
    if (state === STATES.SUCCESS) return 4;
    if (state === STATES.WAITING_FOR_CONFIRMATION || pendingAction) return 3;
    if (verified) return 2;
    if (shipment) return 1;
    return 0;
  }, [state, pendingAction, verified, shipment]);

  const confirmation =
    state === STATES.WAITING_FOR_CONFIRMATION
      ? buildConfirmation(lang, selectedIntent, shipment, pendingValue)
      : null;

  useEffect(() => {
    if (state !== STATES.WAITING_FOR_REVIEW || !trackingNumber) return undefined;

    const timer = setInterval(async () => {
      try {
        const response = await fetch(
          `${API_BASE}/review/${encodeURIComponent(trackingNumber)}`
        );
        const data = await parseResponse(response);

        if (response.ok && data.success && data.status === "RESOLVED") {
          clearInterval(timer);
          addActivity(tr("a_review_resolved"));
          card("success", tr("review_done_title"), tr("review_done"));
          await lookupShipment(trackingNumber, false);
        }
      } catch {
        // Polling is best-effort; normal API error handling remains unchanged.
      }
    }, 3000);

    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, trackingNumber]);

  // -------------------------------------------------
  // Message helpers
  // -------------------------------------------------

  function addMessage(message) {
    setMessages((current) => [
      ...current,
      { id: `${Date.now()}-${Math.random()}`, ...message },
    ]);
  }

  function say(key, params) {
    addMessage({ role: "assistant", text: tr(key, params) });
  }

  function card(tone, title, text, details) {
    addMessage({ kind: "system", tone, title, text, details });
  }

  function addActivity(text) {
    setActivity((current) =>
      current.includes(text) ? current : [...current, text]
    );
  }

  function showToast(text) {
    setToast(text);
    setTimeout(() => setToast(""), 2400);
  }

  // -------------------------------------------------
  // Understanding (LLM + deterministic fallback, server side)
  // -------------------------------------------------

  async function understand(message) {
    try {
      const response = await fetch(`${API_BASE}/agent/understand`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, state: stateRef.current }),
      });
      const data = await parseResponse(response);
      if (!response.ok) throw new ApiError(response.status, data);
      addActivity(
        tr("a_understood", { source: data.source === "llm" ? "LLM" : "rules" })
      );
      return {
        intent: data.intent || "none",
        answer: data.answer || null,
        entities: { ...EMPTY_ENTITIES, ...(data.entities || {}) },
      };
    } catch (error) {
      handleApiError(error, "understand");
      return null;
    }
  }

  function rememberEntities(entities) {
    const current = entitiesRef.current;
    entitiesRef.current = {
      tracking_number: entities?.tracking_number || current.tracking_number,
      delivery_date: entities?.delivery_date || current.delivery_date,
      address: entities?.address || current.address,
    };
  }

  function resetRequestContext() {
    setIntent(null);
    setTracking("");
    setShipmentValue(null);
    setVerification(false);
    setPending(null, "");
    discoveredRef.current = [];
    lookupPhoneRef.current = "";
    needsAddressRef.current = false;
  }

  // -------------------------------------------------
  // Starting / switching a request
  // -------------------------------------------------

  async function beginRequest(intent, entities) {
    const carried = entitiesRef.current;
    resetRequestContext();
    entitiesRef.current = { ...EMPTY_ENTITIES };
    rememberEntities(carried);
    rememberEntities(entities);
    setIntent(intent);

    say(intent === "reschedule" ? "ack_reschedule" : "ack_address");

    const known = entitiesRef.current;
    if (intent === "reschedule" && known.delivery_date) {
      if (validateDeliveryDate(known.delivery_date).valid) {
        say("noted_date", { date: formatDate(langRef.current, known.delivery_date) });
      } else {
        entitiesRef.current = { ...known, delivery_date: null };
      }
    }
    if (intent === "address" && known.address) {
      say("noted_address");
    }

    if (known.tracking_number) {
      const tracking = known.tracking_number;
      entitiesRef.current = { ...entitiesRef.current, tracking_number: null };
      await lookupShipment(tracking);
      return;
    }

    setState(STATES.WAITING_FOR_TRACKING_CHOICE);
    say("ask_have_tracking");
  }

  async function switchIntent(intent, entities) {
    rememberEntities(entities);
    setIntent(intent);
    setPending(null, "");
    say(intent === "reschedule" ? "ack_reschedule" : "ack_address");

    if (verifiedRef.current && trackingRef.current) {
      setLoading(true);
      try {
        const eligible = await checkEarlyEligibility(trackingRef.current);
        if (eligible) continueAfterAccessGranted();
      } catch (error) {
        handleApiError(error, "eligibility");
        setState(STATES.ERROR);
      } finally {
        setLoading(false);
      }
      return;
    }

    await beginRequest(intent, entities);
  }

  async function handleNewRequestMessage(understood) {
    if (!understood) return;
    const { intent, entities } = understood;

    if (intent === "reschedule" || intent === "address") {
      await beginRequest(intent, entities);
      return;
    }

    if (NEW_REQUEST_STATES.has(stateRef.current) && stateRef.current !== STATES.WELCOME) {
      resetRequestContext();
      entitiesRef.current = { ...EMPTY_ENTITIES };
    }
    rememberEntities(entities);
    setState(STATES.WELCOME);

    if (intent === "multiple") say("multiple");
    else if (intent === "greeting") say("greeting");
    else if (intent === "other") say("out_of_scope");
    else say("unclear");
  }

  function handleQuickAction(intent) {
    addMessage({
      role: "user",
      text: tr(intent === "reschedule" ? "user_reschedule" : "user_address"),
    });
    beginRequest(intent, null);
  }

  function handleContextAction(action) {
    if (action === "have_tracking") {
      addMessage({ role: "user", text: tr("user_have_tracking") });
      setState(STATES.WAITING_FOR_TRACKING);
      say("enter_tracking");
      return;
    }

    if (action === "find_shipment") {
      addMessage({ role: "user", text: tr("user_no_tracking") });
      setState(STATES.WAITING_FOR_PHONE_LOOKUP);
      say("enter_phone_lookup");
      return;
    }

    if (action === "try_another_phone") {
      addMessage({ role: "user", text: tr("user_try_phone") });
      setState(STATES.WAITING_FOR_PHONE_LOOKUP);
      say("enter_another_phone");
      return;
    }

    if (action === "enter_tracking") {
      addMessage({ role: "user", text: tr("user_enter_tracking") });
      setState(STATES.WAITING_FOR_TRACKING);
      say("enter_tracking_short");
      return;
    }

    if (action === "transfer_support") {
      addMessage({ role: "user", text: tr("user_transfer") });
      prepareSupportHandoff();
    }
  }

  // -------------------------------------------------
  // Free-text input
  // -------------------------------------------------

  async function handleSubmit(event) {
    event.preventDefault();

    const value = String(input).trim();
    const current = stateRef.current;

    if (!value || loading) return;

    setInput("");

    if (
      current === STATES.WAITING_FOR_PHONE_LOOKUP ||
      current === STATES.WAITING_FOR_CONTACT_PHONE
    ) {
      addMessage({ role: "user", text: tr("user_mobile", { phone: maskPhone(value) }) });
    } else if (current === STATES.WAITING_FOR_VERIFICATION) {
      addMessage({ role: "user", text: tr("user_last4") });
    } else {
      addMessage({ role: "user", text: value });
    }

    // Reply in the customer's language. Verification digits are never used
    // for language detection and are never sent to the understanding service.
    if (current !== STATES.WAITING_FOR_VERIFICATION) {
      setLang(inferLanguage(value, langRef.current));
    }

    if (NEW_REQUEST_STATES.has(current)) {
      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      await handleNewRequestMessage(understood);
      return;
    }

    if (current === STATES.WAITING_FOR_TRACKING_CHOICE) {
      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      if (!understood) return;

      const { intent, answer, entities } = understood;

      if (entities.tracking_number) {
        rememberEntities({ ...entities, tracking_number: null });
        await lookupShipment(entities.tracking_number);
        return;
      }

      if ((intent === "reschedule" || intent === "address") && intent !== intentRef.current) {
        await switchIntent(intent, entities);
        return;
      }

      rememberEntities(entities);

      if (answer === "yes") {
        setState(STATES.WAITING_FOR_TRACKING);
        say("enter_tracking");
        return;
      }

      if (answer === "no") {
        setState(STATES.WAITING_FOR_PHONE_LOOKUP);
        say("enter_phone_lookup");
        return;
      }

      say("choose_tracking_option");
      return;
    }

    if (current === STATES.WAITING_FOR_TRACKING) {
      const direct = extractTracking(value);
      if (direct) {
        await lookupShipment(direct);
        return;
      }

      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      if (!understood) return;

      if (understood.answer === "no") {
        setState(STATES.WAITING_FOR_PHONE_LOOKUP);
        say("enter_phone_lookup");
        return;
      }

      // Never guess: the raw value is sent and the backend validates format.
      await lookupShipment(toAsciiDigits(value).replace(/\s+/g, ""));
      return;
    }

    if (current === STATES.WAITING_FOR_PHONE_LOOKUP) {
      const tracking = extractTracking(value);
      if (tracking) {
        await lookupShipment(tracking);
        return;
      }
      await findShipmentsByPhone(toAsciiDigits(value));
      return;
    }

    if (current === STATES.WAITING_FOR_SHIPMENT_SELECTION) {
      await selectDiscoveredShipment(toAsciiDigits(value));
      return;
    }

    if (current === STATES.WAITING_FOR_VERIFICATION) {
      await verifyCustomer(toAsciiDigits(value));
      return;
    }

    if (current === STATES.WAITING_FOR_CONTACT_PHONE) {
      await collectMissingPhone(toAsciiDigits(value));
      return;
    }

    if (current === STATES.WAITING_FOR_PREREQ_ADDRESS) {
      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      await savePrerequisiteAddress(understood?.entities?.address || value);
      return;
    }

    if (current === STATES.WAITING_FOR_REVIEW) {
      say("review_still");
      return;
    }

    if (current === STATES.WAITING_FOR_RESCHEDULE_DATE) {
      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      if (!understood) return;

      const date =
        understood.entities.delivery_date ||
        (/^\d{4}-\d{2}-\d{2}$/.test(toAsciiDigits(value)) ? toAsciiDigits(value) : null);

      if (!date && understood.intent === "address") {
        await switchIntent("address", understood.entities);
        return;
      }

      if (!date) {
        card("warning", tr("date_choose_title"), tr("date_missing"));
        setState(STATES.WAITING_FOR_RESCHEDULE_DATE);
        return;
      }

      const dateValidation = validateDeliveryDate(date);
      if (!dateValidation.valid) {
        card("warning", tr("date_choose_title"), tr(dateValidation.key));
        say("date_reenter");
        setState(STATES.WAITING_FOR_RESCHEDULE_DATE);
        return;
      }

      prepareConfirmation("reschedule", date);
      return;
    }

    if (current === STATES.WAITING_FOR_NEW_ADDRESS) {
      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      if (!understood) return;

      const hasDigits = /\d/.test(toAsciiDigits(value));

      if (
        (understood.intent === "reschedule" || understood.intent === "multiple") &&
        !understood.entities.address &&
        !hasDigits
      ) {
        await switchIntent("reschedule", understood.entities);
        return;
      }

      if (understood.intent === "address" && !understood.entities.address && !hasDigits) {
        // The customer restated the request instead of giving the address.
        say("ask_new_address");
        return;
      }

      await submitNewAddress(understood.entities.address || value);
      return;
    }

    if (current === STATES.WAITING_FOR_CONFIRMATION) {
      setLoading(true);
      const understood = await understand(value);
      setLoading(false);
      if (understood?.answer === "yes") {
        await confirmAction();
        return;
      }
      if (understood?.answer === "no") {
        cancelConfirmation();
        return;
      }
    }

    say("use_actions");
  }

  function submitNewAddress(value) {
    if (!isValidAddress(value)) {
      card("warning", tr("address_detail_title"), tr("address_short"));
      say("address_example");
      setState(STATES.WAITING_FOR_NEW_ADDRESS);
      return;
    }

    if (addressesMatch(value, shipmentRef.current?.delivery_address)) {
      card("warning", tr("address_same_title"), tr("address_same"));
      say("address_different");
      setState(STATES.WAITING_FOR_NEW_ADDRESS);
      return;
    }

    prepareConfirmation("address", value);
  }

  // -------------------------------------------------
  // Shipment discovery by phone
  // -------------------------------------------------

  async function findShipmentsByPhone(phoneNumber) {
    setLoading(true);
    lookupPhoneRef.current = phoneNumber;

    try {
      const response = await fetch(`${API_BASE}/find-shipments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber }),
      });

      const data = await parseResponse(response);

      if (!response.ok) throw new ApiError(response.status, data);

      if (data.success && data.result === "FOUND") {
        const found = Array.isArray(data.shipments) ? data.shipments : [];

        discoveredRef.current = found;
        addActivity(tr("a_discovery"));

        if (found.length === 1) {
          const candidate = found[0];

          card(
            candidate.requires_review ? "warning" : "success",
            tr("shipment_located_title"),
            candidate.requires_review ? tr("shipment_located_review") : tr("shipment_located_one"),
            [
              { label: tr("l_tracking"), value: candidate.masked_tracking_number },
              { label: tr("l_status"), value: statusLabel(langRef.current, candidate.status) },
              { label: tr("l_emirate"), value: candidate.emirate },
              { label: tr("l_service"), value: candidate.service_type },
            ]
          );

          if (candidate.requires_review) {
            const issue = translatedIssue(candidate.review_issue);
            addActivity(tr("a_guardrail"));
            say("no_guess_handoff");
            prepareSupportHandoff(issue.title, issue.message, candidate.tracking_number);
            return;
          }

          say("use_this_shipment");
          await lookupShipment(candidate.tracking_number, true);
          return;
        }

        card(
          "success",
          tr("multiple_found_title"),
          tr("multiple_found", { count: found.length }),
          found.map((candidate, index) => ({
            label: tr("option_n", { n: index + 1 }),
            value: `${candidate.masked_tracking_number} — ${
              statusLabel(langRef.current, candidate.status) || tr("unknown_status")
            } — ${candidate.emirate || tr("unknown_emirate")}`,
          }))
        );

        say("enter_option", { count: found.length });
        setState(STATES.WAITING_FOR_SHIPMENT_SELECTION);
        return;
      }

      if (data.result === "NO_SHIPMENTS_FOUND" || data.result === "NO_ACTIVE_SHIPMENTS") {
        card("warning", tr("no_active_title"), tr("no_active"));
        say("no_active_next");
        setState(STATES.NO_SHIPMENT_FOUND);
        return;
      }

      if (data.result === "INVALID_PHONE") {
        say("invalid_phone_lookup");
        setState(STATES.WAITING_FOR_PHONE_LOOKUP);
        return;
      }

      if (data.result === "PHONE_DATA_UNAVAILABLE") {
        addActivity(tr("a_identity_unavailable"));
        card("warning", tr("phone_data_unavailable_title"), tr("phone_data_unavailable"));
        prepareSupportHandoff(tr("phone_data_unavailable_title"), tr("phone_data_unavailable"));
        return;
      }

      throw new Error("Unexpected shipment discovery response");
    } catch (error) {
      handleApiError(error, "shipment discovery");
      setState(STATES.WAITING_FOR_PHONE_LOOKUP);
    } finally {
      setLoading(false);
    }
  }

  async function selectDiscoveredShipment(value) {
    const discovered = discoveredRef.current;
    const match = String(value).match(/\d+/);
    const selection = match ? Number(match[0]) : NaN;

    if (!Number.isInteger(selection) || selection < 1 || selection > discovered.length) {
      say("enter_option", { count: discovered.length });
      return;
    }

    const candidate = discovered[selection - 1];

    if (candidate.requires_review) {
      const issue = translatedIssue(candidate.review_issue);
      addActivity(tr("a_guardrail"));
      card("warning", issue.title, issue.message);
      prepareSupportHandoff(issue.title, issue.message, candidate.tracking_number);
      return;
    }

    card(
      "success",
      tr("shipment_selected_title"),
      tr("shipment_selected", { tracking: candidate.masked_tracking_number })
    );

    await lookupShipment(candidate.tracking_number, true);
  }

  function translatedIssue(issue) {
    const fallback = issue || {
      code: "DATA_REVIEW_REQUIRED",
      title: t("en", "data_review_title"),
      message: t("en", "data_review"),
    };
    return {
      code: fallback.code,
      title: issueTitle(langRef.current, fallback.code, fallback.title),
      message: reasonMessage(langRef.current, fallback.code, fallback.message),
    };
  }

  // -------------------------------------------------
  // Business eligibility (deterministic backend rules)
  // -------------------------------------------------

  async function checkEarlyEligibility(tracking) {
    const intent = intentRef.current;
    if (!intent) return true;

    const response = await fetch(`${API_BASE}/eligibility`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracking_number: tracking, intent }),
    });

    const data = await parseResponse(response);
    if (!response.ok) throw new ApiError(response.status, data);

    addActivity(tr("a_eligibility"));

    if (data.allowed) {
      needsAddressRef.current = intent === "reschedule" && Boolean(data.requires_address_first);

      if (intent === "reschedule" && data.reason === "ALREADY_SCHEDULED") {
        card(
          "warning",
          tr("already_scheduled_title"),
          data.current_redelivery_date
            ? tr("already_scheduled_date", { date: data.current_redelivery_date })
            : tr("already_scheduled")
        );
      }

      return true;
    }

    let title = tr("blocked_title");
    if (data.reason === "ALREADY_DELIVERED") {
      title = tr(intent === "reschedule" ? "blocked_reschedule_title" : "blocked_address_title");
    } else if (data.reason === "OUT_FOR_DELIVERY") {
      title = tr(intent === "address" ? "blocked_address_support_title" : "blocked_reschedule_title");
    } else if (data.reason === "RETURNED_TO_SENDER") {
      title = tr("blocked_human_title");
    }

    card("warning", title, reasonMessage(langRef.current, data.reason, data.message));
    say("blocked_next");
    setState(STATES.ACTION_BLOCKED);
    return false;
  }

  // -------------------------------------------------
  // Shipment lookup
  // -------------------------------------------------

  async function lookupShipment(rawTracking, discovered = false) {
    const normalized = String(rawTracking).trim().toUpperCase();

    setTracking(normalized);
    setState(STATES.SHIPMENT_LOOKUP);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/shipment/${encodeURIComponent(normalized)}`);
      const data = await parseResponse(response);

      if (!response.ok) throw new ApiError(response.status, data);

      if (data.success && data.result === "FOUND") {
        setShipmentValue(data.shipment);
        addActivity(tr("a_lookup"));

        if (data.data_quality_warning) {
          addActivity(tr("a_dq_warning"));
          const warning = data.data_quality_warning;
          card(
            "warning",
            issueTitle(langRef.current, warning.code, warning.title || tr("limited_data_title")),
            reasonMessage(langRef.current, warning.code, warning.message)
          );
        }

        const eligible = await checkEarlyEligibility(normalized);
        if (!eligible) return;

        if (!discovered) {
          card("success", tr("shipment_found_title"), tr("shipment_found"), [
            { label: tr("l_tracking"), value: data.shipment.tracking_number },
            { label: tr("l_status"), value: statusLabel(langRef.current, data.shipment.status) },
            { label: tr("l_current_address"), value: data.shipment.delivery_address || tr("not_available") },
            { label: tr("l_service"), value: data.shipment.service_type },
          ]);
        }

        if (data.needs_phone_collection) {
          addActivity(tr("a_missing_phone"));
          card("warning", tr("mobile_required_title"), tr("mobile_required"));
          say("enter_uae_mobile");
          setState(STATES.WAITING_FOR_CONTACT_PHONE);
          return;
        }

        say("ask_last4");
        setState(STATES.WAITING_FOR_VERIFICATION);
        return;
      }

      if (data.result === "INVALID_TRACKING_FORMAT") {
        card(
          "warning",
          tr("tracking_correction_title"),
          reasonMessage(langRef.current, "INVALID_TRACKING_FORMAT", data.message)
        );
        say("tracking_correction");
        setState(STATES.WAITING_FOR_TRACKING);
        return;
      }

      if (data.result === "NOT_FOUND") {
        say("not_found");
        setState(STATES.WAITING_FOR_TRACKING);
        return;
      }

      if (
        data.result === "NEEDS_REVIEW" &&
        data.review_required &&
        data.issue?.handling === "INTERNAL_REVIEW"
      ) {
        const code = data.issue?.code;
        addActivity(tr("a_review_requested"));
        card(
          "warning",
          tr("review_title"),
          code === "INVALID_WEIGHT"
            ? tr("review_weight")
            : code === "OUT_FOR_DELIVERY_MISSING_ADDRESS"
              ? tr("review_ofd_address")
              : reasonMessage(langRef.current, code, data.issue?.message || tr("review_generic"))
        );
        say("review_next");
        setState(STATES.WAITING_FOR_REVIEW);
        return;
      }

      if (data.result === "DUPLICATE" || data.result === "NEEDS_REVIEW") {
        const issue = translatedIssue(
          data.issue || {
            code: data.result === "DUPLICATE" ? "DUPLICATE_RECORDS" : "DATA_REVIEW_REQUIRED",
            title: data.result === "DUPLICATE" ? t("en", "duplicate_title") : t("en", "data_review_title"),
            message: data.result === "DUPLICATE" ? t("en", "duplicate") : t("en", "data_review"),
          }
        );

        addActivity(tr("a_guardrail"));
        card("warning", issue.title, issue.message);
        prepareSupportHandoff(issue.title, issue.message, normalized);
        return;
      }

      throw new Error("Unexpected shipment response");
    } catch (error) {
      handleApiError(error, "shipment");
      setState(STATES.WAITING_FOR_TRACKING);
    } finally {
      setLoading(false);
    }
  }

  // -------------------------------------------------
  // After verification
  // -------------------------------------------------

  function continueAfterAccessGranted() {
    const known = entitiesRef.current;

    if (intentRef.current === "reschedule") {
      if (needsAddressRef.current) {
        setState(STATES.WAITING_FOR_PREREQ_ADDRESS);
        say("prereq_address");
        return;
      }

      // A date the customer already gave is used once, and still goes
      // through validation + the explicit confirmation card.
      if (known.delivery_date && validateDeliveryDate(known.delivery_date).valid) {
        entitiesRef.current = { ...known, delivery_date: null };
        prepareConfirmation("reschedule", known.delivery_date);
        return;
      }

      setState(STATES.WAITING_FOR_RESCHEDULE_DATE);
      say("ask_date");
      return;
    }

    if (
      known.address &&
      isValidAddress(known.address) &&
      !addressesMatch(known.address, shipmentRef.current?.delivery_address)
    ) {
      entitiesRef.current = { ...known, address: null };
      prepareConfirmation("address", known.address);
      return;
    }

    setState(STATES.WAITING_FOR_NEW_ADDRESS);
    say("ask_new_address");
  }

  async function verifyCustomer(last4) {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tracking_number: trackingRef.current, last4 }),
      });
      const data = await parseResponse(response);
      if (!response.ok) throw new ApiError(response.status, data);

      if (data.verified && data.verification_token) {
        setVerification(true, data.verification_token);
        addActivity(tr("a_verified"));
        card("success", tr("verified_title"), tr("verified"));
        continueAfterAccessGranted();
        return;
      }

      if (data.reason === "TOO_MANY_ATTEMPTS") {
        addActivity(tr("a_verify_locked"));
        card("danger", tr("verify_locked_title"), tr("verify_locked"));
        prepareSupportHandoff(tr("verify_locked_title"), tr("verify_locked"));
        return;
      }

      if (data.reason === "INVALID_VERIFICATION_INPUT") {
        say("verify_bad_input");
      } else if (data.reason === "PHONE_UNAVAILABLE") {
        prepareSupportHandoff(tr("verify_unavailable"), tr("verify_unavailable"));
        return;
      } else if (typeof data.attempts_remaining === "number") {
        say("verify_mismatch_left", { left: data.attempts_remaining });
      } else {
        say("verify_mismatch");
      }
      setState(STATES.WAITING_FOR_VERIFICATION);
    } catch (error) {
      handleApiError(error, "verify");
      setState(STATES.WAITING_FOR_VERIFICATION);
    } finally {
      setLoading(false);
    }
  }

  async function collectMissingPhone(phoneNumber) {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/collect-phone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tracking_number: trackingRef.current, phone_number: phoneNumber }),
      });
      const data = await parseResponse(response);
      if (!response.ok) throw new ApiError(response.status, data);

      if (data.reason === "PHONE_ALREADY_REGISTERED") {
        say("phone_already_registered");
        say("ask_last4");
        setState(STATES.WAITING_FOR_VERIFICATION);
        return;
      }

      if (!data.success || !data.verification_token) {
        card(
          "warning",
          tr("enter_valid_mobile_title"),
          reasonMessage(langRef.current, data.reason, data.message || tr("mobile_rejected"))
        );
        setState(STATES.WAITING_FOR_CONTACT_PHONE);
        return;
      }

      lookupPhoneRef.current = phoneNumber;
      setVerification(true, data.verification_token);
      addActivity(tr("a_phone_collected"));
      card("success", tr("contact_accepted_title"), tr("contact_accepted"));

      await refreshShipment();
      continueAfterAccessGranted();
    } catch (error) {
      handleApiError(error, "collect phone");
      setState(STATES.WAITING_FOR_CONTACT_PHONE);
    } finally {
      setLoading(false);
    }
  }

  async function savePrerequisiteAddress(newAddress) {
    if (!isValidAddress(newAddress)) {
      card("warning", tr("address_detail_title"), tr("address_detail_prereq"));
      setState(STATES.WAITING_FOR_PREREQ_ADDRESS);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/repair-address`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tracking_number: trackingRef.current,
          new_address: newAddress,
          verification_token: tokenRef.current,
        }),
      });
      const data = await parseResponse(response);
      if (!response.ok) throw new ApiError(response.status, data);

      if (!data.success) {
        card(
          "warning",
          tr("address_not_saved_title"),
          reasonMessage(langRef.current, data.reason, data.message || tr("address_not_saved"))
        );
        setState(STATES.WAITING_FOR_PREREQ_ADDRESS);
        return;
      }

      needsAddressRef.current = false;
      addActivity(tr("a_address_collected"));
      card("success", tr("address_captured_title"), tr("address_captured"));

      await refreshShipment();

      // Re-run status eligibility after the prerequisite address is fixed.
      const eligible = await checkEarlyEligibility(trackingRef.current);
      if (!eligible) return;

      const known = entitiesRef.current;
      if (known.delivery_date && validateDeliveryDate(known.delivery_date).valid) {
        entitiesRef.current = { ...known, delivery_date: null };
        prepareConfirmation("reschedule", known.delivery_date);
        return;
      }

      setState(STATES.WAITING_FOR_RESCHEDULE_DATE);
      say("address_valid_ask_date");
    } catch (error) {
      handleApiError(error, "address prerequisite");
      setState(STATES.WAITING_FOR_PREREQ_ADDRESS);
    } finally {
      setLoading(false);
    }
  }

  // -------------------------------------------------
  // Confirmation + execution
  // -------------------------------------------------

  function prepareConfirmation(action, value) {
    setPending(action, value);
    addActivity(tr("a_rules"));
    setState(STATES.WAITING_FOR_CONFIRMATION);
    say(action === "reschedule" ? "review_date" : "review_address");
  }

  async function confirmAction() {
    const { action, value } = pendingRef.current;
    const token = tokenRef.current;
    const tracking = trackingRef.current;

    if (!verifiedRef.current || !token || !action || !value) return;

    setState(STATES.EXECUTING_ACTION);
    setLoading(true);
    addActivity(tr("a_confirmed"));

    try {
      const isReschedule = action === "reschedule";

      const response = await fetch(`${API_BASE}${isReschedule ? "/reschedule" : "/update-address"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          isReschedule
            ? { tracking_number: tracking, new_delivery_date: value, verification_token: token, customer_confirmed: true }
            : { tracking_number: tracking, new_address: value, verification_token: token, customer_confirmed: true }
        ),
      });

      const data = await parseResponse(response);
      if (!response.ok) throw new ApiError(response.status, data);

      if (!data.success) {
        const reason = data?.reason || data?.decision?.reason || "UNKNOWN_ACTION_ERROR";
        const message = reasonMessage(
          langRef.current,
          reason,
          data?.decision?.message || data?.message || tr("not_executed")
        );

        if (isReschedule && ["DELIVERY_DATE_REQUIRED", "INVALID_DATE", "PAST_DATE"].includes(reason)) {
          setPending(null, "");
          card("warning", tr(reason === "PAST_DATE" ? "past_date_title" : "date_fix_title"), message);
          say("date_retry");
          setState(STATES.WAITING_FOR_RESCHEDULE_DATE);
          return;
        }

        if (!isReschedule && ["NEW_ADDRESS_REQUIRED", "INVALID_NEW_ADDRESS", "ADDRESS_UNCHANGED"].includes(reason)) {
          setPending(null, "");
          if (reason === "ADDRESS_UNCHANGED") {
            card("warning", tr("address_same_title"), message);
            say("address_different");
          } else {
            card("warning", tr("address_fix_title"), message);
            say("address_retry");
          }
          setState(STATES.WAITING_FOR_NEW_ADDRESS);
          return;
        }

        card("warning", tr("action_failed_title"), message);
        setState(STATES.ERROR);
        return;
      }

      addActivity(tr("a_executed"));

      // Truthful final answer: re-read the shipment record and only claim
      // what the backend state actually shows.
      const fresh = await refreshShipment();
      addActivity(tr("a_state_verified"));

      const applied = isReschedule
        ? fresh &&
          fresh.status === "Scheduled for Redelivery" &&
          String(fresh.scheduled_redelivery_date || "").slice(0, 10) === value
        : fresh && String(fresh.delivery_address || "").trim() === String(value).trim();

      if (!applied) {
        card("danger", tr("unconfirmed_title"), tr("unconfirmed"));
      } else if (isReschedule) {
        card("success", tr("done_reschedule_title"), tr("done_reschedule", {
          tracking: fresh.tracking_number,
          date: formatDate(langRef.current, fresh.scheduled_redelivery_date),
          status: statusLabel(langRef.current, fresh.status),
        }), [
          { label: tr("l_tracking_number"), value: fresh.tracking_number },
          { label: tr("l_new_status"), value: statusLabel(langRef.current, fresh.status) },
          { label: tr("l_scheduled"), value: String(fresh.scheduled_redelivery_date).slice(0, 10) },
        ]);
      } else {
        card("success", tr("done_address_title"), tr("done_address", {
          tracking: fresh.tracking_number,
          address: fresh.delivery_address,
        }), [
          { label: tr("l_previous_address"), value: data.previous_address },
          { label: tr("l_new_address"), value: fresh.delivery_address },
        ]);
      }

      say("next_request");

      setPending(null, "");
      setVerification(false);
      setState(STATES.SUCCESS);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setVerification(false);
        setPending(null, "");
        card("warning", tr("verify_again_title"), tr("verify_again"));
        say("verify_again_ask");
        setState(STATES.WAITING_FOR_VERIFICATION);
      } else {
        handleApiError(error, "action");
        setState(STATES.ERROR);
      }
    } finally {
      setLoading(false);
    }
  }

  function cancelConfirmation() {
    const action = pendingRef.current.action;
    setPending(null, "");
    card("neutral", tr("cancelled_title"), tr("cancelled"));

    if (action === "reschedule") {
      setState(STATES.WAITING_FOR_RESCHEDULE_DATE);
      say("cancelled_date");
    } else {
      setState(STATES.WAITING_FOR_NEW_ADDRESS);
      say("cancelled_address");
    }
  }

  function prepareSupportHandoff(reason, explanation, handoffTracking = "") {
    const maskedPhone = lookupPhoneRef.current ? maskPhone(lookupPhoneRef.current) : tr("not_available");

    addActivity(tr("a_handoff"));

    card(
      "warning",
      tr("handoff_title"),
      tr("handoff_text", { explanation: explanation || tr("handoff_default_expl") }),
      [
        { label: tr("l_reason"), value: reason || tr("handoff_default_reason") },
        {
          label: tr("l_requested_action"),
          value: tr(intentRef.current === "reschedule" ? "user_reschedule" : "user_address"),
        },
        { label: tr("l_tracking_number"), value: handoffTracking || trackingRef.current || tr("not_available") },
        { label: tr("l_customer_mobile"), value: maskedPhone },
        { label: tr("l_verification"), value: verifiedRef.current ? tr("completed") : tr("not_completed") },
        { label: tr("l_status"), value: tr("needs_human") },
      ]
    );

    say("handoff_done");
    setState(STATES.ESCALATED);
  }

  async function refreshShipment() {
    try {
      const response = await fetch(`${API_BASE}/shipment/${encodeURIComponent(trackingRef.current)}`);
      const data = await parseResponse(response);
      if (response.ok && data.success) {
        setShipmentValue(data.shipment);
        return data.shipment;
      }
    } catch {
      // handled by the caller's truthfulness check
    }
    return null;
  }

  async function resetDemo() {
    setResetting(true);

    try {
      const response = await fetch(`${API_BASE}/reset`, { method: "POST" });
      const data = await parseResponse(response);
      if (!response.ok || !data.success) throw new ApiError(response.status, data);

      resetRequestContext();
      entitiesRef.current = { ...EMPTY_ENTITIES };
      setState(STATES.WELCOME);
      setMessages([welcomeMessage(langRef.current)]);
      setActivity([]);
      setInput("");

      showToast(tr("reset_ok"));
    } catch (error) {
      handleApiError(error, "reset");
    } finally {
      setResetting(false);
    }
  }

  function toggleLanguage() {
    const next = langRef.current === "ar" ? "en" : "ar";
    setLang(next);
    if (stateRef.current === STATES.WELCOME && messages.length === 1) {
      setMessages([welcomeMessage(next)]);
    }
  }

  function handleApiError(error, context) {
    let text = tr("error_generic");

    if (error instanceof ApiError && error.status === 422) {
      text = tr("error_validation");
    } else if (error instanceof TypeError) {
      text = tr("error_connection");
    }

    card("danger", context === "reset" ? tr("reset_failed") : tr("error_title"), text);
  }

  return (
    <div className="app-shell" lang={lang}>
      <Header
        lang={lang}
        onReset={resetDemo}
        resetting={resetting}
        onToggleLang={toggleLanguage}
      />

      <div className="workspace">
        <ChatPanel
          lang={lang}
          messages={messages}
          quickActions={quickActions}
          onQuickAction={handleQuickAction}
          onContextAction={handleContextAction}
          state={state}
          input={input}
          setInput={setInput}
          onSubmit={handleSubmit}
          onConfirm={confirmAction}
          onCancelConfirmation={cancelConfirmation}
          confirmation={confirmation}
          loading={loading}
        />

        <ShipmentPanel
          lang={lang}
          shipment={shipment}
          progressStep={progressStep}
          activity={activity}
        />
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

// -------------------------------------------------
// Pure helpers
// -------------------------------------------------

function extractTracking(value) {
  const match = toAsciiDigits(value).match(/(?<![A-Za-z0-9])([A-Za-z]{2}\d{6}[A-Za-z]{2})(?![A-Za-z0-9])/);
  return match ? match[1].toUpperCase() : null;
}

function localToday() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

function validateDeliveryDate(value) {
  const normalized = toAsciiDigits(value).trim();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return { valid: false, key: "date_invalid" };
  }

  const [y, m, d] = normalized.split("-").map(Number);
  const selectedDate = new Date(y, m - 1, d);

  if (
    Number.isNaN(selectedDate.getTime()) ||
    selectedDate.getFullYear() !== y ||
    selectedDate.getMonth() !== m - 1 ||
    selectedDate.getDate() !== d
  ) {
    return { valid: false, key: "date_invalid" };
  }

  if (selectedDate < localToday()) {
    return { valid: false, key: "date_past" };
  }

  return { valid: true, key: "" };
}

function formatDate(lang, iso) {
  const value = String(iso || "").slice(0, 10);
  const [y, m, d] = value.split("-").map(Number);
  if (!y || !m || !d) return value;
  try {
    const label = new Date(y, m - 1, d).toLocaleDateString(lang === "ar" ? "ar-AE" : "en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    return `${label} (${value})`;
  } catch {
    return value;
  }
}

function normalizeAddressForCompare(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[.,،]/g, " ")
    .replace(/\s+/g, " ");
}

function addressesMatch(first, second) {
  const a = normalizeAddressForCompare(first);
  const b = normalizeAddressForCompare(second);
  return Boolean(a && b && a === b);
}

// Mirrors backend/validators.py ADDRESS_PLACEHOLDERS (backend re-validates).
const ADDRESS_PLACEHOLDERS = new Set([
  "test", "n/a", "na", "asdf", "call me", "none", "null", "-", ".", "same as before",
]);

function isValidAddress(value) {
  const normalized = String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
  return normalized.length >= 10 && !ADDRESS_PLACEHOLDERS.has(normalized);
}

function maskPhone(value) {
  const digits = toAsciiDigits(value).replace(/\D/g, "");
  if (digits.length < 4) return "****";
  return "*".repeat(Math.max(digits.length - 4, 4)) + digits.slice(-4);
}

function buildConfirmation(lang, intent, shipment, value) {
  if (intent === "reschedule") {
    return {
      title: t(lang, "confirm_reschedule_title"),
      details: [
        { label: t(lang, "l_tracking_number"), value: shipment?.tracking_number || "—" },
        { label: t(lang, "l_current_status"), value: statusLabel(lang, shipment?.status) || "—" },
        { label: t(lang, "l_new_date"), value: formatDate(lang, value) },
      ],
    };
  }

  return {
    title: t(lang, "confirm_address_title"),
    details: [
      { label: t(lang, "l_current_address"), value: shipment?.delivery_address || "—" },
      { label: t(lang, "l_new_address"), value },
    ],
  };
}

async function parseResponse(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

class ApiError extends Error {
  constructor(status, data) {
    super(data?.message || "API error");
    this.status = status;
    this.data = data;
  }
}
