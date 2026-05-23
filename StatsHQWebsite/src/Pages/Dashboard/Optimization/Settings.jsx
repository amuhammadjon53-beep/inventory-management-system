import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const NAVBAR_HEIGHT = "80px";

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

  html {
    min-height: 100%;
    background-color: #0a0a0a;
  }

  body {
    min-height: 100vh;
    margin: 0;
    padding: 0;
    background-color: #0a0a0a;
    color: #ffffff;
    overflow-y: auto;
  }

  #app {
    min-height: 100vh;
    background-color: #0a0a0a;
  }

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
    font-size: 24px;
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
    font-size: 16px;
    transition: all 0.2s ease;
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background-color: #2a2a2a;
    font-style: normal;
    font-weight: bold;
  }

  .info-icon:hover {
    color: #aa00ff;
    background-color: #3a3a3a;
  }

  .info-tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    background-color: #1a1a1a;
    border: 1px solid #aa00ff;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
    width: 320px;
    z-index: 1000;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    pointer-events: none;
    white-space: normal;
    font-size: 12px;
    line-height: 1.5;
    color: #b0b0b0;
  }

  .info-tooltip::after {
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

  .setting-change-btn:hover {
    background-color: #3a3a3a;
  }

  .setting-note {
    color: #666;
    font-size: 12px;
    margin: 0;
  }

  .setting-note code {
    color: #aa00ff;
  }

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

  .button-group {
    display: flex;
    gap: 10px;
  }

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

  .button-save:hover {
    background-color: #8800cc;
    transform: translateY(-2px);
  }

  .button-save:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }

  .button-cancel {
    background-color: #2a2a2a;
    border: none;
    color: #fff;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
  }

  .button-cancel:hover {
    background-color: #3a3a3a;
  }

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

  .voice-state-emoji {
    font-size: 20px;
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
  }

  .voice-state-checkbox.selected {
    background-color: #aa00ff;
    border: none;
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

  .bot-filter-desc {
    color: #888;
    font-size: 13px;
  }

  .bot-filter-button {
    border: 2px solid #000000;
    color: #fff;
    padding: 10px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
  }

  .bot-filter-button.filtering {
    background-color: #8b0000;
  }

  .bot-filter-button.including {
    background-color: #006400;
  }

  .bot-filter-button:hover {
    transform: scale(1.02);
  }

  .bot-filter-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }

  .permission-boxes {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
  }

  .permission-box {
    flex: 1;
    min-width: 90px;
    background-color: #1a1a1a;
    border: 2px solid #2a2a2a;
    border-radius: 12px;
    padding: 14px 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
  }

  .permission-box:hover {
    border-color: #aa00ff;
    transform: translateY(-2px);
    background-color: #222;
  }

  .permission-box.selected {
    background-color: #2a2a2a;
    border-color: #aa00ff;
    box-shadow: 0 0 15px rgba(170, 0, 255, 0.3);
  }

  .permission-box-icon {
    font-size: 28px;
    margin-bottom: 8px;
    display: block;
  }

  .permission-box-name {
    color: #fff;
    font-weight: 600;
    font-size: 13px;
  }

  .access-boxes {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
  }

  .access-box {
    flex: 1;
    min-width: 90px;
    background-color: #1a1a1a;
    border: 2px solid #2a2a2a;
    border-radius: 12px;
    padding: 14px 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
  }

  .access-box:hover {
    border-color: #aa00ff;
    transform: translateY(-2px);
    background-color: #222;
  }

  .access-box.selected {
    background-color: #2a2a2a;
    border-color: #aa00ff;
    box-shadow: 0 0 15px rgba(170, 0, 255, 0.3);
  }

  .access-box-icon {
    font-size: 28px;
    margin-bottom: 8px;
    display: block;
  }

  .access-box-name {
    color: #fff;
    font-weight: 600;
    font-size: 13px;
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

  .error-icon {
    font-size: 64px;
    margin-bottom: 20px;
  }

  .error-title {
    color: #ff4444;
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 16px;
  }

  .error-message {
    color: #b0b0b0;
    font-size: 16px;
    line-height: 1.6;
    margin-bottom: 8px;
  }

  .no-server {
    text-align: center;
    padding: 80px 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    color: #b0b0b0;
  }

  .no-server h2 {
    color: #ffffff;
    margin-bottom: 16px;
    font-size: 28px;
    font-weight: 600;
  }

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

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

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
    .dashboard-main {
      margin-left: 250px;
    }
    .dashboard-content {
      padding: 30px;
    }
    .settings-grid {
      grid-template-columns: 1fr;
    }
    .permission-boxes, .access-boxes {
      flex-direction: column;
    }
    .permission-box, .access-box {
      min-width: auto;
    }
  }

  @media (max-width: 768px) {
    .dashboard-main {
      margin-left: 0;
    }
    .dashboard-content {
      padding: 20px;
    }
  }
