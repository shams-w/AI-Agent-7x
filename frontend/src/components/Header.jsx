import { t } from "../i18n";

export default function Header({ lang, onReset, resetting, onToggleLang }) {
  return (
    <header className="topbar">
      <div className="brand-wrap">
        <div className="brand-mark">7X</div>
        <div dir="auto">
          <h1>{t(lang, "ui_title")}</h1>
          <p>{t(lang, "ui_subtitle")}</p>
        </div>
      </div>
      <div className="topbar-actions">
        <div className="online-badge"><span className="online-dot" />{t(lang, "ui_online")}</div>
        <button className="secondary-btn" onClick={onToggleLang} data-testid="lang-toggle">
          {t(lang, "ui_lang")}
        </button>
        <button className="secondary-btn" onClick={onReset} disabled={resetting} data-testid="reset">
          {resetting ? t(lang, "ui_resetting") : t(lang, "ui_reset")}
        </button>
      </div>
    </header>
  );
}
