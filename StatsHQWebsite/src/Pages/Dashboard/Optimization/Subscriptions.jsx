import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import {
  Settings, Server, FileText, XCircle, Clock, CheckCircle,
  Ban, AlertCircle, RotateCcw
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const NAVBAR_HEIGHT = "80px";

const PRIVILEGED_USERS = ["1428927519515611141", "591655972414685229"];

// ============================================
// HELPERS
// ============================================

const MODULE_INFO = {
  "optimization-plus": {
    name: "Optimization+",
    icon: <Settings size={22} color="#aa00ff" />,
  },
};

const STATUS_META = {
  active: {
    label: "Active",
    color: "#00b894",
    bg: "rgba(0,184,148,0.15)",
    border: "rgba(0,184,148,0.3)",
    icon: <CheckCircle size={12} />,
  },
  canceled: {
    label: "Cancelled",
    color: "#ff7675",
    bg: "rgba(255,118,117,0.15)",
    border: "rgba(255,118,117,0.3)",
    icon: <Ban size={12} />,
  },
  paused: {
    label: "Paused",
    color: "#f0a500",
    bg: "rgba(240,165,0,0.15)",
    border: "rgba(240,165,0,0.3)",
    icon: <Clock size={12} />,
  },
  past_due: {
    label: "Past Due",
    color: "#f0a500",
    bg: "rgba(240,165,0,0.15)",
    border: "rgba(240,165,0,0.3)",
    icon: <AlertCircle size={12} />,
  },
  trialing: {
    label: "Trialing",
    color: "#5b9cf6",
    bg: "rgba(91,156,246,0.15)",
    border: "rgba(91,156,246,0.3)",
    icon: <Clock size={12} />,
  },
  refunded: {
    label: "Refunded",
    color: "#888",
    bg: "rgba(136,136,136,0.15)",
    border: "rgba(136,136,136,0.3)",
    icon: <RotateCcw size={12} />,
  },
};

const getStatusMeta = (status) => STATUS_META[status] || STATUS_META["canceled"];

const formatDate = (dateStr) => {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

const formatCycle = (cycle) => (cycle === "yearly" ? "Yearly" : "Monthly");

// ============================================
// LOADING SPINNER
// ============================================

const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", padding: "60px", gap: "16px",
      width: "100%", minHeight: "400px",
    }}>
      <div style={{
        width: spinnerSize, height: spinnerSize,
        border: "3px solid rgba(170, 0, 255, 0.2)",
        borderTop: "3px solid #aa00ff", borderRadius: "50%",
        animation: "spin 1s linear infinite",
      }} />
      {text && <span style={{ color: "#aa00ff", fontSize: "14px" }}>{text}</span>}
    </div>
  );
};

// ============================================
// ACCESS DENIED
// ============================================

const AccessDenied = () => (
  <div className="dashboard-content">
    <div className="error-message-container">
      <div className="error-icon">🔒</div>
      <h2 className="error-title">Access Denied</h2>
      <p className="error-message">You don't have permission to view subscriptions for this server.</p>
      <p className="error-message">This page requires <strong>Administrator</strong> permission.</p>
    </div>
  </div>
);

// ============================================
// CONFIRM MODAL
// ============================================

const ConfirmModal = ({ title, message, confirmLabel, onConfirm, onCancel, loading }) => (
  <div className="modal-overlay" onClick={onCancel}>
    <div className="modal-box" onClick={(e) => e.stopPropagation()}>
      <h3 className="modal-title">{title}</h3>
      <p className="modal-message">{message}</p>
      <div className="modal-actions">
        <button className="modal-cancel-btn" onClick={onCancel} disabled={loading}>
          Keep subscription
        </button>
        <button className="modal-confirm-btn danger" onClick={onConfirm} disabled={loading}>
          {loading ? (
            <><div className="btn-spinner" /><span>Processing…</span></>
          ) : confirmLabel}
        </button>
      </div>
    </div>
  </div>
);

// ============================================
// SUBSCRIPTION CARD
// ============================================

