import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";

// API base URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const NAVBAR_HEIGHT = "80px";

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ============================================
// ADVANCED CACHING SYSTEM
// ============================================

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

const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);

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

// Access Denied Component
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

  /* Section styles */
  .reset-section {
    background: linear-gradient(135deg, #0f0f0f 0%, #0a0a0a 100%);
    border: 1px solid #1f1f1f;
    border-radius: 20px;
    padding: 28px;
    margin-bottom: 24px;
    transition: all 0.3s ease;
  }

  .reset-section:hover {
    border-color: #2a2a2a;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid #1f1f1f;
  }

  .section-icon {
    font-size: 28px;
  }

  .section-title {
    font-size: 22px;
    font-weight: 600;
    color: #ffffff;
  }

  .section-subtitle {
    font-size: 14px;
    color: #888;
    margin-left: auto;
  }

  /* Stat types grid */
  .stat-types-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .stat-card {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 14px 16px;
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
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.1);
  }

  .stat-card-content {
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .stat-checkbox {
    width: 20px;
    height: 20px;
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
    font-size: 18px;
  }

  .stat-label {
    font-size: 14px;
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

  .action-buttons-group {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
  }

  .action-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
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

  /* Time period controls */
  .time-period-control {
    display: flex;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
  }

  .time-period-checkbox {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    font-size: 15px;
  }

  .time-period-checkbox input {
    width: 18px;
    height: 18px;
    cursor: pointer;
    accent-color: #aa00ff;
  }

  .days-input-group {
    display: flex;
    align-items: center;
    gap: 12px;
    background-color: #1a1a1a;
    padding: 8px 16px;
    border-radius: 12px;
    border: 1px solid #2a2a2a;
  }

  .days-input {
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 12px;
    color: white;
    width: 80px;
    font-size: 14px;
    text-align: center;
  }

  .days-input:focus {
    outline: none;
    border-color: #aa00ff;
  }

  /* Schedule section */
  .schedule-section {
    margin-top: 8px;
  }

  .add-schedule-button {
    width: 100%;
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border: 2px dashed #2a2a2a;
    border-radius: 16px;
    padding: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    cursor: pointer;
    transition: all 0.3s ease;
    color: #888;
    font-size: 16px;
    font-weight: 500;
  }

  .add-schedule-button:hover {
    border-color: #aa00ff;
    color: #aa00ff;
    background: linear-gradient(135deg, #1f1f1f 0%, #151515 100%);
  }

  .schedule-preview {
    background-color: #1a1a1a;
    border-radius: 16px;
    padding: 20px;
    border: 1px solid #2a2a2a;
    position: relative;
  }

  .schedule-preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .schedule-preview-title {
    font-size: 14px;
    font-weight: 600;
    color: #aa00ff;
  }

  .remove-schedule {
    background: none;
    border: none;
    color: #ff4444;
    cursor: pointer;
    font-size: 18px;
    padding: 4px 8px;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .remove-schedule:hover {
    background-color: rgba(255, 68, 68, 0.1);
  }

  .schedule-preview-content {
    font-size: 15px;
    color: #ffffff;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }

  .schedule-preview-item {
    display: flex;
    align-items: center;
    gap: 8px;
    background-color: #0a0a0a;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 13px;
  }

  /* Reset button */
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

  /* Results section */
  .results-section {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 24px;
    margin-top: 32px;
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

  .results-table {
    width: 100%;
    border-collapse: collapse;
  }

  .results-table th,
  .results-table td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid #1a1a1a;
  }

  .results-table th {
    background-color: #0f0f0f;
    color: #aa00ff;
    font-weight: 600;
    font-size: 13px;
  }

  .success-badge {
    background-color: rgba(0, 184, 148, 0.2);
    color: #00b894;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
  }

  .error-badge {
    background-color: rgba(255, 118, 117, 0.2);
    color: #ff7675;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
  }

  /* Modal overlay */
  .schedule-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 20px;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes slideUp {
    from {
      transform: translateY(30px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .schedule-modal {
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border-radius: 24px;
    width: 100%;
    max-width: 500px;
    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
    border: 1px solid #2a2a2a;
    animation: slideUp 0.3s ease;
    overflow: hidden;
  }

  .schedule-modal-header {
    padding: 24px 24px 16px 24px;
    border-bottom: 1px solid #2a2a2a;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .schedule-modal-title {
    font-size: 20px;
    font-weight: 600;
    background: linear-gradient(135deg, #aa00ff, #ff66cc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .schedule-modal-close {
    background: none;
    border: none;
    color: #888;
    font-size: 24px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .schedule-modal-close:hover {
    color: #ff4444;
    background-color: rgba(255, 68, 68, 0.1);
  }

  .schedule-modal-content {
    padding: 24px;
    min-height: 300px;
  }

  /* Schedule type options */
  .schedule-type-options {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .schedule-type-option {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 16px;
    padding: 18px 20px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .schedule-type-option:hover {
    border-color: #aa00ff;
    background-color: #222;
    transform: translateX(4px);
  }

  .schedule-type-option.selected {
    border-color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
  }

  .schedule-type-icon {
    font-size: 32px;
  }

  .schedule-type-info {
    flex: 1;
  }

  .schedule-type-name {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 4px;
  }

  .schedule-type-desc {
    font-size: 12px;
    color: #888;
  }

  .schedule-type-check {
    color: #aa00ff;
    font-size: 20px;
  }

  /* Form inputs */
  .form-group {
    margin-bottom: 20px;
  }

  .form-label {
    display: block;
    font-size: 14px;
    font-weight: 500;
    color: #aa00ff;
    margin-bottom: 8px;
  }

  .form-input, .form-select {
    width: 100%;
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    color: #ffffff;
    font-size: 14px;
    transition: all 0.2s ease;
  }

  .form-input:focus, .form-select:focus {
    outline: none;
    border-color: #aa00ff;
    box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.1);
  }

  .weekday-options {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
  }

  .weekday-option {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .weekday-option:hover {
    border-color: #aa00ff;
  }

  .weekday-option.selected {
    border-color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.2);
  }

  /* Confirmation page */
  .confirmation-details {
    background-color: #1a1a1a;
    border-radius: 16px;
    padding: 20px;
    margin-top: 16px;
  }

  .confirmation-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #2a2a2a;
  }

  .confirmation-row:last-child {
    border-bottom: none;
  }

  .confirmation-label {
    font-size: 14px;
    color: #888;
  }

  .confirmation-value {
    font-size: 14px;
    font-weight: 500;
    color: #aa00ff;
  }

  .modal-footer {
    padding: 16px 24px 24px 24px;
    border-top: 1px solid #2a2a2a;
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .modal-btn {
    padding: 10px 20px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
  }

  .modal-btn-back {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #ffffff;
  }

  .modal-btn-back:hover {
    border-color: #aa00ff;
    color: #aa00ff;
  }

  .modal-btn-next {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white;
  }

  .modal-btn-next:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
  }

  .modal-btn-cancel {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #888;
  }

  .modal-btn-cancel:hover {
    border-color: #ff4444;
    color: #ff4444;
  }

  /* Step indicator */
  .step-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-bottom: 24px;
  }

  .step-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #2a2a2a;
    transition: all 0.3s ease;
  }

  .step-dot.active {
    width: 24px;
    border-radius: 4px;
    background: linear-gradient(135deg, #aa00ff, #8800cc);
  }

  .step-dot.completed {
    background-color: #00b894;
  }

  /* Other existing styles */
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
    appearance: none;
    background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23aa00ff'%3e%3cpath d='M7 10l5 5 5-5z'/%3e%3c/svg%3e");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 20px;
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
  }

  .entity-search-input {
    width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    outline: none;
    transition: all 0.2s ease;
  }

  .entity-search-input:focus {
    border-color: #aa00ff;
  }

  .entity-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    margin-top: 8px;
    max-height: 300px;
    overflow-y: auto;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  }

  .entity-option {
    padding: 12px 16px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #2a2a2a;
  }

  .entity-option:hover {
    background-color: #2a2a2a;
  }

  .selected-entity-info {
    margin-top: 12px;
    padding: 12px;
    background-color: #1a1a1a;
    border-radius: 8px;
    border-left: 3px solid #aa00ff;
    font-size: 14px;
  }

  .selected-entity-label {
    color: #aa00ff;
    font-weight: 600;
    margin-right: 8px;
  }

  .user-avatar-small {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    object-fit: cover;
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

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
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

  .error-message-container {
    text-align: center;
    padding: 80px 40px;
    background-color: #1a1a1a;
    border: 1px solid #ff4444;
    border-radius: 16px;
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

  .no-server {
    text-align: center;
    padding: 80px 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
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

  @media (max-width: 768px) {
    .dashboard-main {
      margin-left: 0;
    }
    .dashboard-content {
      padding: 16px;
    }
    .reset-section {
      padding: 20px;
    }
    .stat-types-grid {
      grid-template-columns: 1fr;
    }
    .schedule-modal {
      margin: 16px;
      width: calc(100% - 32px);
    }
    .section-header {
      flex-wrap: wrap;
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

const weekdays = [
  { value: 0, label: "Monday", short: "Mon" },
  { value: 1, label: "Tuesday", short: "Tue" },
  { value: 2, label: "Wednesday", short: "Wed" },
  { value: 3, label: "Thursday", short: "Thu" },
  { value: 4, label: "Friday", short: "Fri" },
  { value: 5, label: "Saturday", short: "Sat" },
  { value: 6, label: "Sunday", short: "Sun" }
];

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

// Schedule Modal Component
const ScheduleModal = ({ isOpen, onClose, onConfirm, existingSchedule }) => {
  const [step, setStep] = useState(1);
  const [scheduleType, setScheduleType] = useState(null);
  const [selectedWeekday, setSelectedWeekday] = useState(null);
  const [intervalDays, setIntervalDays] = useState(7);
  const [dayOfMonth, setDayOfMonth] = useState(1);
  const [timeOfDay, setTimeOfDay] = useState("18:00");

  const resetState = () => {
    setStep(1);
    setScheduleType(null);
    setSelectedWeekday(null);
    setIntervalDays(7);
    setDayOfMonth(1);
    setTimeOfDay("18:00");
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleNext = () => {
    if (step === 1 && scheduleType) {
      setStep(2);
    } else if (step === 2) {
      setStep(3);
    }
  };

  const handleBack = () => {
    if (step > 1) {
      setStep(step - 1);
    }
  };

  const handleConfirm = () => {
    let scheduleDescription = "";
    let scheduleData = {};

    if (scheduleType === "weekly") {
      const weekday = weekdays.find(w => w.value === selectedWeekday);
      scheduleDescription = `Every ${weekday?.label} at ${timeOfDay}`;
      scheduleData = { pattern: "weekly", weekday: selectedWeekday, time: timeOfDay };
    } else if (scheduleType === "daily") {
      scheduleDescription = `Every day at ${timeOfDay}`;
      scheduleData = { pattern: "daily", time: timeOfDay };
    } else if (scheduleType === "monthly") {
      scheduleDescription = `Every ${dayOfMonth}${getOrdinal(dayOfMonth)} of the month at ${timeOfDay}`;
      scheduleData = { pattern: "monthly", dayOfMonth: dayOfMonth, time: timeOfDay };
    } else if (scheduleType === "custom") {
      scheduleDescription = `Every ${intervalDays} days at ${timeOfDay}`;
      scheduleData = { pattern: "custom", intervalDays: intervalDays, time: timeOfDay };
    }

    onConfirm(scheduleDescription, scheduleData);
    resetState();
    onClose();
  };

  const getOrdinal = (n) => {
    if (n > 3 && n < 21) return 'th';
    switch (n % 10) {
      case 1: return 'st';
      case 2: return 'nd';
      case 3: return 'rd';
      default: return 'th';
    }
  };

  const getSchedulePreview = () => {
    if (!scheduleType) return null;
    if (scheduleType === "weekly") {
      const weekday = weekdays.find(w => w.value === selectedWeekday);
      return `${weekday?.label || "Select a day"} at ${timeOfDay}`;
    }
    if (scheduleType === "daily") return `Every day at ${timeOfDay}`;
    if (scheduleType === "monthly") return `Every ${dayOfMonth}${getOrdinal(dayOfMonth)} at ${timeOfDay}`;
    if (scheduleType === "custom") return `Every ${intervalDays} days at ${timeOfDay}`;
    return "";
  };

  if (!isOpen) return null;

  return (
    <div className="schedule-modal-overlay" onClick={handleClose}>
      <div className="schedule-modal" onClick={(e) => e.stopPropagation()}>
        <div className="schedule-modal-header">
          <h3 className="schedule-modal-title">Create Reset Schedule</h3>
          <button className="schedule-modal-close" onClick={handleClose}>✕</button>
        </div>

        <div className="step-indicator">
          <div className={`step-dot ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 3 ? 'active' : ''}`}></div>
        </div>

        <div className="schedule-modal-content">
          {step === 1 && (
            <div>
              <h4 style={{ marginBottom: '20px', fontSize: '16px', color: '#fff' }}>Choose schedule type</h4>
              <div className="schedule-type-options">
                <div 
                  className={`schedule-type-option ${scheduleType === 'daily' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('daily')}
                >
                  <div className="schedule-type-icon">📅</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Every Day</div>
                    <div className="schedule-type-desc">Runs at the same time every day</div>
                  </div>
                  {scheduleType === 'daily' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'weekly' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('weekly')}
                >
                  <div className="schedule-type-icon">📆</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Weekly</div>
                    <div className="schedule-type-desc">Runs on a specific day of the week</div>
                  </div>
                  {scheduleType === 'weekly' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'monthly' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('monthly')}
                >
                  <div className="schedule-type-icon">📅</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Monthly</div>
                    <div className="schedule-type-desc">Runs on a specific day of the month</div>
                  </div>
                  {scheduleType === 'monthly' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'custom' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('custom')}
                >
                  <div className="schedule-type-icon">⚙️</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Custom Interval</div>
                    <div className="schedule-type-desc">Runs every X days</div>
                  </div>
                  {scheduleType === 'custom' && <div className="schedule-type-check">✓</div>}
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h4 style={{ marginBottom: '20px', fontSize: '16px', color: '#fff' }}>Configure schedule</h4>
              
              {scheduleType === 'weekly' && (
                <div className="form-group">
                  <label className="form-label">Select Day</label>
                  <div className="weekday-options">
                    {weekdays.map(day => (
                      <div
                        key={day.value}
                        className={`weekday-option ${selectedWeekday === day.value ? 'selected' : ''}`}
                        onClick={() => setSelectedWeekday(day.value)}
                      >
                        {day.short}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {scheduleType === 'monthly' && (
                <div className="form-group">
                  <label className="form-label">Day of Month</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="31"
                    value={dayOfMonth}
                    onChange={(e) => setDayOfMonth(Math.min(31, Math.max(1, parseInt(e.target.value) || 1)))}
                  />
                </div>
              )}

              {scheduleType === 'custom' && (
                <div className="form-group">
                  <label className="form-label">Interval (Days)</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="365"
                    value={intervalDays}
                    onChange={(e) => setIntervalDays(Math.min(365, Math.max(1, parseInt(e.target.value) || 1)))}
                  />
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Time of Day</label>
                <input
                  type="time"
                  className="form-input"
                  value={timeOfDay}
                  onChange={(e) => setTimeOfDay(e.target.value)}
                  step="60"
                />
              </div>

              <div className="confirmation-details" style={{ marginTop: '20px' }}>
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule Preview:</span>
                  <span className="confirmation-value">{getSchedulePreview()}</span>
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <h4 style={{ marginBottom: '20px', fontSize: '16px', color: '#fff' }}>Confirm Schedule</h4>
              <div className="confirmation-details">
                <div className="confirmation-row">
                  <span className="confirmation-label">Type:</span>
                  <span className="confirmation-value">
                    {scheduleType === 'daily' && 'Daily'}
                    {scheduleType === 'weekly' && 'Weekly'}
                    {scheduleType === 'monthly' && 'Monthly'}
                    {scheduleType === 'custom' && 'Custom Interval'}
                  </span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule:</span>
                  <span className="confirmation-value">{getSchedulePreview()}</span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Next Run:</span>
                  <span className="confirmation-value">Will be calculated automatically</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="modal-btn modal-btn-cancel" onClick={handleClose}>Cancel</button>
          {step > 1 && (
            <button className="modal-btn modal-btn-back" onClick={handleBack}>Back</button>
          )}
          {step < 3 && (
            <button 
              className="modal-btn modal-btn-next" 
              onClick={handleNext}
              disabled={step === 1 && !scheduleType}
            >
              Next
            </button>
          )}
          {step === 3 && (
            <button className="modal-btn modal-btn-next" onClick={handleConfirm}>
              Create Schedule
            </button>
          )}
        </div>
      </div>
    </div>
  );
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
  const [resetResults, setResetResults] = useState(null);
  
  // Scope selection
  const [scope, setScope] = useState("server");
  const [selectedStatTypes, setSelectedStatTypes] = useState([]);
  
  // Time period
  const [useTimePeriod, setUseTimePeriod] = useState(false);
  const [timePeriodDays, setTimePeriodDays] = useState(7);
  
  // Schedule
  const [schedule, setSchedule] = useState(null);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  
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

  const isPrivilegedUser = (userId) => PRIVILEGED_USERS.includes(userId);

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
        
        let hasAccessFlag = false;
        
        if (accessLevel === 'Public') {
          hasAccessFlag = true;
        } else if (accessLevel === 'Member') {
          hasAccessFlag = hasAdmin;
        } else if (accessLevel === 'Moderator') {
          hasAccessFlag = hasAdmin || hasManageServer;
        } else if (accessLevel === 'Admin') {
          hasAccessFlag = hasAdmin;
        }
        
        setHasAccess(hasAccessFlag);
      } else {
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
        
        if (isPrivilegedUser(authData.user.id)) {
          setHasAccess(true);
          setDashboardAccessLevel('Admin');
          window.accessLevel = 'Admin';
          
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

  const handleAddSchedule = (scheduleDescription, scheduleData) => {
    setSchedule({ description: scheduleDescription, data: scheduleData });
    showToast(`Schedule added: ${scheduleDescription}`, 'success');
  };

  const handleRemoveSchedule = () => {
    setSchedule(null);
    showToast('Schedule removed', 'info');
  };

  const handleReset = async () => {
    if (selectedStatTypes.length === 0) {
      showToast("Please select at least one statistic type to reset", "error");
      return;
    }

    setActionLoading(true);
    
    try {
      if (schedule) {
        // Create schedule
        await createSchedule();
      } else {
        // Execute reset immediately
        await executeReset();
      }
    } catch (error) {
      console.error('Error:', error);
      showToast("Failed to process request", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const createSchedule = async () => {
    let scopeValue = scope;
    let scopeDetails = "";
    let channelId = null;
    let categoryId = null;
    
    if (scope === "channel" && selectedChannel) {
      scopeDetails = `Channel: #${selectedChannel.name} (ID: ${selectedChannel.id})`;
      channelId = selectedChannel.id;
    } else if (scope === "category" && selectedCategory) {
      scopeDetails = `Category: ${selectedCategory.name} (ID: ${selectedCategory.id})`;
      categoryId = selectedCategory.id;
    } else {
      scopeDetails = "Entire Server";
    }
    
    const resetTypes = selectedStatTypes;
    
    // Map schedule data to API format
    let recurringPattern = null;
    let recurringWeekday = null;
    let recurringDayOfMonth = null;
    let recurringIntervalDays = null;
    let recurringTime = schedule.data.time;
    
    if (schedule.data.pattern === 'daily') {
      recurringPattern = 'daily';
    } else if (schedule.data.pattern === 'weekly') {
      recurringPattern = 'weekly';
      recurringWeekday = schedule.data.weekday;
    } else if (schedule.data.pattern === 'monthly') {
      recurringPattern = 'monthly';
      recurringDayOfMonth = schedule.data.dayOfMonth;
    } else if (schedule.data.pattern === 'custom') {
      recurringPattern = 'custom_days';
      recurringIntervalDays = schedule.data.intervalDays;
    }
    
    const body = {
      guild_id: currentServer.id,
      requested_by_id: currentUserId,
      reset_types: resetTypes,
      schedule_type: "recurring",
      recurring_pattern: recurringPattern,
      recurring_weekday: recurringWeekday,
      recurring_day_of_month: recurringDayOfMonth,
      recurring_time: recurringTime,
      recurring_interval_days: recurringIntervalDays,
      time_period_days: useTimePeriod ? timePeriodDays : null,
      scope_type: scopeValue,
      scope_details: scopeDetails,
      channel_id: channelId,
      category_id: categoryId,
      reason: `Scheduled via dashboard. ${schedule.description}`
    };
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/reset/schedule/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body)
      });
      
      const result = await response.json();
      
      if (result.success) {
        showToast(`✅ Schedule created! Schedule #${result.schedule_id}`, "success");
        setResetResults([{
          type: "schedule",
          label: `Schedule Created (${resetTypes.length} types)`,
          success: true,
          message: `${schedule.description}`,
          schedule_id: result.schedule_id
        }]);
      } else {
        showToast(`❌ Failed to create schedule: ${result.message}`, "error");
        setResetResults([{
          type: "schedule",
          label: "Schedule Creation",
          success: false,
          message: result.message || "Unknown error"
        }]);
      }
    } catch (error) {
      console.error('Error creating schedule:', error);
      showToast("Failed to create schedule", "error");
      setResetResults([{
        type: "schedule",
        label: "Schedule Creation",
        success: false,
        message: error.message || "Network error"
      }]);
    }
  };

  const executeReset = async () => {
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
        
        if (useTimePeriod) {
          body.time_period_days = timePeriodDays;
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
    }
  };

  const getScopeLabel = () => {
    if (scope === "server") return "the entire server";
    if (scope === "channel" && selectedChannel) return `channel #${selectedChannel.name}`;
    if (scope === "category" && selectedCategory) return `category ${selectedCategory.name}`;
    return "the selected scope";
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
                  setUseTimePeriod(false);
                  setSchedule(null);
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
                  setUseTimePeriod(false);
                  setSchedule(null);
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
                        setUseTimePeriod(false);
                        setSchedule(null);
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
                              {user.avatar && <img src={user.avatar} alt="" className="user-avatar-small" />}
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

            {/* SECTION 1: STAT TYPES */}
            <div className="reset-section">
              <div className="section-header">
                <div className="section-icon">📊</div>
                <div className="section-title">Select Stat Types to Reset</div>
                <div className="section-subtitle">
                  {selectedCount > 0 && `${selectedCount} selected`}
                </div>
              </div>
              
              <div className="action-buttons-group">
                <button className="action-button" onClick={handleSelectAll}>
                  <span>✅</span> Select All
                </button>
                <button className="action-button" onClick={handleClearAll}>
                  <span>🗑️</span> Clear All
                </button>
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
                          {stat.value === "all" && <span className="stat-badge">⚠️ DANGER</span>}
                        </div>
                        <div className="stat-description">{stat.description}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* SECTION 2: TIME PERIOD */}
            <div className="reset-section">
              <div className="section-header">
                <div className="section-icon">⏰</div>
                <div className="section-title">Time Period</div>
                <div className="section-subtitle">Choose how far back to delete</div>
              </div>
              
              <div className="time-period-control">
                <label className="time-period-checkbox">
                  <input 
                    type="checkbox" 
                    checked={useTimePeriod}
                    onChange={(e) => setUseTimePeriod(e.target.checked)}
                  />
                  <span>🗓️ Only delete stats from the last</span>
                </label>
                {useTimePeriod && (
                  <div className="days-input-group">
                    <input 
                      type="number"
                      className="days-input"
                      min="1"
                      max="365"
                      value={timePeriodDays}
                      onChange={(e) => setTimePeriodDays(Math.min(365, Math.max(1, parseInt(e.target.value) || 1)))}
                    />
                    <span>days</span>
                    <span style={{ color: "#888", fontSize: "12px" }}>(1-365 days)</span>
                  </div>
                )}
                {!useTimePeriod && (
                  <span style={{ color: "#888", fontSize: "14px" }}>Deleting ALL stats (no time limit)</span>
                )}
              </div>
            </div>

            {/* SECTION 3: SCHEDULE */}
            <div className="reset-section">
              <div className="section-header">
                <div className="section-icon">⏱️</div>
                <div className="section-title">Schedule (Optional)</div>
                <div className="section-subtitle">Set up automatic recurring resets</div>
              </div>
              
              <div className="schedule-section">
                {!schedule ? (
                  <button 
                    className="add-schedule-button"
                    onClick={() => setShowScheduleModal(true)}
                  >
                    <span>➕</span> Add Schedule
                  </button>
                ) : (
                  <div className="schedule-preview">
                    <div className="schedule-preview-header">
                      <span className="schedule-preview-title">📅 Active Schedule</span>
                      <button className="remove-schedule" onClick={handleRemoveSchedule}>✕</button>
                    </div>
                    <div className="schedule-preview-content">
                      <div className="schedule-preview-item">
                        <span>🕐</span> {schedule.description}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Action Button */}
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
                    {schedule ? "📅" : "⚠️"}
                    {schedule ? " CREATE SCHEDULE" : " RESET NOW"}
                  </>
                )}
              </button>
            </div>

            {/* Results Section */}
            {resetResults && resetResults.length > 0 && (
              <div className="results-section">
                <div className="results-header">
                  <div className="results-title">
                    <span>📋</span> {resetResults[0].type === "schedule" ? "Schedule Results" : "Reset Results"}
                  </div>
                  <div className="results-stats">
                    {resetResults.filter(r => r.success).length} of {resetResults.length} successful
                  </div>
                </div>
                <table className="results-table">
                  <thead>
                    <tr>
                      <th>Type</th>
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
            )}
          </div>
          <Footer />
        </main>
      </div>

      {/* Schedule Modal */}
      <ScheduleModal 
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        onConfirm={handleAddSchedule}
        existingSchedule={schedule}
      />

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