`;

const LoadingSpinner = ({ size = "medium", text = "Loading settings..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '60px',
      gap: '16px',
      width: '100%',
      minHeight: '400px'
    }}>
      <div style={{
        width: spinnerSize,
        height: spinnerSize,
        border: '3px solid rgba(170, 0, 255, 0.2)',
        borderTop: `3px solid #aa00ff`,
        borderRadius: '50%',
        animation: 'spin 1s linear infinite'
      }} />
      {text && <span style={{ color: '#aa00ff', fontSize: '14px' }}>{text}</span>}
    </div>
  );
};

const InfoIcon = ({ descriptions }) => {
  const [showTooltip, setShowTooltip] = useState(false);
  let timeout;

  const handleMouseEnter = () => {
    timeout = setTimeout(() => setShowTooltip(true), 300);
  };

  const handleMouseLeave = () => {
    clearTimeout(timeout);
    setShowTooltip(false);
  };

  return (
    <span 
      className="info-icon" 
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{ position: 'relative', cursor: 'help' }}
    >
      ⓘ
      {showTooltip && (
        <div className="info-tooltip">
          {descriptions.map((desc, idx) => (
            <div key={idx} style={{ marginBottom: idx < descriptions.length - 1 ? '8px' : '0' }}>
              <strong style={{ color: '#aa00ff' }}>{desc.level}:</strong> {desc.description}
            </div>
          ))}
        </div>
      )}
    </span>
  );
};

const SettingsCard = ({ title, icon, children, description, infoDescriptions = [] }) => (
  <div className="settings-card">
    <div className="settings-card-header">
      <div className="settings-card-title-section">
        <span className="settings-card-icon">{icon}</span>
        <h3 className="settings-card-title">{title}</h3>
        {infoDescriptions.length > 0 && <InfoIcon descriptions={infoDescriptions} />}
      </div>
    </div>
    {description && <p className="settings-card-description">{description}</p>}
    <div style={{ marginTop: '16px' }}>
      {children}
    </div>
  </div>
);

const PrefixSetting = ({ currentPrefix, onSave, saving }) => {
  const [prefix, setPrefix] = useState(currentPrefix);
  const [editing, setEditing] = useState(false);

  const handleSave = async () => {
    if (prefix.trim() && prefix !== currentPrefix) {
      await onSave(prefix.trim());
      setEditing(false);
    }
  };

  if (!editing) {
    return (
      <div>
        <div className="setting-preview">
          <span className="setting-value">{currentPrefix}</span>
          <button className="setting-change-btn" onClick={() => setEditing(true)}>
            Change
          </button>
        </div>
        <p className="setting-note">
          Current prefix: <code style={{ color: '#aa00ff' }}>{currentPrefix}</code>
        </p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: '12px' }}>
        <input
          type="text"
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          maxLength={10}
          placeholder="Enter new prefix (max 10 chars)"
          className="setting-input"
        />
      </div>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button className="button-cancel" onClick={() => {
          setPrefix(currentPrefix);
          setEditing(false);
        }}>
          Cancel
        </button>
      </div>
    </div>
  );
};

