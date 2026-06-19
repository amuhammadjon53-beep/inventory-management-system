import React, { useState, useEffect, useCallback } from "react";
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

  /* ── History Sync ── */

  .sync-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }

  .sync-controls-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .sync-stat-toggles {
    display: flex;
    gap: 10px;
  }

  .sync-stat-toggle {
    flex: 1;
    padding: 10px 8px;
    border-radius: 10px;
    background-color: #1a1a1a;
    border: 2px solid #2a2a2a;
    color: #888;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
    transition: all 0.2s ease;
    user-select: none;
  }

  .sync-stat-toggle:hover {
    border-color: #aa00ff;
    color: #fff;
  }

  .sync-stat-toggle.active {
    background-color: #1e0033;
    border-color: #aa00ff;
    color: #fff;
    box-shadow: 0 0 10px rgba(170, 0, 255, 0.2);
  }

  .sync-stat-toggle-icon {
    font-size: 20px;
    display: block;
    margin-bottom: 4px;
  }

  .sync-action-buttons {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .sync-btn {
    padding: 10px 16px;
    border-radius: 8px;
    border: none;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: all 0.2s ease;
  }

  .sync-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none !important;
  }

  .sync-btn-primary {
    background-color: #aa00ff;
    color: #fff;
  }

  .sync-btn-primary:hover:not(:disabled) {
    background-color: #8800cc;
    transform: translateY(-1px);
  }

  .sync-btn-secondary {
    background-color: #1a1a1a;
    color: #fff;
    border: 1px solid #2a2a2a;
  }

  .sync-btn-secondary:hover:not(:disabled) {
    background-color: #2a2a2a;
    transform: translateY(-1px);
  }

  .sync-btn-danger {
    background-color: #2a0a0a;
    color: #ff6b6b;
    border: 1px solid #5a1a1a;
  }

  .sync-btn-danger:hover:not(:disabled) {
    background-color: #3a1010;
    transform: translateY(-1px);
  }

  .sync-btn-warning {
    background-color: #1a1500;
    color: #ffd700;
    border: 1px solid #3a3000;
  }

  .sync-btn-warning:hover:not(:disabled) {
    background-color: #2a2000;
    transform: translateY(-1px);
  }

  .sync-row-buttons {
    display: flex;
    gap: 6px;
  }

  .sync-row-btn {
    padding: 5px 10px;
    border-radius: 6px;
    border: none;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }

  .sync-row-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .sync-row-btn-start {
    background-color: #1e0033;
    color: #cc77ff;
    border: 1px solid #440066;
  }

  .sync-row-btn-start:hover:not(:disabled) {
    background-color: #2e0044;
  }

  .sync-row-btn-pause {
    background-color: #1a1500;
    color: #ffd700;
    border: 1px solid #3a3000;
  }

  .sync-row-btn-pause:hover:not(:disabled) {
    background-color: #2a2000;
  }

  .sync-row-btn-cancel {
    background-color: #2a0a0a;
    color: #ff6b6b;
    border: 1px solid #5a1a1a;
  }

  .sync-row-btn-cancel:hover:not(:disabled) {
    background-color: #3a1010;
  }

  .sync-row-btn-reset {
    background-color: #0a0a1a;
    color: #6b9eff;
    border: 1px solid #1a1a4a;
  }

  .sync-row-btn-reset:hover:not(:disabled) {
    background-color: #10102a;
  }

  .sync-channels-panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 420px;
    overflow-y: auto;
  }

  .sync-channels-panel::-webkit-scrollbar {
    width: 4px;
  }

  .sync-channels-panel::-webkit-scrollbar-track {
    background: #1a1a1a;
    border-radius: 2px;
  }

  .sync-channels-panel::-webkit-scrollbar-thumb {
    background: #aa00ff;
    border-radius: 2px;
  }

  .sync-channel-row {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: border-color 0.2s ease;
  }

  .sync-channel-row.running {
    border-color: #aa00ff;
    background-color: #110022;
  }

  .sync-channel-row.caught_up {
    border-color: #00b894;
    background-color: #001a12;
  }

  .sync-channel-row.failed {
    border-color: #ff6b6b;
    background-color: #1a0a0a;
  }

  .sync-channel-row.paused {
    border-color: #ffd700;
    background-color: #1a1500;
  }

  .sync-channel-name {
    flex: 1;
    color: #e0e0e0;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sync-channel-name span {
    color: #555;
    margin-right: 4px;
  }

  .sync-status-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
  }

  .sync-status-badge.pending    { background-color: #2a2a2a; color: #888; }
  .sync-status-badge.running    { background-color: #1e0033; color: #cc77ff; }
  .sync-status-badge.caught_up  { background-color: #001a12; color: #00b894; }
  .sync-status-badge.failed     { background-color: #1a0a0a; color: #ff6b6b; }
  .sync-status-badge.paused     { background-color: #1a1500; color: #ffd700; }
  .sync-status-badge.in_progress { background-color: #1e0033; color: #cc77ff; }

  .sync-progress-bar-wrap {
    width: 60px;
    height: 4px;
    background-color: #2a2a2a;
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
  }

  .sync-progress-bar-fill {
    height: 100%;
    background-color: #aa00ff;
    border-radius: 2px;
    transition: width 0.3s ease;
  }

  .sync-summary-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }

  .sync-summary-chip {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 12px;
    color: #b0b0b0;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .sync-summary-chip strong {
    color: #aa00ff;
  }

  .sync-empty-channels {
    text-align: center;
    color: #555;
    font-size: 13px;
    padding: 40px 20px;
  }

  .sync-section-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #555;
    margin-bottom: 8px;
  }

  .sync-divider {
    border: none;
    border-top: 1px solid #1f1f1f;
    margin: 4px 0 12px 0;
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
    .sync-layout {
      grid-template-columns: 1fr;
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

// ─────────────────────────────────────────────────────────────
// Shared / utility components
// ─────────────────────────────────────────────────────────────

const LoadingSpinner = ({ size = "medium", text = "Loading settings..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: '60px', gap: '16px',
      width: '100%', minHeight: '400px'
    }}>
      <div style={{
        width: spinnerSize, height: spinnerSize,
        border: '3px solid rgba(170, 0, 255, 0.2)',
        borderTop: `3px solid #aa00ff`,
        borderRadius: '50%', animation: 'spin 1s linear infinite'
      }} />
      {text && <span style={{ color: '#aa00ff', fontSize: '14px' }}>{text}</span>}
    </div>
  );
};

const InfoIcon = ({ descriptions }) => {
  const [showTooltip, setShowTooltip] = useState(false);
  let timeout;
  const handleMouseEnter = () => { timeout = setTimeout(() => setShowTooltip(true), 300); };
  const handleMouseLeave = () => { clearTimeout(timeout); setShowTooltip(false); };
  return (
    <span className="info-icon" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}
      style={{ position: 'relative', cursor: 'help' }}>
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
// History Data Sync component
// ─────────────────────────────────────────────────────────────

const STAT_OPTIONS = [
  { key: 'messages', icon: '💬', label: 'Messages' },
  { key: 'mentions', icon: '📣', label: 'Mentions' },
  { key: 'emoji',    icon: '😄', label: 'Emoji'    },
];

const statusLabel = (status) => {
  const map = {
    pending:     'Pending',
    in_progress: 'Running',
    caught_up:   'Caught Up',
    failed:      'Failed',
    paused:      'Paused',
  };
  return map[status] || status || 'Unknown';
};

const statusClass = (status) => {
  if (status === 'in_progress') return 'running';
  return status || 'pending';
};

const HistorySyncSection = ({ guildId, showToast }) => {
  const [syncStatus, setSyncStatus]         = useState(null);   // from GET /status
  const [loadingStatus, setLoadingStatus]   = useState(false);
  const [selectedStats, setSelectedStats]   = useState({ messages: true, mentions: true, emoji: true });
  const [actionLoading, setActionLoading]   = useState({});     // channelId -> bool
  const [globalLoading, setGlobalLoading]   = useState(false);
  const [resetTarget, setResetTarget]       = useState(null);   // { channelId, channelName }

  // ── fetch status ──────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    if (!guildId) return;
    setLoadingStatus(true);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/history-sync/status?guild_id=${guildId}`,
        { credentials: 'include' }
      );
      if (res.ok) {
        const data = await res.json();
        setSyncStatus(data);
      } else if (res.status === 403) {
        showToast('Administrator permission required', 'error');
      } else {
        showToast('Failed to load sync status', 'error');
      }
    } catch {
      showToast('Error loading sync status', 'error');
    } finally {
      setLoadingStatus(false);
    }
  }, [guildId]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // ── helpers ───────────────────────────────────────────────
  const setChannelLoading = (channelId, val) =>
    setActionLoading(prev => ({ ...prev, [channelId]: val }));

  const statPayload = () => ({
    sync_messages: selectedStats.messages,
    sync_mentions: selectedStats.mentions,
    sync_emoji:    selectedStats.emoji,
  });

  const atLeastOneStat = Object.values(selectedStats).some(Boolean);

  // ── global actions ────────────────────────────────────────
  const handleInit = async () => {
    setGlobalLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: String(guildId) }),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Queued ${data.channels_queued} channel(s)`, 'success');
        await fetchStatus();
      } else if (res.status === 403) {
        showToast('Administrator permission required', 'error');
      } else {
        showToast('Failed to initialise sync', 'error');
      }
    } catch {
      showToast('Error initialising sync', 'error');
    } finally {
      setGlobalLoading(false);
    }
  };

  const handleSyncAll = async () => {
    if (!atLeastOneStat) { showToast('Select at least one stat type', 'error'); return; }
    setGlobalLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/sync-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: String(guildId), ...statPayload() }),
      });
      if (res.ok) {
        const data = await res.json();
        const started = data.started_channels?.length ?? 0;
        const skipped = data.skipped_channels?.length ?? 0;
        showToast(`Started ${started} channel(s)${skipped ? `, skipped ${skipped} already running` : ''}`, 'success');
        await fetchStatus();
      } else if (res.status === 403) {
        showToast('Administrator permission required', 'error');
      } else {
        showToast('Failed to start sync', 'error');
      }
    } catch {
      showToast('Error starting sync', 'error');
    } finally {
      setGlobalLoading(false);
    }
  };

  // ── per-channel actions ───────────────────────────────────
  const handleChannelSync = async (channelId) => {
    if (!atLeastOneStat) { showToast('Select at least one stat type', 'error'); return; }
    setChannelLoading(channelId, true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guild_id: String(guildId),
          channel_id: String(channelId),
          ...statPayload(),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(
          data.status === 'already_running' ? 'Already running' : 'Sync started',
          data.status === 'already_running' ? 'info' : 'success'
        );
        await fetchStatus();
      } else if (res.status === 403) {
        showToast('Administrator permission required', 'error');
      } else {
        showToast('Failed to start channel sync', 'error');
      }
    } catch {
      showToast('Error starting channel sync', 'error');
    } finally {
      setChannelLoading(channelId, false);
    }
  };

  const handleChannelPause = async (channelId) => {
    setChannelLoading(channelId, true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: String(guildId), channel_id: String(channelId) }),
      });
      if (res.ok) {
        showToast('Sync paused', 'info');
        await fetchStatus();
      } else {
        showToast('Failed to pause sync', 'error');
      }
    } catch {
      showToast('Error pausing sync', 'error');
    } finally {
      setChannelLoading(channelId, false);
    }
  };

  const handleChannelCancel = async (channelId) => {
    setChannelLoading(channelId, true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: String(guildId), channel_id: String(channelId) }),
      });
      if (res.ok) {
        showToast('Sync cancelled', 'info');
        await fetchStatus();
      } else {
        showToast('Failed to cancel sync', 'error');
      }
    } catch {
      showToast('Error cancelling sync', 'error');
    } finally {
      setChannelLoading(channelId, false);
    }
  };

  const handleChannelReset = async (channelId, stats) => {
    setChannelLoading(channelId, true);
    setResetTarget(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guild_id: String(guildId),
          channel_id: String(channelId),
          stats: stats ?? null,
        }),
      });
      if (res.ok) {
        showToast('Channel progress reset', 'success');
        await fetchStatus();
      } else {
        showToast('Failed to reset channel', 'error');
      }
    } catch {
      showToast('Error resetting channel', 'error');
    } finally {
      setChannelLoading(channelId, false);
    }
  };

  // ── derived summary numbers ───────────────────────────────
  const channels = syncStatus?.channels ?? [];
  const totalChannels  = channels.length;
  const runningCount   = channels.filter(c => c.status === 'in_progress').length;
  const caughtUpCount  = channels.filter(c => c.status === 'caught_up').length;
  const failedCount    = channels.filter(c => c.status === 'failed').length;
  const pendingCount   = channels.filter(c => c.status === 'pending').length;

  // ── reset confirmation modal ──────────────────────────────
  const ResetModal = () => {
    if (!resetTarget) return null;
    const [resetStats, setResetStats] = useState(['messages', 'mentions', 'emoji']);
    const toggleStat = (s) => setResetStats(prev =>
      prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
    );
    return (
      <div style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000
      }}>
        <div style={{
          background: '#111', border: '1px solid #3a1a5a', borderRadius: '16px',
          padding: '28px', maxWidth: '400px', width: '90%'
        }}>
          <h3 style={{ color: '#fff', marginBottom: '8px', fontSize: '18px' }}>Reset Channel Progress</h3>
          <p style={{ color: '#888', fontSize: '13px', marginBottom: '20px' }}>
            Choose which stat types to reset for <strong style={{ color: '#cc77ff' }}>
              #{resetTarget.channelName}
            </strong>. This will trigger a full re-sync for those types.
          </p>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
            {STAT_OPTIONS.map(s => (
              <div key={s.key}
                onClick={() => toggleStat(s.key)}
                style={{
                  flex: 1, padding: '10px 6px', borderRadius: '10px', cursor: 'pointer',
                  textAlign: 'center', fontSize: '12px', fontWeight: 600,
                  background: resetStats.includes(s.key) ? '#1e0033' : '#1a1a1a',
                  border: `2px solid ${resetStats.includes(s.key) ? '#aa00ff' : '#2a2a2a'}`,
                  color: resetStats.includes(s.key) ? '#fff' : '#888',
                  userSelect: 'none'
                }}>
                <span style={{ display: 'block', fontSize: '20px', marginBottom: '4px' }}>{s.icon}</span>
                {s.label}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              disabled={resetStats.length === 0}
              onClick={() => handleChannelReset(resetTarget.channelId, resetStats)}
              style={{
                flex: 1, padding: '10px', borderRadius: '8px', border: 'none',
                background: resetStats.length ? '#6b00cc' : '#333',
                color: '#fff', fontWeight: 600, cursor: resetStats.length ? 'pointer' : 'not-allowed'
              }}>
              Reset Selected
            </button>
            <button
              onClick={() => setResetTarget(null)}
              style={{
                flex: 1, padding: '10px', borderRadius: '8px',
                border: '1px solid #2a2a2a', background: '#1a1a1a',
                color: '#fff', fontWeight: 600, cursor: 'pointer'
              }}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  };

  // ── render ────────────────────────────────────────────────
  return (
    <>
      <ResetModal />

      {/* Stat type selectors + global actions */}
      <div className="sync-layout">
        <div className="sync-controls-panel">

          <div>
            <div className="sync-section-label">Stat Types to Sync</div>
            <div className="sync-stat-toggles">
              {STAT_OPTIONS.map(s => (
                <div key={s.key}
                  className={`sync-stat-toggle ${selectedStats[s.key] ? 'active' : ''}`}
                  onClick={() => setSelectedStats(prev => ({ ...prev, [s.key]: !prev[s.key] }))}>
                  <span className="sync-stat-toggle-icon">{s.icon}</span>
                  {s.label}
                </div>
              ))}
            </div>
            {!atLeastOneStat && (
              <p style={{ color: '#ff6b6b', fontSize: '11px', marginTop: '6px' }}>
                Select at least one stat type to sync.
              </p>
            )}
          </div>

          <hr className="sync-divider" />

          {/* Summary chips */}
          {syncStatus && (
            <div className="sync-summary-row">
              <div className="sync-summary-chip">📋 <strong>{totalChannels}</strong> total</div>
              {runningCount  > 0 && <div className="sync-summary-chip">⚡ <strong>{runningCount}</strong> running</div>}
              {caughtUpCount > 0 && <div className="sync-summary-chip">✅ <strong>{caughtUpCount}</strong> done</div>}
              {pendingCount  > 0 && <div className="sync-summary-chip">⏳ <strong>{pendingCount}</strong> pending</div>}
              {failedCount   > 0 && <div className="sync-summary-chip" style={{ borderColor: '#5a1a1a' }}>❌ <strong style={{ color: '#ff6b6b' }}>{failedCount}</strong> failed</div>}
            </div>
          )}

          <div className="sync-action-buttons">
            <div className="sync-section-label">Global Actions</div>

            <button className="sync-btn sync-btn-secondary" onClick={fetchStatus} disabled={loadingStatus || globalLoading}>
              {loadingStatus ? '⏳ Refreshing...' : '🔄 Refresh Status'}
            </button>

            <button className="sync-btn sync-btn-secondary" onClick={handleInit} disabled={globalLoading || loadingStatus}>
              📋 Initialise All Channels
            </button>

            <button
              className="sync-btn sync-btn-primary"
              onClick={handleSyncAll}
              disabled={globalLoading || loadingStatus || !atLeastOneStat}>
              {globalLoading ? '⏳ Starting...' : '▶ Sync All Channels'}
            </button>
          </div>

          <p style={{ color: '#555', fontSize: '11px', lineHeight: 1.6 }}>
            Syncing backfills historical message, mention, and emoji data into the stats database.
            Large servers may take a while — you can pause and resume at any time.
          </p>
        </div>

        {/* Channel list */}
        <div>
          <div className="sync-section-label" style={{ marginBottom: '10px' }}>
            Channels {loadingStatus && <span style={{ color: '#aa00ff' }}>— refreshing…</span>}
          </div>

          <div className="sync-channels-panel">
            {channels.length === 0 ? (
              <div className="sync-empty-channels">
                {loadingStatus
                  ? 'Loading channels…'
                  : 'No channels found. Click "Initialise All Channels" to populate the list.'}
              </div>
            ) : (
              channels.map(ch => {
                const chId     = String(ch.channel_id ?? ch.id);
                const chName   = ch.channel_name ?? ch.name ?? chId;
                const chStatus = ch.status ?? 'pending';
                const isLoading = !!actionLoading[chId];
                const isRunning = chStatus === 'in_progress';

                // Progress estimate (0–100) — use processed vs total if available
                const progress = ch.progress_pct ?? (isRunning ? null : null);

                return (
                  <div key={chId} className={`sync-channel-row ${statusClass(chStatus)}`}>
                    <div className="sync-channel-name">
                      <span>#</span>{chName}
                    </div>

                    {/* Thin animated bar for in-progress channels without a known % */}
                    {isRunning && (
                      <div className="sync-progress-bar-wrap">
                        <div className="sync-progress-bar-fill"
                          style={{ width: progress != null ? `${progress}%` : '40%' }} />
                      </div>
                    )}

                    <span className={`sync-status-badge ${statusClass(chStatus)}`}>
                      {statusLabel(chStatus)}
                    </span>

                    <div className="sync-row-buttons">
                      {/* Start / Resume */}
                      {!isRunning && (
                        <button
                          className="sync-row-btn sync-row-btn-start"
                          onClick={() => handleChannelSync(chId)}
                          disabled={isLoading || !atLeastOneStat}>
                          {isLoading ? '…' : chStatus === 'paused' || chStatus === 'in_progress' ? '▶ Resume' : '▶ Start'}
                        </button>
                      )}

                      {/* Pause — only when running */}
                      {isRunning && (
                        <button
                          className="sync-row-btn sync-row-btn-pause"
                          onClick={() => handleChannelPause(chId)}
                          disabled={isLoading}>
                          {isLoading ? '…' : '⏸ Pause'}
                        </button>
                      )}

                      {/* Cancel — only when running */}
                      {isRunning && (
                        <button
                          className="sync-row-btn sync-row-btn-cancel"
                          onClick={() => handleChannelCancel(chId)}
                          disabled={isLoading}>
                          {isLoading ? '…' : '✕ Cancel'}
                        </button>
                      )}

                      {/* Reset — always available */}
                      <button
                        className="sync-row-btn sync-row-btn-reset"
                        onClick={() => setResetTarget({ channelId: chId, channelName: chName })}
                        disabled={isLoading}>
                        ↺ Reset
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </>
  );
};

// ─────────────────────────────────────────────────────────────
// Existing settings sub-components (unchanged)
// ─────────────────────────────────────────────────────────────

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
          <button className="setting-change-btn" onClick={() => setEditing(true)}>Change</button>
        </div>
        <p className="setting-note">Current prefix: <code style={{ color: '#aa00ff' }}>{currentPrefix}</code></p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: '12px' }}>
        <input type="text" value={prefix} onChange={(e) => setPrefix(e.target.value)}
          maxLength={10} placeholder="Enter new prefix (max 10 chars)" className="setting-input" />
      </div>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button className="button-cancel" onClick={() => { setPrefix(currentPrefix); setEditing(false); }}>
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
    { value: 'UTC', label: '🌍 UTC (GMT+0)' }, { value: 'EST', label: '🗽 EST (GMT-5)' },
    { value: 'PST', label: '🌴 PST (GMT-8)' }, { value: 'CST', label: '🌾 CST (GMT-6)' },
    { value: 'MST', label: '⛰️ MST (GMT-7)' }, { value: 'GMT', label: '🇬🇧 GMT (GMT+0)' },
    { value: 'CET', label: '🇪🇺 CET (GMT+1)' }, { value: 'EET', label: '🌅 EET (GMT+2)' },
    { value: 'IST', label: '🇮🇳 IST (GMT+5:30)' }, { value: 'JST', label: '🇯🇵 JST (GMT+9)' },
    { value: 'AEST', label: '🇦🇺 AEST (GMT+10)' }, { value: 'NZST', label: '🇳🇿 NZST (GMT+12)' },
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
        style={{ width: '100%', backgroundColor: '#1a1a1a', border: '1px solid #aa00ff',
          borderRadius: '10px', padding: '12px', color: '#fff', fontSize: '14px',
          marginBottom: '12px', cursor: 'pointer', outline: 'none' }}>
        {timezones.map(tz => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
      </select>
      <div className="button-group">
        <button className="button-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button className="button-cancel" onClick={() => { setSelectedTimezone(currentTimezone); setEditing(false); }}>
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
    { value: 'afk',           label: '💤 Afk',           description: 'User is in AFK channel' },
    { value: 'self_mute',     label: '🔇 Self Mute',     description: 'User muted themselves' },
    { value: 'self_deafen',   label: '🎧 Self Deafen',   description: 'User deafened themselves' },
    { value: 'server_mute',   label: '⛔ Server Mute',   description: 'User was muted by moderation' },
    { value: 'server_deafen', label: '🔊 Server Deafen', description: 'User was deafened by moderation' },
    { value: 'streaming',     label: '📺 Streaming',     description: 'User is streaming' },
    { value: 'video',         label: '🎥 Video',         description: 'User has video open' },
    { value: 'suppressed',    label: '🤫 Suppressed',    description: 'Stage audience member' },
  ];

  const handleToggleState = (stateValue) => {
    setSelectedStates(prev =>
      prev.includes(stateValue) ? prev.filter(s => s !== stateValue) : [...prev, stateValue]
    );
  };

  const handleSave = async () => {
    if (JSON.stringify(selectedStates.sort()) !== JSON.stringify((currentStates || []).sort())) {
      await onSave(selectedStates); setEditing(false);
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
          <button className="setting-change-btn" onClick={() => setEditing(true)}>Configure</button>
        </div>
        <p className="setting-note">Voice states determine which voice activities are tracked</p>
      </div>
    );
  }

  return (
    <div>
      <div className="voice-states-grid">
        {voiceStateOptions.map(option => (
          <div key={option.value}
            className={`voice-state-option ${selectedStates.includes(option.value) ? 'selected' : ''}`}
            onClick={() => handleToggleState(option.value)}>
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
        <button className="button-cancel" onClick={() => { setSelectedStates(currentStates || []); setEditing(false); }}>
          Cancel
        </button>
      </div>
    </div>
  );
};

const BotFilterSetting = ({ enabled, onSave, saving }) => (
  <div>
    <div className="bot-filter-container">
      <div>
        <div className="bot-filter-text">{enabled ? '🤖 Filtering Bots' : '🤖 Including Bots'}</div>
        <div className="bot-filter-desc">
          {enabled ? 'Bots are currently filtered out from statistics' : 'Bots are currently included in statistics'}
        </div>
      </div>
      <button className={`bot-filter-button ${enabled ? 'filtering' : 'including'}`}
        onClick={() => onSave(!enabled)} disabled={saving}>
        {saving ? 'Updating...' : enabled ? 'Include Bots' : 'Filter Bots'}
      </button>
    </div>
  </div>
);

const PermissionLevelSetting = ({ currentLevel, onSave, saving }) => {
  const [selectedLevel, setSelectedLevel] = useState(currentLevel);
  const permissionLevels = [
    { value: 'All',              icon: '🌍', shortDesc: 'Anyone can use all commands' },
    { value: 'Default',          icon: '⚙️', shortDesc: 'Most commands for everyone, admin for reset' },
    { value: 'User Restriction', icon: '👤', shortDesc: 'Commands limited to own account' },
    { value: 'Moderator',        icon: '🛡️', shortDesc: 'Manage Server permission required' },
    { value: 'Admin',            icon: '👑', shortDesc: 'Admin permission required' },
  ];
  return (
    <div>
      <div className="permission-boxes">
        {permissionLevels.map(level => (
          <div key={level.value}
            className={`permission-box ${selectedLevel === level.value ? 'selected' : ''}`}
            onClick={() => setSelectedLevel(level.value)}>
            <span className="permission-box-icon">{level.icon}</span>
            <div className="permission-box-name">{level.value}</div>
          </div>
        ))}
      </div>
      {selectedLevel !== currentLevel && (
        <div className="button-group" style={{ marginTop: '16px' }}>
          <button className="button-save" onClick={() => onSave(selectedLevel)} disabled={saving}>
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
    { value: 'Public',    icon: '🌍', shortDesc: 'Any authenticated user can view' },
    { value: 'Member',    icon: '👥', shortDesc: 'Manage Server or Administrator required' },
    { value: 'Moderator', icon: '🛡️', shortDesc: 'Manage Server or Administrator required' },
    { value: 'Admin',     icon: '👑', shortDesc: 'Administrator permission required' },
  ];
  return (
    <div>
      <div className="access-boxes">
        {accessLevels.map(level => (
          <div key={level.value}
            className={`access-box ${selectedLevel === level.value ? 'selected' : ''}`}
            onClick={() => setSelectedLevel(level.value)}>
            <span className="access-box-icon">{level.icon}</span>
            <div className="access-box-name">{level.value}</div>
          </div>
        ))}
      </div>
      {selectedLevel !== currentLevel && (
        <div className="button-group" style={{ marginTop: '16px' }}>
          <button className="button-save" onClick={() => onSave(selectedLevel)} disabled={saving}>
            {saving ? 'Saving...' : 'Apply Changes'}
          </button>
        </div>
      )}
    </div>
  );
};

const SimpleCalendar = ({ onSelectDate, currentDate, onClose }) => {
  const [currentMonth, setCurrentMonth] = useState(currentDate ? new Date(currentDate) : new Date());
  const getDaysInMonth = (date) => new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  const getFirstDayOfMonth = (date) => new Date(date.getFullYear(), date.getMonth(), 1).getDay();
  const handleDateSelect = (day) => { onSelectDate(new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day)); onClose(); };
  const changeMonth = (delta) => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1));
  const daysInMonth = getDaysInMonth(currentMonth);
  const firstDay = getFirstDayOfMonth(currentMonth);
  const days = [];
  let startOffset = firstDay === 0 ? 6 : firstDay - 1;
  for (let i = 0; i < startOffset; i++) days.push(<div key={`empty-${i}`} style={{ padding: '8px' }}></div>);
  for (let i = 1; i <= daysInMonth; i++) {
    const isSelected = currentDate && currentDate.getDate() === i &&
      currentDate.getMonth() === currentMonth.getMonth() &&
      currentDate.getFullYear() === currentMonth.getFullYear();
    days.push(
      <div key={i} onClick={() => handleDateSelect(i)}
        style={{ padding: '8px', textAlign: 'center', cursor: 'pointer', borderRadius: '6px',
          backgroundColor: isSelected ? '#aa00ff' : 'transparent',
          color: isSelected ? '#fff' : '#e0e0e0', transition: 'all 0.2s ease' }}
        onMouseEnter={(e) => { if (!isSelected) e.target.style.backgroundColor = '#2a2a2a'; }}
        onMouseLeave={(e) => { if (!isSelected) e.target.style.backgroundColor = 'transparent'; }}>
        {i}
      </div>
    );
  }
  const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  return (
    <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: '8px', backgroundColor: '#1a1a1a',
      border: '1px solid #aa00ff', borderRadius: '12px', padding: '16px', zIndex: 1000,
      boxShadow: '0 4px 20px rgba(0,0,0,0.3)', minWidth: '280px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <button onClick={() => changeMonth(-1)} style={{ background: 'none', border: 'none', color: '#aa00ff', cursor: 'pointer', fontSize: '18px', padding: '4px 8px' }}>◀</button>
        <span style={{ color: '#fff', fontWeight: 'bold' }}>{monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}</span>
        <button onClick={() => changeMonth(1)} style={{ background: 'none', border: 'none', color: '#aa00ff', cursor: 'pointer', fontSize: '18px', padding: '4px 8px' }}>▶</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px', marginBottom: '8px' }}>
        {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day => (
          <div key={day} style={{ textAlign: 'center', color: '#888', fontSize: '12px', padding: '4px' }}>{day}</div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px' }}>{days}</div>
    </div>
  );
};

const TimePeriodSetting = ({ settings, onSave, saving }) => {
  const [editing, setEditing] = useState(false);
  const [timeMode, setTimeMode] = useState(settings.default_time_mode || 'all_time');
  const [daysBack, setDaysBack] = useState(settings.default_days_back || 7);
  const [fromDate, setFromDate] = useState(settings.default_from_date ? new Date(settings.default_from_date) : null);
  const [toDate, setToDate] = useState(settings.default_to_date ? new Date(settings.default_to_date) : null);
  const [rollingType, setRollingType] = useState(settings.default_rolling_type || 'weekday');
  const [rollingValue, setRollingValue] = useState(settings.default_rolling_value || 0);
  const [showFromCalendar, setShowFromCalendar] = useState(false);
  const [showToCalendar, setShowToCalendar] = useState(false);
  const [validationError, setValidationError] = useState(null);

  const formatDateForDisplay = (date) => {
    if (!date) return '';
    return `${String(date.getDate()).padStart(2,'0')}-${String(date.getMonth()+1).padStart(2,'0')}-${date.getFullYear()}`;
  };
  const parseDateFromString = (dateStr) => {
    if (!dateStr) return null;
    const parts = dateStr.split('-');
    if (parts.length === 3) return new Date(parts[2], parts[1] - 1, parts[0]);
    return null;
  };
  const getPreviewText = () => {
    const mode = settings.default_time_mode || 'all_time';
    if (mode === 'all_time') return 'All Time';
    if (mode === 'days_back') return `Last ${settings.default_days_back || 7} days`;
    if (mode === 'date_range') {
      const from = settings.default_from_date ? formatDateForDisplay(new Date(settings.default_from_date)) : 'Start';
      const to   = settings.default_to_date   ? formatDateForDisplay(new Date(settings.default_to_date))   : 'End';
      return `${from} to ${to}`;
    }
    if (mode === 'rolling_window') {
      if (settings.default_rolling_type === 'weekday') {
        const weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
        return `Rolling — every ${weekdays[settings.default_rolling_value || 0]}`;
      }
      const n = settings.default_rolling_value || 1;
      const ord = n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : `${n}th`;
      return `Rolling — ${ord} of each month`;
    }
    return 'All Time';
  };
  const validateSettings = () => {
    if (timeMode === 'days_back' && (!daysBack || daysBack < 1 || daysBack > 3650)) {
      setValidationError('Days back must be between 1 and 3650'); return false;
    }
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
    if (!validateSettings()) return;
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
    setToDate(settings.default_to_date ? new Date(settings.default_to_date) : null);
    setRollingType(settings.default_rolling_type || 'weekday');
    setRollingValue(settings.default_rolling_value || 0);
    setValidationError(null); setEditing(false);
  };

  if (!editing) {
    return (
      <div>
        <div className="setting-preview">
          <span className="setting-value">{getPreviewText()}</span>
          <button className="setting-change-btn" onClick={() => setEditing(true)}>Change</button>
        </div>
        <p className="setting-note">Default time period used across bot commands and dashboard</p>
      </div>
    );
  }

  return (
    <div>
      <div className="permission-boxes" style={{ marginBottom: '20px' }}>
        {[
          { value: 'all_time',       label: 'All Time',       icon: '🕒' },
          { value: 'days_back',      label: 'Days Back',      icon: '📅' },
          { value: 'date_range',     label: 'Date Range',     icon: '📆' },
          { value: 'rolling_window', label: 'Rolling Window', icon: '🔄' },
        ].map(mode => (
          <div key={mode.value}
            className={`permission-box ${timeMode === mode.value ? 'selected' : ''}`}
            onClick={() => setTimeMode(mode.value)}>
            <span className="permission-box-icon">{mode.icon}</span>
            <div className="permission-box-name">{mode.label}</div>
          </div>
        ))}
      </div>

      {timeMode === 'all_time' && (
        <div style={{ marginBottom: '16px', padding: '12px', backgroundColor: '#1a1a1a', borderRadius: '8px' }}>
          <span style={{ color: '#888', fontSize: '13px' }}>📊 No time filter — all historical data will be used.</span>
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
              { label: 'From Date (optional)', date: fromDate, setDate: setFromDate, show: showFromCalendar, setShow: setShowFromCalendar },
              { label: 'To Date (optional)',   date: toDate,   setDate: setToDate,   show: showToCalendar,   setShow: setShowToCalendar   },
            ].map(({ label, date, setDate, show, setShow }) => (
              <div key={label} style={{ flex: 1, position: 'relative' }}>
                <div style={{ marginBottom: '4px', color: '#888', fontSize: '12px' }}>{label}</div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input type="text" value={date ? formatDateForDisplay(date) : ''}
                    onChange={(e) => setDate(parseDateFromString(e.target.value))}
                    placeholder="DD-MM-YYYY" className="setting-input" style={{ flex: 1 }} />
                  <button onClick={() => setShow(!show)}
                    style={{ backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: '10px',
                      padding: '0 12px', cursor: 'pointer', fontSize: '20px' }}>
                    📅
                  </button>
                </div>
                {show && <SimpleCalendar onSelectDate={(d) => { setDate(d); setShow(false); }}
                  currentDate={date} onClose={() => setShow(false)} />}
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
                style={{ flex: 1, padding: '10px', textAlign: 'center', cursor: 'pointer',
                  backgroundColor: rollingType === type ? '#2a2a2a' : '#1a1a1a',
                  border: `2px solid ${rollingType === type ? '#aa00ff' : '#2a2a2a'}`,
                  borderRadius: '8px', fontWeight: rollingType === type ? 'bold' : 'normal' }}>
                {type === 'weekday' ? 'Day of Week' : 'Day of Month'}
              </div>
            ))}
          </div>
          {rollingType === 'weekday' ? (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
              {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day, index) => (
                <div key={day} onClick={() => setRollingValue(index)}
                  style={{ padding: '8px 12px', cursor: 'pointer', fontSize: '13px', borderRadius: '8px',
                    backgroundColor: rollingValue === index ? '#aa00ff' : '#1a1a1a',
                    border: `1px solid ${rollingValue === index ? '#aa00ff' : '#2a2a2a'}`,
                    color: rollingValue === index ? '#fff' : '#e0e0e0', transition: 'all 0.2s ease' }}>
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
        <button className="button-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
        <button className="button-cancel" onClick={handleCancel}>Cancel</button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Access denied
// ─────────────────────────────────────────────────────────────

const AccessDenied = ({ accessLevel }) => {
  let requiredPermission = "Administrator";
  if (accessLevel === 'Member' || accessLevel === 'Moderator') requiredPermission = "Manage Server or Administrator";
  return (
    <div className="dashboard-content">
      <div className="error-message-container">
        <div className="error-icon">🔒</div>
        <h2 className="error-title">Access Denied</h2>
        <p className="error-message">This server requires <strong>{requiredPermission}</strong> permission to view settings.</p>
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
    const colors = {
      success: { bg: '#00b894', icon: '✅' },
      error:   { bg: '#ff7675', icon: '❌' },
      info:    { bg: '#0984e3', icon: 'ℹ️'  },
    };
    const color = colors[toast.type] || colors.info;
    return (
      <div className="toast-message" style={{ backgroundColor: color.bg }}>
        <span>{color.icon}</span>
        <span>{toast.message}</span>
        <button onClick={() => setToast(null)}
          style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', marginLeft: '10px', fontSize: '16px' }}>✕</button>
      </div>
    );
  };

  useEffect(() => { loadInitialData(); }, []);

  const loadInitialData = async () => {
    setLoadingServers(true); setApiError(null); setHasAccess(null);
    try {
      const authResponse = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include', headers: { 'Accept': 'application/json' },
      });
      if (!authResponse.ok) throw new Error('Auth failed');
      const authData = await authResponse.json();

      if (authData.authenticated && authData.user) {
        setIsAuthenticated(true);
        setCurrentUserId(authData.user.id);
        if (isPrivilegedUser(authData.user.id)) {
          setHasAccess(true); setAccessLevel('Admin'); window.accessLevel = 'Admin';
        }

        const serversResponse = await fetch(`${API_BASE_URL}/api/user/servers`, {
          credentials: 'include', headers: { 'Accept': 'application/json' },
        });
        if (serversResponse.ok) {
          const servers = await serversResponse.json();
          if (Array.isArray(servers) && servers.length > 0) {
            let selectedServer = authData.user.selected_server
              ? servers.find(s => s.id === authData.user.selected_server)
              : null;
            if (!selectedServer) selectedServer = servers[0];
            if (selectedServer) {
              setCurrentServer(selectedServer);
              if (!isPrivilegedUser(authData.user.id)) {
                await checkAndLoadSettings(selectedServer.id, selectedServer.permissions, selectedServer.has_admin, selectedServer.has_manage_server);
              } else {
                await loadSettingsOnly(selectedServer.id);
              }
            } else { setLoading(false); }
          } else { setLoading(false); }
        } else { setLoading(false); }
      } else { setLoading(false); }
    } catch (error) {
      setApiError('Failed to load servers. Please check your connection.');
      setLoading(false);
    } finally { setLoadingServers(false); }
  };

  const loadSettingsOnly = async (guildId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/get`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include', body: JSON.stringify({ guild_id: guildId }),
      });
      if (res.ok) {
        const d = await res.json();
        setSettings(d);
        setAccessLevel(d.dashboard_access_level || 'Member');
      } else { showToast('Failed to load settings', 'error'); }
    } catch { showToast('Error loading settings', 'error'); }
    finally { setLoading(false); }
  };

  const checkAndLoadSettings = async (guildId, permissions, hasAdmin, hasManageServer) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/get`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include', body: JSON.stringify({ guild_id: guildId }),
      });
      if (res.ok) {
        const d = await res.json();
        setSettings(d);
        const lvl = d.dashboard_access_level || 'Member';
        setAccessLevel(lvl);
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
      const res = await fetch(`${API_BASE_URL}/api/settings/update`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: currentServer.id, setting, value }),
      });
      const result = await res.json();
      if (result.success) {
        setSettings(prev => ({ ...prev, [setting]: value }));
        showToast(`Successfully updated ${settingDisplayNames[setting] || setting}`, 'success');
        return true;
      } else { showToast(result.message || 'Failed to update setting', 'error'); return false; }
    } catch { showToast(`Error updating ${settingDisplayNames[setting] || setting}`, 'error'); return false; }
    finally { setSaving(prev => ({ ...prev, [setting]: false })); }
  };

  const updateTimePeriod = async (timePeriodData) => {
    if (!currentServer) return false;
    setSaving(prev => ({ ...prev, timePeriod: true }));
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/time-period/update`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: currentServer.id, ...timePeriodData }),
      });
      const result = await res.json();
      if (result.success) {
        setSettings(prev => ({ ...prev, ...timePeriodData }));
        showToast('Successfully updated time period settings', 'success');
        return true;
      } else { showToast(result.message || 'Failed to update time period settings', 'error'); return false; }
    } catch { showToast('Error updating time period settings', 'error'); return false; }
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
        <div className="no-server"><h2>Please Log In</h2><p>You need to be logged in to configure settings.</p>
          <a href={`${API_BASE_URL}/api/auth/discord`} className="login-button">Login with Discord</a>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (!currentServer) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="no-server"><h2>No Server Available</h2><p>Add the bot to a Discord server to configure settings.</p>
          <a href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands"
            className="invite-button" target="_blank" rel="noopener noreferrer">Invite Bot to Server</a>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (apiError) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="error-message-container"><div className="error-icon">⚠️</div>
          <h2 className="error-title">Error Loading Data</h2>
          <p className="error-message">{apiError}</p>
          <button onClick={() => window.location.reload()} className="invite-button">Retry</button>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  // ── main render ───────────────────────────────────────────
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
                    <SettingsCard title="Prefix" icon="⚙️" description="Change the bot's command prefix">
                      <PrefixSetting currentPrefix={settings.prefix}
                        onSave={(v) => updateSetting('prefix', v)} saving={saving.prefix} />
                    </SettingsCard>

                    <SettingsCard title="Timezone" icon="🌍" description="Set the timezone for time-based statistics">
                      <TimezoneSetting currentTimezone={settings.timezone}
                        onSave={(v) => updateSetting('timezone', v)} saving={saving.timezone} />
                    </SettingsCard>

                    <SettingsCard title="Voice States" icon="🔊" description="Choose which voice states to track">
                      <VoiceStatesSetting currentStates={settings.voice_states}
                        onSave={(v) => updateSetting('voice_states', v)} saving={saving.voiceStates} />
                    </SettingsCard>

                    <SettingsCard title="Bot Filter" icon="🤖" description="Filter bots from statistics">
                      <BotFilterSetting enabled={settings.bot_filter}
                        onSave={(v) => updateSetting('bot_filter', v)} saving={saving.botFilter} />
                    </SettingsCard>

                    <SettingsCard
                      title="Command Permission Access Level" icon="🔐"
                      description="Control who can use bot commands"
                      infoDescriptions={[
                        { level: 'All',              description: 'All members regardless of their permissions are allowed to use any command on the bot including sensitive commands like reset and blacklist' },
                        { level: 'Default',          description: 'The default access level that restricts or enables specific commands for users with specific permissions. All commands on the bot are usable by normal members except for blacklist and settings being accessible via manage server, and reset commands being accessible via administrator permissions' },
                        { level: 'User Restriction', description: 'Mostly the same as Default except users can only use commands that have the user scope on their own account only' },
                        { level: 'Moderator',        description: 'Only users with the Manage Server permission can use any commands on the bot' },
                        { level: 'Admin',            description: 'Only users with the administrator permission can use any commands on the bot' },
                      ]}>
                      <PermissionLevelSetting currentLevel={settings.permission_level}
                        onSave={(v) => updateSetting('permission_level', v)} saving={saving.permissionLevel} />
                    </SettingsCard>

                    <SettingsCard
                      title="Dashboard Access Level" icon="📊"
                      description="Control who can view the web dashboard"
                      infoDescriptions={[
                        { level: 'Public',    description: 'Any member of the server can view the entire dashboard including the optimization section.' },
                        { level: 'Member',    description: 'Members of the server can view the analytics section of the dashboard but they need the Manage Server or Administrator permissions to view the optimization section.' },
                        { level: 'Moderator', description: 'Manage Server or Administrator permission required to view either the analytics or optimization sections of the dashboard.' },
                        { level: 'Admin',     description: 'Administrator permission required to view either the analytics or optimization sections of the dashboard.' },
                      ]}>
                      <DashboardAccessSetting currentLevel={settings.dashboard_access_level || 'Member'}
                        onSave={(v) => updateSetting('dashboard_access_level', v)} saving={saving.dashboardAccess} />
                    </SettingsCard>

                    <SettingsCard
                      title="Time Period" icon="🕐"
                      description="Set the default time period used across bot commands and the dashboard"
                      infoDescriptions={[
                        { level: 'All Time',       description: 'No time filter — all historical data is used' },
                        { level: 'Days Back',       description: 'Show data from the last X days (1-3650 days)' },
                        { level: 'Date Range',      description: 'Show data between specific dates (open-ended allowed)' },
                        { level: 'Rolling Window',  description: 'Show data for a specific recurring day (weekly or monthly)' },
                      ]}>
                      <TimePeriodSetting settings={settings}
                        onSave={(data) => updateTimePeriod(data)} saving={saving.timePeriod} />
                    </SettingsCard>

                    {/* ── History Data Sync — full width ── */}
                    <SettingsCard
                      title="History Data Sync" icon="🗄️"
                      description="Backfill historical message, mention, and emoji data into the stats database. Select which stat types to sync, then start, pause, or reset individual channels."
                      fullWidth
                      infoDescriptions={[
                        { level: 'Initialise', description: 'Seeds all text channels in the server as pending — run this first on a new server so the channel list appears.' },
                        { level: 'Sync All',   description: 'Kicks off a background sync for every channel simultaneously using the selected stat types.' },
                        { level: 'Pause',      description: 'Stops a running sync mid-page and saves the cursor so it can be resumed later from where it left off.' },
                        { level: 'Cancel',     description: 'Stops a running sync. Mechanically identical to Pause — progress is preserved, intent is different.' },
                        { level: 'Reset',      description: 'Wipes the stored ceiling for chosen stat types so the next sync does a full re-scan from scratch.' },
                      ]}>
                      <HistorySyncSection
                        guildId={currentServer.id}
                        showToast={showToast}
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