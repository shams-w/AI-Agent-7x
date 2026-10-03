// Customer-facing text in English and Arabic.
// Replies are templated on purpose: the LLM only understands the customer;
// it never writes claims about what happened to a shipment.

const en = {
  welcome:
    "Hi, I’m your shipment assistant. I can help you reschedule a delivery or update your delivery address. Tell me what you need, in English or Arabic.",
  greeting:
    "Hello! I can help you reschedule a delivery or update your delivery address. What would you like to do?",
  out_of_scope:
    "I can currently help only with rescheduling a delivery or updating a delivery address. Which would you like to do?",
  unclear:
    "I can help with rescheduling a delivery or updating a delivery address. Which would you like to do?",
  multiple:
    "I can do one change at a time. Which would you like to start with: rescheduling the delivery or updating the address?",
  ask_have_tracking: "Do you know your tracking number?",
  ack_reschedule: "Sure, I can help you reschedule the delivery.",
  ack_address: "Sure, I can help you update the delivery address.",
  noted_date: "I’ve noted {date} as the requested delivery date. I’ll ask you to confirm it before anything changes.",
  noted_address: "I’ve noted the new address. I’ll ask you to confirm it before anything changes.",
  enter_tracking: "Great. Please enter your tracking number.",
  enter_tracking_short: "Please enter the tracking number.",
  enter_phone_lookup:
    "No problem. I can help locate your shipment first. Please enter the mobile number used for the shipment.",
  enter_another_phone: "Sure. Please enter another registered mobile number.",
  choose_tracking_option:
    "Please tell me whether you have the tracking number, or I can help you find the shipment with your mobile number.",
  user_have_tracking: "Yes, I have my tracking number.",
  user_no_tracking: "I don’t know my tracking number.",
  user_try_phone: "Try another mobile number",
  user_enter_tracking: "Enter tracking number",
  user_transfer: "Transfer to support",
  user_reschedule: "Reschedule Delivery",
  user_address: "Update Delivery Address",
  user_mobile: "Mobile: {phone}",
  user_last4: "Last 4 digits entered",
  user_new_date: "New delivery date: {date}",

  shipment_located_title: "Shipment located",
  shipment_located_review: "I found a shipment, but it requires manual review.",
  shipment_located_one: "I found one active shipment linked to the registered mobile number.",
  no_guess_handoff:
    "I won’t guess around this data issue. I’ll prepare the request for human support with the context already collected.",
  use_this_shipment:
    "I’ll use this shipment for your request. I still need to verify your identity before making any change.",
  multiple_found_title: "Multiple active shipments found",
  multiple_found: "I found {count} active shipments. Please choose the shipment you mean.",
  option_n: "Option {n}",
  enter_option: "Enter a number from 1 to {count}.",
  no_active_title: "No active shipment found",
  no_active: "I couldn’t locate an active shipment using that mobile number.",
  no_active_next:
    "You can try another registered mobile number, enter your tracking number, or transfer the request to support.",
  invalid_phone_lookup: "Please enter a valid registered mobile number.",
  phone_data_unavailable_title: "Registered mobile data unavailable",
  phone_data_unavailable:
    "I cannot safely identify a shipment by mobile number because the required identity data is unavailable.",
  shipment_selected_title: "Shipment selected",
  shipment_selected: "Using {tracking} for this request.",

  already_scheduled_title: "Redelivery already scheduled",
  already_scheduled_date:
    "A redelivery is already scheduled for {date}. You can continue if you want to change that date.",
  already_scheduled: "A redelivery is already scheduled. You can continue if you want to change it.",
  blocked_title: "Requested action unavailable",
  blocked_reschedule_title: "Reschedule unavailable",
  blocked_address_title: "Address change unavailable",
  blocked_address_support_title: "Address change requires support",
  blocked_human_title: "Human support required",
  blocked_next:
    "Because this change isn’t allowed for this shipment, I won’t ask you to verify or enter new details. You can ask me for a different change, or reset the demo.",

  limited_data_title: "Limited shipment data",
  shipment_found_title: "Shipment found",
  shipment_found: "The shipment was found and is ready for the next step.",
  mobile_required_title: "Mobile number required",
  mobile_required:
    "This shipment does not have a usable registered mobile number. Please provide a valid UAE mobile number to continue this MVP flow.",
  enter_uae_mobile: "Please enter a valid UAE mobile number, for example 05XXXXXXXX or +9715XXXXXXXX.",
  ask_last4: "For security, please enter the last 4 digits of the registered phone number.",
  tracking_correction_title: "Tracking number needs correction",
  tracking_correction:
    "Please re-enter the tracking number exactly as shown. I won’t guess or auto-correct a shipment identifier.",
  not_found: "I couldn’t find that shipment. Please check the tracking number, or use the mobile-number lookup if you don’t know it.",
  review_title: "Shipment review in progress",
  review_weight:
    "The recorded shipment weight is not logically valid, so I have paused the change and routed the shipment for internal review. The original weight has not been changed or guessed.",
  review_ofd_address:
    "This shipment is marked as Out for Delivery, but no valid delivery address is available. I have paused the request and routed it for internal operational review.",
  review_generic:
    "The shipment contains an operational data issue that must be reviewed before an automated change can continue.",
  review_next:
    "Once the operational team marks the review as resolved, I’ll automatically re-check the shipment and tell you what can happen next. For the MVP, internal operational review is simulated. The AI does not invent or correct the source operational value.",
  review_still: "The shipment is still being reviewed. I’ll continue automatically when the internal review is marked as resolved.",
  review_done_title: "Shipment review completed",
  review_done:
    "The (simulated) operational review has been marked resolved. The source data was not changed by the AI. I’ll re-check the current shipment status and data now, then continue only if the requested change is still eligible.",
  duplicate_title: "Conflicting shipment records",
  duplicate: "I found conflicting shipment records, so I will not guess which one is correct.",
  data_review_title: "Shipment data needs review",
  data_review: "This shipment contains data that cannot be safely resolved automatically.",

  prereq_address:
    "Before changing the delivery time, this shipment needs a valid delivery address. Please enter the delivery address first.",
  ask_date: "What date would you like the delivery rescheduled to? You can say “tomorrow”, “next Monday”, or a date like 2026-10-12.",
  ask_new_address: "Please enter the new delivery address (building or villa, street or area, and emirate).",
  verified_title: "Identity verified",
  verified: "Verification completed successfully.",
  verify_mismatch: "Those digits don’t match the registered phone number. Please try again.",
  verify_mismatch_left: "Those digits don’t match the registered phone number. {left} attempt(s) left.",
  verify_bad_input: "Please enter exactly the last 4 digits of the registered phone number.",
  verify_locked_title: "Verification locked",
  verify_locked:
    "Too many incorrect attempts. For your security, verification is temporarily locked for this shipment and no change was made.",
  verify_unavailable: "Customer verification cannot be completed for this shipment.",
  enter_valid_mobile_title: "Enter a valid UAE mobile number",
  mobile_rejected: "The mobile number could not be accepted.",
  phone_already_registered:
    "This shipment already has a registered mobile number, so I need to verify you with its last 4 digits.",
  contact_accepted_title: "Contact number accepted",
  contact_accepted:
    "The mobile number was accepted for this MVP session. In production, this fallback should use OTP or authenticated-account verification.",
  address_detail_title: "Address needs more detail",
  address_detail_prereq: "Please enter a complete delivery address before rescheduling.",
  address_not_saved_title: "Address could not be saved",
  address_not_saved: "Please enter another valid address.",
  address_captured_title: "Delivery address captured",
  address_captured: "The address has been saved. I’ll now re-check whether the delivery-time change is allowed.",
  address_valid_ask_date: "The address is valid. What date would you like the delivery rescheduled to?",

  date_choose_title: "Choose another delivery date",
  date_missing: "I couldn’t find a date in that message. Please give a date such as “tomorrow”, “next Monday” or 2026-10-12.",
  date_invalid: "That delivery date is not valid.",
  date_past: "The delivery date cannot be in the past.",
  date_reenter: "Please enter a valid current or future delivery date.",
  address_short:
    "The new delivery address is missing, too short, or looks like a placeholder.",
  address_example:
    "Please provide a complete delivery address, for example building or villa, street or area, and emirate.",
  address_same_title: "Address already in use",
  address_same: "That address matches the current delivery address, so no update is required.",
  address_different: "Please enter a different delivery address if you still want to make a change.",

  review_date: "Please review the new delivery date before I make the change.",
  review_address: "Please review the current and new address before I make the change.",
  confirm_reschedule_title: "Confirm redelivery",
  confirm_address_title: "Confirm address change",
  confirm_eyebrow: "Review before execution",
  confirm: "Confirm Change",
  executing: "Executing...",
  cancel: "Cancel",

  past_date_title: "Choose a future delivery date",
  date_fix_title: "Delivery date needs correction",
  date_retry: "Please choose another valid delivery date. Your verification is still active.",
  address_fix_title: "Address needs correction",
  address_retry: "Please enter a complete delivery address. Your verification is still active.",
  action_failed_title: "Action not completed",
  not_executed: "The request was not executed.",

  done_reschedule_title: "Delivery rescheduled",
  done_reschedule:
    "Done. Your delivery for {tracking} is now scheduled for {date}. I checked the shipment record and its status is now “{status}”.",
  done_address_title: "Delivery address updated",
  done_address:
    "Done. The delivery address for {tracking} is now: {address}. I checked the shipment record and it shows the new address.",
  unconfirmed_title: "Change not confirmed",
  unconfirmed:
    "The system accepted the request, but I could not confirm the change when I re-checked the shipment record. Please contact support before relying on it.",
  next_request: "Is there anything else I can help you with? I can reschedule a delivery or update an address.",

  cancelled_title: "Change cancelled",
  cancelled: "No shipment data was changed.",
  cancelled_date: "No problem. Choose another delivery date when you’re ready.",
  cancelled_address: "No problem. Enter a different delivery address when you’re ready.",

  verify_again_title: "Verification required again",
  verify_again: "Your verification is missing or has expired. Please verify again before I make any shipment change.",
  verify_again_ask: "Please enter the last 4 digits of the registered phone number again.",

  handoff_title: "Support handoff prepared",
  handoff_text: "{explanation} The collected context is ready for a support agent.",
  handoff_done: "Your request is ready for human support, with the information already collected so you don’t need to start again.",
  handoff_default_reason: "Shipment could not be identified",
  handoff_default_expl: "The request could not be completed automatically.",
  needs_human: "Needs human support",
  completed: "Completed",
  not_completed: "Not completed",
  not_available: "Not available",

  error_generic: "Something went wrong while processing the request.",
  error_validation: "There was a validation issue with the request.",
  error_connection: "I’m having trouble connecting to the shipment system. Please try again.",
  error_title: "Request failed",
  reset_failed: "Reset failed",
  reset_ok: "Demo reset successfully",
  use_actions: "Please use the available action or reset the demo to start a new request.",

  // detail labels
  l_tracking: "Tracking",
  l_tracking_number: "Tracking number",
  l_status: "Status",
  l_current_status: "Current status",
  l_new_status: "New status",
  l_emirate: "Emirate",
  l_service: "Service",
  l_current_address: "Current address",
  l_new_address: "New address",
  l_previous_address: "Previous address",
  l_new_date: "New delivery date",
  l_scheduled: "Scheduled redelivery",
  l_reason: "Reason",
  l_requested_action: "Requested action",
  l_customer_mobile: "Customer mobile",
  l_verification: "Verification status",
  unknown_status: "Unknown status",
  unknown_emirate: "Unknown emirate",

  // UI chrome
  ui_title: "7X AI Shipment Assistant",
  ui_subtitle: "Agentic support for delivery changes",
  ui_online: "AI Agent Online",
  ui_reset: "Reset Demo",
  ui_resetting: "Resetting...",
  ui_conversation: "Customer conversation",
  ui_support: "Shipment support",
  ui_secure: "Verified actions only",
  ui_send: "Send",
  ui_foot: "Actions require identity verification and explicit confirmation.",
  ui_yes_have: "Yes, I have it",
  ui_no_find: "No, find my shipment",
  ui_role_user: "You",
  ui_lang: "العربية",
  ph_default: "Describe what you need help with...",
  ph_tracking_choice: "Choose an option above or type yes / no...",
  ph_tracking: "Enter tracking number...",
  ph_phone: "Enter registered mobile number...",
  ph_selection: "Enter shipment option number...",
  ph_last4: "Enter last 4 digits of registered phone...",
  ph_options: "Choose one of the options above...",
  ph_escalated: "Request transferred to support",
  ph_date: "e.g. tomorrow, next Monday, 2026-10-12",
  ph_address: "Enter the new delivery address...",
  ph_contact: "Enter a UAE mobile number...",

  p_context: "Shipment context",
  p_current: "Current shipment",
  p_empty: "Shipment details will appear here once a tracking number is verified.",
  p_customer: "Customer",
  p_phone: "Phone",
  p_shipment_date: "Shipment date",
  p_last_attempt: "Last attempt",
  p_attempts: "Delivery attempts",
  p_cod: "COD",
  p_weight: "Weight",
  p_address: "Delivery address",
  p_timeline: "Action timeline",
  p_step1: "Shipment identified",
  p_step2: "Customer verified",
  p_step3: "Change reviewed",
  p_step4: "Action completed",
  p_activity: "Agent Activity",
  p_no_activity: "No actions yet.",

  // activity
  a_understood: "Customer message understood ({source})",
  a_discovery: "Shipment discovery completed",
  a_guardrail: "Data quality guardrail triggered",
  a_identity_unavailable: "Identity data unavailable",
  a_eligibility: "Business eligibility checked",
  a_lookup: "Shipment lookup completed",
  a_dq_warning: "Data quality warning handled",
  a_missing_phone: "Missing or invalid contact phone detected",
  a_review_requested: "Internal shipment review requested",
  a_review_resolved: "Internal shipment review resolved",
  a_verified: "Identity verification completed",
  a_verify_locked: "Verification locked after repeated failures",
  a_phone_collected: "Customer contact number collected",
  a_address_collected: "Missing delivery address collected",
  a_rules: "Business rules checked",
  a_confirmed: "Customer confirmation received",
  a_executed: "Backend action executed",
  a_state_verified: "Backend state re-checked",
  a_handoff: "Support handoff prepared",
};