const SubscriptionCard = ({ sub, onCancel, onInvoice, invoiceLoading, cancelLoading }) => {
  const info = MODULE_INFO[sub.module_key] || { name: sub.module_key, icon: <Settings size={22} color="#aa00ff" /> };
  const statusMeta = getStatusMeta(sub.status);
  const isActive = sub.status === "active" || sub.status === "trialing";
  const discountPct = sub.discount_pct ? (sub.discount_pct * 100).toFixed(0) : null;

  return (
    <div className="sub-card">
      {/* Header */}
      <div className="sub-card-header">
        <div className="sub-card-icon">{info.icon}</div>
        <div className="sub-card-title-group">
          <h3 className="sub-card-name">{info.name}</h3>
          <span className="sub-card-price">
            ${parseFloat(sub.final_price_usd || 0).toFixed(2)} / {formatCycle(sub.billing_cycle).toLowerCase()}
            {discountPct && <span className="sub-discount-pill"> · {discountPct}% off</span>}
          </span>
        </div>
        <div
          className="sub-status-badge"
          style={{ color: statusMeta.color, background: statusMeta.bg, border: `1px solid ${statusMeta.border}` }}
        >
          {statusMeta.icon}
          <span>{statusMeta.label}</span>
        </div>
      </div>

      <div className="sub-card-divider" />

      {/* Details */}
      <div className="sub-details-grid">
        <div className="sub-detail-row">
          <Server size={13} className="sub-detail-icon" />
          <span className="sub-detail-label">Server</span>
          <span className="sub-detail-value">{sub.guild_name || sub.guild_id || "—"}</span>
        </div>
        <div className="sub-detail-row">
          <Clock size={13} className="sub-detail-icon" />
          <span className="sub-detail-label">Billing</span>
          <span className="sub-detail-value">{formatCycle(sub.billing_cycle)}</span>
        </div>
        <div className="sub-detail-row">
          <CheckCircle size={13} className="sub-detail-icon" />
          <span className="sub-detail-label">Started</span>
          <span className="sub-detail-value">{formatDate(sub.created_at || sub.current_period_start)}</span>
        </div>
        {sub.current_period_end && isActive && (
          <div className="sub-detail-row">
            <Clock size={13} className="sub-detail-icon" />
            <span className="sub-detail-label">Renews</span>
            <span className="sub-detail-value">{formatDate(sub.current_period_end)}</span>
          </div>
        )}
        {sub.canceled_at && (
          <div className="sub-detail-row">
            <Ban size={13} className="sub-detail-icon" />
            <span className="sub-detail-label">Cancelled</span>
            <span className="sub-detail-value">{formatDate(sub.canceled_at)}</span>
          </div>
        )}
        {sub.paddle_subscription_id && (
          <div className="sub-detail-row">
            <span className="sub-detail-label" style={{ marginLeft: "21px" }}>Sub ID</span>
            <span className="sub-detail-value sub-mono">{sub.paddle_subscription_id.slice(0, 22)}…</span>
          </div>
        )}
        {sub.discord_username && (
          <div className="sub-detail-row">
            <span className="sub-detail-label" style={{ marginLeft: "21px" }}>Subscriber</span>
            <span className="sub-detail-value">{sub.discord_username}</span>
          </div>
        )}
      </div>

      <div className="sub-card-divider" />

      {/* Actions */}
      <div className="sub-card-actions">
        {sub.paddle_transaction_id && (
          <button
            className="sub-action-btn sub-invoice-btn"
            onClick={() => onInvoice(sub)}
            disabled={invoiceLoading}
          >
            {invoiceLoading ? <div className="btn-spinner-sm" /> : <FileText size={14} />}
            <span>Invoice</span>
          </button>
        )}
        {isActive && (
          <button
            className="sub-action-btn sub-cancel-btn"
            onClick={() => onCancel(sub)}
            disabled={cancelLoading}
          >
            {cancelLoading ? <div className="btn-spinner-sm" /> : <XCircle size={14} />}
            <span>Cancel</span>
          </button>
        )}
      </div>
    </div>
  );
};

// ============================================
// SUBSCRIPTIONS DASHBOARD CONTENT
// ============================================

