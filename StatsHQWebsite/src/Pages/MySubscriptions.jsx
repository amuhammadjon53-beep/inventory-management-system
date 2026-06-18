import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Settings, Server, FileText, XCircle, RotateCcw, Clock, CheckCircle, Ban,
  AlertCircle, RefreshCw, ChevronDown, ChevronUp, Receipt, ArrowRightLeft,
  KeyRound, ShieldCheck, X, Search
} from 'lucide-react';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const API_URL = window.location.origin;

// Staff/privileged accounts — mirrors PADDLE_STAFF_DISCORD_IDS on the backend.
// The backend re-checks this independently; this is only used to decide
// whether to show the staff panel in the UI.
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ─── Module registry ────────────────────────────────────────────────────────────
const MODULE_INFO = {
  'optimization-plus': {
    name: 'Optimization+',
    icon: <Settings size={22} color="#aa00ff" />,
  },
};

const getModuleInfo = (moduleKey) =>
  MODULE_INFO[moduleKey] || { name: moduleKey, icon: <Settings size={22} color="#aa00ff" /> };

// ─── Status helpers ─────────────────────────────────────────────────────────────
const STATUS_META = {
  active: {
    label: 'Active',
    color: '#00e07a',
    bg: 'rgba(0,224,122,0.08)',
    border: 'rgba(0,224,122,0.25)',
    icon: <CheckCircle size={13} />,
  },
  canceled: {
    label: 'Cancelled',
    color: '#ff6b6b',
    bg: 'rgba(255,107,107,0.08)',
    border: 'rgba(255,107,107,0.25)',
    icon: <Ban size={13} />,
  },
  paused: {
    label: 'Paused',
    color: '#f0a500',
    bg: 'rgba(240,165,0,0.08)',
    border: 'rgba(240,165,0,0.25)',
    icon: <Clock size={13} />,
  },
  past_due: {
    label: 'Past Due',
    color: '#f0a500',
    bg: 'rgba(240,165,0,0.08)',
    border: 'rgba(240,165,0,0.25)',
    icon: <AlertCircle size={13} />,
  },
  trialing: {
    label: 'Trialing',
    color: '#5b9cf6',
    bg: 'rgba(91,156,246,0.08)',
    border: 'rgba(91,156,246,0.25)',
    icon: <Clock size={13} />,
  },
  refunded: {
    label: 'Refunded',
    color: '#888b99',
    bg: 'rgba(136,139,153,0.08)',
    border: 'rgba(136,139,153,0.25)',
    icon: <RotateCcw size={13} />,
  },
};

// ─── Transaction status meta ────────────────────────────────────────────────────
const TRANSACTION_STATUS_META = {
  completed: {
    label: 'Completed',
    color: '#00e07a',
    bg: 'rgba(0,224,122,0.08)',
    border: 'rgba(0,224,122,0.25)',
  },
  failed: {
    label: 'Failed',
    color: '#ff6b6b',
    bg: 'rgba(255,107,107,0.08)',
    border: 'rgba(255,107,107,0.25)',
  },
  canceled: {
    label: 'Canceled',
    color: '#888b99',
    bg: 'rgba(136,139,153,0.08)',
    border: 'rgba(136,139,153,0.25)',
  },
};

const getTransactionStatusMeta = (status) =>
  TRANSACTION_STATUS_META[status] || TRANSACTION_STATUS_META['canceled'];

const getStatusMeta = (status) => STATUS_META[status] || STATUS_META['canceled'];

// ─── 48-hour refund/cancel eligibility ─────────────────────────────────────────
const isWithin48Hours = (dateStr) => {
  if (!dateStr) return false;
  const created = new Date(dateStr);
  const now = new Date();
  return (now - created) < 48 * 60 * 60 * 1000;
};

const formatDate = (dateStr) => {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  });
};

const formatDateTime = (dateStr) => {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
};

const formatCycle = (cycle) =>
  cycle === 'yearly' ? 'Yearly' : 'Monthly';

const formatNumber = (num) => {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return (num || 0).toString();
};

// ─── Filter tabs ────────────────────────────────────────────────────────────────
const FILTERS = ['all', 'active', 'canceled', 'paused', 'past_due'];

// ─── ConfirmModal ───────────────────────────────────────────────────────────────
const ConfirmModal = ({ title, message, confirmLabel, confirmClass, onConfirm, onCancel, loading, disabled }) => (
  <div className="modal-overlay" onClick={onCancel}>
    <div className="modal-box" onClick={(e) => e.stopPropagation()}>
      <h3 className="modal-title">{title}</h3>
      <p className="modal-message">{message}</p>
      <div className="modal-actions">
        <button className="modal-cancel-btn" onClick={onCancel} disabled={loading}>
          Keep subscription
        </button>
        <button
          className={`modal-confirm-btn ${confirmClass || ''}`}
          onClick={onConfirm}
          disabled={loading || disabled}
        >
          {loading ? <><div className="btn-spinner" /><span>Processing...</span></> : confirmLabel}
        </button>
      </div>
    </div>
  </div>
);