const ar = {
  welcome:
    "أهلاً، أنا مساعد الشحنات. أقدر أساعدك في تغيير موعد التوصيل أو تحديث عنوان التوصيل. اكتب طلبك بالعربي أو بالإنجليزي.",
  greeting: "أهلاً وسهلاً! أقدر أساعدك في تغيير موعد التوصيل أو تحديث عنوان التوصيل. تحب أعمل لك إيه؟",
  out_of_scope: "حالياً أقدر أساعد فقط في تغيير موعد التوصيل أو تحديث عنوان التوصيل. أي واحد منهم تحتاج؟",
  unclear: "أقدر أساعدك في تغيير موعد التوصيل أو تحديث عنوان التوصيل. أي واحد منهم تحتاج؟",
  multiple: "أقدر أنفّذ تغيير واحد في كل مرة. تحب نبدأ بتغيير موعد التوصيل ولا بتحديث العنوان؟",
  ask_have_tracking: "هل رقم التتبع معاك؟",
  ack_reschedule: "تمام، هساعدك في تغيير موعد التوصيل.",
  ack_address: "تمام، هساعدك في تحديث عنوان التوصيل.",
  noted_date: "سجّلت {date} كموعد التوصيل المطلوب. هطلب منك تأكيده قبل أي تغيير.",
  noted_address: "سجّلت العنوان الجديد. هطلب منك تأكيده قبل أي تغيير.",
  enter_tracking: "ممتاز. من فضلك اكتب رقم التتبع.",
  enter_tracking_short: "من فضلك اكتب رقم التتبع.",
  enter_phone_lookup: "ولا يهمك. أقدر ألاقي الشحنة الأول. من فضلك اكتب رقم الموبايل المسجّل على الشحنة.",
  enter_another_phone: "تمام. من فضلك اكتب رقم موبايل مسجّل آخر.",
  choose_tracking_option: "قولّي هل رقم التتبع معاك، أو أقدر أدوّر على الشحنة برقم موبايلك.",
  user_have_tracking: "أيوه، رقم التتبع معايا.",
  user_no_tracking: "رقم التتبع مش معايا.",
  user_try_phone: "جرّب رقم موبايل آخر",
  user_enter_tracking: "إدخال رقم التتبع",
  user_transfer: "تحويل لخدمة العملاء",
  user_reschedule: "تغيير موعد التوصيل",
  user_address: "تحديث عنوان التوصيل",
  user_mobile: "الموبايل: {phone}",
  user_last4: "تم إدخال آخر 4 أرقام",
  user_new_date: "موعد التوصيل الجديد: {date}",

  shipment_located_title: "تم العثور على الشحنة",
  shipment_located_review: "لقيت شحنة، لكنها محتاجة مراجعة يدوية.",
  shipment_located_one: "لقيت شحنة نشطة واحدة مرتبطة برقم الموبايل المسجّل.",
  no_guess_handoff: "مش هخمّن في مشكلة البيانات دي. هجهّز الطلب لخدمة العملاء بالمعلومات اللي اتجمعت.",
  use_this_shipment: "هستخدم الشحنة دي لطلبك. لسه محتاج أتحقق من هويتك قبل أي تغيير.",
  multiple_found_title: "تم العثور على أكثر من شحنة نشطة",
  multiple_found: "لقيت {count} شحنات نشطة. من فضلك اختار الشحنة المقصودة.",
  option_n: "خيار {n}",
  enter_option: "اكتب رقم من 1 إلى {count}.",
  no_active_title: "لا توجد شحنة نشطة",
  no_active: "ما قدرتش ألاقي شحنة نشطة بالرقم ده.",
  no_active_next: "تقدر تجرّب رقم موبايل آخر، أو تكتب رقم التتبع، أو تحوّل الطلب لخدمة العملاء.",
  invalid_phone_lookup: "من فضلك اكتب رقم موبايل مسجّل صحيح.",
  phone_data_unavailable_title: "بيانات الموبايل غير متاحة",
  phone_data_unavailable: "ما أقدرش أحدد الشحنة برقم الموبايل بأمان لأن بيانات الهوية المطلوبة غير متاحة.",
  shipment_selected_title: "تم اختيار الشحنة",
  shipment_selected: "هستخدم الشحنة {tracking} لهذا الطلب.",

  already_scheduled_title: "إعادة التوصيل مجدولة بالفعل",
  already_scheduled_date: "فيه إعادة توصيل مجدولة بالفعل يوم {date}. تقدر تكمّل لو عايز تغيّر الموعد ده.",
  already_scheduled: "فيه إعادة توصيل مجدولة بالفعل. تقدر تكمّل لو عايز تغيّرها.",
  blocked_title: "الإجراء المطلوب غير متاح",
  blocked_reschedule_title: "تغيير الموعد غير متاح",
  blocked_address_title: "تغيير العنوان غير متاح",
  blocked_address_support_title: "تغيير العنوان يحتاج خدمة العملاء",
  blocked_human_title: "يحتاج تدخل خدمة العملاء",
  blocked_next:
    "بما إن التغيير ده غير مسموح للشحنة دي، مش هطلب منك تحقق أو بيانات جديدة. تقدر تطلب تغيير مختلف، أو تعمل Reset للديمو.",

  limited_data_title: "بيانات الشحنة محدودة",
  shipment_found_title: "تم العثور على الشحنة",
  shipment_found: "لقيت الشحنة وجاهزين للخطوة الجاية.",
  mobile_required_title: "مطلوب رقم موبايل",
  mobile_required: "الشحنة دي ما عليهاش رقم موبايل صالح. من فضلك اكتب رقم موبايل إماراتي صحيح للمتابعة (نسخة تجريبية).",
  enter_uae_mobile: "من فضلك اكتب رقم موبايل إماراتي صحيح، مثلاً ‎05XXXXXXXX أو ‎+9715XXXXXXXX.",
  ask_last4: "للأمان، من فضلك اكتب آخر 4 أرقام من رقم الموبايل المسجّل.",
  tracking_correction_title: "رقم التتبع يحتاج تصحيح",
  tracking_correction: "من فضلك اكتب رقم التتبع زي ما هو مكتوب بالظبط. مش هخمّن أو أصحّح رقم الشحنة تلقائياً.",
  not_found: "ما لقيتش الشحنة دي. راجع رقم التتبع، أو دوّر برقم الموبايل لو مش معاك الرقم.",
  review_title: "الشحنة قيد المراجعة",
  review_weight: "الوزن المسجّل للشحنة غير منطقي، فوقّفت التغيير وحوّلت الشحنة لمراجعة داخلية. الوزن الأصلي ما اتغيرش وما اتخمّنش.",
  review_ofd_address: "الشحنة حالتها «خرجت للتوصيل» لكن مفيش عنوان توصيل صالح. وقّفت الطلب وحوّلته لمراجعة تشغيلية داخلية.",
  review_generic: "الشحنة فيها مشكلة بيانات تشغيلية لازم تتراجع قبل أي تغيير تلقائي.",
  review_next: "أول ما الفريق يخلّص المراجعة، هعيد فحص الشحنة تلقائياً وأقولّك الخطوة الجاية. في هذه النسخة التجريبية، المراجعة التشغيلية الداخلية محاكاة فقط. المساعد لا يخترع ولا يصحّح القيمة التشغيلية الأصلية.",
  review_still: "الشحنة لسه قيد المراجعة. هكمّل تلقائياً أول ما المراجعة تخلص.",
  review_done_title: "اكتملت مراجعة الشحنة",
  review_done: "تم إنهاء المراجعة التشغيلية (المحاكاة). المساعد لم يغيّر البيانات الأصلية. هعيد فحص حالة الشحنة وبياناتها دلوقتي، وهكمّل بس لو التغيير لسه مسموح.",
  duplicate_title: "سجلات شحنة متعارضة",
  duplicate: "لقيت سجلات متعارضة لنفس الشحنة، فمش هخمّن أي واحد فيهم الصحيح.",
  data_review_title: "بيانات الشحنة تحتاج مراجعة",
  data_review: "الشحنة فيها بيانات ما ينفعش أتعامل معاها تلقائياً بأمان.",

  prereq_address: "قبل تغيير موعد التوصيل، الشحنة محتاجة عنوان توصيل صالح. من فضلك اكتب عنوان التوصيل الأول.",
  ask_date: "تحب التوصيل يكون إمتى؟ تقدر تقول «بكرة» أو «يوم الخميس» أو تاريخ زي 2026-10-12.",
  ask_new_address: "من فضلك اكتب عنوان التوصيل الجديد (المبنى أو الفيلا، الشارع أو المنطقة، والإمارة).",
  verified_title: "تم التحقق من الهوية",
  verified: "تم التحقق بنجاح.",
  verify_mismatch: "الأرقام دي مش مطابقة لرقم الموبايل المسجّل. حاول تاني.",
  verify_mismatch_left: "الأرقام دي مش مطابقة لرقم الموبايل المسجّل. متبقي {left} محاولة.",
  verify_bad_input: "من فضلك اكتب آخر 4 أرقام بالظبط من رقم الموبايل المسجّل.",
  verify_locked_title: "تم إيقاف التحقق مؤقتاً",
  verify_locked: "محاولات خاطئة كتير. لحمايتك، التحقق متوقف مؤقتاً للشحنة دي وما حصلش أي تغيير.",
  verify_unavailable: "ما ينفعش إتمام التحقق من الهوية للشحنة دي.",
  enter_valid_mobile_title: "اكتب رقم موبايل إماراتي صحيح",
  mobile_rejected: "رقم الموبايل ما اتقبلش.",
  phone_already_registered: "الشحنة دي عليها رقم موبايل مسجّل بالفعل، فلازم أتحقق منك بآخر 4 أرقام منه.",
  contact_accepted_title: "تم قبول رقم التواصل",
  contact_accepted: "تم قبول رقم الموبايل لهذه الجلسة التجريبية. في النسخة الفعلية لازم يكون التحقق برمز OTP أو حساب موثّق.",
  address_detail_title: "العنوان يحتاج تفاصيل أكتر",
  address_detail_prereq: "من فضلك اكتب عنوان توصيل كامل قبل تغيير الموعد.",
  address_not_saved_title: "ما قدرتش أحفظ العنوان",
  address_not_saved: "من فضلك اكتب عنوان صالح آخر.",
  address_captured_title: "تم حفظ عنوان التوصيل",
  address_captured: "اتحفظ العنوان. هعيد التأكد إن تغيير الموعد مسموح.",
  address_valid_ask_date: "العنوان صالح. تحب التوصيل يكون إمتى؟",

  date_choose_title: "اختار موعد توصيل آخر",
  date_missing: "ما لقيتش تاريخ في الرسالة. اكتب مثلاً «بكرة» أو «يوم الاثنين» أو 2026-10-12.",
  date_invalid: "التاريخ ده غير صالح.",
  date_past: "ما ينفعش موعد التوصيل يكون في الماضي.",
  date_reenter: "من فضلك اكتب تاريخ النهارده أو تاريخ قادم.",
  address_short: "العنوان الجديد ناقص أو قصير جداً أو شكله غير حقيقي.",
  address_example: "من فضلك اكتب عنوان كامل، مثلاً المبنى أو الفيلا، الشارع أو المنطقة، والإمارة.",
  address_same_title: "نفس العنوان الحالي",
  address_same: "العنوان ده هو نفس عنوان التوصيل الحالي، فمفيش داعي للتحديث.",
  address_different: "اكتب عنوان مختلف لو لسه عايز تغيّره.",

  review_date: "من فضلك راجع موعد التوصيل الجديد قبل ما أنفّذ التغيير.",
  review_address: "من فضلك راجع العنوان الحالي والجديد قبل ما أنفّذ التغيير.",
  confirm_reschedule_title: "تأكيد إعادة التوصيل",
  confirm_address_title: "تأكيد تغيير العنوان",
  confirm_eyebrow: "مراجعة قبل التنفيذ",
  confirm: "تأكيد التغيير",
  executing: "جاري التنفيذ...",
  cancel: "إلغاء",

  past_date_title: "اختار موعد في المستقبل",
  date_fix_title: "موعد التوصيل يحتاج تصحيح",
  date_retry: "من فضلك اختار موعد توصيل صالح آخر. التحقق بتاعك لسه ساري.",
  address_fix_title: "العنوان يحتاج تصحيح",
  address_retry: "من فضلك اكتب عنوان توصيل كامل. التحقق بتاعك لسه ساري.",
  action_failed_title: "لم يتم تنفيذ الإجراء",
  not_executed: "لم يتم تنفيذ الطلب.",

  done_reschedule_title: "تم تغيير موعد التوصيل",
  done_reschedule:
    "تم. التوصيل للشحنة {tracking} بقى مجدول يوم {date}. راجعت سجل الشحنة وحالتها دلوقتي «{status}».",
  done_address_title: "تم تحديث عنوان التوصيل",
  done_address: "تم. عنوان التوصيل للشحنة {tracking} بقى: {address}. راجعت سجل الشحنة وظاهر فيه العنوان الجديد.",
  unconfirmed_title: "التغيير غير مؤكد",
  unconfirmed: "النظام قبل الطلب، لكن لما راجعت سجل الشحنة ما قدرتش أتأكد إن التغيير اتسجّل. من فضلك تواصل مع خدمة العملاء قبل ما تعتمد عليه.",
  next_request: "أقدر أساعدك في حاجة تانية؟ أقدر أغيّر موعد توصيل أو أحدّث عنوان.",

  cancelled_title: "تم إلغاء التغيير",
  cancelled: "ما حصلش أي تغيير في بيانات الشحنة.",
  cancelled_date: "ولا يهمك. اختار موعد آخر وقت ما تحب.",
  cancelled_address: "ولا يهمك. اكتب عنوان مختلف وقت ما تحب.",

  verify_again_title: "مطلوب التحقق مرة أخرى",
  verify_again: "التحقق مش موجود أو انتهت صلاحيته. من فضلك اتحقق تاني قبل أي تغيير.",
  verify_again_ask: "من فضلك اكتب آخر 4 أرقام من رقم الموبايل المسجّل مرة تانية.",

  handoff_title: "تم تجهيز التحويل لخدمة العملاء",
  handoff_text: "{explanation} المعلومات اللي اتجمعت جاهزة لموظف خدمة العملاء.",
  handoff_done: "طلبك جاهز لخدمة العملاء بالمعلومات اللي اتجمعت، فمش هتحتاج تبدأ من الأول.",
  handoff_default_reason: "ما قدرتش أحدد الشحنة",
  handoff_default_expl: "ما قدرتش أكمّل الطلب تلقائياً.",
  needs_human: "يحتاج خدمة العملاء",
  completed: "تم",
  not_completed: "لم يتم",
  not_available: "غير متاح",

  error_generic: "حصلت مشكلة أثناء تنفيذ الطلب.",
  error_validation: "فيه مشكلة في بيانات الطلب.",
  error_connection: "عندي مشكلة في الاتصال بنظام الشحنات. حاول تاني من فضلك.",
  error_title: "فشل الطلب",
  reset_failed: "فشل الـ Reset",
  reset_ok: "تم إعادة ضبط الديمو",
  use_actions: "من فضلك استخدم الاختيارات المتاحة أو اعمل Reset لبدء طلب جديد.",

  l_tracking: "رقم التتبع",
  l_tracking_number: "رقم التتبع",
  l_status: "الحالة",
  l_current_status: "الحالة الحالية",
  l_new_status: "الحالة الجديدة",
  l_emirate: "الإمارة",
  l_service: "الخدمة",
  l_current_address: "العنوان الحالي",
  l_new_address: "العنوان الجديد",
  l_previous_address: "العنوان السابق",
  l_new_date: "موعد التوصيل الجديد",
  l_scheduled: "موعد إعادة التوصيل",
  l_reason: "السبب",
  l_requested_action: "الإجراء المطلوب",
  l_customer_mobile: "موبايل العميل",
  l_verification: "حالة التحقق",
  unknown_status: "حالة غير معروفة",
  unknown_emirate: "إمارة غير معروفة",

  ui_title: "مساعد الشحنات الذكي 7X",
  ui_subtitle: "دعم ذكي لتغييرات التوصيل",
  ui_online: "المساعد متصل",
  ui_reset: "إعادة ضبط الديمو",
  ui_resetting: "جاري الإعادة...",
  ui_conversation: "محادثة العميل",
  ui_support: "دعم الشحنات",
  ui_secure: "إجراءات موثّقة فقط",
  ui_send: "إرسال",
  ui_foot: "أي تغيير يتطلب التحقق من الهوية وتأكيد صريح.",
  ui_yes_have: "أيوه، معايا",
  ui_no_find: "لا، دوّر على شحنتي",
  ui_role_user: "أنت",
  ui_lang: "English",
  ph_default: "اكتب طلبك هنا...",
  ph_tracking_choice: "اختار من فوق أو اكتب أيوه / لا...",
  ph_tracking: "اكتب رقم التتبع...",
  ph_phone: "اكتب رقم الموبايل المسجّل...",
  ph_selection: "اكتب رقم الخيار...",
  ph_last4: "اكتب آخر 4 أرقام من الموبايل المسجّل...",
  ph_options: "اختار من الاختيارات اللي فوق...",
  ph_escalated: "تم تحويل الطلب لخدمة العملاء",
  ph_date: "مثلاً: بكرة، يوم الخميس، 2026-10-12",
  ph_address: "اكتب عنوان التوصيل الجديد...",
  ph_contact: "اكتب رقم موبايل إماراتي...",

  p_context: "بيانات الشحنة",
  p_current: "الشحنة الحالية",
  p_empty: "بيانات الشحنة هتظهر هنا بعد تحديد رقم التتبع.",
  p_customer: "العميل",
  p_phone: "الموبايل",
  p_shipment_date: "تاريخ الشحن",
  p_last_attempt: "آخر محاولة",
  p_attempts: "محاولات التوصيل",
  p_cod: "الدفع عند الاستلام",
  p_weight: "الوزن",
  p_address: "عنوان التوصيل",
  p_timeline: "مراحل الطلب",
  p_step1: "تحديد الشحنة",
  p_step2: "التحقق من العميل",
  p_step3: "مراجعة التغيير",
  p_step4: "تنفيذ الإجراء",
  p_activity: "نشاط المساعد",
  p_no_activity: "لا يوجد نشاط بعد.",

  a_understood: "تم فهم رسالة العميل ({source})",
  a_discovery: "تم البحث عن الشحنة",
  a_guardrail: "تم تفعيل حماية جودة البيانات",
  a_identity_unavailable: "بيانات الهوية غير متاحة",
  a_eligibility: "تم فحص قواعد الأهلية",
  a_lookup: "تم استعلام الشحنة",
  a_dq_warning: "تم التعامل مع تنبيه جودة البيانات",
  a_missing_phone: "رقم تواصل ناقص أو غير صالح",
  a_review_requested: "تم طلب مراجعة داخلية",
  a_review_resolved: "تم حل المراجعة الداخلية",
  a_verified: "تم التحقق من الهوية",
  a_verify_locked: "تم إيقاف التحقق بعد محاولات فاشلة",
  a_phone_collected: "تم جمع رقم التواصل",
  a_address_collected: "تم جمع عنوان التوصيل الناقص",
  a_rules: "تم فحص قواعد العمل",
  a_confirmed: "تم استلام تأكيد العميل",
  a_executed: "تم تنفيذ الإجراء في النظام",
  a_state_verified: "تمت إعادة فحص حالة النظام",
  a_handoff: "تم تجهيز التحويل لخدمة العملاء",
};

