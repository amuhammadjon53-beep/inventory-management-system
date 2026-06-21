import React, { useState, useEffect, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import ReactDOM from "react-dom";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import {
  History,
  MessageCircle,
  Smile,
  AtSign,
  FolderSync,
  RotateCcw,
  Power,
  Play,
  CircleCheck,
  CircleX,
  NotepadText,
  Zap,
  Hourglass,
  Pause,
  Trash2,
  Lock,
  TriangleAlert,
  Info,
  ShieldAlert,
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const NAVBAR_HEIGHT = "80px";
const ACCENT = "#aa00ff";

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// Poll cadence while at least one channel is actively running
const ACTIVE_POLL_MS = 2500;
const IDLE_POLL_MS = 15000;

// Time period options for how far back a sync should walk.
// value is sync_depth_days sent to the backend; null = full history.
const DEPTH_OPTIONS = [
  { value: 7,    label: '7 days' },
  { value: 30,   label: '30 days' },
  { value: 90,   label: '90 days' },
  { value: 180,  label: '6 months' },
  { value: 365,  label: '1 year' },
  { value: null, label: 'All time' },
];

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

  /* ── Page header ── */
  .hsync-page-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
  }

  .hsync-title-block h1 {
    font-size: 28px;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.3px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .hsync-title-block p {
    color: #777;
    font-size: 13px;
    margin-top: 6px;
    max-width: 640px;
    line-height: 1.5;
  }

  .hsync-live-pulse {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: #555;
    padding: 6px 12px;
    border-radius: 20px;
    background: #111;
    border: 1px solid #222;
  }

  .hsync-live-pulse.live { color: #cc77ff; border-color: #3a1a5a; background: #150022; }

  .hsync-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #444;
  }

  .hsync-dot.live {
    background: #aa00ff;
    box-shadow: 0 0 0 0 rgba(170,0,255,0.6);
    animation: hsyncPulse 1.6s infinite;
  }

  @keyframes hsyncPulse {
    0%   { box-shadow: 0 0 0 0 rgba(170,0,255,0.55); }
    70%  { box-shadow: 0 0 0 7px rgba(170,0,255,0); }
    100% { box-shadow: 0 0 0 0 rgba(170,0,255,0); }
  }

  /* ── Monitor: aggregate totals ── */
  .hsync-monitor {
    background: linear-gradient(160deg, #0f0a16 0%, #0a0a0a 60%);
    border: 1px solid #221830;
    border-radius: 20px;
    padding: 28px 28px 24px 28px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
  }

  .hsync-monitor::before {
    content: '';
    position: absolute;
    top: -120px; right: -120px;
    width: 320px; height: 320px;
    background: radial-gradient(circle, rgba(170,0,255,0.16) 0%, transparent 70%);
    pointer-events: none;
  }

  .hsync-monitor-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 18px;
  }

  .hsync-monitor-heading h2 {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #8a6bb0;
  }

  .hsync-totals-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 22px;
  }

  .hsync-total-card {
    background: #0d0d12;
    border: 1px solid #221a2e;
    border-radius: 14px;
    padding: 16px 18px;
    position: relative;
  }

  .hsync-total-label {
    font-size: 11px;
    color: #6a6a78;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .hsync-total-value {
    font-size: 26px;
    font-weight: 700;
    color: #fff;
    font-family: 'SF Mono', 'Roboto Mono', monospace;
    letter-spacing: -0.5px;
  }

  .hsync-total-value.accent-purple { color: #cc77ff; }
  .hsync-total-value.accent-green  { color: #38d9a9; }
  .hsync-total-value.accent-gold   { color: #ffd24d; }

  /* Running sync cards (the "live monitor") */
  .hsync-running-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 14px;
  }

  .hsync-running-empty {
    text-align: center;
    padding: 36px 20px;
    color: #555;
    font-size: 13px;
    border: 1px dashed #221a2e;
    border-radius: 14px;
    grid-column: 1 / -1;
  }

  .hsync-run-card {
    background: #100a18;
    border: 1px solid #2a1a40;
    border-radius: 14px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    position: relative;
    overflow: hidden;
  }

  .hsync-run-card.paused { border-color: #3a3000; background: #120f02; }
  .hsync-run-card.failed { border-color: #4a1a1a; background: #160808; }

  .hsync-run-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .hsync-run-channel {
    font-size: 14px;
    font-weight: 600;
    color: #f0e6ff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .hsync-run-channel span { color: #5a4a70; margin-right: 3px; }

  .hsync-run-elapsed {
    font-size: 11px;
    color: #7a6a90;
    font-family: monospace;
    white-space: nowrap;
  }

  .hsync-run-stats {
    display: flex;
    gap: 10px;
  }

  .hsync-run-stat {
    flex: 1;
    background: #0a0612;
    border-radius: 9px;
    padding: 8px 6px;
    text-align: center;
    border: 1px solid #1f1530;
  }

  .hsync-run-stat-icon { display: flex; justify-content: center; margin-bottom: 2px; }

  .hsync-run-stat-num {
    font-family: 'SF Mono', 'Roboto Mono', monospace;
    font-size: 15px;
    font-weight: 700;
    color: #e0d0ff;
  }

  .hsync-run-stat-label {
    font-size: 9px;
    color: #5a4a70;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }

  .hsync-run-track {
    height: 4px;
    border-radius: 4px;
    background: #1a1228;
    overflow: hidden;
  }

  .hsync-run-track-fill {
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, #6a00b8, #cc77ff);
    width: 38%;
    animation: hsyncIndeterminate 1.8s ease-in-out infinite;
  }

  @keyframes hsyncIndeterminate {
    0%   { margin-left: -38%; }
    100% { margin-left: 100%; }
  }

  .hsync-run-track-fill.paused { animation: none; background: #6b5a00; width: 100%; margin-left: 0; }

  .hsync-run-card-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .hsync-run-status-pill {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 3px 9px;
    border-radius: 20px;
  }

  .hsync-run-status-pill.in_progress { background: #1e0033; color: #cc77ff; }
  .hsync-run-status-pill.paused      { background: #1a1500; color: #ffd700; }
  .hsync-run-status-pill.failed      { background: #1a0a0a; color: #ff6b6b; }

  /* ── Settings-card visual language reused for the control panel ── */
  .settings-card {
    background-color: #0f0f0f;
    border: 1px solid #1f1f1f;
    border-radius: 16px;
    padding: 24px;
    transition: all 0.2s ease;
  }

  /* ── Accent variant: same gradient + glow as the live monitor ── */
  .settings-card-accent {
    background: linear-gradient(160deg, #0f0a16 0%, #0a0a0a 60%);
    border: 1px solid #221830;
    position: relative;
    overflow: hidden;
  }

  .settings-card-accent::before {
    content: '';
    position: absolute;
    top: -120px; right: -120px;
    width: 320px; height: 320px;
    background: radial-gradient(circle, rgba(170,0,255,0.16) 0%, transparent 70%);
    pointer-events: none;
  }

  .settings-card-accent .settings-card-header {
    border-bottom-color: #221830;
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

  .settings-card-icon { display: flex; align-items: center; }

  .settings-card-title {
    color: #ffffff;
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .settings-card-description {
    color: #888;
    font-size: 13px;
    margin-bottom: 4px;
    line-height: 1.5;
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

  .error-icon { font-size: 64px; margin-bottom: 20px; display: flex; align-items: center; justify-content: center; }
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

  .icon-spin { animation: spin 1s linear infinite; display: inline-flex; }

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

  /* ── Cooldown banner ── */
  .hsync-cooldown-banner {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    background: linear-gradient(135deg, #1a1206 0%, #120d04 100%);
    border: 1px solid #4a3300;
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 20px;
  }

  .hsync-cooldown-banner-icon {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: #2a1d00;
    border: 1px solid #4a3300;
  }

  .hsync-cooldown-banner-title {
    font-size: 13px;
    font-weight: 700;
    color: #ffd24d;
    margin-bottom: 4px;
  }

  .hsync-cooldown-banner-text {
    font-size: 12px;
    color: #b0a070;
    line-height: 1.5;
  }

  .hsync-cooldown-banner-text strong { color: #ffd24d; font-weight: 700; }

  /* ── Always-on heads-up about the 3-month limit (not just when on cooldown) ── */
  .sync-precaution-note {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    background: #120d1c;
    border: 1px solid #2a1f3a;
    border-radius: 12px;
    padding: 12px 14px;
    font-size: 12px;
    color: #b0a0c0;
    line-height: 1.5;
  }

  .sync-precaution-note strong { color: #cc99ff; }

  /* ── Time period selector ── */
  .sync-depth-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .sync-depth-chip {
    flex: 1;
    min-width: 64px;
    padding: 8px 6px;
    border-radius: 8px;
    background-color: #1a1a1a;
    border: 2px solid #2a2a2a;
    color: #888;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
    transition: all 0.2s ease;
    user-select: none;
  }

  .sync-depth-chip:hover { border-color: #aa00ff; color: #fff; }

  .sync-depth-chip.active {
    background-color: #1e0033;
    border-color: #aa00ff;
    color: #fff;
    box-shadow: 0 0 10px rgba(170, 0, 255, 0.2);
  }

  /* ── History Sync control panel ── */

  .sync-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }

  .sync-controls-panel { display: flex; flex-direction: column; gap: 16px; }

  .sync-stat-toggles { display: flex; gap: 10px; }

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

  .sync-stat-toggle:hover { border-color: #aa00ff; color: #fff; }

  .sync-stat-toggle.active {
    background-color: #1e0033;
    border-color: #aa00ff;
    color: #fff;
    box-shadow: 0 0 10px rgba(170, 0, 255, 0.2);
  }

  .sync-stat-toggle-icon { display: flex; justify-content: center; margin-bottom: 4px; }

  .sync-action-buttons { display: flex; flex-direction: column; gap: 8px; }

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

  .sync-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }

  .sync-btn-primary { background-color: #aa00ff; color: #fff; }
  .sync-btn-primary:hover:not(:disabled) { background-color: #8800cc; transform: translateY(-1px); }

  .sync-btn-secondary { background-color: #1a1a1a; color: #fff; border: 1px solid #2a2a2a; }
  .sync-btn-secondary:hover:not(:disabled) { background-color: #2a2a2a; transform: translateY(-1px); }

  .sync-btn-danger { background-color: #1a0a0a; color: #ff8a8a; border: 1px solid #4a1a1a; }
  .sync-btn-danger:hover:not(:disabled) { background-color: #2a1010; transform: translateY(-1px); }

  .sync-row-buttons { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }

  .sync-row-btn {
    padding: 5px 10px;
    border-radius: 6px;
    border: none;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .sync-row-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .sync-row-btn-start { background-color: #1e0033; color: #cc77ff; border: 1px solid #440066; }
  .sync-row-btn-start:hover:not(:disabled) { background-color: #2e0044; }

  .sync-row-btn-pause { background-color: #1a1500; color: #ffd700; border: 1px solid #3a3000; }
  .sync-row-btn-pause:hover:not(:disabled) { background-color: #2a2000; }

  .sync-row-btn-cancel { background-color: #2a0a0a; color: #ff6b6b; border: 1px solid #5a1a1a; }
  .sync-row-btn-cancel:hover:not(:disabled) { background-color: #3a1010; }

  .sync-row-btn-reset { background-color: #0a0a1a; color: #6b9eff; border: 1px solid #1a1a4a; }
  .sync-row-btn-reset:hover:not(:disabled) { background-color: #10102a; }

  .sync-channels-panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 460px;
    overflow-y: auto;
  }

  .sync-channels-panel::-webkit-scrollbar { width: 4px; }
  .sync-channels-panel::-webkit-scrollbar-track { background: #1a1a1a; border-radius: 2px; }
  .sync-channels-panel::-webkit-scrollbar-thumb { background: #aa00ff; border-radius: 2px; }

  .sync-channel-row {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    transition: border-color 0.2s ease;
  }

  .sync-channel-row.in_progress { border-color: #aa00ff; background-color: #110022; }
  .sync-channel-row.caught_up   { border-color: #00b894; background-color: #001a12; }
  .sync-channel-row.failed      { border-color: #ff6b6b; background-color: #1a0a0a; }
  .sync-channel-row.paused      { border-color: #ffd700; background-color: #1a1500; }

  .sync-channel-name {
    flex: 1;
    min-width: 120px;
    color: #e0e0e0;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sync-channel-name span { color: #555; margin-right: 4px; }

  .sync-channel-substat {
    font-size: 10px;
    color: #666;
    font-family: monospace;
    margin-top: 2px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .substat-item { display: inline-flex; align-items: center; gap: 3px; }

  .sync-status-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
  }

  .sync-status-badge.pending     { background-color: #2a2a2a; color: #888; }
  .sync-status-badge.in_progress { background-color: #1e0033; color: #cc77ff; }
  .sync-status-badge.caught_up   { background-color: #001a12; color: #00b894; }
  .sync-status-badge.failed      { background-color: #1a0a0a; color: #ff6b6b; }
  .sync-status-badge.paused      { background-color: #1a1500; color: #ffd700; }

  .sync-summary-row { display: flex; gap: 12px; flex-wrap: wrap; }

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

  .sync-summary-chip strong { color: #aa00ff; }

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

  .sync-divider { border: none; border-top: 1px solid #1f1f1f; margin: 4px 0 12px 0; }

  @media (max-width: 1024px) {
    .dashboard-main { margin-left: 250px; }
    .dashboard-content { padding: 30px; }
    .sync-layout { grid-template-columns: 1fr; }
    .hsync-totals-row { grid-template-columns: repeat(2, 1fr); }
  }

  @media (max-width: 768px) {
    .dashboard-main { margin-left: 0; }
    .dashboard-content { padding: 20px; }
    .hsync-totals-row { grid-template-columns: 1fr 1fr; }
    .sync-depth-row { flex-wrap: wrap; }
    .sync-depth-chip { min-width: 30%; }
  }
`;

// ─────────────────────────────────────────────────────────────
// Shared utility components
// ─────────────────────────────────────────────────────────────

const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
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

// Renders the tooltip into document.body via a portal so it's never clipped
// by overflow:hidden on any ancestor container.
const InfoIcon = ({ descriptions }) => {
  const [tooltipPos, setTooltipPos] = useState(null);
  const iconRef = useRef(null);
  const timeoutRef = useRef(null);

  const showTooltip = () => {
    if (!iconRef.current) return;
    const rect = iconRef.current.getBoundingClientRect();
    setTooltipPos({
      // Centre horizontally over the icon; sit above it with 10px gap
      left: rect.left + rect.width / 2,
      bottom: window.innerHeight - rect.top + 10,
    });
  };

  const handleMouseEnter = () => {
    timeoutRef.current = setTimeout(showTooltip, 300);
  };

  const handleMouseLeave = () => {
    clearTimeout(timeoutRef.current);
    setTooltipPos(null);
  };

  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const tooltip = tooltipPos
    ? ReactDOM.createPortal(
        <div
          className="info-tooltip-portal"
          style={{
            bottom: tooltipPos.bottom,
            left: tooltipPos.left,
            transform: 'translateX(-50%)',
          }}
        >
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
      <span
        ref={iconRef}
        className="info-icon"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <Info size={13} color="#888" />
      </span>
      {tooltip}
    </>
  );
};

const SettingsCard = ({ title, icon, children, description, infoDescriptions = [], fullWidth = false, accentBg = false }) => (
  <div className={`settings-card${accentBg ? ' settings-card-accent' : ''}`} style={fullWidth ? {} : {}}>
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
// Helpers
// ─────────────────────────────────────────────────────────────

const STAT_OPTIONS = [
  { key: 'messages', icon: MessageCircle, label: 'Messages' },
  { key: 'mentions', icon: AtSign,        label: 'Mentions' },
  { key: 'emoji',    icon: Smile,         label: 'Emoji'    },
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

const formatNumber = (n) => {
  if (n == null) return '0';
  return Number(n).toLocaleString('en-US');
};

const formatElapsed = (startedAt) => {
  if (!startedAt) return '—';
  const start = new Date(startedAt).getTime();
  const diff = Math.max(0, Date.now() - start);
  const mins = Math.floor(diff / 60000);
  const hrs = Math.floor(mins / 60);
  if (hrs > 0) return `${hrs}h ${mins % 60}m`;
  if (mins > 0) return `${mins}m`;
  return `${Math.floor(diff / 1000)}s`;
};

const resolveChannelName = (channelId, statusChannelName, channelNames) => {
  const stringId = String(channelId);
  return channelNames[stringId] || statusChannelName || stringId;
};

const formatCooldownRemaining = (eligibleAtIso) => {
  if (!eligibleAtIso) return null;
  const eligibleAt = new Date(eligibleAtIso).getTime();
  const now = Date.now();
  const diffMs = eligibleAt - now;
  if (diffMs <= 0) return null;

  const totalDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  const months = Math.floor(totalDays / 30);
  const days = totalDays % 30;

  if (months > 0 && days > 0) return `${months} month${months !== 1 ? 's' : ''}, ${days} day${days !== 1 ? 's' : ''}`;
  if (months > 0) return `${months} month${months !== 1 ? 's' : ''}`;
  return `${totalDays} day${totalDays !== 1 ? 's' : ''}`;
};

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return '—';
  }
};

// ─────────────────────────────────────────────────────────────
// Live Monitor — the top section
// ─────────────────────────────────────────────────────────────

const LiveMonitor = ({ channels, loading, channelNames }) => {
  const running = channels.filter(c => c.status === 'in_progress' || c.status === 'paused' || c.status === 'failed');

  const totals = channels.reduce((acc, c) => {
    acc.messages += c.messages_processed || 0;
    acc.mentions += c.mentions_processed || 0;
    acc.emoji    += c.emoji_processed || 0;
    return acc;
  }, { messages: 0, mentions: 0, emoji: 0 });

  const activeCount = channels.filter(c => c.status === 'in_progress').length;

  return (
    <div className="hsync-monitor">
      <div className="hsync-monitor-heading">
        <h2>Live Sync Monitor</h2>
        <span className={`hsync-live-pulse ${activeCount > 0 ? 'live' : ''}`}>
          <span className={`hsync-dot ${activeCount > 0 ? 'live' : ''}`} />
          {activeCount > 0 ? `${activeCount} channel${activeCount !== 1 ? 's' : ''} syncing` : 'Idle'}
        </span>
      </div>

      <div className="hsync-totals-row">
        <div className="hsync-total-card">
          <div className="hsync-total-label">
            <MessageCircle size={14} color={ACCENT} /> Messages collected
          </div>
          <div className="hsync-total-value accent-purple">{formatNumber(totals.messages)}</div>
        </div>
        <div className="hsync-total-card">
          <div className="hsync-total-label">
            <AtSign size={14} color={ACCENT} /> Mentions collected
          </div>
          <div className="hsync-total-value">{formatNumber(totals.mentions)}</div>
        </div>
        <div className="hsync-total-card">
          <div className="hsync-total-label">
            <Smile size={14} color={ACCENT} /> Emoji uses collected
          </div>
          <div className="hsync-total-value accent-gold">{formatNumber(totals.emoji)}</div>
        </div>
        <div className="hsync-total-card">
          <div className="hsync-total-label">
            <CircleCheck size={14} color="#38d9a9" /> Channels caught up
          </div>
          <div className="hsync-total-value accent-green">
            {channels.filter(c => c.status === 'caught_up').length} / {channels.length || 0}
          </div>
        </div>
      </div>

      <div className="hsync-running-grid">
        {loading && running.length === 0 ? (
          <div className="hsync-running-empty">Loading live sync data…</div>
        ) : running.length === 0 ? (
          <div className="hsync-running-empty">
            Nothing running right now. Start a sync below and it'll show up here live.
          </div>
        ) : (
          running.map(ch => {
            const chId = String(ch.channel_id);
            const chName = resolveChannelName(chId, ch.channel_name, channelNames);
            return (
              <div key={chId} className={`hsync-run-card ${ch.status === 'paused' ? 'paused' : ''} ${ch.status === 'failed' ? 'failed' : ''}`}>
                <div className="hsync-run-card-top">
                  <div className="hsync-run-channel"><span>#</span>{chName}</div>
                  <div className="hsync-run-elapsed">{formatElapsed(ch.started_at)}</div>
                </div>

                <div className="hsync-run-stats">
                  <div className="hsync-run-stat">
                    <span className="hsync-run-stat-icon"><MessageCircle size={16} color={ACCENT} /></span>
                    <div className="hsync-run-stat-num">{formatNumber(ch.messages_processed)}</div>
                    <div className="hsync-run-stat-label">Msgs</div>
                  </div>
                  <div className="hsync-run-stat">
                    <span className="hsync-run-stat-icon"><AtSign size={16} color={ACCENT} /></span>
                    <div className="hsync-run-stat-num">{formatNumber(ch.mentions_processed)}</div>
                    <div className="hsync-run-stat-label">Mentions</div>
                  </div>
                  <div className="hsync-run-stat">
                    <span className="hsync-run-stat-icon"><Smile size={16} color={ACCENT} /></span>
                    <div className="hsync-run-stat-num">{formatNumber(ch.emoji_processed)}</div>
                    <div className="hsync-run-stat-label">Emoji</div>
                  </div>
                </div>

                <div className="hsync-run-track">
                  <div className={`hsync-run-track-fill ${ch.status === 'paused' ? 'paused' : ''}`} />
                </div>

                <div className="hsync-run-card-foot">
                  <span className={`hsync-run-status-pill ${ch.status}`}>{statusLabel(ch.status)}</span>
                  {ch.error_message && ch.status === 'failed' && (
                    <span style={{ fontSize: '10px', color: '#ff6b6b', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ch.error_message}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Cooldown banner — shown when the guild can't start a new sync
// ─────────────────────────────────────────────────────────────

const CooldownBanner = ({ cooldown }) => {
  if (!cooldown || !cooldown.on_cooldown) return null;
  const remaining = formatCooldownRemaining(cooldown.eligible_at);

  return (
    <div className="hsync-cooldown-banner">
      <span className="hsync-cooldown-banner-icon">
        <ShieldAlert size={18} color="#ffd24d" />
      </span>
      <div>
        <div className="hsync-cooldown-banner-title">History sync is on cooldown</div>
        <div className="hsync-cooldown-banner-text">
          A sync already completed for this server on <strong>{formatDate(cooldown.last_sync_completed_at)}</strong>.
          You can only run one successful sync every 3 months.
          {remaining && <> Next one's available in <strong>{remaining}</strong> (around {formatDate(cooldown.eligible_at)}).</>}
        </div>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Always-visible heads-up about the 3-month limit
// ─────────────────────────────────────────────────────────────

const SyncPrecautionNote = () => (
  <div className="sync-precaution-note">
    <Info size={14} color="#cc99ff" style={{ flexShrink: 0, marginTop: '1px' }} />
    <span>
      Heads up — once a sync finishes successfully, you won't be able to start another one for{' '}
      <strong>3 months</strong>. Double-check your stat types and time period before hitting Sync All.
    </span>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Reset confirmation modal
// ─────────────────────────────────────────────────────────────

const ResetModal = ({ target, onConfirm, onClose, isCancelReset }) => {
  const [resetStats, setResetStats] = useState(['messages', 'mentions', 'emoji']);
  if (!target) return null;
  const toggleStat = (s) => setResetStats(prev =>
    prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
  );
  const isAll = target.channelId === '__ALL__';
  const targetLabel = isAll ? 'all channels' : `#${target.channelName}`;
  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000
    }}>
      <div style={{
        background: '#111', border: '1px solid #3a1a5a', borderRadius: '16px',
        padding: '28px', maxWidth: '400px', width: '90%'
      }}>
        <h3 style={{ color: '#fff', marginBottom: '8px', fontSize: '18px' }}>
          {isCancelReset ? 'Cancel & Reset Channel' : isAll ? 'Reset All Channels' : 'Reset Channel Progress'}
        </h3>
        <p style={{ color: '#888', fontSize: '13px', marginBottom: '20px' }}>
          {isCancelReset
            ? <>This stops the running sync and clears its progress for <strong style={{ color: '#cc77ff' }}>{targetLabel}</strong>. Pick which stat types to clear.</>
            : <>Pick which stat types to clear for <strong style={{ color: '#cc77ff' }}>{targetLabel}</strong>. The next sync for {isAll ? 'them' : 'it'} will start fresh.</>}
        </p>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
          {STAT_OPTIONS.map(s => {
            const Icon = s.icon;
            return (
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
                <span style={{ display: 'flex', justifyContent: 'center', marginBottom: '4px' }}>
                  <Icon size={20} color={ACCENT} />
                </span>
                {s.label}
              </div>
            );
          })}
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            disabled={resetStats.length === 0}
            onClick={() => onConfirm(target.channelId, resetStats)}
            style={{
              flex: 1, padding: '10px', borderRadius: '8px', border: 'none',
              background: resetStats.length ? (isCancelReset ? '#8b0000' : '#6b00cc') : '#333',
              color: '#fff', fontWeight: 600, cursor: resetStats.length ? 'pointer' : 'not-allowed'
            }}>
            {isCancelReset ? 'Cancel & Reset' : isAll ? 'Reset All' : 'Reset Selected'}
          </button>
          <button
            onClick={onClose}
            style={{
              flex: 1, padding: '10px', borderRadius: '8px',
              border: '1px solid #2a2a2a', background: '#1a1a1a',
              color: '#fff', fontWeight: 600, cursor: 'pointer'
            }}>
            Back
          </button>
        </div>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Custom time period modal
// ─────────────────────────────────────────────────────────────

const CustomDepthModal = ({ open, initialValue, onConfirm, onClose }) => {
  const [days, setDays] = useState(initialValue ? String(initialValue) : '');

  useEffect(() => {
    if (open) setDays(initialValue ? String(initialValue) : '');
  }, [open, initialValue]);

  if (!open) return null;

  const parsed = parseInt(days, 10);
  const isValid = Number.isInteger(parsed) && parsed > 0 && String(parsed) === days.trim();

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000
    }}>
      <div style={{
        background: '#111', border: '1px solid #3a1a5a', borderRadius: '16px',
        padding: '28px', maxWidth: '360px', width: '90%'
      }}>
        <h3 style={{ color: '#fff', marginBottom: '8px', fontSize: '18px' }}>Custom Time Period</h3>
        <p style={{ color: '#888', fontSize: '13px', marginBottom: '16px' }}>
          How many days back should the sync go?
        </p>
        <input
          type="number"
          min="1"
          value={days}
          onChange={(e) => setDays(e.target.value)}
          placeholder="e.g. 45"
          autoFocus
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px',
            border: `2px solid ${isValid || days === '' ? '#2a2a2a' : '#ff6b6b'}`,
            background: '#1a1a1a', color: '#fff', fontSize: '14px',
            marginBottom: '8px', outline: 'none'
          }}
        />
        {days !== '' && !isValid && (
          <p style={{ color: '#ff6b6b', fontSize: '11px', marginBottom: '8px' }}>
            Enter a whole number of days, greater than 0.
          </p>
        )}
        <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
          <button
            disabled={!isValid}
            onClick={() => onConfirm(parsed)}
            style={{
              flex: 1, padding: '10px', borderRadius: '8px', border: 'none',
              background: isValid ? '#6b00cc' : '#333',
              color: '#fff', fontWeight: 600, cursor: isValid ? 'pointer' : 'not-allowed'
            }}>
            {isValid ? `Use ${parsed} day${parsed !== 1 ? 's' : ''}` : 'Use'}
          </button>
          <button
            onClick={onClose}
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

// ─────────────────────────────────────────────────────────────
// History Sync control panel
// ─────────────────────────────────────────────────────────────

const HistorySyncControls = ({ syncStatus, loadingStatus, fetchStatus, guildId, showToast, channelNames, cooldown }) => {
  const [selectedStats, setSelectedStats] = useState({ messages: true, mentions: true, emoji: true });
  const [syncDepthDays, setSyncDepthDays] = useState(null); // null = all time
  const [showCustomDepthModal, setShowCustomDepthModal] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [globalLoading, setGlobalLoading] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [cancelResetTarget, setCancelResetTarget] = useState(null);
  const [resetAllTarget, setResetAllTarget] = useState(false);

  const onCooldown = !!cooldown?.on_cooldown;

  const presetDepthValues = DEPTH_OPTIONS.map(o => o.value);
  const isCustomDepth = !presetDepthValues.includes(syncDepthDays);

  const setChannelLoading = (channelId, val) =>
    setActionLoading(prev => ({ ...prev, [channelId]: val }));

  const statPayload = () => ({
    sync_messages: selectedStats.messages,
    sync_mentions: selectedStats.mentions,
    sync_emoji:    selectedStats.emoji,
    sync_depth_days: syncDepthDays,
  });

  const atLeastOneStat = Object.values(selectedStats).some(Boolean);

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
    if (onCooldown) { showToast('History sync is on cooldown for this server', 'error'); return; }
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
      } else if (res.status === 429) {
        showToast('History sync is on cooldown for this server', 'error');
        await fetchStatus();
      } else if (res.status === 409) {
        showToast('A sync run is already in progress for this server', 'error');
      } else {
        showToast('Failed to start sync', 'error');
      }
    } catch {
      showToast('Error starting sync', 'error');
    } finally {
      setGlobalLoading(false);
    }
  };

  const handleChannelSync = async (channelId) => {
    if (onCooldown) { showToast('History sync is on cooldown for this server', 'error'); return; }
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
      } else if (res.status === 429) {
        showToast('History sync is on cooldown for this server', 'error');
        await fetchStatus();
      } else if (res.status === 409) {
        showToast('A sync run is already in progress for this server', 'error');
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
        showToast('Sync paused — resume any time, it picks up where it left off', 'info');
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

  const handleChannelCancelAndReset = async (channelId, stats) => {
    setChannelLoading(channelId, true);
    setCancelResetTarget(null);
    try {
      const cancelRes = await fetch(`${API_BASE_URL}/api/history-sync/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: String(guildId), channel_id: String(channelId) }),
      });
      if (!cancelRes.ok) {
        showToast('Failed to cancel sync', 'error');
        return;
      }
      const resetRes = await fetch(`${API_BASE_URL}/api/history-sync/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guild_id: String(guildId),
          channel_id: String(channelId),
          stats: stats ?? null,
        }),
      });
      if (resetRes.ok) {
        showToast('Sync cancelled and progress reset', 'success');
      } else {
        showToast('Cancelled, but reset failed — try Reset manually', 'error');
      }
      await fetchStatus();
    } catch {
      showToast('Error cancelling channel', 'error');
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

  const handleResetAll = async (_ignoredChannelId, stats) => {
    setResetAllTarget(false);
    setGlobalLoading(true);
    const targets = syncStatus?.channels ?? [];
    try {
      const results = await Promise.allSettled(
        targets.map(ch => fetch(`${API_BASE_URL}/api/history-sync/reset`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            guild_id: String(guildId),
            channel_id: String(ch.channel_id),
            stats: stats ?? null,
          }),
        }))
      );
      const failedCount = results.filter(r => r.status !== 'fulfilled' || !r.value.ok).length;
      if (failedCount === 0) {
        showToast(`Reset progress for ${targets.length} channel(s)`, 'success');
      } else {
        showToast(`Reset finished with ${failedCount} failure(s) out of ${targets.length}`, 'error');
      }
      await fetchStatus();
    } catch {
      showToast('Error resetting all channels', 'error');
    } finally {
      setGlobalLoading(false);
    }
  };

  const channels = syncStatus?.channels ?? [];
  const totalChannels = channels.length;
  const runningCount  = channels.filter(c => c.status === 'in_progress').length;
  const caughtUpCount = channels.filter(c => c.status === 'caught_up').length;
  const failedCount   = channels.filter(c => c.status === 'failed').length;
  const pendingCount  = channels.filter(c => c.status === 'pending').length;

  return (
    <>
      <ResetModal target={resetTarget} onConfirm={handleChannelReset} onClose={() => setResetTarget(null)} isCancelReset={false} />
      <ResetModal target={cancelResetTarget} onConfirm={handleChannelCancelAndReset} onClose={() => setCancelResetTarget(null)} isCancelReset />
      <ResetModal
        target={resetAllTarget ? { channelId: '__ALL__', channelName: 'all channels' } : null}
        onConfirm={handleResetAll}
        onClose={() => setResetAllTarget(false)}
        isCancelReset={false}
      />
      <CustomDepthModal
        open={showCustomDepthModal}
        initialValue={isCustomDepth ? syncDepthDays : ''}
        onConfirm={(value) => { setSyncDepthDays(value); setShowCustomDepthModal(false); }}
        onClose={() => setShowCustomDepthModal(false)}
      />

      <div className="sync-layout">
        <div className="sync-controls-panel">
          <div>
            <div className="sync-section-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              Stat types to sync
              <InfoIcon descriptions={[
                { level: 'Messages', description: 'How many messages each person sent.' },
                { level: 'Mentions', description: 'Who mentioned who, and how often.' },
                { level: 'Emoji',    description: 'Which emojis were used and how many times.' },
              ]} />
            </div>
            <div className="sync-stat-toggles">
              {STAT_OPTIONS.map(s => {
                const Icon = s.icon;
                return (
                  <div key={s.key}
                    className={`sync-stat-toggle ${selectedStats[s.key] ? 'active' : ''}`}
                    onClick={() => setSelectedStats(prev => ({ ...prev, [s.key]: !prev[s.key] }))}>
                    <span className="sync-stat-toggle-icon"><Icon size={20} color={ACCENT} /></span>
                    {s.label}
                  </div>
                );
              })}
            </div>
            {!atLeastOneStat && (
              <p style={{ color: '#ff6b6b', fontSize: '11px', marginTop: '6px' }}>
                Select at least one stat type to sync.
              </p>
            )}
          </div>

          <hr className="sync-divider" />

          {syncStatus && (
            <div className="sync-summary-row">
              <div className="sync-summary-chip">
                <NotepadText size={13} color={ACCENT} /> <strong>{totalChannels}</strong> total
              </div>
              {runningCount  > 0 && (
                <div className="sync-summary-chip">
                  <Zap size={13} color={ACCENT} /> <strong>{runningCount}</strong> running
                </div>
              )}
              {caughtUpCount > 0 && (
                <div className="sync-summary-chip">
                  <CircleCheck size={13} color="#38d9a9" /> <strong>{caughtUpCount}</strong> done
                </div>
              )}
              {pendingCount  > 0 && (
                <div className="sync-summary-chip">
                  <Hourglass size={13} color="#888" /> <strong>{pendingCount}</strong> pending
                </div>
              )}
              {failedCount   > 0 && (
                <div className="sync-summary-chip" style={{ borderColor: '#5a1a1a' }}>
                  <CircleX size={13} color="#ff6b6b" /> <strong style={{ color: '#ff6b6b' }}>{failedCount}</strong> failed
                </div>
              )}
            </div>
          )}

          <div className="sync-action-buttons">
            <div className="sync-section-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              Global actions
              <InfoIcon descriptions={[
                { level: 'Initialise', description: 'Adds every channel in your server to the list below. Run this first if the list is empty.' },
                { level: 'Sync all',   description: 'Backfills history for every channel at once, using the stat types and time period you picked. Only counts toward the 3-month limit if every channel finishes successfully.' },
                { level: 'Reset all',  description: 'Clears synced progress for every channel at once, for the stat types you choose.' },
              ]} />
            </div>

            <button className="sync-btn sync-btn-secondary" onClick={fetchStatus} disabled={loadingStatus || globalLoading}>
              <RotateCcw size={16} color={ACCENT} className={loadingStatus ? 'icon-spin' : ''} />
              {loadingStatus ? 'Refreshing...' : 'Refresh status'}
            </button>

            <button className="sync-btn sync-btn-secondary" onClick={handleInit} disabled={globalLoading || loadingStatus}>
              <Power size={16} color={ACCENT} />
              Initialise all channels
            </button>

            <button
              className="sync-btn sync-btn-danger"
              onClick={() => setResetAllTarget(true)}
              disabled={globalLoading || loadingStatus || channels.length === 0}>
              <Trash2 size={16} color="#ff8a8a" />
              Reset all channels
            </button>

            <div>
              <div className="sync-section-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                Time period
                <InfoIcon descriptions={[
                  { level: 'Time period', description: 'How far back to pull history from. Shorter periods finish faster. "All time" goes as far back as Discord allows, and "Custom" lets you pick an exact number of days.' },
                ]} />
              </div>
              <div className="sync-depth-row">
                {DEPTH_OPTIONS.map(opt => (
                  <div key={opt.label}
                    className={`sync-depth-chip ${!isCustomDepth && syncDepthDays === opt.value ? 'active' : ''}`}
                    onClick={() => setSyncDepthDays(opt.value)}>
                    {opt.label}
                  </div>
                ))}
                <div
                  className={`sync-depth-chip ${isCustomDepth ? 'active' : ''}`}
                  onClick={() => setShowCustomDepthModal(true)}>
                  {isCustomDepth ? `${syncDepthDays} days` : 'Custom'}
                </div>
              </div>
            </div>

            <SyncPrecautionNote />

            <button
              className="sync-btn sync-btn-primary"
              onClick={handleSyncAll}
              disabled={globalLoading || loadingStatus || !atLeastOneStat || onCooldown}
              title={onCooldown ? 'History sync is on cooldown for this server' : undefined}>
              <Play size={16} color="#fff" />
              {globalLoading ? 'Starting...' : onCooldown ? 'On cooldown' : 'Sync all channels'}
            </button>
          </div>

          <p style={{ color: '#555', fontSize: '11px', lineHeight: 1.6 }}>
            Syncing pulls in your server's past messages, mentions, and emoji. Big servers can take a
            while — pause anytime to free things up, or cancel to wipe progress and start over.
          </p>
        </div>

        <div>
          <div className="sync-section-label" style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            Channels {loadingStatus && <span style={{ color: '#aa00ff' }}>— refreshing…</span>}
            <InfoIcon descriptions={[
              { level: 'Start / Resume', description: 'Begins syncing this channel, or picks back up where a paused sync left off.' },
              { level: 'Pause',          description: 'Stops for now without losing progress. Hit Resume later to continue right where it stopped.' },
              { level: 'Cancel',         description: 'Stops the sync and clears its progress for the stat types you choose, so the next sync starts over.' },
              { level: 'Reset',          description: 'Clears progress for the stat types you choose, even if nothing is currently running.' },
            ]} />
          </div>

          <div className="sync-channels-panel">
            {channels.length === 0 ? (
              <div className="sync-empty-channels">
                {loadingStatus
                  ? 'Loading channels…'
                  : 'No channels found. Click "Initialise all channels" to populate the list.'}
              </div>
            ) : (
              channels.map(ch => {
                const chId = String(ch.channel_id);
                const chName = resolveChannelName(chId, ch.channel_name, channelNames);
                const chStatus = ch.status || 'pending';
                const isLoading = !!actionLoading[chId];
                const isRunning = chStatus === 'in_progress';
                const hasAnyProgress = (ch.messages_processed || ch.mentions_processed || ch.emoji_processed);
                const startDisabled = isLoading || !atLeastOneStat || (onCooldown && chStatus !== 'paused' && !isRunning);

                return (
                  <div key={chId} className={`sync-channel-row ${chStatus}`}>
                    <div className="sync-channel-name">
                      <div><span>#</span>{chName}</div>
                      {hasAnyProgress > 0 && (
                        <div className="sync-channel-substat">
                          <span className="substat-item"><MessageCircle size={11} color={ACCENT} />{formatNumber(ch.messages_processed)}</span>
                          <span className="substat-item"><AtSign size={11} color={ACCENT} />{formatNumber(ch.mentions_processed)}</span>
                          <span className="substat-item"><Smile size={11} color={ACCENT} />{formatNumber(ch.emoji_processed)}</span>
                        </div>
                      )}
                    </div>

                    <span className={`sync-status-badge ${chStatus}`}>
                      {statusLabel(chStatus)}
                    </span>

                    <div className="sync-row-buttons">
                      {!isRunning && (
                        <button
                          className="sync-row-btn sync-row-btn-start"
                          onClick={() => handleChannelSync(chId)}
                          disabled={startDisabled}
                          title={onCooldown && startDisabled ? 'History sync is on cooldown for this server' : undefined}>
                          {isLoading ? '…' : (
                            <>
                              <Play size={11} color="#cc77ff" />
                              {chStatus === 'paused' ? 'Resume' : 'Start'}
                            </>
                          )}
                        </button>
                      )}

                      {isRunning && (
                        <button
                          className="sync-row-btn sync-row-btn-pause"
                          onClick={() => handleChannelPause(chId)}
                          disabled={isLoading}>
                          {isLoading ? '…' : (
                            <>
                              <Pause size={11} color="#ffd700" />
                              Pause
                            </>
                          )}
                        </button>
                      )}

                      {(isRunning || chStatus === 'paused') && (
                        <button
                          className="sync-row-btn sync-row-btn-cancel"
                          onClick={() => setCancelResetTarget({ channelId: chId, channelName: chName })}
                          disabled={isLoading}>
                          {isLoading ? '…' : (
                            <>
                              <CircleX size={11} color="#ff6b6b" />
                              Cancel
                            </>
                          )}
                        </button>
                      )}

                      <button
                        className="sync-row-btn sync-row-btn-reset"
                        onClick={() => setResetTarget({ channelId: chId, channelName: chName })}
                        disabled={isLoading}>
                        <Trash2 size={11} color="#6b9eff" />
                        Reset
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
// Access denied
// ─────────────────────────────────────────────────────────────

const AccessDenied = () => (
  <div className="dashboard-content">
    <div className="error-message-container">
      <div className="error-icon"><Lock size={48} color="#ff4444" /></div>
      <h2 className="error-title">Access Denied</h2>
      <p className="error-message">History sync requires <strong>Administrator</strong> permission on this server.</p>
    </div>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Root page component
// ─────────────────────────────────────────────────────────────

const HistorySyncPage = () => {
  const [currentServer, setCurrentServer] = useState(null);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [apiError, setApiError] = useState(null);
  const [toast, setToast] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);

  const [syncStatus, setSyncStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(false);

  const [channelNames, setChannelNames] = useState({});

  const pollTimer = useRef(null);

  const isPrivilegedUser = (userId) => PRIVILEGED_USERS.includes(userId);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const ToastMessage = () => {
    if (!toast) return null;
    const colors = {
      success: { bg: '#00b894', Icon: CircleCheck },
      error:   { bg: '#ff7675', Icon: CircleX },
      info:    { bg: '#0984e3', Icon: Info },
    };
    const color = colors[toast.type] || colors.info;
    return (
      <div className="toast-message" style={{ backgroundColor: color.bg }}>
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          {color.Icon ? <color.Icon size={16} color="#fff" /> : null}
        </span>
        <span>{toast.message}</span>
        <button onClick={() => setToast(null)}
          style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', marginLeft: '10px', display: 'inline-flex', alignItems: 'center' }}>
          <CircleX size={16} color="white" />
        </button>
      </div>
    );
  };

  const fetchStatus = useCallback(async (guildId) => {
    if (!guildId) return;
    setLoadingStatus(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/history-sync/status?guild_id=${guildId}`, {
        credentials: 'include',
      });
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
  }, []);

  const fetchChannelNames = useCallback(async (guildId) => {
    if (!guildId) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/server/real-channels?guild_id=${guildId}`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const map = {};
          data.forEach(ch => { map[String(ch.id)] = ch.name; });
          setChannelNames(map);
        }
      }
    } catch {
      // Silent failure — components fall back to raw channel IDs.
    }
  }, []);

  useEffect(() => {
    if (currentServer?.id) {
      fetchChannelNames(currentServer.id);
    }
  }, [currentServer, fetchChannelNames]);

  useEffect(() => {
    if (!currentServer || hasAccess !== true) return;

    const tick = async () => {
      await fetchStatus(currentServer.id);
    };
    tick();

    const scheduleNext = () => {
      const channels = syncStatus?.channels ?? [];
      const anyRunning = channels.some(c => c.status === 'in_progress');
      const delay = anyRunning ? ACTIVE_POLL_MS : IDLE_POLL_MS;
      pollTimer.current = setTimeout(async () => {
        await tick();
        scheduleNext();
      }, delay);
    };
    scheduleNext();

    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentServer, hasAccess]);

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
          const serversResponse = await fetch(`${API_BASE_URL}/api/user/servers`, {
            credentials: 'include', headers: { 'Accept': 'application/json' },
          });
          if (serversResponse.ok) {
            const servers = await serversResponse.json();
            if (Array.isArray(servers) && servers.length > 0) {
              const selected = authData.user.selected_server
                ? servers.find(s => s.id === authData.user.selected_server) || servers[0]
                : servers[0];
              setCurrentServer(selected);
              setHasAccess(true);
            }
          }
          setLoadingServers(false);
          return;
        }

        const serversResponse = await fetch(`${API_BASE_URL}/api/user/servers`, {
          credentials: 'include', headers: { 'Accept': 'application/json' },
        });
        if (serversResponse.ok) {
          const servers = await serversResponse.json();
          if (Array.isArray(servers) && servers.length > 0) {
            const selected = authData.user.selected_server
              ? servers.find(s => s.id === authData.user.selected_server) || servers[0]
              : servers[0];
            if (selected) {
              setCurrentServer(selected);
              setHasAccess(!!selected.has_admin);
            }
          }
        }
      }
    } catch (error) {
      setApiError('Failed to load servers. Please check your connection.');
    } finally {
      setLoadingServers(false);
    }
  };

  if (loadingServers) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="loading-container"><LoadingSpinner text="Loading servers..." /></div>
      </div><Footer /></main></div><style>{styles}</style></>);
  }

  if (!isAuthenticated) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="no-server"><h2>Please Log In</h2><p>You need to be logged in to manage history sync.</p>
          <a href={`${API_BASE_URL}/api/auth/discord`} className="login-button">Login with Discord</a>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (!currentServer) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="no-server"><h2>No Server Available</h2><p>Add the bot to a Discord server to manage history sync.</p>
          <a href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands"
            className="invite-button" target="_blank" rel="noopener noreferrer">Invite bot to server</a>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (apiError) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="error-message-container"><div className="error-icon"><TriangleAlert size={48} color="#ff4444" /></div>
          <h2 className="error-title">Error loading data</h2>
          <p className="error-message">{apiError}</p>
          <button onClick={() => window.location.reload()} className="invite-button">Retry</button>
        </div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (hasAccess === null) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
      <main className="dashboard-main"><div className="dashboard-content">
        <div className="loading-container"><LoadingSpinner text="Checking permissions..." /></div>
      </div><Footer /></main></div><style>{styles}</style></>);
  }

  const channels = syncStatus?.channels ?? [];
  const cooldown = syncStatus?.cooldown ?? { on_cooldown: false };

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        <main className="dashboard-main">
          <div className="dashboard-content">
            {hasAccess ? (
              <>
                <div className="hsync-page-header">
                  <div className="hsync-title-block">
                    <h1><History size={26} color={ACCENT} /> History Data Sync</h1>
                    <p>
                      Pull in your server's past messages, mentions, and emoji so your stats go back
                      further than the day you started tracking. Watch it happen live below, then start,
                      pause, or reset individual channels.
                    </p>
                  </div>
                </div>

                <CooldownBanner cooldown={cooldown} />

                <LiveMonitor channels={channels} loading={loadingStatus && !syncStatus} channelNames={channelNames} />

                <SettingsCard
                  title="Sync Controls" icon={<FolderSync size={22} color={ACCENT} />}
                  description="Choose what to sync and how far back, then run it for one channel or all of them."
                  accentBg
                >
                  <HistorySyncControls
                    syncStatus={syncStatus}
                    loadingStatus={loadingStatus}
                    fetchStatus={() => fetchStatus(currentServer.id)}
                    guildId={currentServer.id}
                    showToast={showToast}
                    channelNames={channelNames}
                    cooldown={cooldown}
                  />
                </SettingsCard>
              </>
            ) : (
              <AccessDenied />
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
    <HistorySyncPage />
  </React.StrictMode>
);

export default HistorySyncPage;