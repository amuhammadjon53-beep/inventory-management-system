import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../Components/NavBar.jsx";
import Footer from "../Components/Footer.jsx";
import DashboardSidebar from "../Components/sidebar.jsx";

// API base URL - your FastAPI backend
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

// ADMIN USERS - only these two IDs may view this page (also enforced server-side via require_admin)
const ADMIN_USERS = ['1428927519515611141', '591655972414685229'];

const NAVBAR_HEIGHT = "80px";

// ---- Shared small components (kept local so this page has no new dependencies) ----

const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: '30px', gap: '12px',
      width: '100%', height: '100%', minHeight: '150px'
    }}>
      <div style={{
        width: spinnerSize, height: spinnerSize,
        border: '3px solid #2a2a2a', borderTop: '3px solid #aa00ff',
        borderRadius: '50%', animation: 'spin 1s linear infinite'
      }} />
      {text && <span style={{ color: '#b0b0b0', fontSize: '14px' }}>{text}</span>}
      <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
};

const LoadingCard = () => (
  <div className="panel-wrapper">
    <LoadingSpinner size="medium" text="Loading data..." />
  </div>
);

const AccessDenied = () => (
  <div className="no-selection">
    <h2>🔒 Access Denied</h2>
    <p>This page is restricted to StatsHQ administrators.</p>
  </div>
);

const formatBytes = (bytes) => {
  if (bytes === null || bytes === undefined) return 'N/A';
  const n = Number(bytes);
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(2)} KB`;
  return `${n} B`;
};

const formatMs = (ms) => {
  if (ms === null || ms === undefined) return 'N/A';
  const n = Number(ms);
  if (n >= 1000) return `${(n / 1000).toFixed(2)}s`;
  return `${n.toFixed(1)}ms`;
};

const formatMoney = (v) => {
  if (v === null || v === undefined) return '$0.00';
  return `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const formatDate = (v) => {
  if (!v) return 'Never';
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
};

// ---- Tab content components ----