const dictionaries = { en, ar };

export function t(lang, key, params = {}) {
  const table = dictionaries[lang] || en;
  let text = table[key] ?? en[key] ?? key;
  for (const [name, value] of Object.entries(params)) {
    text = text.split(`{${name}}`).join(String(value ?? ""));
  }
  return text;
}

// Backend reason / issue codes -> customer text. Unknown codes fall back to
// the backend's own (English) message so nothing is silently dropped.
const reasonText = {
  en: {},
  ar: {
    ALREADY_DELIVERED: "الشحنة اتسلّمت بالفعل، فما ينفعش تغيير الموعد أو العنوان.",
    RETURNED_TO_SENDER: "الشحنة رجعت للمرسل وتحتاج تدخل خدمة العملاء.",
    OUT_FOR_DELIVERY: "الشحنة خرجت للتوصيل حالياً، فالتغيير التلقائي غير متاح ويحتاج خدمة العملاء.",
    STATUS_NOT_SUPPORTED: "حالة الشحنة دي مش مدعومة للتغيير التلقائي.",
    NOT_FOUND: "ما لقيتش الشحنة.",
    INVALID_TRACKING_FORMAT: "شكل رقم التتبع غير صحيح. اكتبه زي ما هو مكتوب على الشحنة بالظبط، أو دوّر برقم الموبايل.",
    PAST_DATE: "ما ينفعش موعد التوصيل يكون في الماضي.",
    INVALID_DATE: "صيغة التاريخ غير صحيحة.",
    DELIVERY_DATE_REQUIRED: "مطلوب موعد توصيل جديد.",
    INVALID_NEW_ADDRESS: "من فضلك اكتب عنوان توصيل كامل.",
    ADDRESS_UNCHANGED: "العنوان الجديد هو نفس العنوان الحالي.",
    INVALID_PHONE: "ده مش رقم موبايل إماراتي صحيح. من فضلك اكتبه تاني، مثلاً ‎05XXXXXXXX أو ‎+9715XXXXXXXX (050، 052، 054، 055، 056 أو 058).",
    TEST_RECORD: "السجل ده بيانات اختبار وما ينفعش يُستخدم لأي إجراء للعميل.",
    INVALID_WEIGHT: "وزن الشحنة المسجّل غير صالح ويحتاج مراجعة.",
    MISSING_STATUS: "حالة الشحنة غير موجودة، فما أقدرش أحدد إذا كان التغيير مسموح.",
    UNKNOWN_STATUS: "حالة الشحنة المسجّلة غير معروفة، فما أقدرش أحدد إذا كان التغيير مسموح.",
    INVALID_TRACKING_DATA: "بيانات التتبع غير موثوقة كفاية لتغيير تلقائي.",
    MISSING_PHONE: "الشحنة ما عليهاش رقم موبايل مسجّل يصلح للتحقق.",
    INVALID_TIMELINE: "فيه تواريخ متعارضة في الشحنة، فمش هعمل تغيير تلقائي.",
    INVALID_SHIPMENT_DATE: "تاريخ الشحن ناقص أو غير صالح أو غير واضح، والسجل يحتاج مراجعة.",
    INVALID_LAST_ATTEMPT_DATE: "تاريخ آخر محاولة توصيل غير صالح أو غير واضح، والسجل يحتاج مراجعة.",
    INVALID_ADDRESS: "عنوان التوصيل المسجّل ناقص أو غير صالح.",
    INVALID_DELIVERY_ATTEMPTS: "عدد محاولات التوصيل ناقص أو غير صالح، والسجل يحتاج مراجعة.",
    CROSS_FIELD_INCONSISTENCY: "فيه بيانات متعارضة في الشحنة، والسجل يحتاج مراجعة يدوية.",
    INVALID_COD: "مبلغ الدفع عند الاستلام غير واضح، والسجل يحتاج مراجعة.",
    SUSPICIOUS_COD: "مبلغ الدفع عند الاستلام غير معتاد ويحتاج مراجعة قبل أي تغيير.",
    MISSING_LAST_ATTEMPT: "تاريخ آخر محاولة توصيل غير متاح، لكن أقدر أكمّل لأن الطلب مش معتمد عليه.",
    SENSITIVE_NOTES_HIDDEN: "تم إخفاء ملاحظات داخلية حساسة عن المساعد.",
    DATA_REVIEW_REQUIRED: "الشحنة فيها بيانات ما ينفعش أتعامل معاها تلقائياً بأمان.",
    DUPLICATE_RECORDS: "لقيت أكثر من سجل لنفس رقم التتبع، فمش هخمّن أي واحد الصحيح.",
    OUT_FOR_DELIVERY_MISSING_ADDRESS: "الشحنة خرجت للتوصيل ومفيش عنوان صالح، فاتحوّلت لمراجعة داخلية.",
  },
};

