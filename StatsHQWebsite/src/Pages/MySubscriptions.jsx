import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Zap, Server, FileText, XCircle, RotateCcw, ChevronDown, Clock, CheckCircle, Ban, AlertCircle, RefreshCw, PauseCircle } from 'lucide-react';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const API_URL = window.location.origin;

// ─── Module registry ────────────────────────────────────────────────────────────
const MODULE_INFO = {
  'optimization-plus': {
    name: 'Optimization+',
    icon: <Zap size={22} color="#aa00ff" />,
  },
};

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

const formatCycle = (cycle) =>
  cycle === 'yearly' ? 'Yearly' : 'Monthly';

// Auto-renew is considered "off" if Paddle has a scheduled cancellation
// at the end of the current billing period.
const isAutoRenewOff = (sub) =>
  sub?.scheduled_change?.action === 'cancel';

// ─── Filter tabs ────────────────────────────────────────────────────────────────
const FILTERS = ['all', 'active', 'canceled', 'paused', 'past_due'];

// ─── ConfirmModal ───────────────────────────────────────────────────────────────
const ConfirmModal = ({ title, message, confirmLabel, confirmClass, onConfirm, onCancel, loading }) => (
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
          disabled={loading}
        >
          {loading ? <><div className="btn-spinner" /><span>Processing...</span></> : confirmLabel}
        </button>
      </div>
    </div>
  </div>
);

