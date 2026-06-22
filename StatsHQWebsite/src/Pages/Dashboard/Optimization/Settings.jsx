import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import ReactDOM from "react-dom";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import {
  ALargeSmall,
  Earth,
  Volume2,
  Bot,
  UserRoundKey,
  LayoutDashboard,
  Clock,
  History,
  Globe,
  Cog,
  UserCog,
  ShieldUser,
  Crown,
  User,
  MicOff,
  HeadphoneOff,
  MouseOff,
  TvMinimalPlay,
  Video,
  CircleOff,
  VolumeX,
  EarOff,
  Info,
  ToggleRight,
  MessageCircle,
  UserPlus,
  Smile,
  Gamepad2,
  ChartColumnIncreasing,
  ChartNoAxesCombined,
  AtSign,
  RotateCcw,
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const NAVBAR_HEIGHT = "80px";
const ACCENT = "#aa00ff";

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

const styles = `
  @font-face {
    font-family: 'Horndon';
    src: url('/HorndonD.ttf') format('truetype');
    font-display: swap;
  }

  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  }

  .navbar .logo span:last-child {
    font-family: 'Horndon', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    font-weight: normal;
    letter-spacing: 0.5px;
  }

  html { min-height: 100%; background-color: #0a0a0a; }
  body { min-height: 100vh; margin: 0; padding: 0; background-color: #0a0a0a; color: #ffffff; overflow-y: auto; }
  #app { min-height: 100vh; background-color: #0a0a0a; }

  .dashboard-page {
    max-width: 100%;
    margin: 0 auto;
    background-color: #0a0a0a;
    color: #ffffff;
    min-height: 100vh;
    display: flex;
    position: relative;
  }

  .dashboard-main {
    flex: 1;
    margin-left: 280px;
    background-color: #0a0a0a;
    min-height: calc(100vh - ${NAVBAR_HEIGHT});
  }

  .dashboard-content {
    max-width: 1600px;
    margin: 0 auto;
    padding: 20px 40px 40px 40px;
    background-color: #0a0a0a;
  }

  .settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
    gap: 24px;
    margin-top: 0;
  }

  .settings-card {
    background-color: #0f0f0f;
    border: 1px solid #1f1f1f;
    border-radius: 16px;
    padding: 24px;
    transition: all 0.2s ease;
  }

  .settings-card:hover {
    transform: translateY(-2px);
    border-color: rgba(170, 0, 255, 0.4);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.1);
  }

  .settings-card-full {
    grid-column: 1 / -1;
  }

  .settings-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    border-bottom: 1px solid #1f1f1f;
    padding-bottom: 12px;
  }

  .settings-card-title-section {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .settings-card-icon {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .settings-card-title {
    color: #ffffff;
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .info-icon {
    color: #888;
    cursor: help;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background-color: #2a2a2a;
    flex-shrink: 0;
  }

  .info-icon:hover { color: #aa00ff; background-color: #3a3a3a; }

  .info-tooltip-portal {
    position: fixed;
    background-color: #1a1a1a;
    border: 1px solid #aa00ff;
    border-radius: 8px;
    padding: 12px;
    width: 300px;
    z-index: 99999;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    pointer-events: none;
    white-space: normal;
    font-size: 12px;
    line-height: 1.5;
    color: #b0b0b0;
  }

  .info-tooltip-portal::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border-width: 6px;
    border-style: solid;
    border-color: #aa00ff transparent transparent transparent;
  }

  .settings-card-description {
    color: #888;
    font-size: 13px;
    margin-bottom: 20px;
    line-height: 1.5;
  }

  .setting-preview {
    background-color: #1a1a1a;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border: 1px solid #2a2a2a;
  }

  .setting-value {
    color: #aa00ff;
    font-family: monospace;
    font-size: 18px;
    font-weight: bold;
  }

  .setting-change-btn {
    background-color: #2a2a2a;
    border: none;
    color: #fff;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
  }

  .setting-change-btn:hover { background-color: #3a3a3a; }

  .setting-note {
    color: #666;
    font-size: 12px;
    margin: 0;
  }

  .setting-note code { color: #aa00ff; }

  .setting-input {
    width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 12px;
    font-size: 16px;
    outline: none;
  }

  .setting-input:focus {
    border-color: #aa00ff;
    box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
  }

  .button-group { display: flex; gap: 10px; }

  .button-save {
    background-color: #aa00ff;
    border: none;
    color: #fff;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
  }

  .button-save:hover { background-color: #8800cc; transform: translateY(-2px); }
  .button-save:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

  .button-cancel {
    background-color: #2a2a2a;
    border: none;
    color: #fff;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
  }

  .button-cancel:hover { background-color: #3a3a3a; }

  .button-reset {
    background-color: transparent;
    border: 1px solid #3a3a3a;
    color: #b0b0b0;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .button-reset:hover { background-color: #2a2a2a; color: #fff; border-color: #4a4a4a; }
  .button-reset:disabled { opacity: 0.5; cursor: not-allowed; }

  .voice-states-grid {
    margin-bottom: 16px;
    max-height: 350px;
    overflow-y: auto;
  }

  .voice-state-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    margin-bottom: 8px;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
  }

  .voice-state-option.selected {
    background-color: #2a2a2a;
    border-color: #aa00ff;
  }

  .voice-state-info {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
  }

  .voice-state-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background-color: #2a2a2a;
    flex-shrink: 0;
  }

  .voice-state-option.selected .voice-state-icon {
    background-color: rgba(170, 0, 255, 0.15);
  }

  .voice-state-label {
    color: #fff;
    font-weight: 500;
    margin-bottom: 4px;
    font-size: 13px;
  }

  .voice-state-desc {
    color: #888;
    font-size: 11px;
  }

  .voice-state-checkbox {
    width: 22px;
    height: 22px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    flex-shrink: 0;
  }

  .voice-state-checkbox.selected {
    background-color: #aa00ff;
    border: none;
  }

  /* ── Tracked-items pill summary (used by Voice States & Stat Type Toggle previews) ── */
  .tracked-pill-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  .tracked-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background-color: #232323;
    border: 1px solid #2f2f2f;
    border-radius: 999px;
    padding: 4px 10px 4px 8px;
    font-size: 11.5px;
    font-weight: 500;
    color: #d8d8d8;
    letter-spacing: 0.1px;
  }

  .tracked-pill-empty {
    color: #666;
    font-size: 12px;
    font-style: italic;
  }

  .bot-filter-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: #1a1a1a;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 12px;
    border: 1px solid #2a2a2a;
  }

  .bot-filter-text {
    color: #fff;
    font-weight: 500;
    margin-bottom: 6px;
    font-size: 15px;
  }

  .bot-filter-desc { color: #888; font-size: 13px; }

  .bot-filter-button {
    border: 2px solid #000000;
    color: #fff;
    padding: 10px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
  }

  .bot-filter-button.filtering { background-color: #8b0000; }
  .bot-filter-button.including { background-color: #006400; }
  .bot-filter-button:hover { transform: scale(1.02); }
  .bot-filter-button:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

  /* ── Option boxes (permission / access / time period mode) ── */
  .option-boxes {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 20px;
  }

  .option-box {
    flex: 1;
    min-width: 80px;
    background-color: #1a1a1a;
    border: 2px solid #2a2a2a;
    border-radius: 12px;
    padding: 14px 8px 10px 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .option-box:hover {
    border-color: #aa00ff;
    transform: translateY(-2px);
    background-color: #181818;
  }

  .option-box.selected {
    background-color: #160026;
    border-color: #aa00ff;
    box-shadow: 0 0 15px rgba(170, 0, 255, 0.25);
  }

  .option-box-name {
    color: #fff;
    font-weight: 600;
    font-size: 12px;
    line-height: 1.2;
  }

  /* ── History sync card ── */
  .history-sync-link-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 20px 10px;
    text-align: center;
  }

  .history-sync-go-btn {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background-color: #aa00ff;
    border: none;
    color: #fff;
    padding: 16px 36px;
    border-radius: 12px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    text-decoration: none;
    transition: all 0.2s ease;
  }

  .history-sync-go-btn:hover {
    background-color: #8800cc;
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(170, 0, 255, 0.35);
  }

  .loading-container {
    text-align: center;
    padding: 80px 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
  }

  .error-message-container {
    text-align: center;
    padding: 80px 40px;
    background-color: #1a1a1a;
    border: 1px solid #ff4444;
    border-radius: 16px;
    margin-top: 40px;
  }

  .error-icon { font-size: 64px; margin-bottom: 20px; }
  .error-title { color: #ff4444; font-size: 28px; font-weight: 600; margin-bottom: 16px; }
  .error-message { color: #b0b0b0; font-size: 16px; line-height: 1.6; margin-bottom: 8px; }

  .no-server {
    text-align: center;
    padding: 80px 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    color: #b0b0b0;
  }

  .no-server h2 { color: #ffffff; margin-bottom: 16px; font-size: 28px; font-weight: 600; }

  .invite-button, .login-button {
    display: inline-block;
    background-color: #aa00ff;
    color: white;
    padding: 12px 28px;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 600;
    margin-top: 20px;
    transition: all 0.2s ease;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }

  .invite-button:hover, .login-button:hover {
    background-color: #8800cc;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
  }

  @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
  @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

  .toast-message {
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    z-index: 9999;
    animation: slideIn 0.3s ease;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    font-weight: 500;
  }

  @media (max-width: 1024px) {
    .dashboard-main { margin-left: 250px; }
    .dashboard-content { padding: 30px; }
    .settings-grid { grid-template-columns: 1fr; }
    .option-boxes { flex-direction: column; }
    .option-box { min-width: auto; }
  }

  @media (max-width: 768px) {
    .dashboard-main { margin-left: 0; }
    .dashboard-content { padding: 20px; }
  }
`;

// ─────────────────────────────────────────────────────────────
// Portal-based InfoIcon (same pattern as HistorySync)
// ─────────────────────────────────────────────────────────────

const InfoIcon = ({ descriptions }) => {
  const [tooltipPos, setTooltipPos] = useState(null);
  const iconRef = React.useRef(null);
  const timeoutRef = React.useRef(null);

  const show = () => {
    if (!iconRef.current) return;
    const rect = iconRef.current.getBoundingClientRect();
    setTooltipPos({ left: rect.left + rect.width / 2, bottom: window.innerHeight - rect.top + 10 });
  };

  const handleMouseEnter = () => { timeoutRef.current = setTimeout(show, 300); };
  const handleMouseLeave = () => { clearTimeout(timeoutRef.current); setTooltipPos(null); };
  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const tooltip = tooltipPos
    ? ReactDOM.createPortal(
        <div className="info-tooltip-portal" style={{ bottom: tooltipPos.bottom, left: tooltipPos.left, transform: 'translateX(-50%)' }}>
          {descriptions.map((desc, idx) => (
            <div key={idx} style={{ marginBottom: idx < descriptions.length - 1 ? '8px' : '0' }}>
              <strong style={{ color: '#aa00ff' }}>{desc.level}:</strong> {desc.description}
            </div>
          ))}
        </div>,
        document.body
      )
    : null;

  return (
    <>
      <span ref={iconRef} className="info-icon" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
        <Info size={13} color="#888" />
      </span>
      {tooltip}
    </>
  );
};

// ─────────────────────────────────────────────────────────────
// SettingsCard
// ─────────────────────────────────────────────────────────────

const SettingsCard = ({ title, icon, children, description, infoDescriptions = [], fullWidth = false }) => (
  <div className={`settings-card${fullWidth ? ' settings-card-full' : ''}`}>
    <div className="settings-card-header">
      <div className="settings-card-title-section">
        <span className="settings-card-icon">{icon}</span>
        <h3 className="settings-card-title">{title}</h3>
        {infoDescriptions.length > 0 && <InfoIcon descriptions={infoDescriptions} />}
      </div>
    </div>
    {description && <p className="settings-card-description">{description}</p>}
    <div style={{ marginTop: '16px' }}>{children}</div>
  </div>
);

// ─────────────────────────────────────────────────────────────
// LoadingSpinner
// ─────────────────────────────────────────────────────────────

const LoadingSpinner = ({ size = "medium", text = "Loading settings..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px', gap: '16px', width: '100%', minHeight: '400px' }}>
      <div style={{ width: spinnerSize, height: spinnerSize, border: '3px solid rgba(170, 0, 255, 0.2)', borderTop: `3px solid #aa00ff`, borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
      {text && <span style={{ color: '#aa00ff', fontSize: '14px' }}>{text}</span>}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// History Data Sync link box
// ─────────────────────────────────────────────────────────────

const HistorySyncLinkBox = () => (
  <div className="history-sync-link-box">
    <p style={{ color: '#888', fontSize: '13px', lineHeight: 1.6, margin: 0, maxWidth: '340px' }}>
      Unlock stats from before the bot arrived. Pull in months or years of messages, mentions, and emoji — all the history that was already there waiting.
    </p>
    <a href="/Dashboard/History Data Sync/" className="history-sync-go-btn">
      <History size={20} color="#fff" />
      Go to History Data Sync
    </a>
  </div>
);

// ─────────────────────────────────────────────────────────────
// PrefixSetting
// ─────────────────────────────────────────────────────────────

const PrefixSetting = ({ currentPrefix, onSave, saving }) => {
  const [prefix, setPrefix] = useState(currentPrefix);
  const [editing, setEditing] = useState(false);

  const handleSave = async () => {
    if (prefix.trim() && prefix !== currentPrefix) { await onSave(prefix.trim()); setEditing(false); }
  };

  if (!editing) return (
    <div>
      <div className="setting-preview">
        <span className="setting-value">{currentPrefix}</span>
        <button className="setting-change-btn" onClick={() => setEditing(true)}>Change</button>
      </div>
      <p className="setting-note">Current prefix: <code style={{ color: '#aa00ff' }}>{currentPrefix}</code></p>
    </div>
  );

  return (
    <div>
      <div style={{ marginBottom: '12px' }}>
        <input type="text" value={prefix} onChange={(e) => setPrefix(e.target.value)}
          maxLength={10} placeholder="Enter new prefix (max 10 chars)" className="setting-input" />
      </div>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
        <button className="button-cancel" onClick={() => { setPrefix(currentPrefix); setEditing(false); }}>Cancel</button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// TimezoneSetting
// ─────────────────────────────────────────────────────────────

const TimezoneSetting = ({ currentTimezone, onSave, saving }) => {
  const [selectedTimezone, setSelectedTimezone] = useState(currentTimezone);
  const [editing, setEditing] = useState(false);

  const timezones = [
    { value: 'UTC',  label: '🌍 UTC (GMT+0)'    }, { value: 'EST',  label: '🗽 EST (GMT-5)'    },
    { value: 'PST',  label: '🌴 PST (GMT-8)'    }, { value: 'CST',  label: '🌾 CST (GMT-6)'    },
    { value: 'MST',  label: '⛰️ MST (GMT-7)'    }, { value: 'GMT',  label: '🇬🇧 GMT (GMT+0)'   },
    { value: 'CET',  label: '🇪🇺 CET (GMT+1)'   }, { value: 'EET',  label: '🌅 EET (GMT+2)'    },
    { value: 'IST',  label: '🇮🇳 IST (GMT+5:30)' }, { value: 'JST',  label: '🇯🇵 JST (GMT+9)'   },
    { value: 'AEST', label: '🇦🇺 AEST (GMT+10)'  }, { value: 'NZST', label: '🇳🇿 NZST (GMT+12)' },
  ];

  const handleSave = async () => {
    if (selectedTimezone !== currentTimezone) { await onSave(selectedTimezone); setEditing(false); }
  };

  if (!editing) {
    const current = timezones.find(tz => tz.value === currentTimezone) || timezones[0];
    return (
      <div>
        <div className="setting-preview">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span>{current.label.split(' ')[0]}</span>
            <span className="setting-value">{currentTimezone}</span>
          </div>
          <button className="setting-change-btn" onClick={() => setEditing(true)}>Change</button>
        </div>
        <p className="setting-note">Current timezone: <strong style={{ color: '#aa00ff' }}>{currentTimezone}</strong></p>
      </div>
    );
  }

  return (
    <div>
      <select value={selectedTimezone} onChange={(e) => setSelectedTimezone(e.target.value)}
        style={{ width: '100%', backgroundColor: '#1a1a1a', border: '1px solid #aa00ff', borderRadius: '10px', padding: '12px', color: '#fff', fontSize: '14px', marginBottom: '12px', cursor: 'pointer', outline: 'none' }}>
        {timezones.map(tz => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
      </select>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
        <button className="button-cancel" onClick={() => { setSelectedTimezone(currentTimezone); setEditing(false); }}>Cancel</button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// VoiceStatesSetting
// ─────────────────────────────────────────────────────────────

const VoiceStatesSetting = ({ currentStates, onSave, saving }) => {
  const [selectedStates, setSelectedStates] = useState(currentStates || []);
  const [editing, setEditing] = useState(false);

  const voiceStateOptions = [
    { value: 'afk',           Icon: MouseOff,      label: 'AFK',           description: 'User is in AFK channel' },
    { value: 'self_mute',     Icon: MicOff,        label: 'Self mute',     description: 'User muted themselves' },
    { value: 'self_deafen',   Icon: HeadphoneOff,  label: 'Self deafen',   description: 'User deafened themselves' },
    { value: 'server_mute',   Icon: VolumeX,       label: 'Server mute',   description: 'User was muted by moderation' },
    { value: 'server_deafen', Icon: EarOff,        label: 'Server deafen', description: 'User was deafened by moderation' },
    { value: 'streaming',     Icon: TvMinimalPlay, label: 'Streaming',     description: 'User is streaming' },
    { value: 'video',         Icon: Video,         label: 'Video',         description: 'User has video open' },
    { value: 'suppressed',    Icon: CircleOff,     label: 'Suppressed',    description: 'Stage audience member' },
  ];

  const handleToggle = (val) =>
    setSelectedStates(prev => prev.includes(val) ? prev.filter(s => s !== val) : [...prev, val]);

  const handleSave = async () => {
    if (JSON.stringify(selectedStates.sort()) !== JSON.stringify((currentStates || []).sort())) {
      await onSave(selectedStates); setEditing(false);
    }
  };

  if (!editing) {
    const selectedCount = (currentStates || []).length;
    return (
      <div>
        <div className="setting-preview" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <span className="setting-value">{selectedCount} state{selectedCount !== 1 ? 's' : ''} tracked</span>
            {selectedCount > 0 ? (
              <div className="tracked-pill-row">
                {currentStates.map(state => {
                  const opt = voiceStateOptions.find(o => o.value === state);
                  return opt ? (
                    <span key={state} className="tracked-pill">
                      <opt.Icon size={12} color="#aa00ff" /> {opt.label}
                    </span>
                  ) : null;
                })}
              </div>
            ) : (
              <div className="tracked-pill-row"><span className="tracked-pill-empty">No voice states tracked</span></div>
            )}
          </div>
          <button className="setting-change-btn" onClick={() => setEditing(true)}>Configure</button>
        </div>
        <p className="setting-note">Voice states determine which voice activities are tracked</p>
      </div>
    );
  }

  return (
    <div>
      <div className="voice-states-grid">
        {voiceStateOptions.map(({ value, Icon, label, description }) => {
          const isSelected = selectedStates.includes(value);
          return (
            <div key={value} className={`voice-state-option ${isSelected ? 'selected' : ''}`} onClick={() => handleToggle(value)}>
              <div className="voice-state-info">
                <div className="voice-state-icon">
                  <Icon size={16} color={isSelected ? ACCENT : '#666'} />
                </div>
                <div>
                  <div className="voice-state-label">{label}</div>
                  <div className="voice-state-desc">{description}</div>
                </div>
              </div>
              <div className={`voice-state-checkbox ${isSelected ? 'selected' : ''}`}>
                {isSelected && <span style={{ color: '#fff', fontSize: '12px', fontWeight: 'bold' }}>✓</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save changes'}</button>
        <button className="button-cancel" onClick={() => { setSelectedStates(currentStates || []); setEditing(false); }}>Cancel</button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// StatTypesSetting — enable/disable which stat types are tracked
// ─────────────────────────────────────────────────────────────

const STAT_TYPE_OPTIONS = [
  { key: 'track_messages',        Icon: MessageCircle,         label: 'Messages' },
  { key: 'track_voice',           Icon: Volume2,                label: 'Voice activity' },
  { key: 'track_invites',         Icon: UserPlus,               label: 'Invites' },
  { key: 'track_emojis',          Icon: Smile,                  label: 'Emojis' },
  { key: 'track_status_activity', Icon: Gamepad2,                label: 'Status activity' },
  { key: 'track_mentions',        Icon: AtSign,                  label: 'Mentions' },
  { key: 'track_member_growth',   Icon: ChartColumnIncreasing,   label: 'Member growth' },
  { key: 'track_role_growth',     Icon: ChartNoAxesCombined,     label: 'Role growth' },
];

const StatTypesSetting = ({ guildId, showToast }) => {
  const [toggles, setToggles] = useState(null);
  const [selectedKeys, setSelectedKeys] = useState([]);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  const loadToggles = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/stat-toggles?guild_id=${guildId}`, {
        credentials: 'include', headers: { 'Accept': 'application/json' }
      });
      if (res.ok) {
        const data = await res.json();
        setToggles(data);
        setSelectedKeys(STAT_TYPE_OPTIONS.filter(o => data[o.key]).map(o => o.key));
      }
    } catch {
      showToast && showToast('Error loading stat type toggles', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (guildId) loadToggles(); }, [guildId]);

  const handleToggle = (key) =>
    setSelectedKeys(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      STAT_TYPE_OPTIONS.forEach(o => { payload[o.key] = selectedKeys.includes(o.key); });

      const res = await fetch(`${API_BASE_URL}/api/settings/stat-toggles/set-bulk`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ guild_id: guildId, toggles: payload })
      });
      const result = await res.json();
      if (res.ok && result.success) {
        setToggles(result.toggles);
        showToast && showToast('Updated stat type toggles', 'success');
        setEditing(false);
      } else {
        showToast && showToast(result.detail || 'Failed to update stat toggles', 'error');
      }
    } catch {
      showToast && showToast('Error updating stat toggles', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/stat-toggles/reset`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ guild_id: guildId })
      });
      const result = await res.json();
      if (res.ok && result.success) {
        setToggles(result.toggles);
        setSelectedKeys(STAT_TYPE_OPTIONS.filter(o => result.toggles[o.key]).map(o => o.key));
        showToast && showToast('Reverted stat types to default', 'success');
        setEditing(false);
      } else {
        showToast && showToast(result.detail || 'Failed to reset stat toggles', 'error');
      }
    } catch {
      showToast && showToast('Error resetting stat toggles', 'error');
    } finally {
      setResetting(false);
    }
  };

  const handleCancel = () => {
    if (toggles) setSelectedKeys(STAT_TYPE_OPTIONS.filter(o => toggles[o.key]).map(o => o.key));
    setEditing(false);
  };

  if (loading || !toggles) {
    return <LoadingSpinner size="small" text="Loading stat types..." />;
  }

  if (!editing) {
    const enabledOptions = STAT_TYPE_OPTIONS.filter(o => toggles[o.key]);
    return (
      <div>
        <div className="setting-preview" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <span className="setting-value">{enabledOptions.length} of {STAT_TYPE_OPTIONS.length} tracked</span>
            {enabledOptions.length > 0 ? (
              <div className="tracked-pill-row">
                {enabledOptions.map(({ key, Icon, label }) => (
                  <span key={key} className="tracked-pill">
                    <Icon size={12} color="#aa00ff" /> {label}
                  </span>
                ))}
              </div>
            ) : (
              <div className="tracked-pill-row"><span className="tracked-pill-empty">No stat types tracked</span></div>
            )}
          </div>
          <button className="setting-change-btn" onClick={() => setEditing(true)}>Configure</button>
        </div>
        <div className="button-group">
          <button className="button-reset" onClick={handleReset} disabled={resetting}>
            <RotateCcw size={13} /> {resetting ? 'Reverting...' : 'Revert to default'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="voice-states-grid">
        {STAT_TYPE_OPTIONS.map(({ key, Icon, label }) => {
          const isSelected = selectedKeys.includes(key);
          return (
            <div key={key} className={`voice-state-option ${isSelected ? 'selected' : ''}`} onClick={() => handleToggle(key)}>
              <div className="voice-state-info">
                <div className="voice-state-icon">
                  <Icon size={16} color={isSelected ? ACCENT : '#666'} />
                </div>
                <div className="voice-state-label" style={{ marginBottom: 0 }}>{label}</div>
              </div>
              <div className={`voice-state-checkbox ${isSelected ? 'selected' : ''}`}>
                {isSelected && <span style={{ color: '#fff', fontSize: '12px', fontWeight: 'bold' }}>✓</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save changes'}</button>
        <button className="button-cancel" onClick={handleCancel}>Cancel</button>
        <button className="button-reset" onClick={handleReset} disabled={resetting}>
          <RotateCcw size={13} /> {resetting ? 'Reverting...' : 'Revert to default'}
        </button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// BotFilterSetting
// ─────────────────────────────────────────────────────────────

const BotFilterSetting = ({ enabled, onSave, saving }) => (
  <div>
    <div className="bot-filter-container">
      <div>
        <div className="bot-filter-text">{enabled ? 'Filtering bots' : 'Including bots'}</div>
        <div className="bot-filter-desc">
          {enabled ? 'Bots are currently filtered out from statistics' : 'Bots are currently included in statistics'}
        </div>
      </div>
      <button className={`bot-filter-button ${enabled ? 'filtering' : 'including'}`}
        onClick={() => onSave(!enabled)} disabled={saving}>
        {saving ? 'Updating...' : enabled ? 'Include bots' : 'Filter bots'}
      </button>
    </div>
  </div>
);

// ─────────────────────────────────────────────────────────────
// PermissionLevelSetting
// ─────────────────────────────────────────────────────────────

const PermissionLevelSetting = ({ currentLevel, onSave, saving }) => {
  const [selectedLevel, setSelectedLevel] = useState(currentLevel);

  const permissionLevels = [
    { value: 'All',              Icon: Globe,    label: 'All' },
    { value: 'Default',          Icon: Cog,      label: 'Default' },
    { value: 'User Restriction', Icon: UserCog,  label: 'User restriction' },
    { value: 'Moderator',        Icon: ShieldUser, label: 'Moderator' },
    { value: 'Admin',            Icon: Crown,    label: 'Admin' },
  ];

  return (
    <div>
      <div className="option-boxes">
        {permissionLevels.map(({ value, Icon, label }) => (
          <div key={value} className={`option-box ${selectedLevel === value ? 'selected' : ''}`}
            onClick={() => setSelectedLevel(value)}>
            <Icon size={24} color={selectedLevel === value ? ACCENT : '#666'} />
            <div className="option-box-name">{label}</div>
          </div>
        ))}
      </div>
      {selectedLevel !== currentLevel && (
        <div className="button-group" style={{ marginTop: '16px' }}>
          <button className="button-save" onClick={() => onSave(selectedLevel)} disabled={saving}>
            {saving ? 'Saving...' : 'Apply changes'}
          </button>
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// DashboardAccessSetting
// ─────────────────────────────────────────────────────────────

const DashboardAccessSetting = ({ currentLevel, onSave, saving }) => {
  const [selectedLevel, setSelectedLevel] = useState(currentLevel);

  const accessLevels = [
    { value: 'Public',    Icon: Globe,      label: 'Public' },
    { value: 'Member',    Icon: User,       label: 'Member' },
    { value: 'Moderator', Icon: ShieldUser, label: 'Moderator' },
    { value: 'Admin',     Icon: Crown,      label: 'Admin' },
  ];

  return (
    <div>
      <div className="option-boxes">
        {accessLevels.map(({ value, Icon, label }) => (
          <div key={value} className={`option-box ${selectedLevel === value ? 'selected' : ''}`}
            onClick={() => setSelectedLevel(value)}>
            <Icon size={24} color={selectedLevel === value ? ACCENT : '#666'} />
            <div className="option-box-name">{label}</div>
          </div>
        ))}
      </div>
      {selectedLevel !== currentLevel && (
        <div className="button-group" style={{ marginTop: '16px' }}>
          <button className="button-save" onClick={() => onSave(selectedLevel)} disabled={saving}>
            {saving ? 'Saving...' : 'Apply changes'}
          </button>
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// SimpleCalendar
// ─────────────────────────────────────────────────────────────

const SimpleCalendar = ({ onSelectDate, currentDate, onClose }) => {
  const [currentMonth, setCurrentMonth] = useState(currentDate ? new Date(currentDate) : new Date());
  const getDaysInMonth = (d) => new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  const getFirstDay = (d) => new Date(d.getFullYear(), d.getMonth(), 1).getDay();
  const changeMonth = (delta) => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1));
  const daysInMonth = getDaysInMonth(currentMonth);
  const firstDay = getFirstDay(currentMonth);
  const days = [];
  let startOffset = firstDay === 0 ? 6 : firstDay - 1;
  for (let i = 0; i < startOffset; i++) days.push(<div key={`e-${i}`} style={{ padding: '8px' }} />);
  for (let i = 1; i <= daysInMonth; i++) {
    const isSel = currentDate && currentDate.getDate() === i && currentDate.getMonth() === currentMonth.getMonth() && currentDate.getFullYear() === currentMonth.getFullYear();
    days.push(
      <div key={i} onClick={() => { onSelectDate(new Date(currentMonth.getFullYear(), currentMonth.getMonth(), i)); onClose(); }}
        style={{ padding: '8px', textAlign: 'center', cursor: 'pointer', borderRadius: '6px', backgroundColor: isSel ? '#aa00ff' : 'transparent', color: isSel ? '#fff' : '#e0e0e0', transition: 'all 0.2s' }}
        onMouseEnter={(e) => { if (!isSel) e.target.style.backgroundColor = '#2a2a2a'; }}
        onMouseLeave={(e) => { if (!isSel) e.target.style.backgroundColor = 'transparent'; }}>
        {i}
      </div>
    );
  }
  const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  return (
    <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: '8px', backgroundColor: '#1a1a1a', border: '1px solid #aa00ff', borderRadius: '12px', padding: '16px', zIndex: 1000, boxShadow: '0 4px 20px rgba(0,0,0,0.3)', minWidth: '280px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <button onClick={() => changeMonth(-1)} style={{ background: 'none', border: 'none', color: '#aa00ff', cursor: 'pointer', fontSize: '18px', padding: '4px 8px' }}>◀</button>
        <span style={{ color: '#fff', fontWeight: 'bold' }}>{monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}</span>
        <button onClick={() => changeMonth(1)} style={{ background: 'none', border: 'none', color: '#aa00ff', cursor: 'pointer', fontSize: '18px', padding: '4px 8px' }}>▶</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px', marginBottom: '8px' }}>
        {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => (
          <div key={d} style={{ textAlign: 'center', color: '#888', fontSize: '12px', padding: '4px' }}>{d}</div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px' }}>{days}</div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// TimePeriodSetting
// ─────────────────────────────────────────────────────────────

const TimePeriodSetting = ({ settings, onSave, saving }) => {
  const [editing, setEditing] = useState(false);
  const [timeMode, setTimeMode] = useState(settings.default_time_mode || 'all_time');
  const [daysBack, setDaysBack] = useState(settings.default_days_back || 7);
  const [fromDate, setFromDate] = useState(settings.default_from_date ? new Date(settings.default_from_date) : null);
  const [toDate, setToDate]     = useState(settings.default_to_date   ? new Date(settings.default_to_date)   : null);
  const [rollingType, setRollingType]   = useState(settings.default_rolling_type  || 'weekday');
  const [rollingValue, setRollingValue] = useState(settings.default_rolling_value || 0);
  const [showFromCal, setShowFromCal] = useState(false);
  const [showToCal, setShowToCal]     = useState(false);
  const [validationError, setValidationError] = useState(null);

  const fmtDate = (d) => d ? `${String(d.getDate()).padStart(2,'0')}-${String(d.getMonth()+1).padStart(2,'0')}-${d.getFullYear()}` : '';
  const parseDate = (s) => { if (!s) return null; const p = s.split('-'); return p.length === 3 ? new Date(p[2], p[1]-1, p[0]) : null; };

  const getPreviewText = () => {
    const m = settings.default_time_mode || 'all_time';
    if (m === 'all_time') return 'All time';
    if (m === 'days_back') return `Last ${settings.default_days_back || 7} days`;
    if (m === 'date_range') {
      const from = settings.default_from_date ? fmtDate(new Date(settings.default_from_date)) : 'Start';
      const to   = settings.default_to_date   ? fmtDate(new Date(settings.default_to_date))   : 'End';
      return `${from} to ${to}`;
    }
    if (m === 'rolling_window') {
      if (settings.default_rolling_type === 'weekday') {
        const days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
        return `Rolling — every ${days[settings.default_rolling_value || 0]}`;
      }
      const n = settings.default_rolling_value || 1;
      const ord = n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : `${n}th`;
      return `Rolling — ${ord} of each month`;
    }
    return 'All time';
  };

  const validate = () => {
    if (timeMode === 'days_back' && (!daysBack || daysBack < 1 || daysBack > 3650)) { setValidationError('Days back must be between 1 and 3650'); return false; }
    if (timeMode === 'date_range') {
      if (!fromDate && !toDate) { setValidationError('At least one date must be provided'); return false; }
      if (fromDate && toDate && fromDate >= toDate) { setValidationError('From date must be before to date'); return false; }
    }
    if (timeMode === 'rolling_window') {
      if (rollingType === 'weekday' && (rollingValue < 0 || rollingValue > 6)) { setValidationError('Invalid weekday'); return false; }
      if (rollingType === 'monthly' && (!rollingValue || rollingValue < 1 || rollingValue > 31)) { setValidationError('Day of month must be 1–31'); return false; }
    }
    setValidationError(null); return true;
  };

  const handleSave = async () => {
    if (!validate()) return;
    await onSave({
      default_time_mode: timeMode,
      default_days_back: timeMode === 'days_back' ? daysBack : null,
      default_from_date: fromDate ? fromDate.toISOString() : null,
      default_to_date:   toDate   ? toDate.toISOString()   : null,
      default_rolling_type:  timeMode === 'rolling_window' ? rollingType  : null,
      default_rolling_value: timeMode === 'rolling_window' ? rollingValue : null,
    });
    setEditing(false);
  };

  const handleCancel = () => {
    setTimeMode(settings.default_time_mode || 'all_time');
    setDaysBack(settings.default_days_back || 7);
    setFromDate(settings.default_from_date ? new Date(settings.default_from_date) : null);
    setToDate(settings.default_to_date     ? new Date(settings.default_to_date)   : null);
    setRollingType(settings.default_rolling_type   || 'weekday');
    setRollingValue(settings.default_rolling_value || 0);
    setValidationError(null); setEditing(false);
  };

  const timeModes = [
    { value: 'all_time',       Icon: Clock,    label: 'All time'       },
    { value: 'days_back',      Icon: Clock,    label: 'Days back'      },
    { value: 'date_range',     Icon: Clock,    label: 'Date range'     },
    { value: 'rolling_window', Icon: Clock,    label: 'Rolling window' },
  ];

  if (!editing) return (
    <div>
      <div className="setting-preview">
        <span className="setting-value">{getPreviewText()}</span>
        <button className="setting-change-btn" onClick={() => setEditing(true)}>Change</button>
      </div>
      <p className="setting-note">Default time period used across bot commands and dashboard</p>
    </div>
  );

  return (
    <div>
      <div className="option-boxes" style={{ marginBottom: '20px' }}>
        {[
          { value: 'all_time',       label: 'All time'       },
          { value: 'days_back',      label: 'Days back'      },
          { value: 'date_range',     label: 'Date range'     },
          { value: 'rolling_window', label: 'Rolling window' },
        ].map(mode => (
          <div key={mode.value} className={`option-box ${timeMode === mode.value ? 'selected' : ''}`}
            onClick={() => setTimeMode(mode.value)}>
            <Clock size={22} color={timeMode === mode.value ? ACCENT : '#666'} />
            <div className="option-box-name">{mode.label}</div>
          </div>
        ))}
      </div>

      {timeMode === 'all_time' && (
        <div style={{ marginBottom: '16px', padding: '12px', backgroundColor: '#1a1a1a', borderRadius: '8px' }}>
          <span style={{ color: '#888', fontSize: '13px' }}>No time filter — all historical data will be used.</span>
        </div>
      )}

      {timeMode === 'days_back' && (
        <div style={{ marginBottom: '16px' }}>
          <input type="number" value={daysBack} onChange={(e) => setDaysBack(parseInt(e.target.value))}
            min="1" max="3650" className="setting-input" placeholder="Number of days (1-3650)" />
          {validationError && <div style={{ color: '#ff7675', fontSize: '12px', marginTop: '8px' }}>{validationError}</div>}
        </div>
      )}

      {timeMode === 'date_range' && (
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
            {[
              { label: 'From date (optional)', date: fromDate, setDate: setFromDate, show: showFromCal, setShow: setShowFromCal },
              { label: 'To date (optional)',   date: toDate,   setDate: setToDate,   show: showToCal,   setShow: setShowToCal   },
            ].map(({ label, date, setDate, show, setShow }) => (
              <div key={label} style={{ flex: 1, position: 'relative' }}>
                <div style={{ marginBottom: '4px', color: '#888', fontSize: '12px' }}>{label}</div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input type="text" value={date ? fmtDate(date) : ''} onChange={(e) => setDate(parseDate(e.target.value))}
                    placeholder="DD-MM-YYYY" className="setting-input" style={{ flex: 1 }} />
                  <button onClick={() => setShow(!show)} style={{ backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: '10px', padding: '0 12px', cursor: 'pointer', fontSize: '20px' }}>📅</button>
                </div>
                {show && <SimpleCalendar onSelectDate={(d) => { setDate(d); setShow(false); }} currentDate={date} onClose={() => setShow(false)} />}
                <div style={{ color: '#666', fontSize: '11px', marginTop: '4px' }}>Leave empty for open end</div>
              </div>
            ))}
          </div>
          {validationError && <div style={{ color: '#ff7675', fontSize: '12px', marginTop: '8px' }}>{validationError}</div>}
        </div>
      )}

      {timeMode === 'rolling_window' && (
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
            {['weekday', 'monthly'].map(type => (
              <div key={type} onClick={() => setRollingType(type)}
                style={{ flex: 1, padding: '10px', textAlign: 'center', cursor: 'pointer', backgroundColor: rollingType === type ? '#2a2a2a' : '#1a1a1a', border: `2px solid ${rollingType === type ? '#aa00ff' : '#2a2a2a'}`, borderRadius: '8px', fontWeight: rollingType === type ? 'bold' : 'normal', color: '#fff' }}>
                {type === 'weekday' ? 'Day of week' : 'Day of month'}
              </div>
            ))}
          </div>
          {rollingType === 'weekday' ? (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
              {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day, idx) => (
                <div key={day} onClick={() => setRollingValue(idx)}
                  style={{ padding: '8px 12px', cursor: 'pointer', fontSize: '13px', borderRadius: '8px', backgroundColor: rollingValue === idx ? '#aa00ff' : '#1a1a1a', border: `1px solid ${rollingValue === idx ? '#aa00ff' : '#2a2a2a'}`, color: rollingValue === idx ? '#fff' : '#e0e0e0', transition: 'all 0.2s' }}>
                  {day}
                </div>
              ))}
            </div>
          ) : (
            <div>
              <input type="number" value={rollingValue} onChange={(e) => setRollingValue(parseInt(e.target.value))}
                min="1" max="31" className="setting-input" placeholder="Day of month (1-31)" />
              {validationError && <div style={{ color: '#ff7675', fontSize: '12px', marginTop: '8px' }}>{validationError}</div>}
            </div>
          )}
        </div>
      )}

      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save changes'}</button>
        <button className="button-cancel" onClick={handleCancel}>Cancel</button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Access denied
// ─────────────────────────────────────────────────────────────

const AccessDenied = ({ accessLevel }) => {
  let required = "Administrator";
  if (accessLevel === 'Member' || accessLevel === 'Moderator') required = "Manage Server or Administrator";
  return (
    <div className="dashboard-content">
      <div className="error-message-container">
        <div className="error-icon">🔒</div>
        <h2 className="error-title">Access denied</h2>
        <p className="error-message">This server requires <strong>{required}</strong> permission to view settings.</p>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Root page component
// ─────────────────────────────────────────────────────────────

const SettingsDashboard = () => {
  const [currentServer, setCurrentServer]     = useState(null);
  const [loading, setLoading]                 = useState(true);
  const [loadingServers, setLoadingServers]   = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess]             = useState(null);
  const [settings, setSettings]               = useState(null);
  const [apiError, setApiError]               = useState(null);
  const [toast, setToast]                     = useState(null);
  const [accessLevel, setAccessLevel]         = useState('Member');
  const [currentUserId, setCurrentUserId]     = useState(null);
  const [saving, setSaving] = useState({
    prefix: false, timezone: false, voiceStates: false, botFilter: false,
    permissionLevel: false, dashboardAccess: false, timePeriod: false,
  });

  const isPrivilegedUser = (userId) => PRIVILEGED_USERS.includes(userId);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const ToastMessage = () => {
    if (!toast) return null;
    const colors = { success: { bg: '#00b894', icon: '✅' }, error: { bg: '#ff7675', icon: '❌' }, info: { bg: '#0984e3', icon: 'ℹ️' } };
    const color = colors[toast.type] || colors.info;
    return (
      <div className="toast-message" style={{ backgroundColor: color.bg }}>
        <span>{color.icon}</span>
        <span>{toast.message}</span>
        <button onClick={() => setToast(null)} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', marginLeft: '10px', fontSize: '16px' }}>✕</button>
      </div>
    );
  };

  useEffect(() => { loadInitialData(); }, []);

  const loadInitialData = async () => {
    setLoadingServers(true); setApiError(null); setHasAccess(null);
    try {
      const authRes = await fetch(`${API_BASE_URL}/api/auth/status`, { credentials: 'include', headers: { 'Accept': 'application/json' } });
      if (!authRes.ok) throw new Error('Auth failed');
      const authData = await authRes.json();

      if (authData.authenticated && authData.user) {
        setIsAuthenticated(true);
        setCurrentUserId(authData.user.id);
        if (isPrivilegedUser(authData.user.id)) { setHasAccess(true); setAccessLevel('Admin'); window.accessLevel = 'Admin'; }

        const srvRes = await fetch(`${API_BASE_URL}/api/user/servers`, { credentials: 'include', headers: { 'Accept': 'application/json' } });
        if (srvRes.ok) {
          const servers = await srvRes.json();
          if (Array.isArray(servers) && servers.length > 0) {
            let sel = authData.user.selected_server ? servers.find(s => s.id === authData.user.selected_server) : null;
            if (!sel) sel = servers[0];
            if (sel) {
              setCurrentServer(sel);
              if (!isPrivilegedUser(authData.user.id)) {
                await checkAndLoadSettings(sel.id, sel.permissions, sel.has_admin, sel.has_manage_server);
              } else {
                await loadSettingsOnly(sel.id);
              }
            } else { setLoading(false); }
          } else { setLoading(false); }
        } else { setLoading(false); }
      } else { setLoading(false); }
    } catch {
      setApiError('Failed to load servers. Please check your connection.');
      setLoading(false);
    } finally { setLoadingServers(false); }
  };

  const loadSettingsOnly = async (guildId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/get`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ guild_id: guildId }) });
      if (res.ok) { const d = await res.json(); setSettings(d); setAccessLevel(d.dashboard_access_level || 'Member'); }
      else showToast('Failed to load settings', 'error');
    } catch { showToast('Error loading settings', 'error'); }
    finally { setLoading(false); }
  };

  const checkAndLoadSettings = async (guildId, permissions, hasAdmin, hasManageServer) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/get`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ guild_id: guildId }) });
      if (res.ok) {
        const d = await res.json(); setSettings(d);
        const lvl = d.dashboard_access_level || 'Member'; setAccessLevel(lvl);
        let access = false;
        if (lvl === 'Public') access = true;
        else if (lvl === 'Member' || lvl === 'Moderator') access = hasAdmin || hasManageServer;
        else access = hasAdmin;
        setHasAccess(access);
      } else { showToast('Failed to load settings', 'error'); setHasAccess(false); }
    } catch { showToast('Error loading settings', 'error'); setHasAccess(false); }
    finally { setLoading(false); }
  };

  const settingDisplayNames = {
    prefix: 'Prefix', timezone: 'Timezone', voice_states: 'Voice States',
    bot_filter: 'Bot Filter', permission_level: 'Command Permission Access Level',
    dashboard_access_level: 'Dashboard Access Level',
  };

  const updateSetting = async (setting, value) => {
    if (!currentServer) return false;
    setSaving(prev => ({ ...prev, [setting]: true }));
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/update`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ guild_id: currentServer.id, setting, value }) });
      const result = await res.json();
      if (result.success) { setSettings(prev => ({ ...prev, [setting]: value })); showToast(`Updated ${settingDisplayNames[setting] || setting}`, 'success'); return true; }
      else { showToast(result.message || 'Failed to update setting', 'error'); return false; }
    } catch { showToast(`Error updating ${settingDisplayNames[setting] || setting}`, 'error'); return false; }
    finally { setSaving(prev => ({ ...prev, [setting]: false })); }
  };

  const updateTimePeriod = async (data) => {
    if (!currentServer) return false;
    setSaving(prev => ({ ...prev, timePeriod: true }));
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/time-period/update`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ guild_id: currentServer.id, ...data }) });
      const result = await res.json();
      if (result.success) { setSettings(prev => ({ ...prev, ...data })); showToast('Updated default time period', 'success'); return true; }
      else { showToast(result.message || 'Failed to update time period', 'error'); return false; }
    } catch { showToast('Error updating time period', 'error'); return false; }
    finally { setSaving(prev => ({ ...prev, timePeriod: false })); }
  };

  // ── render guards ─────────────────────────────────────────
  if (loadingServers || (isAuthenticated && !currentServer && !apiError)) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="loading-container"><LoadingSpinner text="Loading servers..." /></div>
      </div><Footer /></main></div><style>{styles}</style></>);
  }

  if (hasAccess === null && isAuthenticated && currentServer && !isPrivilegedUser(currentUserId)) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="loading-container"><LoadingSpinner text="Checking permissions..." /></div>
      </div><Footer /></main></div><style>{styles}</style></>);
  }

  if (!isAuthenticated) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="no-server"><h2>Please log in</h2><p>You need to be logged in to configure settings.</p>
          <a href={`${API_BASE_URL}/api/auth/discord`} className="login-button">Login with Discord</a>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (!currentServer) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="no-server"><h2>No server available</h2><p>Add the bot to a Discord server to configure settings.</p>
          <a href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands"
            className="invite-button" target="_blank" rel="noopener noreferrer">Invite bot to server</a>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (apiError) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="error-message-container"><div className="error-icon">⚠️</div>
          <h2 className="error-title">Error loading data</h2>
          <p className="error-message">{apiError}</p>
          <button onClick={() => window.location.reload()} className="invite-button">Retry</button>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        <main className="dashboard-main">
          <div className="dashboard-content">
            {hasAccess ? (
              <>
                {settings ? (
                  <div className="settings-grid">

                    {/* 1 — Prefix */}
                    <SettingsCard title="Prefix" icon={<ALargeSmall size={22} color={ACCENT} />}
                      description="Change the bot's command prefix">
                      <PrefixSetting currentPrefix={settings.prefix}
                        onSave={(v) => updateSetting('prefix', v)} saving={saving.prefix} />
                    </SettingsCard>

                    {/* 2 — Bot Filter */}
                    <SettingsCard title="Bot Filter" icon={<Bot size={22} color={ACCENT} />}
                      description="Filter bots from statistics">
                      <BotFilterSetting enabled={settings.bot_filter}
                        onSave={(v) => updateSetting('bot_filter', v)} saving={saving.botFilter} />
                    </SettingsCard>

                    {/* 3 — Timezone */}
                    <SettingsCard title="Timezone" icon={<Earth size={22} color={ACCENT} />}
                      description="Set the timezone for time-based statistics">
                      <TimezoneSetting currentTimezone={settings.timezone}
                        onSave={(v) => updateSetting('timezone', v)} saving={saving.timezone} />
                    </SettingsCard>

                    {/* 4 — Default Time Period */}
                    <SettingsCard title="Default Time Period" icon={<Clock size={22} color={ACCENT} />}
                      description="Set the default time period used across bot commands and the dashboard"
                      infoDescriptions={[
                        { level: 'All time',       description: 'No time filter — all historical data is used' },
                        { level: 'Days back',       description: 'Show data from the last X days (1–3650 days)' },
                        { level: 'Date range',      description: 'Show data between specific dates (open-ended allowed)' },
                        { level: 'Rolling window',  description: 'Show data for a specific recurring day (weekly or monthly)' },
                      ]}>
                      <TimePeriodSetting settings={settings}
                        onSave={(data) => updateTimePeriod(data)} saving={saving.timePeriod} />
                    </SettingsCard>

                    {/* 5 — Stat Type Toggle */}
                    <SettingsCard title="Stat Type Toggle" icon={<ToggleRight size={22} color={ACCENT} />}
                      description="Choose which stat types the bot actively tracks on this server"
                      infoDescriptions={[
                        { level: 'How it works', description: 'These are the stat types tracked by the bot. Enable or disable any of them — disabling a type stops new data being collected for it, but existing data is kept.' },
                      ]}>
                      <StatTypesSetting guildId={currentServer.id} showToast={showToast} />
                    </SettingsCard>

                    {/* 6 — Voice States */}
                    <SettingsCard title="Voice States" icon={<Volume2 size={22} color={ACCENT} />}
                      description="Choose which voice states to track"
                      infoDescriptions={[
                        { level: 'Your choice',     description: 'Whichever states you select below are the ones the bot will track and log stats for. Anything left unchecked is ignored entirely.' },
                        { level: 'AFK',             description: 'User is sitting in the AFK channel' },
                        { level: 'Self mute',       description: 'User muted their own mic' },
                        { level: 'Self deafen',     description: 'User deafened themselves' },
                        { level: 'Server mute',     description: 'A moderator muted the user' },
                        { level: 'Server deafen',   description: 'A moderator deafened the user' },
                        { level: 'Streaming',       description: 'User is screen sharing / streaming' },
                        { level: 'Video',           description: 'User has their camera on' },
                        { level: 'Suppressed',      description: 'User is a stage audience member without speaker permission' },
                      ]}>
                      <VoiceStatesSetting currentStates={settings.voice_states}
                        onSave={(v) => updateSetting('voice_states', v)} saving={saving.voiceStates} />
                    </SettingsCard>

                    {/* 7 — Command Permission Access Level */}
                    <SettingsCard
                      title="Command Permission Access Level" icon={<UserRoundKey size={22} color={ACCENT} />}
                      description="Control who can use bot commands"
                      infoDescriptions={[
                        { level: 'All',              description: 'All members regardless of their permissions are allowed to use any command on the bot including sensitive commands like reset and blacklist.' },
                        { level: 'Default',          description: 'All commands are usable by normal members except blacklist and settings (Manage Server) and reset commands (Administrator).' },
                        { level: 'User restriction', description: 'Mostly the same as Default except users can only use commands that have the user scope on their own account only.' },
                        { level: 'Moderator',        description: 'Only users with the Manage Server permission can use any commands on the bot.' },
                        { level: 'Admin',            description: 'Only users with the Administrator permission can use any commands on the bot.' },
                      ]}>
                      <PermissionLevelSetting currentLevel={settings.permission_level}
                        onSave={(v) => updateSetting('permission_level', v)} saving={saving.permissionLevel} />
                    </SettingsCard>

                    {/* 8 — Dashboard Access Level */}
                    <SettingsCard
                      title="Dashboard Access Level" icon={<LayoutDashboard size={22} color={ACCENT} />}
                      description="Control who can view the web dashboard"
                      infoDescriptions={[
                        { level: 'Public',    description: 'Any member of the server can view the entire dashboard including the optimization section.' },
                        { level: 'Member',    description: 'Members can view analytics but need Manage Server or Administrator to access the optimization section.' },
                        { level: 'Moderator', description: 'Manage Server or Administrator required to view any section of the dashboard.' },
                        { level: 'Admin',     description: 'Administrator permission required to view any section of the dashboard.' },
                      ]}>
                      <DashboardAccessSetting currentLevel={settings.dashboard_access_level || 'Member'}
                        onSave={(v) => updateSetting('dashboard_access_level', v)} saving={saving.dashboardAccess} />
                    </SettingsCard>

                    {/* 9 — History Data Sync */}
                    <SettingsCard
                      title="History Data Sync" icon={<History size={22} color={ACCENT} />}
                      description="Backfill historical messages, mentions, and emoji data from before the bot's join.">
                      <HistorySyncLinkBox />
                    </SettingsCard>

                  </div>
                ) : (
                  <div className="loading-container">
                    <LoadingSpinner text="Loading settings..." />
                  </div>
                )}
              </>
            ) : (
              <AccessDenied accessLevel={accessLevel} />
            )}
          </div>
          <Footer />
        </main>
      </div>
      <ToastMessage />
      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(<React.StrictMode><SettingsDashboard /></React.StrictMode>);

export default SettingsDashboard;