const issueTitleAr = {
  TEST_RECORD: "سجل اختبار محظور",
  INVALID_WEIGHT: "وزن الشحنة يحتاج مراجعة",
  MISSING_STATUS: "حالة الشحنة غير متاحة",
  UNKNOWN_STATUS: "حالة الشحنة تحتاج مراجعة",
  INVALID_TRACKING_DATA: "بيانات التتبع تحتاج مراجعة",
  MISSING_PHONE: "التحقق من العميل غير متاح",
  INVALID_PHONE: "التحقق من العميل غير متاح",
  INVALID_TIMELINE: "تواريخ الشحنة تحتاج مراجعة",
  INVALID_SHIPMENT_DATE: "تاريخ الشحن يحتاج مراجعة",
  INVALID_LAST_ATTEMPT_DATE: "تاريخ آخر محاولة يحتاج مراجعة",
  INVALID_ADDRESS: "عنوان التوصيل يحتاج مراجعة",
  INVALID_DELIVERY_ATTEMPTS: "محاولات التوصيل تحتاج مراجعة",
  CROSS_FIELD_INCONSISTENCY: "بيانات شحنة متعارضة",
  INVALID_COD: "بيانات الدفع تحتاج مراجعة",
  SUSPICIOUS_COD: "بيانات الدفع تحتاج مراجعة",
  MISSING_LAST_ATTEMPT: "سجل الشحنة محدود",
  SENSITIVE_NOTES_HIDDEN: "ملاحظة محمية",
  DATA_REVIEW_REQUIRED: "بيانات الشحنة تحتاج مراجعة",
  DUPLICATE_RECORDS: "سجلات شحنة متعارضة",
  OUT_FOR_DELIVERY_MISSING_ADDRESS: "بيانات الشحنة تحتاج مراجعة",
};