const TimezoneSetting = ({ currentTimezone, onSave, saving }) => {
  const [selectedTimezone, setSelectedTimezone] = useState(currentTimezone);
  const [editing, setEditing] = useState(false);

  const timezones = [
    { value: 'UTC', label: '🌍 UTC (GMT+0)' },
    { value: 'EST', label: '🗽 EST (GMT-5)' },
    { value: 'PST', label: '🌴 PST (GMT-8)' },
    { value: 'CST', label: '🌾 CST (GMT-6)' },
    { value: 'MST', label: '⛰️ MST (GMT-7)' },
    { value: 'GMT', label: '🇬🇧 GMT (GMT+0)' },
    { value: 'CET', label: '🇪🇺 CET (GMT+1)' },
    { value: 'EET', label: '🌅 EET (GMT+2)' },
    { value: 'IST', label: '🇮🇳 IST (GMT+5:30)' },
    { value: 'JST', label: '🇯🇵 JST (GMT+9)' },
    { value: 'AEST', label: '🇦🇺 AEST (GMT+10)' },
    { value: 'NZST', label: '🇳🇿 NZST (GMT+12)' }
  ];

  const handleSave = async () => {
    if (selectedTimezone !== currentTimezone) {
      await onSave(selectedTimezone);
      setEditing(false);
    }
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
          <button className="setting-change-btn" onClick={() => setEditing(true)}>
            Change
          </button>
        </div>
        <p className="setting-note">
          Current timezone: <strong style={{ color: '#aa00ff' }}>{currentTimezone}</strong>
        </p>
      </div>
    );
  }

  return (
    <div>
      <select
        value={selectedTimezone}
        onChange={(e) => setSelectedTimezone(e.target.value)}
        style={{
          width: '100%',
          backgroundColor: '#1a1a1a',
          border: '1px solid #aa00ff',
          borderRadius: '10px',
          padding: '12px',
          color: '#fff',
          fontSize: '14px',
          marginBottom: '12px',
          cursor: 'pointer',
          outline: 'none'
        }}
      >
        {timezones.map(tz => (
          <option key={tz.value} value={tz.value}>
            {tz.label}
          </option>
        ))}
      </select>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button className="button-cancel" onClick={() => {
          setSelectedTimezone(currentTimezone);
          setEditing(false);
        }}>
          Cancel
        </button>
      </div>
    </div>
  );
};

