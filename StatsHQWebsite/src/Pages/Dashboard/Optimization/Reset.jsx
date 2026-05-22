import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";

// API base URL
const API_BASE_URL = '';
const NAVBAR_HEIGHT = "80px";

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ============================================
// ADVANCED CACHING SYSTEM
// ============================================

// Enhanced cache for server data with size limits and TTL
class ServerDataCache {
  constructor(maxSize = 30, ttl = 5 * 60 * 1000) {
    this.cache = new Map();
    this.maxSize = maxSize;
    this.TTL = ttl;
  }

  set(key, value) {
    if (this.cache.size >= this.maxSize) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
    }
    this.cache.set(key, {
      data: value,
      timestamp: Date.now()
    });
  }

  get(key) {
    const entry = this.cache.get(key);
    if (entry && (Date.now() - entry.timestamp < this.TTL)) {
      return entry.data;
    }
    if (entry) {
      this.cache.delete(key);
    }
    return null;
  }

  clear() {
    this.cache.clear();
  }

  clearPattern(pattern) {
    for (const [key, value] of this.cache) {
      if (key.includes(pattern)) {
        this.cache.delete(key);
      }
    }
  }
}

// Initialize cache
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);

// Stable cache key generator
const getCacheKey = (type, id, params) => {
  const sortObject = (obj) => {
    if (!obj || typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) return obj.map(sortObject);
    
    return Object.keys(obj)
      .sort()
      .reduce((result, key) => {
        result[key] = sortObject(obj[key]);
        return result;
      }, {});
  };
  
  const sortedParams = sortObject(params || {});
  return `${type}:${id}:${JSON.stringify(sortedParams)}`;
};

// Access Denied Component - UPDATED TO MATCH SETTINGS STYLE
const AccessDenied = () => {
  let requiredPermission = "Administrator";
  const accessLevel = window.accessLevel || 'Member';
  
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
        <p className="error-message">You don't have permission to reset statistics for this server.</p>
        <p className="error-message">This server requires <strong>{requiredPermission}</strong> permission to reset statistics.</p>
      </div>
    </div>
  );
};

// Loading spinner component
const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
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