export function reasonMessage(lang, code, fallback) {
  if (lang === "ar" && code && reasonText.ar[code]) return reasonText.ar[code];
  return fallback || (code ? String(code) : "");
}

export function issueTitle(lang, code, fallback) {
  if (lang === "ar" && code && issueTitleAr[code]) return issueTitleAr[code];
  return fallback;
}

const statusAr = {
  "Delivered": "تم التسليم",
  "Failed Delivery": "فشل التوصيل",
  "Scheduled for Redelivery": "مجدولة لإعادة التوصيل",
  "In Transit": "في الطريق",
  "Out for Delivery": "خرجت للتوصيل",
  "Returned to Sender": "أُعيدت للمرسل",
};

export function statusLabel(lang, status) {
  if (!status) return status;
  if (lang === "ar" && statusAr[status]) return statusAr[status];
  return status;
}

// Arabic-Indic and Persian digits -> ASCII digits.
export function toAsciiDigits(value) {
  return String(value ?? "").replace(/[٠-٩۰-۹]/g, (d) =>
    String("٠١٢٣٤٥٦٧٨٩".indexOf(d) >= 0 ? "٠١٢٣٤٥٦٧٨٩".indexOf(d) : "۰۱۲۳۴۵۶۷۸۹".indexOf(d))
  );
}

// Language of the customer's latest message. Digits/tracking-only messages
// keep the current language.
export function inferLanguage(text, current) {
  const value = String(text || "");
  if (/[؀-ۿ]/.test(value)) return "ar";
  const withoutTracking = value.replace(/[A-Za-z]{2}\d{6}[A-Za-z]{2}/g, "");
  const latinWords = withoutTracking.match(/[A-Za-z]{2,}/g) || [];
  if (latinWords.length >= 2 || (latinWords.length === 1 && latinWords[0].length >= 3 && !/^(yes|no|ok)$/i.test(latinWords[0]))) {
    return "en";
  }
  return current;
}