// ─── SubscriptionCard ───────────────────────────────────────────────────────────
const SubscriptionCard = ({
  sub, onCancel, onRefund, onInvoice, onToggleAutoRenew,
  invoiceLoading, cancelLoading, refundLoading, autoRenewLoading,
}) => {
  const info = MODULE_INFO[sub.module_key] || { name: sub.module_key, icon: <Zap size={22} color="#aa00ff" /> };
  const statusMeta = getStatusMeta(sub.status);
  const eligible = sub.status === 'active' && isWithin48Hours(sub.created_at || sub.current_period_start);
  const discountPct = sub.discount_pct ? (sub.discount_pct * 100).toFixed(0) : null;
  const autoRenewOff = isAutoRenewOff(sub);
  const showAutoRenewToggle = sub.status === 'active' || sub.status === 'trialing';

  return (
    <div className="module-card">
      <div className="card-sheen" />

      {/* Header */}
      <div className="module-header">
        <div className="module-icon">{info.icon}</div>
        <div className="module-title-group">
          <h2 className="module-name">{info.name}</h2>
          <span className="module-price">
            ${parseFloat(sub.final_price_usd || 0).toFixed(2)}
            {' '}/ {formatCycle(sub.billing_cycle).toLowerCase()}
            {discountPct && (
              <span className="discount-pill"> · {discountPct}% off</span>
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
          <span className="detail-value">{formatCycle(sub.billing_cycle)}</span>
        </div>
        <div className="detail-row">
          <CheckCircle size={13} className="detail-icon" />
          <span className="detail-label">Started</span>
          <span className="detail-value">{formatDate(sub.created_at || sub.current_period_start)}</span>
        </div>
        {sub.current_period_end && sub.status === 'active' && (
          <div className="detail-row">
            <Clock size={13} className="detail-icon" />
            <span className="detail-label">Renews</span>
            <span className="detail-value">
              {autoRenewOff
                ? `Ends ${formatDate(sub.current_period_end)}`
                : formatDate(sub.current_period_end)}
            </span>
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

      {/* Auto-renew toggle */}
      {showAutoRenewToggle && (
        <div className="autorenew-row">
          <div className="autorenew-label-group">
            {autoRenewOff ? <PauseCircle size={14} color="#f0a500" /> : <RefreshCw size={14} color="#00e07a" />}
            <span className="autorenew-label">Auto-renew</span>
            <span className="autorenew-sublabel">
              {autoRenewOff
                ? `Off — ends ${formatDate(sub.current_period_end)}`
                : 'On'}
            </span>
          </div>
          <button
            className={`autorenew-toggle ${!autoRenewOff ? 'on' : 'off'}`}
            role="switch"
            aria-checked={!autoRenewOff}
            onClick={() => onToggleAutoRenew(sub, autoRenewOff)}
            disabled={autoRenewLoading}
            title={autoRenewOff ? 'Turn auto-renew back on' : 'Turn auto-renew off'}
          >
            {autoRenewLoading ? (
              <div className="btn-spinner-sm" style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
            ) : (
              <span className="autorenew-knob" />
            )}
          </button>
        </div>
      )}

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

  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const [filter, setFilter] = useState('all');

  // Per-card loading states (keyed by paddle_subscription_id)
  const [invoiceLoading, setInvoiceLoading] = useState(null);
  const [cancelLoading, setCancelLoading] = useState(null);
  const [refundLoading, setRefundLoading] = useState(null);
  const [autoRenewLoading, setAutoRenewLoading] = useState(null);

  // Confirm modal state
  const [modal, setModal] = useState(null); // { type: 'cancel'|'refund'|'autorenew-off', sub }

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

  // ─── Auto-renew toggle ───────────────────────────────────────────────────────
  // Turning ON requires no confirmation. Turning OFF (i.e. scheduling a
  // cancellation at period end) is confirmed via modal since it changes
  // what happens to the subscription.
  const requestToggleAutoRenew = (sub, currentlyOff) => {
    if (currentlyOff) {
      doToggleAutoRenew(sub, true);
    } else {
      setModal({ type: 'autorenew-off', sub });
    }
  };

  const doToggleAutoRenew = async (sub, enable) => {
    setAutoRenewLoading(sub.paddle_subscription_id);
    try {
      const res = await fetch(`${API_URL}/api/paddle/subscriptions/${sub.paddle_subscription_id}/auto-renew`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update auto-renew');

      setSubscriptions(prev =>
        prev.map(s =>
          s.paddle_subscription_id === sub.paddle_subscription_id
            ? {
                ...s,
                scheduled_change: enable
                  ? null
                  : { action: 'cancel', effective_at: 'next_billing_period' },
              }
            : s
        )
      );
      setSuccessMsg(enable ? 'Auto-renew turned back on.' : 'Auto-renew turned off — subscription will end at period close.');
      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err) {
      setError(err.message);
      setTimeout(() => setError(null), 5000);
    } finally {
      setAutoRenewLoading(null);
    }
  };

  const handleAutoRenewOffConfirm = () => {
    const sub = modal.sub;
    setModal(null);
    doToggleAutoRenew(sub, false);
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
              <Zap size={48} color="#aa00ff" />
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
                        onToggleAutoRenew={requestToggleAutoRenew}
                        invoiceLoading={invoiceLoading === sub.paddle_subscription_id}
                        cancelLoading={cancelLoading === sub.paddle_subscription_id}
                        refundLoading={refundLoading === sub.paddle_subscription_id}
                        autoRenewLoading={autoRenewLoading === sub.paddle_subscription_id}
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
                        onToggleAutoRenew={requestToggleAutoRenew}
                        invoiceLoading={invoiceLoading === sub.paddle_subscription_id}
                        cancelLoading={cancelLoading === sub.paddle_subscription_id}
                        refundLoading={refundLoading === sub.paddle_subscription_id}
                        autoRenewLoading={autoRenewLoading === sub.paddle_subscription_id}
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

      {/* Confirm modal */}
      {modal && (
        <ConfirmModal
          title={
            modal.type === 'cancel'
              ? 'Cancel subscription?'
              : modal.type === 'refund'
              ? 'Request a refund?'
              : 'Turn off auto-renew?'
          }
          message={
            modal.type === 'cancel'
              ? `This will immediately cancel your ${MODULE_INFO[modal.sub.module_key]?.name || modal.sub.module_key} subscription. Access will be revoked right away.`
              : modal.type === 'refund'
              ? `This will refund your $${parseFloat(modal.sub.final_price_usd || 0).toFixed(2)} payment and cancel the subscription. Funds typically arrive in 5–10 business days.`
              : `Your ${MODULE_INFO[modal.sub.module_key]?.name || modal.sub.module_key} subscription will stay active until ${formatDate(modal.sub.current_period_end)}, then it won't renew. You can turn auto-renew back on anytime before then.`
          }
          confirmLabel={
            modal.type === 'cancel'
              ? 'Yes, cancel it'
              : modal.type === 'refund'
              ? 'Yes, refund me'
              : 'Yes, turn it off'
          }
          confirmClass={modal.type === 'cancel' ? 'danger' : 'warning'}
          onConfirm={
            modal.type === 'cancel'
              ? handleCancelConfirm
              : modal.type === 'refund'
              ? handleRefundConfirm
              : handleAutoRenewOffConfirm
          }
          onCancel={() => setModal(null)}
          loading={
            modal.type === 'cancel'
              ? cancelLoading === modal.sub.paddle_subscription_id
              : modal.type === 'refund'
              ? refundLoading === modal.sub.paddle_subscription_id
              : autoRenewLoading === modal.sub.paddle_subscription_id
          }
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
    display: flex; gap: 8px; margin-bottom: 32px;
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

  /* ── Auto-renew toggle row ── */
  .autorenew-row {
    display: flex; align-items: center; justify-content: space-between;
    margin-top: 16px; padding: 10px 14px;
    background: rgba(255,255,255,0.02); border: 1px solid #2c2f3a; border-radius: 10px;
    position: relative; z-index: 1;
  }
  .autorenew-label-group { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .autorenew-label { font-size: 13px; font-weight: 600; color: #d0d0d0; }
  .autorenew-sublabel { font-size: 12px; color: #555870; }

  .autorenew-toggle {
    position: relative;
    width: 42px; height: 24px; border-radius: 999px;
    border: 1px solid #2c2f3a; cursor: pointer; flex-shrink: 0;
    transition: background 0.2s ease, border-color 0.2s ease;
    padding: 0;
  }
  .autorenew-toggle.on { background: rgba(0,224,122,0.25); border-color: rgba(0,224,122,0.5); }
  .autorenew-toggle.off { background: rgba(136,139,153,0.15); border-color: #2c2f3a; }
  .autorenew-toggle:disabled { cursor: not-allowed; opacity: 0.7; }
  .autorenew-knob {
    position: absolute; top: 2px; left: 2px;
    width: 18px; height: 18px; border-radius: 50%;
    background: #ffffff;
    transition: transform 0.2s cubic-bezier(0.34,1.56,0.64,1);
    box-shadow: 0 1px 3px rgba(0,0,0,0.4);
  }
  .autorenew-toggle.on .autorenew-knob { transform: translateX(18px); background: #00e07a; }
  .autorenew-toggle.off .autorenew-knob { transform: translateX(0); background: #888b99; }

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
  }
  .action-btn:disabled { cursor: not-allowed; opacity: 0.5; }

  .invoice-btn {
    background: transparent; border: 1px solid rgba(170,0,255,0.35); color: #aa00ff;
  }
  .invoice-btn:hover:not(:disabled) { background: rgba(170,0,255,0.1); border-color: rgba(170,0,255,0.6); }

  .cancel-btn {
    background: transparent; border: 1px solid rgba(255,107,107,0.35); color: #ff8888;
  }
  .cancel-btn:hover:not(:disabled) { background: rgba(255,107,107,0.1); border-color: #ff6b6b; }

  .refund-btn {
    background: transparent; border: 1px solid rgba(240,165,0,0.35); color: #f0a500;
  }
  .refund-btn:hover:not(:disabled) { background: rgba(240,165,0,0.08); border-color: rgba(240,165,0,0.6); }

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

  .modal-title { font-size: 20px; font-weight: 700; color: #ffffff; margin-bottom: 12px; }
  .modal-message { font-size: 14px; color: #888b99; line-height: 1.65; margin-bottom: 28px; }
  .modal-actions { display: flex; gap: 10px; }

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
  .modal-confirm-btn:disabled { cursor: not-allowed; opacity: 0.6; }

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
  }

  @media (max-width: 480px) {
    .modules-label { font-size: 16px; letter-spacing: 3px; }
    .filter-tabs { gap: 6px; }
    .filter-tab { padding: 6px 11px; font-size: 12px; }
    .module-footer { gap: 6px; }
    .action-btn { padding: 9px 12px; font-size: 12px; }
  }
`;

const root = createRoot(document.getElementById('app'));
root.render(
  <React.StrictMode>
    <MySubscriptionsPage />
  </React.StrictMode>
);

export default MySubscriptionsPage;