// Styles
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
    overflow-x: hidden;
  }

  body {
    min-height: 100vh;
    margin: 0;
    padding: 0;
    background-color: #0a0a0a;
    color: #ffffff;
    overflow-y: auto;
    overflow-x: hidden;
    width: 100%;
  }

  #app {
    min-height: 100vh;
    background-color: #0a0a0a;
    overflow-x: hidden;
    width: 100%;
  }

  .dashboard-page {
    max-width: 100%;
    margin: 0 auto;
    background-color: #0a0a0a;
    color: #ffffff;
    min-height: 100vh;
    display: flex;
    position: relative;
    overflow-x: hidden;
  }

  .dashboard-main {
    flex: 1;
    margin-left: 280px;
    background-color: #0a0a0a;
    min-height: 100vh;
    overflow-x: hidden;
    width: 100%;
  }

  .dashboard-content {
    max-width: 1600px;
    margin: 0 auto;
    padding: 20px 40px 40px 40px;
    background-color: #0a0a0a;
    overflow-x: hidden;
    width: 100%;
    box-sizing: border-box;
  }

  .view-selector {
    display: flex;
    gap: 12px;
    margin-bottom: 32px;
    flex-wrap: wrap;
  }

  .view-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 24px;
    font-size: 16px;
    font-weight: 500;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .view-button:hover {
    border-color: #aa00ff;
    color: #ffffff;
    transform: translateY(-2px);
  }

  .view-button.active {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border-color: #aa00ff;
    color: white;
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
  }

  .scope-selector-section {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 32px;
  }

  .section-title {
    color: #ffffff;
    font-size: 24px;
    font-weight: 600;
    margin: 0 0 20px 0;
    position: relative;
    display: inline-block;
  }

  .section-title::after {
    content: '';
    position: absolute;
    bottom: -8px;
    left: 0;
    width: 60px;
    height: 3px;
    background-color: #aa00ff;
    border-radius: 2px;
  }

  .scope-controls {
    display: flex;
    gap: 20px;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .scope-selector {
    flex: 1;
    min-width: 250px;
  }

  .scope-dropdown-wrapper {
    position: relative;
  }

  .scope-dropdown {
    width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    cursor: pointer;
    outline: none;
    transition: all 0.2s ease;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23aa00ff'%3e%3cpath d='M7 10l5 5 5-5z'/%3e%3c/svg%3e");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 20px;
  }

  .scope-dropdown option {
    background-color: #1a1a1a;
    color: #ffffff;
    padding: 12px;
  }

  .scope-dropdown:focus {
    border-color: #aa00ff;
    box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
  }

  .entity-selector-wrapper {
    flex: 2;
    min-width: 250px;
    max-width: 100%;
    width: 100%;
  }

  .entity-selector-input-wrapper {
    position: relative;
    width: 100%;
    max-width: 100%;
  }

  .entity-search-input {
    width: 100%;
    max-width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    outline: none;
    transition: all 0.2s ease;
    box-sizing: border-box;
  }

  .entity-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    width: 100%;
    max-width: 100%;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    margin-top: 8px;
    max-height: 300px;
    overflow-y: auto;
    overflow-x: hidden;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    box-sizing: border-box;
  }

  .entity-option {
    padding: 12px 16px;
    color: #ffffff;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid #2a2a2a;
    width: 100%;
    box-sizing: border-box;
  }

  .entity-option-info {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  .entity-name {
    font-weight: 500;
    color: #ffffff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .entity-subtext {
    color: #888;
    font-size: 12px;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .selected-entity-info {
    margin-top: 12px;
    padding: 12px;
    background-color: #1a1a1a;
    border-radius: 8px;
    border-left: 3px solid #aa00ff;
    font-size: 14px;
    word-break: break-word;
    overflow-wrap: break-word;
    max-width: 100%;
    box-sizing: border-box;
  }

  .selected-entity-label {
    color: #aa00ff;
    font-weight: 600;
    margin-right: 8px;
  }

  .stat-types-section {
    margin-top: 24px;
  }

  .stat-types-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
  }

  .action-buttons-group {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }

  .action-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .action-button:hover {
    border-color: #aa00ff;
    color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
  }

  .selection-counter {
    background-color: #1a1a1a;
    border: 1px solid #aa00ff;
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    color: #aa00ff;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .stat-types-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }

  .stat-card {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .stat-card:hover {
    border-color: #aa00ff;
    background-color: #222;
    transform: translateY(-2px);
  }

  .stat-card.selected {
    border-color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
  }

  .stat-card-content {
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }

  .stat-checkbox {
    width: 18px;
    height: 18px;
    margin-top: 2px;
    cursor: pointer;
    accent-color: #aa00ff;
    flex-shrink: 0;
  }

  .stat-info {
    flex: 1;
  }

  .stat-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    flex-wrap: wrap;
  }

  .stat-emoji {
    font-size: 20px;
  }

  .stat-label {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
  }

  .stat-badge {
    font-size: 10px;
    background-color: rgba(255, 68, 68, 0.2);
    padding: 2px 8px;
    border-radius: 12px;
    color: #ff8888;
  }

  .stat-description {
    font-size: 12px;
    color: #888;
    line-height: 1.4;
  }

  .reset-button-container {
    display: flex;
    justify-content: flex-end;
    margin-top: 32px;
  }

  .reset-button {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 14px 32px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .reset-button:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.4);
  }

  .reset-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .results-section {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 24px;
    margin-top: 32px;
    overflow: hidden;
  }

  .results-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 16px;
  }

  .results-title {
    font-size: 18px;
    font-weight: 600;
    color: #aa00ff;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .results-stats {
    font-size: 13px;
    color: #888;
    background-color: #1a1a1a;
    padding: 4px 12px;
    border-radius: 20px;
  }

  .results-table-wrapper {
    overflow-x: auto;
    width: 100%;
    max-width: 100%;
  }

  .results-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: auto;
    min-width: 100%;
  }

  .results-table th,
  .results-table td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid #1a1a1a;
    word-break: break-word;
  }

  .results-table th {
    background-color: #0f0f0f;
    color: #aa00ff;
    font-weight: 600;
    font-size: 13px;
    white-space: nowrap;
  }

  .results-table tr:hover {
    background-color: #1a1a1a;
  }

  .success-badge {
    background-color: rgba(0, 184, 148, 0.2);
    color: #00b894;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
    white-space: nowrap;
  }

  .error-badge {
    background-color: rgba(255, 118, 117, 0.2);
    color: #ff7675;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
    white-space: nowrap;
  }

  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 16px;
  }

  .modal {
    background-color: #1a1a1a;
    border-radius: 16px;
    max-width: 500px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    padding: 24px;
    border: 1px solid #2a2a2a;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }

  .modal-title {
    font-size: 20px;
    font-weight: 600;
    color: #ff4444;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .modal-close {
    background: none;
    border: none;
    color: #888;
    font-size: 24px;
    cursor: pointer;
    flex-shrink: 0;
  }

  .modal-close:hover {
    color: #ff4444;
  }

  .warning-box {
    background-color: rgba(255, 68, 68, 0.1);
    border: 1px solid #ff4444;
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    word-break: break-word;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
    flex-wrap: wrap;
  }

  .modal-cancel {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 10px 20px;
    color: #ffffff;
    cursor: pointer;
  }

  .modal-cancel:hover {
    border-color: #aa00ff;
  }

  .modal-confirm {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    color: white;
    cursor: pointer;
    font-weight: 600;
  }

  .modal-confirm:hover {
    transform: translateY(-2px);
    box-shadow: 0 2px 8px rgba(170, 0, 255, 0.3);
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
    margin-top: 0;
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

  .invite-button, .login-button {
    display: inline-block;
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white;
    padding: 12px 28px;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 600;
    margin-top: 20px;
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

  .loading-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid white;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    display: inline-block;
  }

  .user-avatar-small {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    object-fit: cover;
  }

  @media (max-width: 1024px) {
    .dashboard-main {
      margin-left: 250px;
    }
    .dashboard-content {
      padding: 30px;
    }
    .scope-controls {
      flex-direction: column;
    }
    .entity-selector-wrapper {
      width: 100%;
    }
    .stat-types-grid {
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    }
  }

  @media (max-width: 768px) {
    .dashboard-main {
      margin-left: 0;
      width: 100%;
    }
    .dashboard-content {
      padding: 16px;
      width: 100%;
    }
    .view-selector {
      flex-direction: column;
    }
    .view-button {
      text-align: center;
    }
    .stat-types-grid {
      grid-template-columns: 1fr;
    }
    .stat-types-header {
      flex-direction: column;
      align-items: flex-start;
    }
    .scope-selector-section {
      padding: 16px;
    }
    .results-section {
      padding: 16px;
      margin-left: -16px;
      margin-right: -16px;
      width: calc(100% + 32px);
      border-radius: 0;
      border-left: none;
      border-right: none;
    }
    .results-table th,
    .results-table td {
      padding: 10px 12px;
      font-size: 13px;
    }
    .results-table th:nth-child(3),
    .results-table td:nth-child(3) {
      max-width: 150px;
    }
    .action-buttons-group {
      width: 100%;
    }
    .action-button {
      flex: 1;
      justify-content: center;
    }
    .reset-button-container {
      justify-content: center;
    }
    .reset-button {
      width: 100%;
      justify-content: center;
    }
    .selected-entity-info {
      font-size: 13px;
    }
    .modal {
      margin: 16px;
      width: calc(100% - 32px);
    }
  }

  @media (max-width: 480px) {
    .dashboard-content {
      padding: 12px;
    }
    .results-section {
      margin-left: -12px;
      margin-right: -12px;
      width: calc(100% + 24px);
    }
    .results-table th,
    .results-table td {
      padding: 8px 8px;
      font-size: 12px;
    }
    .results-table th:nth-child(2),
    .results-table td:nth-child(2) {
      max-width: 80px;
    }
    .success-badge, .error-badge {
      padding: 3px 6px;
      font-size: 10px;
    }
    .section-title {
      font-size: 20px;
    }
    .scope-selector-section {
      padding: 12px;
    }
    .stat-card {
      padding: 12px;
    }
    .entity-option {
      padding: 10px 12px;
    }
    .user-avatar-small {
      width: 28px;
      height: 28px;
    }
    .entity-name {
      font-size: 13px;
    }
    .entity-subtext {
      font-size: 11px;
    }
  }
`;

// Stat types configuration
const STAT_TYPES = {
  server: {
    all: { label: "All Statistics", description: "Reset ALL statistics (irreversible!)", emoji: "⚠️", serverWideOnly: false },
    messages: { label: "Messages", description: "Reset message tracking", emoji: "💬", serverWideOnly: false },
    "voice activity": { label: "Voice Activity", description: "Reset voice session history", emoji: "🔊", serverWideOnly: false },
    "invite tracking": { label: "Invite Tracking", description: "Reset invite tracking", emoji: "📨", serverWideOnly: true },
    "emoji stats": { label: "Emoji Stats", description: "Reset emoji usage", emoji: "😀", serverWideOnly: false },
    activity: { label: "Activity", description: "Reset activity tracking (sessions, streaks, logs)", emoji: "🎮", serverWideOnly: true },
    mentions: { label: "Mentions", description: "Reset user mentions", emoji: "📢", serverWideOnly: false },
    "role growth": { label: "Role Growth", description: "Reset role growth tracking", emoji: "👥", serverWideOnly: true },
    "member growth": { label: "Member Growth", description: "Reset member join/leave tracking", emoji: "📈", serverWideOnly: true }
  },
  user: {
    all: { label: "All Statistics", description: "Reset ALL statistics", emoji: "⚠️", serverWideOnly: false },
    messages: { label: "Messages", description: "Reset message tracking", emoji: "💬", serverWideOnly: false },
    "voice activity": { label: "Voice Activity", description: "Reset voice activity", emoji: "🔊", serverWideOnly: false },
    activity: { label: "Activity", description: "Reset activity tracking", emoji: "🎮", serverWideOnly: true },
    "invite tracking": { label: "Invite Tracking", description: "Reset invite tracking", emoji: "📨", serverWideOnly: true },
    "emoji stats": { label: "Emoji Stats", description: "Reset emoji usage", emoji: "😀", serverWideOnly: false },
    mentions: { label: "Mentions", description: "Reset mentions", emoji: "📢", serverWideOnly: false },
    "role growth": { label: "Role Growth", description: "Reset role growth tracking", emoji: "👥", serverWideOnly: true }
  }
};

// Helper function to filter stat types based on scope
const getFilteredStatTypes = (commandType, scope) => {
  const types = STAT_TYPES[commandType];
  if (!types) return [];
  
  return Object.entries(types)
    .filter(([key, config]) => {
      if (scope === "server") return true;
      return !config.serverWideOnly;
    })
    .map(([key, config]) => ({
      value: key,
      label: config.label,
      description: config.description,
      emoji: config.emoji
    }));
};

const ResetDashboard = () => {
  const [selectedView, setSelectedView] = useState("server");
  const [currentServer, setCurrentServer] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [actionLoading, setActionLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [toast, setToast] = useState(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [resetResults, setResetResults] = useState(null);
  
  // Scope selection
  const [scope, setScope] = useState("server");
  const [selectedStatTypes, setSelectedStatTypes] = useState([]);
  
  // Channel/Category selection
  const [channelSearch, setChannelSearch] = useState("");
  const [categorySearch, setCategorySearch] = useState("");
  const [channels, setChannels] = useState([]);
  const [filteredChannels, setFilteredChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [filteredCategories, setFilteredCategories] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false);
  
  // User selection for user view
  const [userSearch, setUserSearch] = useState("");
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  
  // Data loading flags
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [channelsLoaded, setChannelsLoaded] = useState(false);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);

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

  // Check if current user is privileged
  const isPrivilegedUser = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  // Check server access based on dashboard access level
  const checkServerAccess = async (guildId, hasAdmin, hasManageServer) => {
    try {
      const settingsResponse = await fetch(`${API_BASE_URL}/api/settings/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: guildId })
      });

      if (settingsResponse.ok) {
        const settingsData = await settingsResponse.json();
        const accessLevel = settingsData.dashboard_access_level || 'Member';
        setDashboardAccessLevel(accessLevel);
        window.accessLevel = accessLevel;
        
        const isAdmin = hasAdmin;
        const hasManageServerPerm = hasManageServer;
        
        let hasAccessFlag = false;
        
        if (accessLevel === 'Public') {
          hasAccessFlag = true;
        } else if (accessLevel === 'Member') {
          hasAccessFlag = isAdmin;
        } else if (accessLevel === 'Moderator') {
          hasAccessFlag = isAdmin || hasManageServerPerm;
        } else if (accessLevel === 'Admin') {
          hasAccessFlag = isAdmin;
        } else {
          hasAccessFlag = isAdmin;
        }
        
        setHasAccess(hasAccessFlag);
        
        if (!hasAccessFlag) {
        }
        
      } else {
        console.error('Failed to get settings for guild:', guildId);
        setHasAccess(false);
      }
    } catch (error) {
      console.error('Error checking server access:', error);
      setHasAccess(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (currentServer && hasAccess && initialLoadComplete) {
      loadData();
    }
  }, [currentServer, hasAccess]);

  useEffect(() => {
    if (scope !== "channel" && scope !== "category") {
      setSelectedChannel(null);
      setSelectedCategory(null);
      setChannelSearch("");
      setCategorySearch("");
    }
  }, [scope]);

  // Filter channels based on search
  useEffect(() => {
    if (channelSearch.trim() === "") {
      setFilteredChannels(channels);
    } else {
      const searchLower = channelSearch.toLowerCase();
      setFilteredChannels(channels.filter(channel => 
        channel.name?.toLowerCase().includes(searchLower) ||
        channel.id?.includes(searchLower)
      ));
    }
  }, [channelSearch, channels]);

  // Filter categories based on search
  useEffect(() => {
    if (categorySearch.trim() === "") {
      setFilteredCategories(categories);
    } else {
      const searchLower = categorySearch.toLowerCase();
      setFilteredCategories(categories.filter(category => 
        category.name?.toLowerCase().includes(searchLower) ||
        category.id?.includes(searchLower)
      ));
    }
  }, [categorySearch, categories]);

  // Filter users based on search
  useEffect(() => {
    if (userSearch.trim() === "") {
      setFilteredUsers(users);
    } else {
      const searchLower = userSearch.toLowerCase();
      setFilteredUsers(users.filter(user => 
        (user.display_name?.toLowerCase().includes(searchLower) ||
         user.username?.toLowerCase().includes(searchLower) ||
         user.global_name?.toLowerCase().includes(searchLower) ||
         user.id?.includes(searchLower))
      ));
    }
  }, [userSearch, users]);

  const loadInitialData = async () => {
    setLoadingServers(true);
    setApiError(null);
    setHasAccess(null);
    try {
      const authResponse = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (!authResponse.ok) throw new Error('Auth failed');
      
      const authData = await authResponse.json();
      
      if (authData.authenticated && authData.user) {
        setIsAuthenticated(true);
        setCurrentUserId(authData.user.id);
        
        // Check if user is privileged
        if (isPrivilegedUser(authData.user.id)) {
          setHasAccess(true);
          setDashboardAccessLevel('Admin');
          window.accessLevel = 'Admin';
          
          // Still need to get servers for privileged user
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
              }
            }
          }
          setInitialLoadComplete(true);
          setLoadingServers(false);
          return;
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
              await checkServerAccess(
                selectedServer.id, 
                selectedServer.has_admin, 
                selectedServer.has_manage_server
              );
            }
            setInitialLoadComplete(true);
          } else {
            setInitialLoadComplete(true);
          }
        } else {
          setInitialLoadComplete(true);
        }
      } else {
        setInitialLoadComplete(true);
      }
    } catch (error) {
      console.error('Error loading initial data:', error);
      setApiError('Failed to load servers. Please check your connection.');
      setInitialLoadComplete(true);
    } finally {
      setLoadingServers(false);
    }
  };

  const loadData = async () => {
    if (!currentServer || !hasAccess) return;
    
    setLoading(true);
    
    await Promise.all([
      fetchAllUsers(),
      fetchAllChannels(),
      fetchAllCategories()
    ]);
    
    setLoading(false);
  };

  const fetchAllUsers = async () => {
    try {
      const cacheKey = getCacheKey('reset-users', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setUsers(cached);
        setFilteredUsers(cached);
        setUsersLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-users?guild_id=${currentServer.id}&limit=500`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setUsers(data);
        setFilteredUsers(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching users:', error);
    } finally {
      setUsersLoaded(true);
    }
  };

  const fetchAllChannels = async () => {
    try {
      const cacheKey = getCacheKey('reset-channels', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setChannels(cached);
        setFilteredChannels(cached);
        setChannelsLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setChannels(data);
        setFilteredChannels(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching channels:', error);
    } finally {
      setChannelsLoaded(true);
    }
  };

  const fetchAllCategories = async () => {
    try {
      const cacheKey = getCacheKey('reset-categories', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setCategories(cached);
        setFilteredCategories(cached);
        setCategoriesLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setCategories(data);
        setFilteredCategories(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching categories:', error);
    } finally {
      setCategoriesLoaded(true);
    }
  };

  const handleStatTypeToggle = (statType) => {
    setSelectedStatTypes(prev => {
      if (prev.includes(statType)) {
        return prev.filter(t => t !== statType);
      } else {
        return [...prev, statType];
      }
    });
  };

  const handleSelectAll = () => {
    const availableTypes = getFilteredStatTypes(selectedView, scope);
    setSelectedStatTypes(availableTypes.map(t => t.value));
    showToast(`Selected all ${availableTypes.length} stat types`, 'info');
  };

  const handleClearAll = () => {
    setSelectedStatTypes([]);
    showToast('Cleared all selections', 'info');
  };

  const handleReset = async () => {
    if (selectedStatTypes.length === 0) {
      showToast("Please select at least one statistic type to reset", "error");
      return;
    }

    setShowConfirmModal(true);
  };

  const executeReset = async () => {
    setShowConfirmModal(false);
    setActionLoading(true);
    setResetResults(null);
    
    const results = [];
    
    try {
      for (const statType of selectedStatTypes) {
        let endpoint = "";
        let body = {};
        
        if (selectedView === "server") {
          endpoint = `${API_BASE_URL}/api/reset/server`;
          body = {
            guild_id: currentServer.id,
            stat_type: statType
          };
          
          if (scope === "channel" && selectedChannel) {
            body.channel_id = selectedChannel.id;
          } else if (scope === "category" && selectedCategory) {
            body.category_id = selectedCategory.id;
          }
        } else {
          if (!selectedUser) {
            showToast("Please select a user", "error");
            setActionLoading(false);
            return;
          }
          
          endpoint = `${API_BASE_URL}/api/reset/user`;
          body = {
            guild_id: currentServer.id,
            user_id: selectedUser.id,
            stat_type: statType
          };
          
          if (scope === "channel" && selectedChannel) {
            body.channel_id = selectedChannel.id;
          } else if (scope === "category" && selectedCategory) {
            body.category_id = selectedCategory.id;
          }
        }
        
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body)
        });
        
        const result = await response.json();
        
        results.push({
          statType,
          label: STAT_TYPES[selectedView][statType]?.label || statType,
          success: result.success,
          message: result.message,
          deleted_counts: result.deleted_counts
        });
      }
      
      setResetResults(results);
      
      // Clear relevant caches after reset
      serverDataCache.clearPattern('reset-users');
      serverDataCache.clearPattern('reset-channels');
      serverDataCache.clearPattern('reset-categories');
      
      const successCount = results.filter(r => r.success).length;
      if (successCount === results.length) {
        showToast(`Successfully reset ${successCount} statistic types`, "success");
      } else if (successCount > 0) {
        showToast(`Reset ${successCount}/${results.length} statistic types`, "info");
      } else {
        showToast("Failed to reset statistics", "error");
      }
      
    } catch (error) {
      console.error('Error resetting stats:', error);
      showToast("Failed to reset statistics", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const getScopeLabel = () => {
    if (scope === "server") return "the entire server";
    if (scope === "channel" && selectedChannel) return `channel #${selectedChannel.name}`;
    if (scope === "category" && selectedCategory) return `category ${selectedCategory.name}`;
    return "the selected scope";
  };

  const getResetDescription = () => {
    if (selectedView === "server") {
      return `Are you sure you want to reset ${selectedStatTypes.length} statistic type(s) from ${getScopeLabel()}?`;
    } else {
      const userName = selectedUser ? (selectedUser.display_name || selectedUser.username || selectedUser.global_name || selectedUser.name || selectedUser.id) : "this user";
      return `Are you sure you want to reset ${selectedStatTypes.length} statistic type(s) for ${userName} from ${getScopeLabel()}?`;
    }
  };

  // Loading state
  if (loadingServers || (isAuthenticated && !currentServer && !apiError && !initialLoadComplete)) {
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

  // Permission checking in progress
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
                <p>You need to be logged in to reset statistics.</p>
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
                <p>Add the bot to a Discord server to reset statistics.</p>
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

  // Access Denied
  if (hasAccess === false) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <AccessDenied />
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Error
  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message-container">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => window.location.reload()}>Retry</button>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  const availableStatTypes = getFilteredStatTypes(selectedView, scope);
  const selectedCount = selectedStatTypes.length;
  const hasSelection = selectedCount > 0;

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            {/* View Selector */}
            <div className="view-selector">
              <button 
                className={`view-button ${selectedView === "server" ? "active" : ""}`}
                onClick={() => {
                  setSelectedView("server");
                  setSelectedStatTypes([]);
                  setScope("server");
                  setSelectedUser(null);
                  setUserSearch("");
                }}
              >
                Server
              </button>
              <button 
                className={`view-button ${selectedView === "user" ? "active" : ""}`}
                onClick={() => {
                  setSelectedView("user");
                  setSelectedStatTypes([]);
                  setScope("server");
                  setSelectedUser(null);
                  setUserSearch("");
                }}
              >
                User
              </button>
            </div>

            {/* Scope Selector Section */}
            <div className="scope-selector-section">
              <h2 className="section-title">Select Scope</h2>
              <div className="scope-controls">
                <div className="scope-selector">
                  <div className="scope-dropdown-wrapper">
                    <select 
                      className="scope-dropdown"
                      value={scope}
                      onChange={(e) => {
                        setScope(e.target.value);
                        setSelectedStatTypes([]);
                      }}
                    >
                      <option value="server">Server</option>
                      <option value="channel">Channel</option>
                      <option value="category">Category</option>
                    </select>
                  </div>
                </div>
                
                {scope === "channel" && (
                  <div className="entity-selector-wrapper">
                    <div className="entity-selector-input-wrapper">
                      <input
                        type="text"
                        placeholder="Search channels by name or ID..."
                        value={channelSearch}
                        onChange={(e) => setChannelSearch(e.target.value)}
                        onFocus={() => setShowChannelDropdown(true)}
                        onBlur={() => setTimeout(() => setShowChannelDropdown(false), 200)}
                        className="entity-search-input"
                      />
                      {showChannelDropdown && filteredChannels.length > 0 && (
                        <div className="entity-dropdown">
                          {filteredChannels.slice(0, 20).map(channel => (
                            <div
                              key={channel.id}
                              className="entity-option"
                              onMouseDown={() => {
                                setSelectedChannel(channel);
                                setChannelSearch(channel.name);
                                setShowChannelDropdown(false);
                              }}
                            >
                              <div className="entity-option-info">
                                <span className="entity-name">#{channel.name}</span>
                              </div>
                              <span className="entity-subtext">ID: {channel.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {selectedChannel && (
                      <div className="selected-entity-info">
                        <span className="selected-entity-label">Selected Channel:</span>
                        #{selectedChannel.name} (ID: {selectedChannel.id})
                      </div>
                    )}
                  </div>
                )}
                
                {scope === "category" && (
                  <div className="entity-selector-wrapper">
                    <div className="entity-selector-input-wrapper">
                      <input
                        type="text"
                        placeholder="Search categories by name or ID..."
                        value={categorySearch}
                        onChange={(e) => setCategorySearch(e.target.value)}
                        onFocus={() => setShowCategoryDropdown(true)}
                        onBlur={() => setTimeout(() => setShowCategoryDropdown(false), 200)}
                        className="entity-search-input"
                      />
                      {showCategoryDropdown && filteredCategories.length > 0 && (
                        <div className="entity-dropdown">
                          {filteredCategories.slice(0, 20).map(category => (
                            <div
                              key={category.id}
                              className="entity-option"
                              onMouseDown={() => {
                                setSelectedCategory(category);
                                setCategorySearch(category.name);
                                setShowCategoryDropdown(false);
                              }}
                            >
                              <div className="entity-option-info">
                                <span className="entity-name">📁 {category.name}</span>
                              </div>
                              <span className="entity-subtext">ID: {category.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {selectedCategory && (
                      <div className="selected-entity-info">
                        <span className="selected-entity-label">Selected Category:</span>
                        {selectedCategory.name} (ID: {selectedCategory.id})
                      </div>
                    )}
                  </div>
                )}
              </div>
              
              {/* User selector for user view */}
              {selectedView === "user" && (
                <div className="entity-selector-wrapper" style={{ marginTop: "20px", width: "100%" }}>
                  <div className="entity-selector-input-wrapper">
                    <input
                      type="text"
                      placeholder="Search users by name or ID..."
                      value={userSearch}
                      onChange={(e) => setUserSearch(e.target.value)}
                      onFocus={() => setShowUserDropdown(true)}
                      onBlur={() => setTimeout(() => setShowUserDropdown(false), 200)}
                      className="entity-search-input"
                    />
                    {showUserDropdown && filteredUsers.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredUsers.slice(0, 20).map(user => (
                          <div
                            key={user.id}
                            className="entity-option"
                            onMouseDown={() => {
                              setSelectedUser(user);
                              setUserSearch(user.display_name || user.username || user.global_name || user.name);
                              setShowUserDropdown(false);
                            }}
                          >
                            <div className="entity-option-info">
                              {user.avatar && (
                                <img 
                                  src={user.avatar} 
                                  alt="" 
                                  className="user-avatar-small"
                                />
                              )}
                              <span className="entity-name">
                                {user.display_name || user.global_name || user.username || `User ${user.id}`}
                              </span>
                            </div>
                            <span className="entity-subtext">ID: {user.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {selectedUser && (
                    <div className="selected-entity-info">
                      <span className="selected-entity-label">Selected User:</span>
                      {selectedUser.display_name || selectedUser.global_name || selectedUser.username || selectedUser.name || selectedUser.id}
                      <span style={{ color: "#888", marginLeft: "8px" }}>(ID: {selectedUser.id})</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Stat Types Section */}
            <div className="stat-types-section">
              <div className="stat-types-header">
                <h2 className="section-title">Select Stat Types to Reset</h2>
                <div className="action-buttons-group">
                  <button className="action-button" onClick={handleSelectAll}>
                    <span>✅</span> Select All
                  </button>
                  <button className="action-button" onClick={handleClearAll}>
                    <span>🗑️</span> Clear All
                  </button>
                  {hasSelection && (
                    <div className="selection-counter">
                      <span>📌</span> {selectedCount} selected
                    </div>
                  )}
                </div>
              </div>
              
              <div className="stat-types-grid">
                {availableStatTypes.map(stat => (
                  <div 
                    key={stat.value}
                    className={`stat-card ${selectedStatTypes.includes(stat.value) ? "selected" : ""}`}
                    onClick={() => handleStatTypeToggle(stat.value)}
                  >
                    <div className="stat-card-content">
                      <input 
                        type="checkbox" 
                        checked={selectedStatTypes.includes(stat.value)}
                        onChange={() => {}}
                        onClick={(e) => e.stopPropagation()}
                        className="stat-checkbox"
                      />
                      <div className="stat-info">
                        <div className="stat-header">
                          <span className="stat-emoji">{stat.emoji}</span>
                          <span className="stat-label">{stat.label}</span>
                          {stat.value === "all" && (
                            <span className="stat-badge">⚠️ DANGER</span>
                          )}
                        </div>
                        <div className="stat-description">{stat.description}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Reset Button */}
            <div className="reset-button-container">
              <button 
                className="reset-button"
                onClick={handleReset}
                disabled={actionLoading || !hasSelection}
              >
                {actionLoading ? (
                  <>
                    <div className="loading-spinner"></div>
                    Processing...
                  </>
                ) : (
                  <>
                    <span>⚠️</span>
                    RESET
                  </>
                )}
              </button>
            </div>

            {/* Results Section */}
            {resetResults && resetResults.length > 0 && (
              <div className="results-section">
                <div className="results-header">
                  <div className="results-title">
                    <span>📋</span> Reset Results
                  </div>
                  <div className="results-stats">
                    {resetResults.filter(r => r.success).length} of {resetResults.length} successful
                  </div>
                </div>
                <div className="results-table-wrapper">
                  <table className="results-table">
                    <thead>
                      <tr>
                        <th>Stat Type</th>
                        <th>Status</th>
                        <th>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {resetResults.map((result, idx) => (
                        <tr key={idx}>
                          <td style={{ fontWeight: 500 }}>{result.label}</td>
                          <td>
                            {result.success ? (
                              <span className="success-badge">✓ Success</span>
                            ) : (
                              <span className="error-badge">✗ Failed</span>
                            )}
                          </td>
                          <td style={{ fontSize: "12px", color: "#888" }}>{result.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          <Footer />
        </main>
      </div>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="modal-overlay" onClick={() => setShowConfirmModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">⚠️ Confirm Reset</h3>
              <button className="modal-close" onClick={() => setShowConfirmModal(false)}>✕</button>
            </div>
            <div className="warning-box">
              <span style={{ fontSize: "20px" }}>⚠️</span>
              <span>This action is PERMANENT and CANNOT be undone!</span>
            </div>
            <p style={{ wordBreak: 'break-word' }}>{getResetDescription()}</p>
            {selectedStatTypes.length > 0 && (
              <p style={{ marginTop: "16px", fontSize: "13px", color: "#888", wordBreak: 'break-word' }}>
                Will reset: {selectedStatTypes.map(t => STAT_TYPES[selectedView][t]?.label || t).join(", ")}
              </p>
            )}
            <div className="modal-footer">
              <button className="modal-cancel" onClick={() => setShowConfirmModal(false)}>Cancel</button>
              <button className="modal-confirm" onClick={executeReset}>Confirm Reset</button>
            </div>
          </div>
        </div>
      )}
      
      <ToastMessage />
      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <ResetDashboard />
  </React.StrictMode>
);

export default ResetDashboard;