// ─── SwitchServerModal ──────────────────────────────────────────────────────────
const SwitchServerModal = ({ sub, servers, serversLoading, onConfirm, onCancel, loading, error }) => {
  const [targetGuildId, setTargetGuildId] = useState('');
  const eligibleServers = servers.filter(s => s.id !== sub.guild_id?.toString() && s.id !== sub.guild_id);

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-icon-badge">
          <ArrowRightLeft size={20} color="#aa00ff" />
        </div>
        <h3 className="modal-title">Move to a different server</h3>
        <p className="modal-message">
          Move the {getModuleInfo(sub.module_key).name} subscription off{' '}
          <strong style={{ color: '#d0d0d0' }}>{sub.guild_name || sub.guild_id}</strong>{' '}
          and onto another server you administer. Access on the current server
          will be revoked immediately and granted on the new one.
        </p>

        {serversLoading ? (
          <div className="switch-servers-loading">
            <div className="btn-spinner-sm" />
            <span>Loading your servers...</span>
          </div>
        ) : eligibleServers.length === 0 ? (
          <div className="switch-empty-notice">
            <AlertCircle size={14} />
            <span>No other admin-eligible servers found.</span>
          </div>
        ) : (
          <div className="switch-server-list">
            {eligibleServers.map(s => (
              <button
                key={s.id}
                className={`switch-server-option ${targetGuildId === s.id ? 'selected' : ''}`}
                onClick={() => setTargetGuildId(s.id)}
              >
                <img
                  src={s.iconUrl || 'https://cdn.discordapp.com/embed/avatars/0.png'}
                  alt=""
                  className="switch-server-icon"
                  onError={(e) => { e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; }}
                />
                <span className="switch-server-name">{s.name}</span>
                {targetGuildId === s.id && <CheckCircle size={16} color="#aa00ff" />}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="switch-error-notice">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        <div className="modal-actions">
          <button className="modal-cancel-btn" onClick={onCancel} disabled={loading}>
            Cancel
          </button>
          <button
            className="modal-confirm-btn primary"
            onClick={() => onConfirm(targetGuildId)}
            disabled={loading || !targetGuildId}
          >
            {loading ? <><div className="btn-spinner" /><span>Moving...</span></> : 'Move subscription'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── StaffGrantPanel ────────────────────────────────────────────────────────────
const StaffGrantPanel = ({ apiUrl, onGranted }) => {
  const [expanded, setExpanded] = useState(false);
  const [guildIdInput, setGuildIdInput] = useState('');
  const [moduleKey, setModuleKey] = useState('all');
  const [reason, setReason] = useState('');
  const [expiresInDays, setExpiresInDays] = useState(365);

  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState(null);
  const [lookedUpGuild, setLookedUpGuild] = useState(null);

  const [grantLoading, setGrantLoading] = useState(false);
  const [grantError, setGrantError] = useState(null);
  const [grantSuccess, setGrantSuccess] = useState(null);

  const handleLookup = async () => {
    const trimmed = guildIdInput.trim();
    if (!trimmed) {
      setLookupError('Enter a server ID first.');
      return;
    }
    setLookupLoading(true);
    setLookupError(null);
    setLookedUpGuild(null);
    setGrantSuccess(null);
    try {
      const res = await fetch(`${apiUrl}/api/admin/lookup-server/${trimmed}`, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
      const result = await res.json();
      if (result.success && result.found) {
        setLookedUpGuild(result.server);
      } else {
        setLookupError(result.message || 'Server not found or bot is not in this server.');
      }
    } catch (err) {
      setLookupError('Failed to look up server. Please try again.');
    } finally {
      setLookupLoading(false);
    }
  };

  const handleGrant = async () => {
    if (!lookedUpGuild) return;
    if (!reason.trim()) {
      setGrantError("A reason is required — it's recorded in the audit log.");
      return;
    }
    setGrantLoading(true);
    setGrantError(null);
    try {
      const res = await fetch(`${apiUrl}/api/paddle/staff/grants`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          guild_id: lookedUpGuild.id,
          module_key: moduleKey,
          reason: reason.trim(),
          expires_in_days: Number(expiresInDays) || 365,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create grant');

      setGrantSuccess(
        `Granted ${moduleKey === 'all' ? 'all modules' : moduleKey} to ${lookedUpGuild.name} until ${formatDate(data.expires_at)}.`
      );
      setLookedUpGuild(null);
      setGuildIdInput('');
      setReason('');
      if (onGranted) onGranted();
    } catch (err) {
      setGrantError(err.message);
    } finally {
      setGrantLoading(false);
    }
  };

  return (
    <div className="staff-panel-wrap">
      <button className="staff-toggle-btn" onClick={() => setExpanded(!expanded)}>
        <KeyRound size={14} />
        <span>{expanded ? 'Hide staff tools' : 'Staff tools — grant server access'}</span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <div className="staff-panel">
          <div className="staff-panel-header">
            <ShieldCheck size={16} color="#aa00ff" />
            <span>Grant comp access by server ID</span>
          </div>
          <p className="staff-panel-subtext">
            Look up a server by Discord ID, then grant module access without a
            Paddle purchase. Every grant is recorded with your account and a reason, and expires automatically.
          </p>

          <div className="staff-lookup-row">
            <div className="staff-input-wrap">
              <Search size={14} className="staff-input-icon" />
              <input
                type="text"
                className="staff-text-input"
                placeholder="Server ID (e.g. 123456789012345678)"
                value={guildIdInput}
                onChange={(e) => { setGuildIdInput(e.target.value); setGrantSuccess(null); }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleLookup(); }}
              />
            </div>
            <button className="staff-lookup-btn" onClick={handleLookup} disabled={lookupLoading}>
              {lookupLoading ? <div className="btn-spinner-sm" /> : 'Look up'}
            </button>
          </div>

          {lookupError && (
            <div className="switch-error-notice">
              <AlertCircle size={14} />
              <span>{lookupError}</span>
            </div>
          )}

          {grantSuccess && (
            <div className="staff-success-notice">
              <CheckCircle size={14} />
              <span>{grantSuccess}</span>
            </div>
          )}

          {lookedUpGuild && (
            <div className="staff-result-card">
              <div className="staff-result-server">
                <img
                  src={lookedUpGuild.icon_url || 'https://cdn.discordapp.com/embed/avatars/0.png'}
                  alt=""
                  className="staff-result-icon"
                  onError={(e) => { e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; }}
                />
                <div className="staff-result-info">
                  <div className="staff-result-name">{lookedUpGuild.name}</div>
                  <div className="staff-result-meta">
                    ID: {lookedUpGuild.id} · {formatNumber(lookedUpGuild.member_count)} members
                  </div>
                </div>
              </div>

              <div className="staff-form-grid">
                <label className="staff-field">
                  <span className="staff-field-label">Module</span>
                  <select
                    className="staff-select"
                    value={moduleKey}
                    onChange={(e) => setModuleKey(e.target.value)}
                  >
                    <option value="all">All modules</option>
                    {Object.entries(MODULE_INFO).map(([key, info]) => (
                      <option key={key} value={key}>{info.name}</option>
                    ))}
                  </select>
                </label>

                <label className="staff-field">
                  <span className="staff-field-label">Expires in (days)</span>
                  <input
                    type="number"
                    min={1}
                    max={3650}
                    className="staff-number-input"
                    value={expiresInDays}
                    onChange={(e) => setExpiresInDays(e.target.value)}
                  />
                </label>
              </div>

              <label className="staff-field" style={{ marginTop: '12px' }}>
                <span className="staff-field-label">Reason (required, audit log)</span>
                <input
                  type="text"
                  className="staff-text-input full-width"
                  placeholder="e.g. partner deal, internal test server"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>

              {grantError && (
                <div className="switch-error-notice" style={{ marginTop: '12px' }}>
                  <AlertCircle size={14} />
                  <span>{grantError}</span>
                </div>
              )}

              <div className="staff-result-actions">
                <button className="staff-discard-btn" onClick={() => setLookedUpGuild(null)}>
                  Discard
                </button>
                <button className="staff-grant-btn" onClick={handleGrant} disabled={grantLoading}>
                  {grantLoading ? <><div className="btn-spinner-sm" /><span>Granting...</span></> : 'Grant access'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── StaffGrantsList ────────────────────────────────────────────────────────────
const StaffGrantsList = ({ apiUrl, onGrantRevoked }) => {
  const [expanded, setExpanded] = useState(false);
  const [grants, setGrants] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [revokingId, setRevokingId] = useState(null);
  const [revokeConfirm, setRevokeConfirm] = useState(null);

  const fetchMyGrants = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/api/paddle/staff/grants/my-grants`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' },
      });
      if (!res.ok) throw new Error('Failed to fetch grants');
      const data = await res.json();
      setGrants(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async (grant) => {
    setRevokingId(grant.paddle_subscription_id);
    try {
      const res = await fetch(
        `${apiUrl}/api/paddle/staff/grants/${grant.paddle_subscription_id}`,
        {
          method: 'DELETE',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to revoke grant');
      }
      // Remove from list or update status
      setGrants(prev => prev.filter(g => g.paddle_subscription_id !== grant.paddle_subscription_id));
      if (onGrantRevoked) onGrantRevoked();
      setRevokeConfirm(null);
    } catch (err) {
      setError(err.message);
      setTimeout(() => setError(null), 5000);
    } finally {
      setRevokingId(null);
    }
  };

  const toggleExpand = () => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);
    if (newExpanded && grants.length === 0) {
      fetchMyGrants();
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return '#00e07a';
      case 'canceled': return '#ff6b6b';
      case 'refunded': return '#888b99';
      default: return '#888b99';
    }
  };

  const getModuleDisplay = (moduleKey) => {
    return MODULE_INFO[moduleKey]?.name || moduleKey || 'Unknown';
  };

  return (
    <div className="staff-panel-wrap" style={{ marginTop: '12px' }}>
      <button className="staff-toggle-btn" onClick={toggleExpand}>
        <KeyRound size={14} />
        <span>{expanded ? 'Hide my grants' : `My grants (${grants.length})`}</span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <div className="staff-panel">
          <div className="staff-panel-header">
            <ShieldCheck size={16} color="#aa00ff" />
            <span>Grants you've issued</span>
            <button 
              className="staff-refresh-btn"
              onClick={fetchMyGrants}
              disabled={loading}
            >
              <RefreshCw size={13} className={loading ? 'spinning' : ''} />
            </button>
          </div>
          <p className="staff-panel-subtext">
            All comp grants you've created. Each grant is automatically revoked
            if the subscription is canceled or expires.
          </p>

          {loading ? (
            <div className="history-loading">
              <div className="btn-spinner-sm" />
              <span>Loading your grants...</span>
            </div>
          ) : error ? (
            <div className="history-error">
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
          ) : grants.length === 0 ? (
            <div className="history-empty">
              <span>You haven't issued any comp grants yet.</span>
            </div>
          ) : (
            <div className="grants-list">
              {grants.map(grant => (
                <div key={grant.paddle_subscription_id} className="grant-item">
                  <div className="grant-header">
                    <div className="grant-server">
                      <span className="grant-guild-name">
                        {grant.guild_name || grant.guild_id}
                      </span>
                      <span className="grant-module">
                        {getModuleDisplay(grant.module_key)}
                      </span>
                    </div>
                    <span 
                      className="grant-status"
                      style={{ color: getStatusColor(grant.status) }}
                    >
                      {grant.status}
                    </span>
                  </div>
                  
                  <div className="grant-details">
                    <div className="grant-detail">
                      <Clock size={12} />
                      <span>Created {formatDate(grant.created_at)}</span>
                    </div>
                    {grant.current_period_end && (
                      <div className="grant-detail">
                        <Clock size={12} />
                        <span>Expires {formatDate(grant.current_period_end)}</span>
                      </div>
                    )}
                    {grant.grant_reason && (
                      <div className="grant-detail reason">
                        <span className="reason-label">Reason:</span>
                        <span className="reason-text">"{grant.grant_reason}"</span>
                      </div>
                    )}
                  </div>

                  {grant.status === 'active' && (
                    <div className="grant-actions">
                      <button
                        className="grant-revoke-btn"
                        onClick={() => setRevokeConfirm(grant)}
                        disabled={revokingId === grant.paddle_subscription_id}
                      >
                        {revokingId === grant.paddle_subscription_id ? (
                          <><div className="btn-spinner-sm" /><span>Revoking...</span></>
                        ) : (
                          <><XCircle size={13} /><span>Revoke access</span></>
                        )}
                      </button>
                    </div>
                  )}

                  {grant.status === 'canceled' && (
                    <div className="grant-revoked-badge">
                      <XCircle size={12} color="#ff6b6b" />
                      <span>Revoked</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Revoke confirmation modal */}
      {revokeConfirm && (
        <ConfirmModal
          title="Revoke comp grant?"
          message={`This will immediately revoke ${getModuleDisplay(revokeConfirm.module_key)} access for ${revokeConfirm.guild_name || revokeConfirm.guild_id}. This action cannot be undone.`}
          confirmLabel="Yes, revoke access"
          confirmClass="danger"
          onConfirm={() => handleRevoke(revokeConfirm)}
          onCancel={() => setRevokeConfirm(null)}
          loading={revokingId === revokeConfirm.paddle_subscription_id}
        />
      )}
    </div>
  );
};

// ─── SubscriptionCard ───────────────────────────────────────────────────────────
const SubscriptionCard = ({
  sub,
  onCancel,
  onRefund,
  onInvoice,
  onTransactionInvoice,
  onSwitchServer,
  invoiceLoading,
  cancelLoading,
  refundLoading,
  transactionHistory,
  onToggleHistory,
  isHistoryExpanded,
}) => {
  const info = getModuleInfo(sub.module_key);
  const statusMeta = getStatusMeta(sub.status);
  const eligible = sub.status === 'active' && isWithin48Hours(sub.created_at || sub.current_period_start);
  const discountPct = sub.discount_pct ? (sub.discount_pct * 100).toFixed(0) : null;
  const isStaffGrant = sub.source === 'staff_grant';

  const historyData = transactionHistory[sub.paddle_subscription_id];
  const isLoading = historyData?.loading || false;
  const transactions = historyData?.transactions || [];
  const error = historyData?.error || null;

  return (
    <div className="module-card">
      <div className="card-sheen" />

      {/* Header */}
      <div className="module-header">
        <div className="module-icon">{info.icon}</div>
        <div className="module-title-group">
          <h2 className="module-name">{info.name}</h2>
          <span className="module-price">
            {isStaffGrant ? (
              <span className="staff-grant-pill">Staff grant</span>
            ) : (
              <>
                ${parseFloat(sub.final_price_usd || 0).toFixed(2)}
                {' '}/ {formatCycle(sub.billing_cycle).toLowerCase()}
                {discountPct && <span className="discount-pill"> · {discountPct}% off</span>}
              </>
            )}
          </span>
        </div>
        <div
          className="status-badge"
          style={{
            color: statusMeta.color,
            background: statusMeta.bg,
            border: `1px solid ${statusMeta.border}`,
          }}
        >
          {statusMeta.icon}
          <span>{statusMeta.label}</span>
        </div>
      </div>

      <div className="module-divider" />

      {/* Details grid */}
      <div className="sub-details">
        <div className="detail-row">
          <Server size={13} className="detail-icon" />
          <span className="detail-label">Server</span>
          <span className="detail-value">{sub.guild_name || sub.guild_id || '—'}</span>
        </div>
        <div className="detail-row">
          <Clock size={13} className="detail-icon" />
          <span className="detail-label">Billing</span>
          <span className="detail-value">{isStaffGrant ? 'Comp access' : formatCycle(sub.billing_cycle)}</span>
        </div>
        <div className="detail-row">
          <CheckCircle size={13} className="detail-icon" />
          <span className="detail-label">Started</span>
          <span className="detail-value">{formatDate(sub.created_at || sub.current_period_start)}</span>
        </div>
        {sub.current_period_end && sub.status === 'active' && (
          <div className="detail-row">
            <RefreshCw size={13} className="detail-icon" />
            <span className="detail-label">{isStaffGrant ? 'Expires' : 'Renews'}</span>
            <span className="detail-value">{formatDate(sub.current_period_end)}</span>
          </div>
        )}
        {sub.canceled_at && (
          <div className="detail-row">
            <Ban size={13} className="detail-icon" />
            <span className="detail-label">Cancelled</span>
            <span className="detail-value">{formatDate(sub.canceled_at)}</span>
          </div>
        )}
        {sub.paddle_subscription_id && (
          <div className="detail-row">
            <span className="detail-label" style={{ marginLeft: '21px' }}>Sub ID</span>
            <span className="detail-value mono">{sub.paddle_subscription_id.slice(0, 18)}…</span>
          </div>
        )}
      </div>

      {/* 48-hour eligibility notice */}
      {eligible && (
        <div className="eligible-notice">
          <AlertCircle size={13} />
          <span>Cancel or refund available — within 48 hours of purchase</span>
        </div>
      )}

      <div className="module-divider" />

      {/* Footer actions */}
      <div className="module-footer">
        {sub.paddle_transaction_id && (
          <button
            className="action-btn invoice-btn"
            onClick={() => onInvoice(sub)}
            disabled={invoiceLoading}
          >
            {invoiceLoading ? <div className="btn-spinner-sm" /> : <FileText size={14} />}
            <span>Invoice</span>
          </button>
        )}

        <button
          className={`action-btn history-toggle-btn ${isHistoryExpanded ? 'active' : ''}`}
          onClick={() => onToggleHistory(sub.paddle_subscription_id)}
          disabled={isLoading}
        >
          <Receipt size={14} />
          <span>{isHistoryExpanded ? 'Hide history' : 'View history'}</span>
          {isHistoryExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {sub.status === 'active' && (
          <button
            className="action-btn switch-btn"
            onClick={() => onSwitchServer(sub)}
          >
            <ArrowRightLeft size={14} />
            <span>Switch server</span>
          </button>
        )}

        {eligible && (
          <>
            <button
              className="action-btn cancel-btn"
              onClick={() => onCancel(sub)}
              disabled={cancelLoading}
            >
              {cancelLoading ? <div className="btn-spinner-sm" /> : <XCircle size={14} />}
              <span>Cancel</span>
            </button>
            <button
              className="action-btn refund-btn"
              onClick={() => onRefund(sub)}
              disabled={refundLoading}
            >
              {refundLoading ? <div className="btn-spinner-sm" /> : <RotateCcw size={14} />}
              <span>Refund</span>
            </button>
          </>
        )}
      </div>

      {/* Invoice history expanded section */}
      {isHistoryExpanded && (
        <>
          <div className="history-divider" />
          <div className="history-section">
            <div className="history-header">
              <span className="history-title">Invoice History</span>
              <span className="history-count">{transactions.length} transactions</span>
            </div>

            {isLoading ? (
              <div className="history-loading">
                <div className="btn-spinner-sm" />
                <span>Loading transaction history...</span>
              </div>
            ) : error ? (
              <div className="history-error">
                <AlertCircle size={14} />
                <span>{error}</span>
              </div>
            ) : transactions.length === 0 ? (
              <div className="history-empty">
                <span>No transaction history available yet.</span>
              </div>
            ) : (
              <div className="history-list">
                {transactions.map((tx, index) => {
                  const txStatusMeta = getTransactionStatusMeta(tx.status);
                  const isCompleted = tx.status === 'completed';
                  const amount = tx.amount_usd != null && tx.amount_usd > 0
                    ? `$${parseFloat(tx.amount_usd).toFixed(2)}`
                    : '—';

                  return (
                    <div key={tx.paddle_transaction_id || index} className="history-item">
                      <div className="history-item-main">
                        <div className="history-item-left">
                          <span className="history-item-date">{formatDateTime(tx.created_at)}</span>
                          <span className="history-item-type">{tx.transaction_type || '—'}</span>
                        </div>
                        <div className="history-item-right">
                          <span className="history-item-amount">{amount}</span>
                          <span
                            className="history-item-status"
                            style={{
                              color: txStatusMeta.color,
                              background: txStatusMeta.bg,
                              border: `1px solid ${txStatusMeta.border}`,
                            }}
                          >
                            {txStatusMeta.label}
                          </span>
                          {isCompleted && tx.paddle_transaction_id && (
                            <button
                              className="history-item-invoice-btn"
                              onClick={() => onTransactionInvoice(tx.paddle_transaction_id)}
                              title="Get invoice for this transaction"
                            >
                              <FileText size={13} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {eligible && (
        <p className="module-footnote">
          Cancel or refund eligibility expires {' '}
          {(() => {
            const d = new Date(new Date(sub.created_at || sub.current_period_start).getTime() + 48 * 3600 * 1000);
            return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
          })()}
        </p>
      )}
    </div>
  );
};

// ─── Main page ──────────────────────────────────────────────────────────────────
const MySubscriptionsPage = () => {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showLoginOverlay, setShowLoginOverlay] = useState(false);
  const [isPrivileged, setIsPrivileged] = useState(false);

  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const [filter, setFilter] = useState('all');

  // Per-card loading states (keyed by paddle_subscription_id)
  const [invoiceLoading, setInvoiceLoading] = useState(null);
  const [cancelLoading, setCancelLoading] = useState(null);
  const [refundLoading, setRefundLoading] = useState(null);

  // Invoice history state
  const [transactionHistory, setTransactionHistory] = useState({});
  const [historyInvoiceLoading, setHistoryInvoiceLoading] = useState(null);

  // Confirm modal state
  const [modal, setModal] = useState(null); // { type: 'cancel'|'refund', sub }

  // Server-switch state
  const [switchModalSub, setSwitchModalSub] = useState(null);
  const [userServers, setUserServers] = useState([]);
  const [userServersLoading, setUserServersLoading] = useState(false);
  const [switchLoading, setSwitchLoading] = useState(false);
  const [switchError, setSwitchError] = useState(null);

  const hasFetchedRef = useRef(false);

  // ─── Auth ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch(`${API_URL}/api/auth/status`, {
          credentials: 'include',
          headers: { 'Cache-Control': 'no-cache' },
        });
        if (!res.ok) throw new Error('Auth check failed');
        const data = await res.json();
        if (data.authenticated) {
          setUser(data.user);
          const uid = String(data.user.id || data.user.discord_id || '');
          setIsPrivileged(PRIVILEGED_USERS.includes(uid));
        } else {
          setShowLoginOverlay(true);
        }
      } catch {
        setShowLoginOverlay(true);
      } finally {
        setAuthChecked(true);
      }
    };
    checkAuth();
  }, []);

  useEffect(() => {
    if (!user || hasFetchedRef.current) return;
    hasFetchedRef.current = true;
    fetchSubscriptions();
  }, [user]);

  const fetchSubscriptions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/paddle/subscriptions/user/me`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' },
      });
      if (!res.ok) throw new Error(`Failed to fetch subscriptions: ${res.status}`);
      const data = await res.json();
      // Sort: active first, then by created_at desc
      const sorted = [...(data || [])].sort((a, b) => {
        const aActive = a.status === 'active' ? 0 : 1;
        const bActive = b.status === 'active' ? 0 : 1;
        if (aActive !== bActive) return aActive - bActive;
        return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      });
      setSubscriptions(sorted);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = () => {
    window.location.href = `${API_URL}/api/auth/discord?returnTo=${encodeURIComponent(window.location.href)}`;
  };

  // ─── Invoice ───────────────────────────────────────────────────────────────
  const handleInvoice = async (sub) => {
    setInvoiceLoading(sub.paddle_subscription_id);
    try {
      const res = await fetch(`${API_URL}/api/paddle/transactions/${sub.paddle_transaction_id}/invoice`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error('Could not retrieve invoice');
      const data = await res.json();
      const url = data?.data?.url || data?.url;
      if (!url) throw new Error('No invoice URL returned');
      window.open(url, '_blank');
    } catch (err) {
      setError(err.message);
      setTimeout(() => setError(null), 5000);
    } finally {
      setInvoiceLoading(null);
    }
  };

  // ─── Transaction Invoice ──────────────────────────────────────────────────
  const handleTransactionInvoice = async (transactionId) => {
    setHistoryInvoiceLoading(transactionId);
    try {
      const res = await fetch(`${API_URL}/api/paddle/transactions/${transactionId}/invoice`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error('Could not retrieve invoice');
      const data = await res.json();
      const url = data?.data?.url || data?.url;
      if (!url) throw new Error('No invoice URL returned');
      window.open(url, '_blank');
    } catch (err) {
      setTransactionHistory(prev => {
        const subId = Object.keys(prev).find(key =>
          prev[key]?.transactions?.some(tx => tx.paddle_transaction_id === transactionId)
        );
        if (!subId) return prev;
        return {
          ...prev,
          [subId]: { ...prev[subId], error: err.message || 'Failed to retrieve invoice' }
        };
      });
      setTimeout(() => {
        setTransactionHistory(prev => {
          const subId = Object.keys(prev).find(key =>
            prev[key]?.transactions?.some(tx => tx.paddle_transaction_id === transactionId)
          );
          if (!subId) return prev;
          return { ...prev, [subId]: { ...prev[subId], error: null } };
        });
      }, 5000);
    } finally {
      setHistoryInvoiceLoading(null);
    }
  };

  // ─── Toggle Invoice History ──────────────────────────────────────────────
  const toggleHistory = async (subscriptionId) => {
    const current = transactionHistory[subscriptionId];
    const isExpanded = current?.expanded || false;

    if (isExpanded) {
      setTransactionHistory(prev => ({
        ...prev,
        [subscriptionId]: { ...prev[subscriptionId], expanded: false },
      }));
      return;
    }

    if (!current?.transactions && !current?.loading) {
      setTransactionHistory(prev => ({
        ...prev,
        [subscriptionId]: { expanded: true, loading: true, transactions: [], error: null },
      }));

      try {
        const res = await fetch(`${API_URL}/api/paddle/transactions/subscription/${subscriptionId}`, {
          credentials: 'include',
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `Failed to fetch transaction history: ${res.status}`);
        }

        const data = await res.json();
        setTransactionHistory(prev => ({
          ...prev,
          [subscriptionId]: { expanded: true, loading: false, transactions: data || [], error: null },
        }));
      } catch (err) {
        setTransactionHistory(prev => ({
          ...prev,
          [subscriptionId]: {
            expanded: true, loading: false, transactions: [],
            error: err.message || 'Failed to load transaction history',
          },
        }));
      }
    } else {
      setTransactionHistory(prev => ({
        ...prev,
        [subscriptionId]: { ...prev[subscriptionId], expanded: true },
      }));
    }
  };

  // ─── Cancel ────────────────────────────────────────────────────────────────
  const handleCancelConfirm = async () => {
    const sub = modal.sub;
    setCancelLoading(sub.paddle_subscription_id);
    setModal(null);
    try {
      const res = await fetch(`${API_URL}/api/paddle/subscriptions/${sub.paddle_subscription_id}/cancel`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ effective_from: 'immediately' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to cancel subscription');
      setSubscriptions(prev =>
        prev.map(s =>
          s.paddle_subscription_id === sub.paddle_subscription_id
            ? { ...s, status: 'canceled', canceled_at: new Date().toISOString() }
            : s
        )
      );
      setSuccessMsg('Subscription cancelled successfully.');
      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err) {
      setError(err.message);
      setTimeout(() => setError(null), 5000);
    } finally {
      setCancelLoading(null);
    }
  };

  // ─── Refund ────────────────────────────────────────────────────────────────
  const handleRefundConfirm = async () => {
    const sub = modal.sub;
    setRefundLoading(sub.paddle_subscription_id);
    setModal(null);
    try {
      const res = await fetch(`${API_URL}/api/paddle/subscriptions/${sub.paddle_subscription_id}/refund`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Customer requested refund within 48 hours' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to process refund');
      setSubscriptions(prev =>
        prev.map(s =>
          s.paddle_subscription_id === sub.paddle_subscription_id
            ? { ...s, status: 'refunded' }
            : s
        )
      );
      setSuccessMsg('Refund processed. Funds typically arrive within 5–10 business days.');
      setTimeout(() => setSuccessMsg(null), 7000);
    } catch (err) {
      setError(err.message);
      setTimeout(() => setError(null), 5000);
    } finally {
      setRefundLoading(null);
    }
  };

  // ─── Server switching ──────────────────────────────────────────────────────
  const openSwitchModal = async (sub) => {
    setSwitchModalSub(sub);
    setSwitchError(null);
    if (userServers.length === 0) {
      setUserServersLoading(true);
      try {
        const res = await fetch(`${API_URL}/api/user/servers`, {
          credentials: 'include',
          headers: { 'Cache-Control': 'no-cache' },
        });
        if (!res.ok) throw new Error('Failed to fetch your servers');
        const data = await res.json();
        const processed = (data || []).map(s => ({
          ...s,
          iconUrl: s.icon
            ? `https://cdn.discordapp.com/icons/${s.id}/${s.icon}.png?size=64`
            : 'https://cdn.discordapp.com/embed/avatars/0.png',
        }));
        setUserServers(processed);
      } catch (err) {
        setSwitchError(err.message);
      } finally {
        setUserServersLoading(false);
      }
    }
  };

  const handleSwitchConfirm = async (newGuildId) => {
    if (!switchModalSub || !newGuildId) return;
    setSwitchLoading(true);
    setSwitchError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/paddle/subscriptions/${switchModalSub.paddle_subscription_id}/switch-guild`,
        {
          method: 'PATCH',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_guild_id: newGuildId }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to switch server');

      const newServer = userServers.find(s => s.id === newGuildId);
      setSubscriptions(prev =>
        prev.map(s =>
          s.paddle_subscription_id === switchModalSub.paddle_subscription_id
            ? { ...s, guild_id: newGuildId, guild_name: newServer?.name || s.guild_name }
            : s
        )
      );
      setSuccessMsg(`Moved subscription to ${newServer?.name || 'the new server'}.`);
      setTimeout(() => setSuccessMsg(null), 5000);
      setSwitchModalSub(null);
    } catch (err) {
      setSwitchError(err.message);
    } finally {
      setSwitchLoading(false);
    }
  };

  // ─── Filtered views ────────────────────────────────────────────────────────
  const HISTORY_STATUSES = ['canceled', 'paused', 'past_due', 'refunded'];

  const filtered = subscriptions.filter(s => {
    if (filter === 'all') return true;
    return s.status === filter;
  });

  const activeSubs = filtered.filter(s => s.status === 'active' || s.status === 'trialing');
  const historySubs = filtered.filter(s => HISTORY_STATUSES.includes(s.status));

  const totalCount = subscriptions.length;
  const activeCount = subscriptions.filter(s => s.status === 'active').length;

  // ─── Login overlay ─────────────────────────────────────────────────────────
  if (authChecked && showLoginOverlay) {
    return (
      <>
        <NavBar />
        <div className="cart-page">
          <div className="login-overlay">
            <div className="login-modal">
              <div className="login-icon">🔒</div>
              <h2>Sign in to view your subscriptions</h2>
              <p>Log in with Discord to manage your active subscriptions and billing history.</p>
              <button className="login-button" onClick={handleLogin}>Log In with Discord</button>
            </div>
          </div>
        </div>
        <Footer />
        <style>{allStyles}</style>
      </>
    );
  }

  if (!authChecked) {
    return (
      <>
        <NavBar />
        <div className="cart-page">
          <div className="state-container"><div className="spinner" /></div>
        </div>
        <Footer />
        <style>{allStyles}</style>
      </>
    );
  }

  return (
    <>
      <NavBar />
      <div className="cart-page">
        <div className="bg-glow bg-glow-1" />
        <div className="bg-glow bg-glow-2" />

        <div className="cart-container">
          {/* Page header */}
          <div className="modules-divider">
            <div className="divider-line" />
            <span className="modules-label">MY SUBSCRIPTIONS</span>
            <div className="divider-line" />
          </div>

          {/* Stats bar */}
          {!loading && subscriptions.length > 0 && (
            <div className="stats-bar">
              <div className="stat-chip">
                <span className="stat-num">{totalCount}</span>
                <span className="stat-label">Total</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-chip">
                <span className="stat-num" style={{ color: '#00e07a' }}>{activeCount}</span>
                <span className="stat-label">Active</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-chip">
                <span className="stat-num" style={{ color: '#aa00ff' }}>
                  ${subscriptions
                    .filter(s => s.status === 'active')
                    .reduce((acc, s) => acc + parseFloat(s.final_price_usd || 0), 0)
                    .toFixed(2)}
                </span>
                <span className="stat-label">/ mo active spend</span>
              </div>
            </div>
          )}

          {/* Filter tabs */}
          {!loading && subscriptions.length > 0 && (
            <div className="filter-tabs">
              {FILTERS.map(f => {
                const count = f === 'all'
                  ? subscriptions.length
                  : subscriptions.filter(s => s.status === f).length;
                return (
                  <button
                    key={f}
                    className={`filter-tab ${filter === f ? 'active' : ''}`}
                    onClick={() => setFilter(f)}
                  >
                    <span className="tab-label">
                      {f === 'all' ? 'All' : f === 'past_due' ? 'Past Due' : f.charAt(0).toUpperCase() + f.slice(1)}
                    </span>
                    {count > 0 && <span className="tab-count">{count}</span>}
                  </button>
                );
              })}
            </div>
          )}

          {/* Staff tools */}
          {isPrivileged && (
            <>
              <StaffGrantPanel apiUrl={API_URL} onGranted={fetchSubscriptions} />
              <StaffGrantsList apiUrl={API_URL} onGrantRevoked={fetchSubscriptions} />
            </>
          )}

          {/* Messages */}
          {error && <div className="global-error">{error}</div>}
          {successMsg && <div className="global-success">{successMsg}</div>}

          {/* Content */}
          {loading ? (
            <div className="state-container">
              <div className="spinner" />
              <p className="state-text">Loading your subscriptions...</p>
            </div>
          ) : subscriptions.length === 0 ? (
            <div className="empty-cart">
              <Settings size={48} color="#aa00ff" />
              <h2>No subscriptions yet</h2>
              <p>Browse available modules and power up your servers.</p>
              <a href="/Premium/index.html" className="browse-link">Browse Modules</a>
            </div>
          ) : (
            <>
              {/* Active section */}
              {activeSubs.length > 0 && (
                <div className="sub-section">
                  <div className="section-header">
                    <CheckCircle size={15} color="#00e07a" />
                    <span className="section-title">Active</span>
                    <span className="section-count">{activeSubs.length}</span>
                  </div>
                  <div className="modules-grid">
                    {activeSubs.map(sub => (
                      <SubscriptionCard
                        key={sub.paddle_subscription_id || sub.id}
                        sub={sub}
                        onCancel={(s) => setModal({ type: 'cancel', sub: s })}
                        onRefund={(s) => setModal({ type: 'refund', sub: s })}
                        onInvoice={handleInvoice}
                        onTransactionInvoice={handleTransactionInvoice}
                        onSwitchServer={openSwitchModal}
                        invoiceLoading={invoiceLoading === sub.paddle_subscription_id}
                        cancelLoading={cancelLoading === sub.paddle_subscription_id}
                        refundLoading={refundLoading === sub.paddle_subscription_id}
                        transactionHistory={transactionHistory}
                        onToggleHistory={toggleHistory}
                        isHistoryExpanded={transactionHistory[sub.paddle_subscription_id]?.expanded || false}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* History section */}
              {historySubs.length > 0 && (
                <div className="sub-section">
                  <div className="section-header">
                    <Clock size={15} color="#555870" />
                    <span className="section-title" style={{ color: '#555870' }}>History</span>
                    <span className="section-count" style={{ background: 'rgba(85,88,112,0.15)', color: '#555870' }}>
                      {historySubs.length}
                    </span>
                  </div>
                  <div className="modules-grid">
                    {historySubs.map(sub => (
                      <SubscriptionCard
                        key={sub.paddle_subscription_id || sub.id}
                        sub={sub}
                        onCancel={(s) => setModal({ type: 'cancel', sub: s })}
                        onRefund={(s) => setModal({ type: 'refund', sub: s })}
                        onInvoice={handleInvoice}
                        onTransactionInvoice={handleTransactionInvoice}
                        onSwitchServer={openSwitchModal}
                        invoiceLoading={invoiceLoading === sub.paddle_subscription_id}
                        cancelLoading={cancelLoading === sub.paddle_subscription_id}
                        refundLoading={refundLoading === sub.paddle_subscription_id}
                        transactionHistory={transactionHistory}
                        onToggleHistory={toggleHistory}
                        isHistoryExpanded={transactionHistory[sub.paddle_subscription_id]?.expanded || false}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Empty filtered state */}
              {activeSubs.length === 0 && historySubs.length === 0 && (
                <div className="empty-filter">
                  <p>No subscriptions match this filter.</p>
                  <button className="clear-filter-btn" onClick={() => setFilter('all')}>
                    Show all
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Cancel/Refund confirm modal */}
      {modal && (
        <ConfirmModal
          title={modal.type === 'cancel' ? 'Cancel subscription?' : 'Request a refund?'}
          message={
            modal.type === 'cancel'
              ? `This will immediately cancel your ${getModuleInfo(modal.sub.module_key).name} subscription. Access will be revoked right away.`
              : `This will refund your $${parseFloat(modal.sub.final_price_usd || 0).toFixed(2)} payment and cancel the subscription. Funds typically arrive in 5–10 business days.`
          }
          confirmLabel={modal.type === 'cancel' ? 'Yes, cancel it' : 'Yes, refund me'}
          confirmClass={modal.type === 'cancel' ? 'danger' : 'warning'}
          onConfirm={modal.type === 'cancel' ? handleCancelConfirm : handleRefundConfirm}
          onCancel={() => setModal(null)}
          loading={
            modal.type === 'cancel'
              ? cancelLoading === modal.sub.paddle_subscription_id
              : refundLoading === modal.sub.paddle_subscription_id
          }
        />
      )}

      {/* Switch server modal */}
      {switchModalSub && (
        <SwitchServerModal
          sub={switchModalSub}
          servers={userServers}
          serversLoading={userServersLoading}
          onConfirm={handleSwitchConfirm}
          onCancel={() => { setSwitchModalSub(null); setSwitchError(null); }}
          loading={switchLoading}
          error={switchError}
        />
      )}

      <Footer />
      <style>{allStyles}</style>
    </>
  );
};

// ─── Styles ────────────────────────────────────────────────────────────────────
const allStyles = `
  @font-face {
    font-family: 'Horndon';
    src: url('/HorndonD.ttf') format('truetype');
    font-display: swap;
  }

  * { margin: 0; padding: 0; box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }

  html, body, #app { min-height: 100vh; background-color: #0a0a0a; color: #ffffff; }

  .cart-page {
    background-color: #0a0a0a;
    min-height: calc(100vh - 80px);
    padding: 60px 0 80px;
    display: flex;
    justify-content: center;
    position: relative;
    overflow: hidden;
  }

  .bg-glow { position: absolute; border-radius: 50%; filter: blur(120px); pointer-events: none; opacity: 0.35; }
  .bg-glow-1 { width: 500px; height: 500px; background: #aa00ff; top: -200px; left: -150px; }
  .bg-glow-2 { width: 450px; height: 450px; background: #5500aa; bottom: -150px; right: -150px; }

  .cart-container {
    max-width: 640px;
    margin: 0 auto;
    padding: 0 40px;
    width: 100%;
    position: relative;
    z-index: 1;
  }

  /* ── Divider header ── */
  .modules-divider {
    display: flex; align-items: center; gap: 24px; margin-bottom: 36px;
    width: 100vw; position: relative; left: 50%; right: 50%;
    margin-left: -50vw; margin-right: -50vw;
  }
  .divider-line {
    flex: 1; height: 1px;
    background: linear-gradient(to right, transparent 0%, rgba(255,255,255,0.06) 8%, rgba(255,255,255,0.3) 25%, rgba(255,255,255,0.7) 50%, rgba(255,255,255,0.3) 75%, transparent 100%);
  }
  .modules-divider .divider-line:last-child {
    background: linear-gradient(to left, transparent 0%, rgba(255,255,255,0.06) 8%, rgba(255,255,255,0.3) 25%, rgba(255,255,255,0.7) 50%, rgba(255,255,255,0.3) 75%, transparent 100%);
  }
  .modules-label {
    font-size: 28px; font-weight: 800; letter-spacing: 7px; color: #ffffff;
    text-shadow: 0 0 12px rgba(255,255,255,0.95), 0 0 28px rgba(255,255,255,0.6), 0 0 55px rgba(255,255,255,0.25);
    white-space: nowrap; flex-shrink: 0;
  }

  /* ── Stats bar ── */
  .stats-bar {
    display: flex; align-items: center; gap: 0;
    background: #14151c; border: 1px solid #2c2f3a; border-radius: 12px;
    padding: 16px 24px; margin-bottom: 20px;
    max-width: 520px; margin-left: auto; margin-right: auto;
  }
  .stat-chip { display: flex; flex-direction: column; align-items: center; flex: 1; gap: 2px; }
  .stat-num { font-size: 20px; font-weight: 800; color: #ffffff; }
  .stat-label { font-size: 11px; color: #555870; font-weight: 500; letter-spacing: 0.5px; }
  .stat-divider { width: 1px; height: 32px; background: #2c2f3a; margin: 0 8px; }

  /* ── Filter tabs ── */
  .filter-tabs {
    display: flex; gap: 8px; margin-bottom: 20px;
    max-width: 520px; margin-left: auto; margin-right: auto;
    flex-wrap: wrap;
  }
  .filter-tab {
    display: flex; align-items: center; gap: 6px;
    padding: 7px 14px;
    background: #14151c; border: 1px solid #2c2f3a; border-radius: 20px;
    color: #888b99; font-size: 13px; font-weight: 500; cursor: pointer;
    transition: all 0.2s ease;
  }
  .filter-tab:hover { border-color: rgba(170,0,255,0.35); color: #d0d0d0; }
  .filter-tab.active {
    background: rgba(170,0,255,0.1); border-color: rgba(170,0,255,0.5);
    color: #ffffff;
  }
  .tab-label { font-size: 13px; }
  .tab-count {
    font-size: 11px; font-weight: 700; padding: 1px 6px;
    background: rgba(170,0,255,0.15); color: #aa00ff; border-radius: 10px;
  }
  .filter-tab.active .tab-count { background: rgba(170,0,255,0.25); }

  /* ── Staff panel ── */
  .staff-panel-wrap {
    max-width: 520px; margin: 0 auto 24px; display: flex; flex-direction: column;
  }
  .staff-toggle-btn {
    display: flex; align-items: center; gap: 8px;
    align-self: flex-start;
    padding: 8px 16px;
    background: rgba(170,0,255,0.06); border: 1px solid rgba(170,0,255,0.3);
    border-radius: 20px; color: #aa00ff; font-size: 12.5px; font-weight: 600;
    cursor: pointer; transition: all 0.2s ease;
  }
  .staff-toggle-btn:hover { background: rgba(170,0,255,0.12); border-color: rgba(170,0,255,0.5); }

  .staff-panel {
    margin-top: 12px;
    background: #14151c; border: 1px solid rgba(170,0,255,0.3); border-radius: 16px;
    padding: 22px;
    animation: slideDown 0.2s ease;
  }
  .staff-panel-header {
    display: flex; align-items: center; gap: 8px;
    font-size: 14px; font-weight: 700; color: #ffffff; margin-bottom: 6px;
  }
  .staff-panel-subtext {
    font-size: 12.5px; color: #888b99; line-height: 1.55; margin-bottom: 18px;
  }

  .staff-lookup-row { display: flex; gap: 10px; }
  .staff-input-wrap { position: relative; flex: 1; }
  .staff-input-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: #555870; }
  .staff-text-input {
    width: 100%; padding: 11px 14px 11px 36px;
    background: #0a0a0a; border: 1px solid #2c2f3a; border-radius: 10px;
    color: #ffffff; font-size: 13px; font-family: 'SF Mono', 'Fira Code', monospace;
    transition: border-color 0.2s ease;
  }
  .staff-text-input.full-width { padding-left: 14px; font-family: inherit; }
  .staff-text-input:focus { outline: none; border-color: #aa00ff; }
  .staff-text-input::placeholder { color: #555870; }

  .staff-lookup-btn {
    padding: 11px 20px; background: rgba(170,0,255,0.12); border: 1px solid rgba(170,0,255,0.4);
    border-radius: 10px; color: #aa00ff; font-size: 13px; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease; white-space: nowrap;
    display: flex; align-items: center; justify-content: center; min-width: 84px;
  }
  .staff-lookup-btn:hover:not(:disabled) { background: rgba(170,0,255,0.2); border-color: #aa00ff; }
  .staff-lookup-btn:disabled { opacity: 0.6; cursor: not-allowed; }

  .staff-success-notice {
    display: flex; align-items: center; gap: 7px; margin-top: 14px; padding: 10px 12px;
    background: rgba(0,224,122,0.07); border: 1px solid rgba(0,224,122,0.25); border-radius: 8px;
    font-size: 12.5px; color: #00e07a;
  }

  .staff-result-card {
    margin-top: 16px; padding: 16px; background: #0a0a0a;
    border: 1px solid #2c2f3a; border-radius: 12px;
  }
  .staff-result-server { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .staff-result-icon { width: 44px; height: 44px; border-radius: 50%; border: 2px solid rgba(170,0,255,0.4); object-fit: cover; }
  .staff-result-info { flex: 1; min-width: 0; }
  .staff-result-name { font-size: 15px; font-weight: 700; color: #ffffff; }
  .staff-result-meta { font-size: 12px; color: #888b99; margin-top: 2px; }

  .staff-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .staff-field { display: flex; flex-direction: column; gap: 6px; }
  .staff-field-label { font-size: 11.5px; color: #888b99; font-weight: 600; letter-spacing: 0.3px; }
  .staff-select, .staff-number-input {
    padding: 10px 12px; background: #0a0a0a; border: 1px solid #2c2f3a; border-radius: 8px;
    color: #ffffff; font-size: 13px;
  }
  .staff-select:focus, .staff-number-input:focus { outline: none; border-color: #aa00ff; }

  .staff-result-actions { display: flex; gap: 10px; margin-top: 18px; }
  .staff-discard-btn {
    flex: 1; padding: 10px; background: transparent; border: 1px solid #2c2f3a;
    color: #888b99; font-size: 13px; font-weight: 600; border-radius: 8px; cursor: pointer;
    transition: all 0.2s ease;
  }
  .staff-discard-btn:hover { border-color: #444; color: #d0d0d0; }
  .staff-grant-btn {
    flex: 2; padding: 10px; border: none; border-radius: 8px;
    background: linear-gradient(135deg, #aa00ff, #7700cc); color: #ffffff;
    font-size: 13px; font-weight: 700; cursor: pointer;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    transition: all 0.2s ease;
  }
  .staff-grant-btn:hover:not(:disabled) { box-shadow: 0 4px 16px rgba(170,0,255,0.4); }
  .staff-grant-btn:disabled { opacity: 0.6; cursor: not-allowed; }

  .staff-grant-pill {
    display: inline-flex; align-items: center; padding: 2px 9px;
    background: rgba(170,0,255,0.12); border: 1px solid rgba(170,0,255,0.3);
    color: #aa00ff; border-radius: 10px; font-size: 11px; font-weight: 700;
    letter-spacing: 0.3px;
  }

  /* ── Staff grants list ── */
  .staff-refresh-btn {
    display: flex; align-items: center; justify-content: center;
    margin-left: auto; padding: 4px 6px;
    background: transparent; border: 1px solid rgba(170,0,255,0.3);
    border-radius: 6px; color: #aa00ff; cursor: pointer;
    transition: all 0.2s ease;
  }
  .staff-refresh-btn:hover:not(:disabled) { background: rgba(170,0,255,0.1); }
  .staff-refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .spinning { animation: spin 0.8s linear infinite; }

  .grants-list { display: flex; flex-direction: column; gap: 12px; max-height: 400px; overflow-y: auto; padding-right: 4px; }
  .grants-list::-webkit-scrollbar { width: 4px; }
  .grants-list::-webkit-scrollbar-thumb { background: rgba(170,0,255,0.3); border-radius: 2px; }

  .grant-item {
    padding: 14px 16px;
    background: #0a0a0a;
    border: 1px solid #2c2f3a;
    border-radius: 10px;
    transition: border-color 0.2s ease;
  }
  .grant-item:hover { border-color: rgba(170,0,255,0.3); }

  .grant-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
  }
  .grant-server { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .grant-guild-name { font-size: 14px; font-weight: 600; color: #ffffff; }
  .grant-module {
    font-size: 12px; color: #aa00ff; font-weight: 500;
    padding: 2px 8px; background: rgba(170,0,255,0.1); border-radius: 4px;
  }
  .grant-status { font-size: 12px; font-weight: 600; text-transform: capitalize; }

  .grant-details { display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
  .grant-detail {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: #888b99;
  }
  .grant-detail.reason { flex-wrap: wrap; }
  .reason-label { font-weight: 500; color: #555870; }
  .reason-text { color: #d0d0d0; font-style: italic; }

  .grant-actions { margin-top: 10px; display: flex; gap: 8px; }
  .grant-revoke-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 14px;
    background: rgba(255,107,107,0.1);
    border: 1px solid rgba(255,107,107,0.3);
    border-radius: 6px;
    color: #ff8888; font-size: 12px; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease;
  }
  .grant-revoke-btn:hover:not(:disabled) { background: rgba(255,107,107,0.2); border-color: #ff6b6b; }
  .grant-revoke-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .grant-revoked-badge {
    display: flex; align-items: center; gap: 6px;
    margin-top: 10px; padding: 4px 10px;
    background: rgba(255,107,107,0.08);
    border: 1px solid rgba(255,107,107,0.2);
    border-radius: 4px;
    font-size: 12px; color: #ff888b;
  }

  /* ── Section headers ── */
  .sub-section { margin-bottom: 40px; }
  .section-header {
    display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
    max-width: 520px; margin-left: auto; margin-right: auto;
  }
  .section-title { font-size: 13px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #e0e0e0; }
  .section-count {
    font-size: 11px; font-weight: 700; padding: 2px 7px;
    background: rgba(0,224,122,0.12); color: #00e07a; border-radius: 10px;
  }

  /* ── Modules grid ── */
  .modules-grid { display: flex; flex-direction: column; gap: 20px; align-items: center; }

  /* ── Card ── */
  .module-card {
    position: relative; background-color: #14151c; border: 1px solid #2c2f3a;
    border-radius: 16px; padding: 28px 24px;
    transition: border-color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
    width: 100%; max-width: 520px; display: flex; flex-direction: column; overflow: hidden;
  }
  .module-card:hover {
    border-color: rgba(170, 0, 255, 0.35);
    box-shadow: 0 8px 40px rgba(170, 0, 255, 0.1);
    transform: translateY(-2px);
  }
  .card-sheen {
    position: absolute; top: 0; left: -100%; width: 60%; height: 100%;
    background: linear-gradient(100deg, transparent 0%, rgba(170,0,255,0.04) 50%, transparent 100%);
    transition: left 0.8s ease; pointer-events: none;
  }
  .module-card:hover .card-sheen { left: 120%; }

  /* ── Card header ── */
  .module-header { display: flex; align-items: center; gap: 14px; position: relative; z-index: 1; }
  .module-icon {
    display: flex; align-items: center; justify-content: center;
    width: 46px; height: 46px;
    background: rgba(170,0,255,0.1); border: 1px solid rgba(170,0,255,0.25); border-radius: 10px;
    flex-shrink: 0;
    transition: transform 0.4s cubic-bezier(0.34,1.56,0.64,1), background 0.3s ease;
  }
  .module-card:hover .module-icon { transform: rotate(90deg); background: rgba(170,0,255,0.18); }
  .module-title-group { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
  .module-name { font-size: 19px; font-weight: 700; color: #ffffff; }
  .module-price { font-size: 13px; color: #aa00ff; font-weight: 500; }
  .discount-pill { font-size: 12px; color: #00e07a; font-weight: 600; }

  /* ── Status badge ── */
  .status-badge {
    display: flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px;
    font-size: 12px; font-weight: 600; flex-shrink: 0;
    white-space: nowrap;
  }

  /* ── Divider ── */
  .module-divider { height: 1px; background-color: #2c2f3a; margin: 20px 0; position: relative; z-index: 1; }

  /* ── Detail rows ── */
  .sub-details { display: flex; flex-direction: column; gap: 10px; position: relative; z-index: 1; }
  .detail-row { display: flex; align-items: center; gap: 8px; }
  .detail-icon { color: #555870; flex-shrink: 0; }
  .detail-label { font-size: 12px; color: #555870; font-weight: 500; min-width: 54px; }
  .detail-value { font-size: 13px; color: #d0d0d0; font-weight: 500; }
  .detail-value.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; color: #888b99; }

  /* ── Eligible notice ── */
  .eligible-notice {
    display: flex; align-items: center; gap: 7px;
    margin-top: 14px; padding: 9px 12px;
    background: rgba(240,165,0,0.07); border: 1px solid rgba(240,165,0,0.2); border-radius: 8px;
    font-size: 12px; color: #f0a500; position: relative; z-index: 1;
  }

  /* ── Footer actions ── */
  .module-footer {
    display: flex; gap: 8px; position: relative; z-index: 1; flex-wrap: wrap;
  }
  .action-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 10px 16px; border-radius: 8px;
    font-size: 13px; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease; white-space: nowrap;
    background: transparent; border: 1px solid #2c2f3a; color: #888b99;
  }
  .action-btn:hover:not(:disabled) { border-color: rgba(170,0,255,0.4); color: #d0d0d0; }
  .action-btn:disabled { cursor: not-allowed; opacity: 0.5; }
  .action-btn.active { border-color: rgba(170,0,255,0.5); color: #aa00ff; background: rgba(170,0,255,0.05); }

  .invoice-btn {
    border-color: rgba(170,0,255,0.35); color: #aa00ff;
  }
  .invoice-btn:hover:not(:disabled) { background: rgba(170,0,255,0.1); border-color: rgba(170,0,255,0.6); }

  .switch-btn {
    border-color: rgba(91,156,246,0.35); color: #5b9cf6;
  }
  .switch-btn:hover:not(:disabled) { background: rgba(91,156,246,0.1); border-color: rgba(91,156,246,0.6); }

  .cancel-btn {
    border-color: rgba(255,107,107,0.35); color: #ff8888;
  }
  .cancel-btn:hover:not(:disabled) { background: rgba(255,107,107,0.1); border-color: #ff6b6b; }

  .refund-btn {
    border-color: rgba(240,165,0,0.35); color: #f0a500;
  }
  .refund-btn:hover:not(:disabled) { background: rgba(240,165,0,0.08); border-color: rgba(240,165,0,0.6); }

  .history-toggle-btn {
    border-color: rgba(170,0,255,0.25);
  }
  .history-toggle-btn:hover:not(:disabled) { border-color: rgba(170,0,255,0.5); color: #d0d0d0; }
  .history-toggle-btn.active { border-color: rgba(170,0,255,0.5); color: #aa00ff; background: rgba(170,0,255,0.05); }

  /* ── History section ── */
  .history-divider {
    height: 1px;
    background-color: #2c2f3a;
    margin: 16px 0 16px 0;
    position: relative;
    z-index: 1;
  }

  .history-section {
    position: relative;
    z-index: 1;
    animation: slideDown 0.25s ease;
  }

  @keyframes slideDown {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .history-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
  }

  .history-title {
    font-size: 13px;
    font-weight: 600;
    color: #d0d0d0;
    letter-spacing: 0.5px;
  }

  .history-count {
    font-size: 12px;
    color: #555870;
    font-weight: 500;
  }

  .history-loading {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 0;
    color: #888b99;
    font-size: 13px;
  }

  .history-error {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    background: rgba(255,107,107,0.08);
    border: 1px solid rgba(255,107,107,0.2);
    border-radius: 8px;
    color: #ff8888;
    font-size: 13px;
  }

  .history-empty {
    padding: 12px 0;
    color: #555870;
    font-size: 13px;
  }

  .history-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 400px;
    overflow-y: auto;
    padding-right: 4px;
  }

  .history-list::-webkit-scrollbar { width: 4px; }
  .history-list::-webkit-scrollbar-track { background: rgba(44,47,58,0.3); border-radius: 2px; }
  .history-list::-webkit-scrollbar-thumb { background: rgba(170,0,255,0.3); border-radius: 2px; }

  .history-item {
    padding: 10px 12px;
    background: rgba(20,21,28,0.5);
    border: 1px solid rgba(44,47,58,0.5);
    border-radius: 8px;
    transition: border-color 0.2s ease;
  }
  .history-item:hover { border-color: rgba(170,0,255,0.2); }

  .history-item-main {
    display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  .history-item-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .history-item-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .history-item-date { font-size: 12px; color: #888b99; font-weight: 500; white-space: nowrap; }
  .history-item-type {
    font-size: 12px; color: #d0d0d0; font-weight: 500; text-transform: capitalize;
    padding: 2px 8px; background: rgba(44,47,58,0.5); border-radius: 4px; white-space: nowrap;
  }
  .history-item-amount { font-size: 14px; color: #ffffff; font-weight: 600; white-space: nowrap; }
  .history-item-status {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 11px; font-weight: 600; white-space: nowrap;
  }
  .history-item-invoice-btn {
    display: flex; align-items: center; justify-content: center; padding: 4px 6px;
    background: transparent; border: 1px solid rgba(170,0,255,0.3); border-radius: 6px;
    color: #aa00ff; cursor: pointer; transition: all 0.2s ease;
  }
  .history-item-invoice-btn:hover { background: rgba(170,0,255,0.1); border-color: rgba(170,0,255,0.6); transform: scale(1.05); }

  /* ── Footnote ── */
  .module-footnote { margin-top: 12px; font-size: 11px; color: #555870; font-style: italic; position: relative; z-index: 1; }

  /* ── Spinners ── */
  .btn-spinner-sm {
    width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.2); border-top-color: currentColor;
    border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0;
  }
  .btn-spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.3); border-top-color: #ffffff;
    border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Messages ── */
  .global-error {
    background: rgba(255,107,107,0.1); border: 1px solid #ff6b6b; color: #ff8888;
    padding: 14px 20px; border-radius: 12px; font-size: 14px; margin-bottom: 24px; text-align: center;
    max-width: 520px; margin-left: auto; margin-right: auto;
  }
  .global-success {
    background: rgba(0,224,122,0.08); border: 1px solid rgba(0,224,122,0.3); color: #00e07a;
    padding: 14px 20px; border-radius: 12px; font-size: 14px; margin-bottom: 24px; text-align: center;
    max-width: 520px; margin-left: auto; margin-right: auto;
  }

  /* ── Empty states ── */
  .empty-cart {
    display: flex; flex-direction: column; align-items: center;
    gap: 16px; text-align: center; padding: 80px 20px;
    background-color: #14151c; border: 1px solid #2c2f3a; border-radius: 16px;
    max-width: 520px; margin: 0 auto;
  }
  .empty-cart h2 { font-size: 22px; font-weight: 700; }
  .empty-cart p { font-size: 14px; color: #888b99; max-width: 300px; line-height: 1.6; }
  .browse-link {
    margin-top: 8px; padding: 12px 28px;
    background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
    color: #ffffff; font-size: 14px; font-weight: 600; border-radius: 8px; text-decoration: none;
    transition: transform 0.25s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.25s ease;
  }
  .browse-link:hover { transform: translateY(-2px); box-shadow: 0 6px 24px rgba(170,0,255,0.45); }

  .empty-filter {
    display: flex; flex-direction: column; align-items: center; gap: 12px;
    padding: 48px 20px; text-align: center; color: #555870; font-size: 14px;
  }
  .clear-filter-btn {
    padding: 8px 20px; background: transparent; border: 1px solid #2c2f3a;
    border-radius: 8px; color: #888b99; font-size: 13px; cursor: pointer;
    transition: all 0.2s ease;
  }
  .clear-filter-btn:hover { border-color: rgba(170,0,255,0.4); color: #d0d0d0; }

  /* ── Confirm modal ── */
  .modal-overlay {
    position: fixed; inset: 0; z-index: 100;
    background: rgba(0,0,0,0.75); backdrop-filter: blur(8px);
    display: flex; align-items: center; justify-content: center; padding: 20px;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

  .modal-box {
    background: #14151c; border: 1px solid #2c2f3a; border-radius: 20px;
    padding: 36px 32px; max-width: 440px; width: 100%;
    animation: slideUp 0.2s ease;
    box-shadow: 0 24px 60px rgba(0,0,0,0.6);
  }
  @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

  .modal-icon-badge {
    width: 44px; height: 44px; border-radius: 12px;
    background: rgba(170,0,255,0.1); border: 1px solid rgba(170,0,255,0.3);
    display: flex; align-items: center; justify-content: center; margin-bottom: 16px;
  }

  .modal-title { font-size: 20px; font-weight: 700; color: #ffffff; margin-bottom: 12px; }
  .modal-message { font-size: 14px; color: #888b99; line-height: 1.65; margin-bottom: 20px; }
  .modal-actions { display: flex; gap: 10px; margin-top: 8px; }

  .modal-cancel-btn {
    flex: 1; padding: 12px; background: transparent; border: 1px solid #2c2f3a;
    color: #888b99; font-size: 14px; font-weight: 600; border-radius: 8px; cursor: pointer;
    transition: all 0.2s ease;
  }
  .modal-cancel-btn:hover:not(:disabled) { border-color: #444; color: #d0d0d0; }
  .modal-cancel-btn:disabled { cursor: not-allowed; opacity: 0.5; }

  .modal-confirm-btn {
    flex: 1; padding: 12px; border: none; color: #ffffff;
    font-size: 14px; font-weight: 700; border-radius: 8px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    transition: all 0.2s ease;
  }
  .modal-confirm-btn.danger { background: linear-gradient(135deg, #ff4444, #cc2222); }
  .modal-confirm-btn.danger:hover:not(:disabled) { box-shadow: 0 4px 16px rgba(255,68,68,0.4); }
  .modal-confirm-btn.warning { background: linear-gradient(135deg, #f0a500, #c07800); }
  .modal-confirm-btn.warning:hover:not(:disabled) { box-shadow: 0 4px 16px rgba(240,165,0,0.4); }
  .modal-confirm-btn.primary { background: linear-gradient(135deg, #aa00ff, #7700cc); }
  .modal-confirm-btn.primary:hover:not(:disabled) { box-shadow: 0 4px 16px rgba(170,0,255,0.4); }
  .modal-confirm-btn:disabled { cursor: not-allowed; opacity: 0.6; }

  /* ── Switch server modal extras ── */
  .switch-servers-loading {
    display: flex; align-items: center; gap: 10px; padding: 16px 0;
    color: #888b99; font-size: 13px;
  }
  .switch-empty-notice, .switch-error-notice {
    display: flex; align-items: center; gap: 8px; padding: 10px 12px;
    border-radius: 8px; font-size: 12.5px; margin-bottom: 4px;
  }
  .switch-empty-notice { background: rgba(240,165,0,0.07); border: 1px solid rgba(240,165,0,0.2); color: #f0a500; }
  .switch-error-notice { background: rgba(255,107,107,0.08); border: 1px solid rgba(255,107,107,0.2); color: #ff8888; }

  .switch-server-list {
    display: flex; flex-direction: column; gap: 8px; max-height: 260px;
    overflow-y: auto; margin-bottom: 16px; padding-right: 2px;
  }
  .switch-server-list::-webkit-scrollbar { width: 4px; }
  .switch-server-list::-webkit-scrollbar-thumb { background: rgba(170,0,255,0.3); border-radius: 2px; }

  .switch-server-option {
    display: flex; align-items: center; gap: 12px; padding: 10px 12px;
    background: #0a0a0a; border: 1px solid #2c2f3a; border-radius: 10px;
    cursor: pointer; transition: all 0.2s ease; text-align: left;
  }
  .switch-server-option:hover { border-color: rgba(170,0,255,0.4); }
  .switch-server-option.selected { border-color: #aa00ff; background: rgba(170,0,255,0.06); }
  .switch-server-icon { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }
  .switch-server-name { flex: 1; font-size: 13.5px; color: #d0d0d0; font-weight: 500; }

  /* ── Loader & auth ── */
  .state-container {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: calc(100vh - 200px); width: 100%; gap: 20px; padding: 20px;
  }
  .spinner {
    width: 48px; height: 48px; border: 4px solid #232323;
    border-top-color: #aa00ff; border-right-color: #aa00ff;
    border-radius: 50%; animation: spin 1s linear infinite;
  }
  .state-text { color: #b0b0b0; font-size: 14px; }

  .login-overlay {
    position: relative; min-height: calc(100vh - 200px); width: 100%;
    display: flex; align-items: center; justify-content: center; padding: 40px 20px; z-index: 10;
  }
  .login-modal {
    background: rgba(10,10,10,0.95); backdrop-filter: blur(20px);
    border: 2px solid #aa00ff; border-radius: 40px; padding: 60px 40px;
    max-width: 500px; width: 100%; text-align: center;
    box-shadow: 0 30px 60px rgba(170,0,255,0.3);
    animation: modalAppear 0.5s ease; position: relative; z-index: 10;
  }
  @keyframes modalAppear { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
  .login-icon { font-size: 80px; margin-bottom: 30px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }
  .login-modal h2 {
    font-size: 32px; font-weight: 800; margin-bottom: 16px;
    background: linear-gradient(135deg, #ffffff, #aa00ff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }
  .login-modal p { color: #b0b0b0; font-size: 16px; margin-bottom: 32px; line-height: 1.6; }
  .login-button {
    background-image: linear-gradient(135deg, #aa00ff, #ff00aa);
    color: white; border: none; padding: 10px 28px; border-radius: 50px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(170,0,255,0.3);
  }
  .login-button:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(170,0,255,0.4); }

  /* ── Responsive ── */
  @media (max-width: 768px) {
    .cart-page { padding: 40px 0 60px; }
    .cart-container { padding: 0 20px; max-width: 100%; }
    .modules-divider { gap: 14px; }
    .modules-label { font-size: 20px; letter-spacing: 5px; }
    .module-card { padding: 24px 18px; max-width: 100%; }
    .module-name { font-size: 17px; }
    .stats-bar { padding: 14px 18px; }
    .modal-box { padding: 28px 22px; }
    .modal-actions { flex-direction: column; }
    .staff-form-grid { grid-template-columns: 1fr; }
    .staff-lookup-row { flex-direction: column; }

    .history-item-main { flex-direction: column; align-items: flex-start; gap: 8px; }
    .history-item-right { width: 100%; justify-content: flex-start; }
  }

  @media (max-width: 480px) {
    .modules-label { font-size: 16px; letter-spacing: 3px; }
    .filter-tabs { gap: 6px; }
    .filter-tab { padding: 6px 11px; font-size: 12px; }
    .module-footer { gap: 6px; }
    .action-btn { padding: 9px 12px; font-size: 12px; }

    .history-item-date { font-size: 11px; }
    .history-item-type { font-size: 11px; }
    .history-item-amount { font-size: 13px; }
  }
`;

const root = createRoot(document.getElementById('app'));
root.render(
  <React.StrictMode>
    <MySubscriptionsPage />
  </React.StrictMode>
);

export default MySubscriptionsPage;