const OverviewTab = ({ loading, data }) => {
  if (loading) return <LoadingCard />;
  if (!data) return <div className="no-data-message">No diagnostics data available</div>;

  return (
    <>
      <div className="summary-stats">
        <div className="stat-card">
          <h3>Total DB Size</h3>
          <p className="stat-value">{data.total_db_size || 'N/A'}</p>
        </div>
        <div className="stat-card">
          <h3>Restart Count</h3>
          <p className="stat-value">{(data.restart_count || 0).toLocaleString()}</p>
        </div>
        <div className="stat-card">
          <h3>Last Restart</h3>
          <p className="stat-value-small">{formatDate(data.last_restart_at)}</p>
        </div>
        <div className="stat-card">
          <h3>Tables Tracked</h3>
          <p className="stat-value">{(data.tables || []).length}</p>
        </div>
      </div>

      <div className="panel-section">
        <h2 className="section-title">All Tables by Size</h2>
        <div className="panel-wrapper">
          <table className="diag-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Table</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {(data.tables || []).map((t, i) => (
                <tr key={t.table_name}>
                  <td className="dim">{i + 1}</td>
                  <td>{t.table_name}</td>
                  <td>{t.size}</td>
                </tr>
              ))}
              {(data.tables || []).length === 0 && (
                <tr><td colSpan={3} className="no-data-message">No table data available</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
};

const SyncJobsTab = ({ loading, data }) => {
  if (loading) return <LoadingCard />;
  const jobs = data?.jobs || [];

  return (
    <div className="panel-section">
      <h2 className="section-title">Sync Job Runs</h2>
      <div className="panel-wrapper">
        <table className="diag-table">
          <thead>
            <tr>
              <th>Job</th>
              <th>Success</th>
              <th>Failed</th>
              <th>Last Run</th>
              <th>Avg Duration</th>
              <th>p50</th>
              <th>p95</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.job_type}>
                <td>{j.job_type}</td>
                <td className="ok">{j.success_count}</td>
                <td className={j.failed_count > 0 ? "bad" : "dim"}>{j.failed_count}</td>
                <td>{formatDate(j.last_run_at)}</td>
                <td>{formatMs(j.avg_duration_ms)}</td>
                <td>{formatMs(j.p50_duration_ms)}</td>
                <td>{formatMs(j.p95_duration_ms)}</td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr><td colSpan={7} className="no-data-message">No sync jobs have run yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const BatchWritesTab = ({ loading, data }) => {
  if (loading) return <LoadingCard />;
  const batches = data?.batches || [];

  return (
    <div className="panel-section">
      <h2 className="section-title">Redis Batch Writes</h2>
      <div className="panel-wrapper">
        <table className="diag-table">
          <thead>
            <tr>
              <th>Batch Type</th>
              <th>Total Success</th>
              <th>Total Failed</th>
              <th>Success Rate</th>
              <th>Flush Count</th>
              <th>Last Flush</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => {
              const total = Number(b.total_success || 0) + Number(b.total_failed || 0);
              const rate = total > 0 ? ((b.total_success / total) * 100).toFixed(1) : 'N/A';
              return (
                <tr key={b.batch_type}>
                  <td>{b.batch_type}</td>
                  <td className="ok">{b.total_success}</td>
                  <td className={b.total_failed > 0 ? "bad" : "dim"}>{b.total_failed}</td>
                  <td>{rate === 'N/A' ? rate : `${rate}%`}</td>
                  <td>{b.total_flushes}</td>
                  <td>{formatDate(b.last_flush_at)}</td>
                </tr>
              );
            })}
            {batches.length === 0 && (
              <tr><td colSpan={6} className="no-data-message">No batch writes recorded yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const BusinessTab = ({ loading, data }) => {
  if (loading) return <LoadingCard />;
  if (!data) return <div className="no-data-message">No business data available</div>;

  return (
    <>
      <div className="summary-stats">
        <div className="stat-card">
          <h3>MRR</h3>
          <p className="stat-value">{formatMoney(data.mrr)}</p>
        </div>
        <div className="stat-card">
          <h3>Total Revenue (All Time)</h3>
          <p className="stat-value">{formatMoney(data.total_revenue_all_time)}</p>
        </div>
        <div className="stat-card">
          <h3>New (30d)</h3>
          <p className="stat-value">{data.new_last_30d ?? 0}</p>
        </div>
        <div className="stat-card">
          <h3>Churned (30d)</h3>
          <p className="stat-value">{data.churned_last_30d ?? 0}</p>
        </div>
        <div className="stat-card">
          <h3>Churn Rate</h3>
          <p className="stat-value">{data.churn_rate_pct ?? 0}%</p>
        </div>
      </div>

      <div className="panel-section">
        <h2 className="section-title">Active Subscriptions by Product</h2>
        <div className="panel-wrapper">
          <table className="diag-table">
            <thead>
              <tr><th>Product</th><th>Billing Cycle</th><th>Count</th></tr>
            </thead>
            <tbody>
              {(data.active_by_tier || []).map((r, i) => (
                <tr key={i}>
                  <td>{r.product || 'Unknown'}</td>
                  <td>{r.billing_cycle}</td>
                  <td>{r.count}</td>
                </tr>
              ))}
              {(data.active_by_tier || []).length === 0 && (
                <tr><td colSpan={3} className="no-data-message">No active subscriptions</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel-section">
        <h2 className="section-title">Top Spenders</h2>
        <div className="panel-wrapper">
          <table className="diag-table">
            <thead>
              <tr><th>#</th><th>Discord ID</th><th>Guild ID</th><th>Total Paid</th></tr>
            </thead>
            <tbody>
              {(data.top_spenders || []).map((r, i) => (
                <tr key={i}>
                  <td className="dim">{i + 1}</td>
                  <td>{r.discord_id || 'N/A'}</td>
                  <td>{r.guild_id || 'N/A'}</td>
                  <td>{formatMoney(r.total_paid)}</td>
                </tr>
              ))}
              {(data.top_spenders || []).length === 0 && (
                <tr><td colSpan={4} className="no-data-message">No payment data available</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel-section">
        <h2 className="section-title">Subscriptions by Guild</h2>
        <div className="panel-wrapper">
          <table className="diag-table">
            <thead>
              <tr><th>Guild</th><th>Guild ID</th><th>Product</th><th>Billing</th><th>Status</th></tr>
            </thead>
            <tbody>
              {(data.subscriptions_by_guild || []).map((r, i) => (
                <tr key={i}>
                  <td>{r.guild_name || 'Unknown'}</td>
                  <td>{r.guild_id}</td>
                  <td>{r.product || 'Unknown'}</td>
                  <td>{r.billing_cycle}</td>
                  <td className="ok">{r.status}</td>
                </tr>
              ))}
              {(data.subscriptions_by_guild || []).length === 0 && (
                <tr><td colSpan={5} className="no-data-message">No active guild subscriptions</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel-section">
        <h2 className="section-title">Multi-Server Discount Distribution</h2>
        <div className="panel-wrapper">
          <table className="diag-table">
            <thead>
              <tr><th>Server Count at Purchase</th><th>Discount</th><th>Count</th></tr>
            </thead>
            <tbody>
              {(data.discount_distribution || []).map((r, i) => (
                <tr key={i}>
                  <td>{r.server_count_at_purchase}</td>
                  <td>{r.discount_pct}%</td>
                  <td>{r.count}</td>
                </tr>
              ))}
              {(data.discount_distribution || []).length === 0 && (
                <tr><td colSpan={3} className="no-data-message">No discount data available</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
};

const RateLimitsTab = ({ loading, data }) => {
  if (loading) return <LoadingCard />;
  const entries = data ? Object.entries(data) : [];

  return (
    <div className="panel-section">
      <h2 className="section-title">Rate Limiter (API process)</h2>
      <p className="panel-note">
        Reflects the FastAPI process's own rate limiter instance. The bot process keeps a separate
        instance — check <code>!diag</code> in Discord for bot-side rate limit stats.
      </p>
      <div className="panel-wrapper">
        <table className="diag-table">
          <thead>
            <tr><th>Type</th><th>Total</th><th>Limited</th><th>Timeout</th><th>Current Rate</th></tr>
          </thead>
          <tbody>
            {entries.map(([type, s]) => (
              <tr key={type}>
                <td>{type}</td>
                <td>{s.total}</td>
                <td className={s.limited > 0 ? "bad" : "dim"}>{s.limited}</td>
                <td className={s.timeout > 0 ? "bad" : "dim"}>{s.timeout}</td>
                <td>{s.current_rate_per_sec}/s</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={5} className="no-data-message">No rate limit data yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ---- Main dashboard component ----

const DiagnosticsDashboard = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [apiError, setApiError] = useState(null);

  const [activeTab, setActiveTab] = useState('overview');

  const [loadingOverview, setLoadingOverview] = useState(true);
  const [loadingSyncJobs, setLoadingSyncJobs] = useState(true);
  const [loadingBatches, setLoadingBatches] = useState(true);
  const [loadingBusiness, setLoadingBusiness] = useState(true);
  const [loadingRateLimits, setLoadingRateLimits] = useState(true);

  const [overviewData, setOverviewData] = useState(null);
  const [syncJobsData, setSyncJobsData] = useState(null);
  const [batchesData, setBatchesData] = useState(null);
  const [businessData, setBusinessData] = useState(null);
  const [rateLimitsData, setRateLimitsData] = useState(null);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    setCheckingAuth(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.authenticated && data.user) {
          setIsAuthenticated(true);
          const admin = ADMIN_USERS.includes(String(data.user.id));
          setIsAdmin(admin);
          if (admin) fetchAllTabs();
        }
      }
    } catch (e) {
      console.error('Error checking auth:', e);
      setApiError('Failed to verify access.');
    } finally {
      setCheckingAuth(false);
    }
  };

  const fetchAllTabs = () => {
    fetchOverview();
    fetchSyncJobs();
    fetchBatches();
    fetchBusiness();
    fetchRateLimits();
  };

  const fetchOverview = async () => {
    setLoadingOverview(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/diagnostics/db-size`, {
        credentials: 'include', headers: { 'Accept': 'application/json' }
      });
      if (res.ok) setOverviewData(await res.json());
    } catch (e) { console.error('Error fetching db-size:', e); } finally { setLoadingOverview(false); }
  };

  const fetchSyncJobs = async () => {
    setLoadingSyncJobs(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/diagnostics/sync-jobs`, {
        credentials: 'include', headers: { 'Accept': 'application/json' }
      });
      if (res.ok) setSyncJobsData(await res.json());
    } catch (e) { console.error('Error fetching sync-jobs:', e); } finally { setLoadingSyncJobs(false); }
  };

  const fetchBatches = async () => {
    setLoadingBatches(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/diagnostics/batch-writes`, {
        credentials: 'include', headers: { 'Accept': 'application/json' }
      });
      if (res.ok) setBatchesData(await res.json());
    } catch (e) { console.error('Error fetching batch-writes:', e); } finally { setLoadingBatches(false); }
  };

  const fetchBusiness = async () => {
    setLoadingBusiness(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/diagnostics/business`, {
        credentials: 'include', headers: { 'Accept': 'application/json' }
      });
      if (res.ok) setBusinessData(await res.json());
    } catch (e) { console.error('Error fetching business:', e); } finally { setLoadingBusiness(false); }
  };

  const fetchRateLimits = async () => {
    setLoadingRateLimits(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/diagnostics/rate-limits`, {
        credentials: 'include', headers: { 'Accept': 'application/json' }
      });
      if (res.ok) setRateLimitsData(await res.json());
    } catch (e) { console.error('Error fetching rate-limits:', e); } finally { setLoadingRateLimits(false); }
  };

  const handleRefresh = () => fetchAllTabs();

  const TABS = [
    { key: 'overview', label: 'DB Overview' },
    { key: 'sync', label: 'Sync Jobs' },
    { key: 'batches', label: 'Batch Writes' },
    { key: 'business', label: 'Business' },
    { key: 'ratelimits', label: 'Rate Limits' },
  ];

  const styles = `
    * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }
    html { min-height: 100%; background-color: #0a0a0a; }
    body { min-height: 100vh; margin: 0; padding: 0; background-color: #0a0a0a; color: #ffffff; }

    .dashboard-page { max-width: 100%; margin: 0 auto; background-color: #0a0a0a; color: #ffffff; min-height: 100vh; display: flex; position: relative; }
    .dashboard-main { flex: 1; margin-left: 280px; background-color: #0a0a0a; min-height: 100vh; width: calc(100% - 280px); }
    .dashboard-content { max-width: 1600px; margin: 0 auto; padding: 20px 40px 40px 40px; width: 100%; }

    .diag-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
    .diag-title { font-size: 32px; font-weight: 700; }
    .refresh-button { background-color: #1a1a1a; color: #ffffff; border: 1px solid #2a2a2a; border-radius: 10px; padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
    .refresh-button:hover { border-color: #aa00ff; background-color: #222; }

    .tab-bar { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; border-bottom: 1px solid #1a1a1a; padding-bottom: 0; }
    .tab-button { background: none; border: none; color: #b0b0b0; padding: 12px 20px; font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s ease; }
    .tab-button:hover { color: #ffffff; }
    .tab-button.active { color: #aa00ff; border-bottom-color: #aa00ff; }

    .summary-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 24px; margin-bottom: 32px; }
    .stat-card { background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; padding: 24px; transition: all 0.2s ease; min-height: 110px; display: flex; flex-direction: column; justify-content: center; }
    .stat-card:hover { border-color: #aa00ff; box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2); }
    .stat-card h3 { color: #b0b0b0; font-size: 13px; font-weight: 500; margin: 0 0 10px 0; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-value { color: #ffffff !important; font-size: 32px; font-weight: 700; margin: 0; background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
    .stat-value-small { color: #ffffff; font-size: 16px; font-weight: 600; }

    .section-title { color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; position: relative; display: inline-block; }
    .section-title::after { content: ''; position: absolute; bottom: -6px; left: 0; width: 44px; height: 3px; background-color: #aa00ff; border-radius: 2px; }
    .panel-section { margin-bottom: 36px; }
    .panel-note { color: #888; font-size: 13px; margin: -8px 0 16px 0; }
    .panel-note code { color: #aa00ff; background: #1a1a1a; padding: 2px 6px; border-radius: 4px; }

    .panel-wrapper { background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; overflow: hidden; transition: all 0.2s ease; width: 100%; }
    .panel-wrapper:hover { border-color: #aa00ff; }

    .diag-table { width: 100%; border-collapse: collapse; }
    .diag-table th { text-align: left; color: #b0b0b0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; padding: 14px 20px; border-bottom: 1px solid #1a1a1a; background-color: #0f0f0f; }
    .diag-table td { padding: 12px 20px; font-size: 14px; border-bottom: 1px solid #141414; }
    .diag-table tbody tr:hover { background-color: #131313; }
    .diag-table tbody tr:last-child td { border-bottom: none; }
    .diag-table .dim { color: #666; }
    .diag-table .ok { color: #4ade80; }
    .diag-table .bad { color: #ff5c5c; }

    .no-data-message { text-align: center; padding: 40px; color: #888; font-size: 14px; }
    .no-selection { text-align: center; padding: 100px; background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; color: #b0b0b0; }
    .no-selection h2 { color: #ffffff; margin-bottom: 16px; }
    .loading { text-align: center; padding: 60px; color: #b0b0b0; font-size: 18px; }
    .error-message { text-align: center; padding: 40px; background-color: #0a0a0a; border: 1px solid #ff3333; border-radius: 16px; color: #ff3333; margin-bottom: 20px; }

    @media (max-width: 1024px) {
      .dashboard-main { margin-left: 250px; width: calc(100% - 250px); }
      .dashboard-content { padding: 16px; }
    }
    @media (max-width: 768px) {
      .dashboard-main { margin-left: 0; width: 100%; }
      .dashboard-content { padding: 12px; }
      .summary-stats { grid-template-columns: 1fr; }
      .diag-table { font-size: 12px; }
      .diag-table th, .diag-table td { padding: 10px 12px; }
    }
  `;

  if (checkingAuth) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={false} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading"><LoadingSpinner size="large" text="Checking access..." /></div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={false} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <AccessDenied />
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
        <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={false} />
        <main className="dashboard-main">
          <div className="dashboard-content">
            <div className="diag-header">
              <h1 className="diag-title">Diagnostics</h1>
              <button className="refresh-button" onClick={handleRefresh}>↻ Refresh All</button>
            </div>

            {apiError && <div className="error-message">{apiError}</div>}

            <div className="tab-bar">
              {TABS.map(tab => (
                <button
                  key={tab.key}
                  className={`tab-button ${activeTab === tab.key ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {activeTab === 'overview' && <OverviewTab loading={loadingOverview} data={overviewData} />}
            {activeTab === 'sync' && <SyncJobsTab loading={loadingSyncJobs} data={syncJobsData} />}
            {activeTab === 'batches' && <BatchWritesTab loading={loadingBatches} data={batchesData} />}
            {activeTab === 'business' && <BusinessTab loading={loadingBusiness} data={businessData} />}
            {activeTab === 'ratelimits' && <RateLimitsTab loading={loadingRateLimits} data={rateLimitsData} />}
          </div>
          <Footer />
        </main>
      </div>
      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <DiagnosticsDashboard />
  </React.StrictMode>
);

export default DiagnosticsDashboard;