const SubscriptionsDashboard = ({ currentServer, currentUserId }) => {
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [toast, setToast] = useState(null);
  const [modal, setModal] = useState(null);
  const [invoiceLoading, setInvoiceLoading] = useState(null);
  const [cancelLoading, setCancelLoading] = useState(null);

  const showToast = (message, type = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    if (currentServer) fetchSubscriptions();
  }, [currentServer]);

  const fetchSubscriptions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/paddle/subscriptions/guild/${currentServer.id}`,
        { credentials: "include", headers: { "Cache-Control": "no-cache" } }
      );
      if (!res.ok) throw new Error(`Failed to fetch subscriptions (${res.status})`);
      const data = await res.json();
      const sorted = [...(data || [])].sort((a, b) => {
        const aActive = a.status === "active" ? 0 : 1;
        const bActive = b.status === "active" ? 0 : 1;
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

  const handleInvoice = async (sub) => {
    setInvoiceLoading(sub.paddle_subscription_id);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/paddle/transactions/${sub.paddle_transaction_id}/invoice`,
        { credentials: "include" }
      );
      if (!res.ok) throw new Error("Could not retrieve invoice");
      const data = await res.json();
      const url = data?.data?.url || data?.url;
      if (!url) throw new Error("No invoice URL returned");
      window.open(url, "_blank");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setInvoiceLoading(null);
    }
  };

  const handleCancelConfirm = async () => {
    const sub = modal.sub;
    setCancelLoading(sub.paddle_subscription_id);
    setModal(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/paddle/subscriptions/${sub.paddle_subscription_id}/cancel`,
        {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ effective_from: "immediately" }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to cancel subscription");
      setSubscriptions((prev) =>
        prev.map((s) =>
          s.paddle_subscription_id === sub.paddle_subscription_id
            ? { ...s, status: "canceled", canceled_at: new Date().toISOString() }
            : s
        )
      );
      showToast("Subscription cancelled successfully.", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setCancelLoading(null);
    }
  };

  const FILTERS = ["all", "active", "canceled", "paused", "past_due"];
  const HISTORY_STATUSES = ["canceled", "paused", "past_due", "refunded"];

  const filtered = subscriptions.filter((s) => filter === "all" || s.status === filter);
  const activeSubs = filtered.filter((s) => s.status === "active" || s.status === "trialing");
  const historySubs = filtered.filter((s) => HISTORY_STATUSES.includes(s.status));

  const activeCount = subscriptions.filter((s) => s.status === "active").length;
  const totalSpend = subscriptions
    .filter((s) => s.status === "active")
    .reduce((acc, s) => acc + parseFloat(s.final_price_usd || 0), 0)
    .toFixed(2);

  const ToastComponent = () => {
    if (!toast) return null;
    const colors = {
      success: { bg: "#00b894", icon: "✅" },
      error: { bg: "#ff7675", icon: "❌" },
      info: { bg: "#0984e3", icon: "ℹ️" },
    };
    const c = colors[toast.type] || colors.info;
    return (
      <div className="toast-message" style={{ backgroundColor: c.bg }}>
        <span>{c.icon}</span>
        <span>{toast.message}</span>
        <button onClick={() => setToast(null)} style={{ background: "none", border: "none", color: "white", cursor: "pointer", marginLeft: "10px", fontSize: "16px" }}>✕</button>
      </div>
    );
  };

  return (
    <>
      {/* Stats bar */}
      {!loading && subscriptions.length > 0 && (
        <div className="reset-section" style={{ marginBottom: "24px" }}>
          <div className="section-header">
            <div className="section-icon">💳</div>
            <div className="section-title">Server Subscriptions</div>
            <div className="section-subtitle">{currentServer?.name}</div>
          </div>
          <div className="stats-bar">
            <div className="stat-chip">
              <span className="stat-num">{subscriptions.length}</span>
              <span className="stat-label-sm">Total</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-chip">
              <span className="stat-num" style={{ color: "#00b894" }}>{activeCount}</span>
              <span className="stat-label-sm">Active</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-chip">
              <span className="stat-num" style={{ color: "#aa00ff" }}>${totalSpend}</span>
              <span className="stat-label-sm">/ mo active</span>
            </div>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      {!loading && subscriptions.length > 0 && (
        <div className="filter-tabs-row">
          {FILTERS.map((f) => {
            const count = f === "all"
              ? subscriptions.length
              : subscriptions.filter((s) => s.status === f).length;
            return (
              <button
                key={f}
                className={`filter-tab-btn ${filter === f ? "active" : ""}`}
                onClick={() => setFilter(f)}
              >
                {f === "all" ? "All" : f === "past_due" ? "Past Due" : f.charAt(0).toUpperCase() + f.slice(1)}
                {count > 0 && <span className="filter-count">{count}</span>}
              </button>
            );
          })}
          <button
            className="action-button"
            onClick={fetchSubscriptions}
            style={{ marginLeft: "auto" }}
          >
            🔄 Refresh
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="reset-section" style={{ borderColor: "#ff4444" }}>
          <p style={{ color: "#ff7675" }}>⚠️ {error}</p>
          <button className="apply-days-btn" style={{ marginTop: "12px" }} onClick={fetchSubscriptions}>
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="reset-section">
          <LoadingSpinner text="Loading subscriptions…" />
        </div>
      )}

      {/* Empty */}
      {!loading && !error && subscriptions.length === 0 && (
        <div className="reset-section" style={{ textAlign: "center", padding: "60px" }}>
          <div style={{ fontSize: "48px", marginBottom: "16px" }}>💳</div>
          <h3 style={{ color: "#fff", marginBottom: "8px" }}>No subscriptions</h3>
          <p style={{ color: "#888" }}>This server doesn't have any subscription history yet.</p>
        </div>
      )}

      {/* Active section */}
      {!loading && activeSubs.length > 0 && (
        <div className="reset-section">
          <div className="section-header">
            <div className="section-icon">✅</div>
            <div className="section-title" style={{ fontSize: "18px" }}>Active</div>
            <div className="section-subtitle">{activeSubs.length} subscription{activeSubs.length !== 1 ? "s" : ""}</div>
          </div>
          <div className="subs-grid">
            {activeSubs.map((sub) => (
              <SubscriptionCard
                key={sub.paddle_subscription_id || sub.id}
                sub={sub}
                onCancel={(s) => setModal({ type: "cancel", sub: s })}
                onInvoice={handleInvoice}
                invoiceLoading={invoiceLoading === sub.paddle_subscription_id}
                cancelLoading={cancelLoading === sub.paddle_subscription_id}
              />
            ))}
          </div>
        </div>
      )}

      {/* History section */}
      {!loading && historySubs.length > 0 && (
        <div className="reset-section">
          <div className="section-header">
            <div className="section-icon">🕓</div>
            <div className="section-title" style={{ fontSize: "18px", color: "#888" }}>History</div>
            <div className="section-subtitle">{historySubs.length} record{historySubs.length !== 1 ? "s" : ""}</div>
          </div>
          <div className="subs-grid">
            {historySubs.map((sub) => (
              <SubscriptionCard
                key={sub.paddle_subscription_id || sub.id}
                sub={sub}
                onCancel={(s) => setModal({ type: "cancel", sub: s })}
                onInvoice={handleInvoice}
                invoiceLoading={invoiceLoading === sub.paddle_subscription_id}
                cancelLoading={cancelLoading === sub.paddle_subscription_id}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty filter */}
      {!loading && subscriptions.length > 0 && activeSubs.length === 0 && historySubs.length === 0 && (
        <div className="reset-section" style={{ textAlign: "center", padding: "40px" }}>
          <p style={{ color: "#888" }}>No subscriptions match this filter.</p>
          <button className="action-button" style={{ marginTop: "12px" }} onClick={() => setFilter("all")}>
            Show all
          </button>
        </div>
      )}

      {/* Cancel confirm modal */}
      {modal?.type === "cancel" && (
        <ConfirmModal
          title="Cancel subscription?"
          message={`This will immediately cancel the ${MODULE_INFO[modal.sub.module_key]?.name || modal.sub.module_key} subscription for ${modal.sub.guild_name || "this server"}. Access will be revoked right away.`}
          confirmLabel="Yes, cancel it"
          onConfirm={handleCancelConfirm}
          onCancel={() => setModal(null)}
          loading={cancelLoading === modal.sub.paddle_subscription_id}
        />
      )}

      <ToastComponent />
    </>
  );
};

// ============================================
// MAIN PAGE COMPONENT
// ============================================

const SubscriptionsPage = () => {
  const [currentServer, setCurrentServer] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  const isPrivilegedUser = (userId) => PRIVILEGED_USERS.includes(userId);

  const loadInitialData = async () => {
    try {
      const authRes = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!authRes.ok) throw new Error("Auth failed");
      const authData = await authRes.json();

      if (!authData.authenticated || !authData.user) {
        setIsAuthenticated(false);
        setLoading(false);
        return;
      }

      setIsAuthenticated(true);
      setCurrentUserId(authData.user.id);

      const serversRes = await fetch(`${API_BASE_URL}/api/user/servers`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });

      if (!serversRes.ok) throw new Error("Failed to fetch servers");
      const servers = await serversRes.json();

      let selectedServer = null;
      if (Array.isArray(servers) && servers.length > 0) {
        if (authData.user.selected_server) {
          selectedServer = servers.find((s) => s.id === authData.user.selected_server);
        }
        if (!selectedServer) selectedServer = servers[0];
      }

      if (selectedServer) {
        setCurrentServer(selectedServer);
        if (isPrivilegedUser(authData.user.id)) {
          setHasAccess(true);
        } else {
          setHasAccess(!!selectedServer.has_admin);
        }
      } else {
        setHasAccess(false);
      }
    } catch (err) {
      console.error("Error loading initial data:", err);
      setHasAccess(false);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <LoadingSpinner text="Loading…" />
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
              <div className="error-message-container">
                <div className="error-icon">🔒</div>
                <h2 className="error-title">Sign In Required</h2>
                <p className="error-message">Please log in to view subscription management.</p>
                <a href={`${API_BASE_URL}/api/auth/discord`} className="invite-button" style={{ display: "inline-block", marginTop: "16px" }}>
                  Log in with Discord
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

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        <main className="dashboard-main">
          <div className="dashboard-content">
            <SubscriptionsDashboard currentServer={currentServer} currentUserId={currentUserId} />
          </div>
          <Footer />
        </main>
      </div>
      <style>{styles}</style>
    </>
  );
};

// ============================================
// STYLES
// ============================================

const styles = `
  @font-face {
    font-family: 'Horndon';
    src: url('/HorndonD.ttf') format('truetype');
    font-display: swap;
  }

  * {
    margin: 0; padding: 0; box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  }

  html { min-height: 100%; background-color: #0a0a0a; overflow-x: hidden; }
  body { min-height: 100vh; margin: 0; padding: 0; background-color: #0a0a0a; color: #ffffff; overflow-y: auto; overflow-x: hidden; width: 100%; }
  #app { min-height: 100vh; background-color: #0a0a0a; overflow-x: hidden; width: 100%; }

  .dashboard-page {
    max-width: 100%; margin: 0 auto; background-color: #0a0a0a; color: #ffffff;
    min-height: 100vh; display: flex; position: relative; overflow-x: hidden;
  }

  .dashboard-main {
    flex: 1; margin-left: 280px; background-color: #0a0a0a;
    min-height: 100vh; overflow-x: hidden; width: 100%;
  }

  .dashboard-content {
    max-width: 1600px; margin: 0 auto; padding: 20px 40px 40px 40px;
    background-color: #0a0a0a; overflow-x: hidden; width: 100%; box-sizing: border-box;
  }

  .navbar {
    position: sticky !important; top: 0 !important; z-index: 1000 !important;
  }

  /* ── Section card ── */
  .reset-section {
    background: linear-gradient(135deg, #0f0f0f 0%, #0a0a0a 100%);
    border: 1px solid #1f1f1f; border-radius: 20px; padding: 28px;
    margin-bottom: 24px; transition: border-color 0.3s ease;
  }
  .reset-section:hover { border-color: #2a2a2a; }

  .section-header {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #1f1f1f;
  }
  .section-icon { font-size: 26px; }
  .section-title {
    font-size: 20px; font-weight: 600; color: #ffffff; display: flex; align-items: center;
  }
  .section-subtitle { font-size: 13px; color: #888; margin-left: auto; }

  /* ── Stats bar ── */
  .stats-bar {
    display: flex; align-items: center; gap: 0;
    background: #111; border: 1px solid #2a2a2a; border-radius: 14px;
    padding: 18px 28px;
  }
  .stat-chip { display: flex; flex-direction: column; align-items: center; flex: 1; gap: 4px; }
  .stat-num { font-size: 22px; font-weight: 800; color: #ffffff; }
  .stat-label-sm { font-size: 11px; color: #666; font-weight: 500; letter-spacing: 0.5px; }
  .stat-divider { width: 1px; height: 36px; background: #2a2a2a; margin: 0 12px; }

  /* ── Filter tabs ── */
  .filter-tabs-row {
    display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap; align-items: center;
  }
  .filter-tab-btn {
    display: flex; align-items: center; gap: 7px;
    padding: 8px 16px; background: #1a1a1a; border: 1px solid #2a2a2a;
    border-radius: 20px; color: #888; font-size: 13px; font-weight: 500;
    cursor: pointer; transition: all 0.2s ease;
  }
  .filter-tab-btn:hover { border-color: rgba(170,0,255,0.4); color: #ccc; }
  .filter-tab-btn.active {
    background: rgba(170,0,255,0.1); border-color: rgba(170,0,255,0.5); color: #ffffff;
  }
  .filter-count {
    font-size: 11px; font-weight: 700; padding: 1px 7px;
    background: rgba(170,0,255,0.15); color: #aa00ff; border-radius: 10px;
  }
  .filter-tab-btn.active .filter-count { background: rgba(170,0,255,0.25); }

  /* ── Action button ── */
  .action-button {
    background-color: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px;
    padding: 8px 16px; font-size: 13px; font-weight: 500; color: #b0b0b0;
    cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; gap: 8px;
  }
  .action-button:hover { border-color: #aa00ff; color: #aa00ff; background-color: rgba(170,0,255,0.1); }

  /* ── Subscriptions grid ── */
  .subs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }

  /* ── Subscription card ── */
  .sub-card {
    background: #111; border: 1px solid #2a2a2a; border-radius: 16px;
    padding: 22px; transition: border-color 0.2s ease, box-shadow 0.2s ease;
    display: flex; flex-direction: column;
  }
  .sub-card:hover { border-color: rgba(170,0,255,0.3); box-shadow: 0 4px 20px rgba(170,0,255,0.08); }

  .sub-card-header { display: flex; align-items: center; gap: 12px; }
  .sub-card-icon {
    width: 44px; height: 44px; background: rgba(170,0,255,0.1);
    border: 1px solid rgba(170,0,255,0.25); border-radius: 10px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    transition: transform 0.3s ease, background 0.3s ease;
  }
  .sub-card:hover .sub-card-icon { transform: rotate(90deg); background: rgba(170,0,255,0.18); }
  .sub-card-title-group { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
  .sub-card-name { font-size: 17px; font-weight: 700; color: #ffffff; }
  .sub-card-price { font-size: 12px; color: #aa00ff; font-weight: 500; }
  .sub-discount-pill { color: #00b894; font-size: 11px; font-weight: 600; }

  .sub-status-badge {
    display: flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;
    flex-shrink: 0; white-space: nowrap;
  }

  .sub-card-divider { height: 1px; background: #2a2a2a; margin: 16px 0; }

  .sub-details-grid { display: flex; flex-direction: column; gap: 8px; }
  .sub-detail-row { display: flex; align-items: center; gap: 8px; }
  .sub-detail-icon { color: #555; flex-shrink: 0; }
  .sub-detail-label { font-size: 12px; color: #666; font-weight: 500; min-width: 62px; }
  .sub-detail-value { font-size: 13px; color: #ccc; font-weight: 500; }
  .sub-mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; color: #777; }

  .sub-card-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .sub-action-btn {
    display: flex; align-items: center; gap: 6px; padding: 9px 16px;
    border-radius: 8px; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: all 0.2s ease; white-space: nowrap;
  }
  .sub-action-btn:disabled { cursor: not-allowed; opacity: 0.5; }
  .sub-invoice-btn { background: transparent; border: 1px solid rgba(170,0,255,0.35); color: #aa00ff; }
  .sub-invoice-btn:hover:not(:disabled) { background: rgba(170,0,255,0.1); border-color: rgba(170,0,255,0.6); }
  .sub-cancel-btn { background: transparent; border: 1px solid rgba(255,118,117,0.35); color: #ff8888; }
  .sub-cancel-btn:hover:not(:disabled) { background: rgba(255,118,117,0.1); border-color: #ff7675; }

  /* ── Spinners ── */
  .btn-spinner-sm {
    width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.2);
    border-top-color: currentColor; border-radius: 50%;
    animation: spin 0.7s linear infinite; flex-shrink: 0;
  }
  .btn-spinner {
    width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #ffffff; border-radius: 50%;
    animation: spin 0.8s linear infinite; flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Modal ── */
  .modal-overlay {
    position: fixed; inset: 0; z-index: 10000;
    background: rgba(0,0,0,0.85); backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center; padding: 20px;
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

  .modal-box {
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border: 1px solid #ff4444; border-radius: 20px; padding: 32px;
    max-width: 440px; width: 100%;
    animation: slideUp 0.25s ease;
    box-shadow: 0 20px 50px rgba(0,0,0,0.6);
  }
  @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

  .modal-title { font-size: 20px; font-weight: 700; color: #ff7675; margin-bottom: 12px; }
  .modal-message { font-size: 14px; color: #aaa; line-height: 1.65; margin-bottom: 24px; }
  .modal-actions { display: flex; gap: 10px; }

  .modal-cancel-btn {
    flex: 1; padding: 11px; background: #1a1a1a; border: 1px solid #2a2a2a;
    color: #888; font-size: 14px; font-weight: 600; border-radius: 8px;
    cursor: pointer; transition: all 0.2s ease;
  }
  .modal-cancel-btn:hover:not(:disabled) { border-color: #444; color: #ccc; }
  .modal-cancel-btn:disabled { cursor: not-allowed; opacity: 0.5; }

  .modal-confirm-btn {
    flex: 1; padding: 11px; border: none; color: #ffffff;
    font-size: 14px; font-weight: 700; border-radius: 8px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    transition: all 0.2s ease;
  }
  .modal-confirm-btn.danger { background: linear-gradient(135deg, #ff4444, #cc2222); }
  .modal-confirm-btn.danger:hover:not(:disabled) { box-shadow: 0 4px 16px rgba(255,68,68,0.4); }
  .modal-confirm-btn:disabled { cursor: not-allowed; opacity: 0.6; }

  /* ── Toast ── */
  .toast-message {
    position: fixed; bottom: 20px; right: 20px; padding: 12px 20px;
    border-radius: 10px; display: flex; align-items: center; gap: 10px;
    z-index: 9999; animation: slideInRight 0.3s ease;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); font-weight: 500;
  }
  @keyframes slideInRight {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }

  /* ── Error / Access denied ── */
  .error-message-container {
    text-align: center; padding: 80px 40px; background: #1a1a1a;
    border: 1px solid #ff4444; border-radius: 16px;
  }
  .error-icon { font-size: 64px; margin-bottom: 20px; }
  .error-title { color: #ff4444; font-size: 28px; font-weight: 600; margin-bottom: 16px; }
  .error-message { color: #aaa; font-size: 15px; margin-top: 8px; }
  .invite-button {
    display: inline-block; background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white; padding: 12px 28px; border-radius: 10px; text-decoration: none;
    font-weight: 600;
  }

  /* ── Responsive ── */
  @media (max-width: 768px) {
    .dashboard-main { margin-left: 0; }
    .dashboard-content { padding: 16px; }
    .subs-grid { grid-template-columns: 1fr; }
    .filter-tabs-row { gap: 6px; }
    .modal-actions { flex-direction: column; }
    .stats-bar { padding: 14px 16px; }
  }
`;

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <SubscriptionsPage />
  </React.StrictMode>
);

export default SubscriptionsPage;