const VoiceStatesSetting = ({ currentStates, onSave, saving }) => {
  const [selectedStates, setSelectedStates] = useState(currentStates || []);
  const [editing, setEditing] = useState(false);

  const voiceStateOptions = [
    { value: 'afk', label: '💤 Afk', description: 'User is in AFK channel' },
    { value: 'self_mute', label: '🔇 Self Mute', description: 'User muted themselves' },
    { value: 'self_deafen', label: '🎧 Self Deafen', description: 'User deafened themselves' },
    { value: 'server_mute', label: '⛔ Server Mute', description: 'User was muted by moderation' },
    { value: 'server_deafen', label: '🔊 Server Deafen', description: 'User was deafened by moderation' },
    { value: 'streaming', label: '📺 Streaming', description: 'User is streaming' },
    { value: 'video', label: '🎥 Video', description: 'User has video open' },
    { value: 'suppressed', label: '🤫 Suppressed', description: 'Stage audience member' }
  ];

  const handleToggleState = (stateValue) => {
    if (selectedStates.includes(stateValue)) {
      setSelectedStates(selectedStates.filter(s => s !== stateValue));
    } else {
      setSelectedStates([...selectedStates, stateValue]);
    }
  };

  const handleSave = async () => {
    if (JSON.stringify(selectedStates.sort()) !== JSON.stringify((currentStates || []).sort())) {
      await onSave(selectedStates);
      setEditing(false);
    }
  };

  if (!editing) {
    const selectedCount = (currentStates || []).length;
    return (
      <div>
        <div className="setting-preview">
          <div>
            <span className="setting-value">{selectedCount} state{selectedCount !== 1 ? 's' : ''} tracked</span>
            {selectedCount > 0 && (
              <div style={{ fontSize: '12px', color: '#888', marginTop: '4px' }}>
                {currentStates.map(state => {
                  const option = voiceStateOptions.find(opt => opt.value === state);
                  return option ? option.label.split(' ')[0] : state;
                }).join(' ')}
              </div>
            )}
          </div>
          <button className="setting-change-btn" onClick={() => setEditing(true)}>
            Configure
          </button>
        </div>
        <p className="setting-note">
          Voice states determine which voice activities are tracked
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="voice-states-grid">
        {voiceStateOptions.map(option => (
          <div
            key={option.value}
            className={`voice-state-option ${selectedStates.includes(option.value) ? 'selected' : ''}`}
            onClick={() => handleToggleState(option.value)}
          >
            <div className="voice-state-info">
              <span className="voice-state-emoji">{option.label.split(' ')[0]}</span>
              <div>
                <div className="voice-state-label">{option.label.split(' ').slice(1).join(' ')}</div>
                <div className="voice-state-desc">{option.description}</div>
              </div>
            </div>
            <div className={`voice-state-checkbox ${selectedStates.includes(option.value) ? 'selected' : ''}`}>
              {selectedStates.includes(option.value) && <span style={{ color: '#fff', fontSize: '12px', fontWeight: 'bold' }}>✓</span>}
            </div>
          </div>
        ))}
      </div>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
        <button className="button-cancel" onClick={() => {
          setSelectedStates(currentStates || []);
          setEditing(false);
        }}>
          Cancel
        </button>
      </div>
    </div>
  );
};

const BotFilterSetting = ({ enabled, onSave, saving }) => {
  const handleToggle = async () => {
    await onSave(!enabled);
  };

  return (
    <div>
      <div className="bot-filter-container">
        <div>
          <div className="bot-filter-text">
            {enabled ? '🤖 Filtering Bots' : '🤖 Including Bots'}
          </div>
          <div className="bot-filter-desc">
            {enabled 
              ? 'Bots are currently filtered out from statistics' 
              : 'Bots are currently included in statistics'}
          </div>
        </div>
        <button
          className={`bot-filter-button ${enabled ? 'filtering' : 'including'}`}
          onClick={handleToggle}
          disabled={saving}
        >
          {saving ? 'Updating...' : (enabled ? 'Include Bots' : 'Filter Bots')}
        </button>
      </div>
    </div>
  );
};

const PermissionLevelSetting = ({ currentLevel, onSave, saving }) => {
  const [selectedLevel, setSelectedLevel] = useState(currentLevel);

  const permissionLevels = [
    { value: 'All', icon: '🌍', shortDesc: 'Anyone can use all commands' },
    { value: 'Default', icon: '⚙️', shortDesc: 'Most commands for everyone, admin for reset' },
    { value: 'User Restriction', icon: '👤', shortDesc: 'Commands limited to own account' },
    { value: 'Moderator', icon: '🛡️', shortDesc: 'Manage Server permission required' },
    { value: 'Admin', icon: '👑', shortDesc: 'Admin permission required' }
  ];

  const handleSelect = (level) => {
    setSelectedLevel(level);
  };

  const handleSave = async () => {
    if (selectedLevel !== currentLevel) {
      await onSave(selectedLevel);
    }
  };

  return (
    <div>
      <div className="permission-boxes">
        {permissionLevels.map(level => (
          <div
            key={level.value}
            className={`permission-box ${selectedLevel === level.value ? 'selected' : ''}`}
            onClick={() => handleSelect(level.value)}
          >
            <span className="permission-box-icon">{level.icon}</span>
            <div className="permission-box-name">{level.value}</div>
          </div>
        ))}
      </div>
      
      {selectedLevel !== currentLevel && (
        <div className="button-group" style={{ marginTop: '16px' }}>
          <button className="button-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Apply Changes'}
          </button>
        </div>
      )}
    </div>
  );
};

const DashboardAccessSetting = ({ currentLevel, onSave, saving }) => {
  const [selectedLevel, setSelectedLevel] = useState(currentLevel);

  const accessLevels = [
    { value: 'Public', icon: '🌍', shortDesc: 'Any authenticated user can view' },
    { value: 'Member', icon: '👥', shortDesc: 'Manage Server or Administrator required' },
    { value: 'Moderator', icon: '🛡️', shortDesc: 'Manage Server or Administrator required' },
    { value: 'Admin', icon: '👑', shortDesc: 'Administrator permission required' }
  ];

  const handleSelect = (level) => {
    setSelectedLevel(level);
  };

  const handleSave = async () => {
    if (selectedLevel !== currentLevel) {
      await onSave(selectedLevel);
    }
  };

  return (
    <div>
      <div className="access-boxes">
        {accessLevels.map(level => (
          <div
            key={level.value}
            className={`access-box ${selectedLevel === level.value ? 'selected' : ''}`}
            onClick={() => handleSelect(level.value)}
          >
            <span className="access-box-icon">{level.icon}</span>
            <div className="access-box-name">{level.value}</div>
          </div>
        ))}
      </div>
      
      {selectedLevel !== currentLevel && (
        <div className="button-group" style={{ marginTop: '16px' }}>
          <button className="button-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Apply Changes'}
          </button>
        </div>
      )}
    </div>
  );
};

const AccessDenied = ({ accessLevel }) => {
  let requiredPermission = "Administrator";
  if (accessLevel === 'Member' || accessLevel === 'Moderator') {
    requiredPermission = "Manage Server or Administrator";
  } else if (accessLevel === 'Admin') {
    requiredPermission = "Administrator";
  }
  
  return (
    <div className="dashboard-content">
      <div className="error-message-container">
        <div className="error-icon">🔒</div>
        <h2 className="error-title">Access Denied</h2>
        <p className="error-message">This server requires <strong>{requiredPermission}</strong> permission to view settings.</p>
        <p className="error-message" style={{ fontSize: '13px', marginTop: '8px' }}>
        </p>
      </div>
    </div>
  );
};

const SettingsDashboard = () => {
  const [currentServer, setCurrentServer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [settings, setSettings] = useState(null);
  const [apiError, setApiError] = useState(null);
  const [toast, setToast] = useState(null);
  const [accessLevel, setAccessLevel] = useState('Member');
  const [currentUserId, setCurrentUserId] = useState(null);
  const [saving, setSaving] = useState({
    prefix: false,
    timezone: false,
    voiceStates: false,
    botFilter: false,
    permissionLevel: false,
    dashboardAccess: false
  });

  // Check if current user is privileged
  const isPrivilegedUser = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const ToastMessage = () => {
    if (!toast) return null;
    const colors = {
      success: { bg: '#00b894', icon: '✅' },
      error: { bg: '#ff7675', icon: '❌' },
      info: { bg: '#0984e3', icon: 'ℹ️' }
    };
    const color = colors[toast.type] || colors.info;
    
    return (
      <div className="toast-message" style={{ backgroundColor: color.bg }}>
        <span>{color.icon}</span>
        <span>{toast.message}</span>
        <button onClick={() => setToast(null)} style={{
          background: 'none',
          border: 'none',
          color: 'white',
          cursor: 'pointer',
          marginLeft: '10px',
          fontSize: '16px'
        }}>✕</button>
      </div>
    );
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    setLoadingServers(true);
    setApiError(null);
    setHasAccess(null);
    
    try {
      const authResponse = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      
      if (!authResponse.ok) {
        throw new Error('Auth failed');
      }
      
      const authData = await authResponse.json();
     
      
      if (authData.authenticated && authData.user) {
        setIsAuthenticated(true);
        setCurrentUserId(authData.user.id);
        
        // Check if user is privileged
        if (isPrivilegedUser(authData.user.id)) {
          setHasAccess(true);
          setAccessLevel('Admin');
          window.accessLevel = 'Admin';
        }
        
        const serversResponse = await fetch(`${API_BASE_URL}/api/user/servers`, {
          credentials: 'include',
          headers: { 'Accept': 'application/json' }
        });
        
        
        if (serversResponse.ok) {
          const servers = await serversResponse.json();
          
          if (Array.isArray(servers) && servers.length > 0) {
            let selectedServer = null;
            if (authData.user.selected_server) {
              selectedServer = servers.find(s => s.id === authData.user.selected_server);
          
            }
            if (!selectedServer && servers.length > 0) {
              selectedServer = servers[0];
             
            }
            
            if (selectedServer) {
             
              setCurrentServer(selectedServer);
              
              // Only check permissions if not privileged (privileged users already have access)
              if (!isPrivilegedUser(authData.user.id)) {
                await checkAndLoadSettings(
                  selectedServer.id, 
                  selectedServer.permissions,
                  selectedServer.has_admin,
                  selectedServer.has_manage_server
                );
              } else {
                // For privileged users, still load settings
                await loadSettingsOnly(selectedServer.id);
              }
            } else {
              setLoading(false);
            }
          } else {
            setLoading(false);
          }
        } else {
          setLoading(false);
        }
      } else {
        setLoading(false);
      }
    } catch (error) {
      console.error('🔴 Error loading initial data:', error);
      setApiError('Failed to load servers. Please check your connection.');
      setLoading(false);
    } finally {
      setLoadingServers(false);
    }
  };

  const loadSettingsOnly = async (guildId) => {
    
    try {
      const settingsResponse = await fetch(`${API_BASE_URL}/api/settings/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: guildId })
      });


      if (settingsResponse.ok) {
        const settingsData = await settingsResponse.json();
      
        setSettings(settingsData);
        
        const dashboardAccessLevel = settingsData.dashboard_access_level || 'Member';
        setAccessLevel(dashboardAccessLevel);
       
      } else {
        
        const errorText = await settingsResponse.text();
   
        showToast('Failed to load settings', 'error');
      }
    } catch (error) {
      console.error('🔴 Error loading settings:', error);
      showToast('Error loading settings', 'error');
    } finally {
      setLoading(false);
    }
  };

  const checkAndLoadSettings = async (guildId, permissions, hasAdmin, hasManageServer) => {
  
    
    try {
     
      const settingsResponse = await fetch(`${API_BASE_URL}/api/settings/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: guildId })
      });


      if (settingsResponse.ok) {
        const settingsData = await settingsResponse.json();
       
        setSettings(settingsData);
        
        const dashboardAccessLevel = settingsData.dashboard_access_level || 'Member';
        setAccessLevel(dashboardAccessLevel);
      
        
        const isAdmin = hasAdmin;
        const hasManageServerPerm = hasManageServer;
        
       
        
        let hasAccessFlag = false;
        
        if (dashboardAccessLevel === 'Public') {
          hasAccessFlag = true;
         
        } else if (dashboardAccessLevel === 'Member') {
          hasAccessFlag = isAdmin || hasManageServerPerm;
      
        } else if (dashboardAccessLevel === 'Moderator') {
          hasAccessFlag = isAdmin || hasManageServerPerm;
         
        } else if (dashboardAccessLevel === 'Admin') {
          hasAccessFlag = isAdmin;
          
        } else {
          hasAccessFlag = isAdmin;
        
        }
        
        setHasAccess(hasAccessFlag);
      } else {
     
        const errorText = await settingsResponse.text();
   
        showToast('Failed to load settings', 'error');
        setHasAccess(false);
      }
    } catch (error) {
      console.error('🔴 Error checking access:', error);
      showToast('Error loading settings', 'error');
      setHasAccess(false);
    } finally {
      setLoading(false);
    }
  };

  const settingDisplayNames = {
    prefix: 'Prefix',
    timezone: 'Timezone',
    voice_states: 'Voice States',
    bot_filter: 'Bot Filter',
    permission_level: 'Command Permission Access Level',
    dashboard_access_level: 'Dashboard Access Level'
  };

  const updateSetting = async (setting, value) => {
    if (!currentServer) return false;

    setSaving(prev => ({ ...prev, [setting]: true }));
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/settings/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
            guild_id: currentServer.id,
            setting: setting,
            value: value
        })
        });

        const result = await response.json();
        
        if (result.success) {
        setSettings(prev => ({ ...prev, [setting]: value }));
        
        const displayName = settingDisplayNames[setting] || setting;
        showToast(`Successfully updated ${displayName}`, 'success');
        return true;
        } else {
        showToast(result.message || 'Failed to update setting', 'error');
        return false;
        }
    } catch (error) {
        console.error(`Error updating ${setting}:`, error);
        const displayName = settingDisplayNames[setting] || setting;
        showToast(`❌ Error updating ${displayName}`, 'error');
        return false;
    } finally {
        setSaving(prev => ({ ...prev, [setting]: false }));
    }
  };

  // Loading state
  if (loadingServers || (isAuthenticated && !currentServer && !apiError)) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading-container">
                <LoadingSpinner text="Loading servers..." />
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Permission checking in progress (only for non-privileged users)
  if (hasAccess === null && isAuthenticated && currentServer && !isPrivilegedUser(currentUserId)) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading-container">
                <LoadingSpinner text="Checking permissions..." />
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Not authenticated
  if (!isAuthenticated) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>Please Log In</h2>
                <p>You need to be logged in to configure settings.</p>
                <a href={`${API_BASE_URL}/api/auth/discord`} className="login-button">Login with Discord</a>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // No server
  if (!currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>No Server Available</h2>
                <p>Add the bot to a Discord server to configure settings.</p>
                <a 
                  href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands" 
                  className="invite-button" 
                  target="_blank" 
                  rel="noopener noreferrer"
                >
                  Invite Bot to Server
                </a>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Error state
  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message-container">
                <div className="error-icon">⚠️</div>
                <h2 className="error-title">Error Loading Data</h2>
                <p className="error-message">{apiError}</p>
                <button onClick={() => window.location.reload()} className="invite-button">Retry</button>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar 
          currentServerId={currentServer?.id} 
          topOffset={NAVBAR_HEIGHT}
        />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            {hasAccess ? (
              <>
                {settings ? (
                  <div className="settings-grid">
                    <SettingsCard title="Prefix" icon="⚙️" description="Change the bot's command prefix">
                      <PrefixSetting
                        currentPrefix={settings.prefix}
                        onSave={(value) => updateSetting('prefix', value)}
                        saving={saving.prefix}
                      />
                    </SettingsCard>

                    <SettingsCard title="Timezone" icon="🌍" description="Set the timezone for time-based statistics">
                      <TimezoneSetting
                        currentTimezone={settings.timezone}
                        onSave={(value) => updateSetting('timezone', value)}
                        saving={saving.timezone}
                      />
                    </SettingsCard>

                    <SettingsCard title="Voice States" icon="🔊" description="Choose which voice states to track">
                      <VoiceStatesSetting
                        currentStates={settings.voice_states}
                        onSave={(value) => updateSetting('voice_states', value)}
                        saving={saving.voiceStates}
                      />
                    </SettingsCard>

                    <SettingsCard title="Bot Filter" icon="🤖" description="Filter bots from statistics">
                      <BotFilterSetting
                        enabled={settings.bot_filter}
                        onSave={(value) => updateSetting('bot_filter', value)}
                        saving={saving.botFilter}
                      />
                    </SettingsCard>

                    <SettingsCard 
                      title="Command Permission Access Level" 
                      icon="🔐" 
                      description="Control who can use bot commands"
                      infoDescriptions={[
                        { level: 'All', description: 'All members regardless of their permissions are allowed to use any command on the bot including sensitive commands like reset and blacklist' },
                        { level: 'Default', description: 'The default access level that restricts or enables specific commands for users with specific permissions. All commands on the bot are usable by normal members except for blacklist and settings being accessible via manage server, and reset commands being accessible via administrator permissions' },
                        { level: 'User Restriction', description: 'Mostly the same as Default except users can only use commands that have the user scope on their own account only' },
                        { level: 'Moderator', description: 'Only users with the Manage Server permission can use any commands on the bot' },
                        { level: 'Admin', description: 'Only users with the administrator permission can use any commands on the bot' }
                      ]}
                    >
                      <PermissionLevelSetting
                        currentLevel={settings.permission_level}
                        onSave={(value) => updateSetting('permission_level', value)}
                        saving={saving.permissionLevel}
                      />
                    </SettingsCard>

                    <SettingsCard 
                      title="Dashboard Access Level" 
                      icon="📊" 
                      description="Control who can view the web dashboard"
                      infoDescriptions={[
                        { level: 'Public', description: 'Any member of the server can view the entire dashboard including the optimization section.' },
                        { level: 'Member', description: 'Members of the server can view the analytics section of the dashboard but they need the Manage Server or Administrator permissions to view the optimization section.' },
                        { level: 'Moderator', description: 'Manage Server or Administrator permission required to view either the analytics or optimization sections of the dashboard.' },
                        { level: 'Admin', description: 'Administrator permission required to view either the analytics or optimization sections of the dashboard.' }
                      ]}
                    >
                      <DashboardAccessSetting
                        currentLevel={settings.dashboard_access_level || 'Member'}
                        onSave={(value) => updateSetting('dashboard_access_level', value)}
                        saving={saving.dashboardAccess}
                      />
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
root.render(
  <React.StrictMode>
    <SettingsDashboard />
  </React.StrictMode>
);

export default SettingsDashboard;