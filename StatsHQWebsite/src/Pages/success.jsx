// checkout-success/index.html
import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { CheckCircle, RefreshCw, Server, Zap } from 'lucide-react';
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

// ─── Main page ──────────────────────────────────────────────────────────────────
const CheckoutSuccessPage = () => {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showLoginOverlay, setShowLoginOverlay] = useState(false);

  const [pollingState, setPollingState] = useState('loading'); // 'loading' | 'success' | 'timeout'
  const [foundSubscription, setFoundSubscription] = useState(null);
  const [pollingAttempts, setPollingAttempts] = useState(0);
  const [error, setError] = useState(null);

  const hasFetchedRef = useRef(false);
  const pollingTimerRef = useRef(null);
  const pollingTimeoutRef = useRef(null);
  const MAX_ATTEMPTS = 10;
  const POLL_INTERVAL = 2000;

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

  // ─── Poll for subscription ──────────────────────────────────────────────────
  useEffect(() => {
    if (!user || hasFetchedRef.current) return;
    hasFetchedRef.current = true;
    startPolling();
  }, [user]);

  const startPolling = () => {
    let attempts = 0;
    setPollingAttempts(0);

    const poll = async () => {
      attempts++;
      setPollingAttempts(attempts);

      try {
        const res = await fetch(`${API_URL}/api/paddle/subscriptions/user/me`, {
          credentials: 'include',
          headers: { 'Cache-Control': 'no-cache' },
        });

        if (!res.ok) {
          throw new Error(`Failed to fetch subscriptions: ${res.status}`);
        }

        const data = await res.json();
        const subscriptions = data || [];

        // Check for any subscription created in the last 5 minutes
        const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
        const recentSub = subscriptions.find(sub => {
          const createdAt = new Date(sub.created_at);
          return createdAt > fiveMinutesAgo;
        });

        if (recentSub) {
          // Found it!
          setFoundSubscription(recentSub);
          setPollingState('success');
          clearInterval(pollingTimerRef.current);
          clearTimeout(pollingTimeoutRef.current);
          return;
        }

        // If we've reached max attempts, stop polling
        if (attempts >= MAX_ATTEMPTS) {
          setPollingState('timeout');
          clearInterval(pollingTimerRef.current);
          clearTimeout(pollingTimeoutRef.current);
          return;
        }

      } catch (err) {
        // Network failure: just log and continue polling
        console.error('Polling error:', err);
        // Don't stop polling on network errors
      }
    };

    // Poll immediately, then every 2 seconds
    poll();
    pollingTimerRef.current = setInterval(poll, POLL_INTERVAL);

    // Set a timeout to stop polling after 20 seconds
    pollingTimeoutRef.current = setTimeout(() => {
      if (pollingState === 'loading') {
        setPollingState('timeout');
        clearInterval(pollingTimerRef.current);
      }
    }, MAX_ATTEMPTS * POLL_INTERVAL);

    // Cleanup
    return () => {
      clearInterval(pollingTimerRef.current);
      clearTimeout(pollingTimeoutRef.current);
    };
  };

  const handleManualRefresh = () => {
    setPollingState('loading');
    setPollingAttempts(0);
    setError(null);
    startPolling();
  };

  const handleLogin = () => {
    window.location.href = `${API_URL}/api/auth/discord?returnTo=${encodeURIComponent(window.location.href)}`;
  };

  // ─── Get module display name ──────────────────────────────────────────────
  const getModuleName = (moduleKey) => {
    return MODULE_INFO[moduleKey]?.name || moduleKey || 'Unknown Module';
  };

  const getServerName = (guildName, guildId) => {
    return guildName || guildId || 'Unknown Server';
  };

  // ─── Login overlay ─────────────────────────────────────────────────────────
  if (authChecked && showLoginOverlay) {
    return (
      <>
        <NavBar />
        <div className="checkout-page">
          <div className="login-overlay">
            <div className="login-modal">
              <div className="login-icon">🔒</div>
              <h2>Sign in to confirm your subscription</h2>
              <p>Log in with Discord to see your subscription status and manage your account.</p>
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
        <div className="checkout-page">
          <div className="state-container"><div className="spinner" /></div>
        </div>
        <Footer />
        <style>{allStyles}</style>
      </>
    );
  }

  // ─── Render states ─────────────────────────────────────────────────────────
  const renderLoading = () => (
    <div className="state-container">
      <div className="spinner" />
      <p className="state-text">Finalizing your subscription...</p>
      <p className="state-subtext">Please wait while we activate your subscription</p>
    </div>
  );

  const renderSuccess = () => {
    const moduleName = getModuleName(foundSubscription?.module_key);
    const serverName = getServerName(
      foundSubscription?.guild_name,
      foundSubscription?.guild_id
    );

    return (
      <div className="success-container">
        <div className="success-icon-wrapper">
          <div className="success-icon-bg">
            <CheckCircle size={64} color="#00e07a" strokeWidth={2} />
          </div>
          <div className="success-ring" />
        </div>

        <h2 className="success-title">You're all set!</h2>
        <p className="success-message">
          Your subscription to <strong>{moduleName}</strong> has been activated.
        </p>

        <div className="success-details">
          <div className="detail-item">
            <span className="detail-label">Module</span>
            <span className="detail-value">{moduleName}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Server</span>
            <div className="detail-value server-info">
              <Server size={14} color="#888b99" />
              <span>{serverName}</span>
            </div>
          </div>
          {foundSubscription?.billing_cycle && (
            <div className="detail-item">
              <span className="detail-label">Billing</span>
              <span className="detail-value">
                {foundSubscription.billing_cycle === 'yearly' ? 'Yearly' : 'Monthly'}
              </span>
            </div>
          )}
          {foundSubscription?.created_at && (
            <div className="detail-item">
              <span className="detail-label">Started</span>
              <span className="detail-value">
                {new Date(foundSubscription.created_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
            </div>
          )}
        </div>

        <div className="success-actions">
          <a href="/MySubscriptions/index.html" className="primary-btn">
            Go to My Subscriptions
          </a>
          <a href="/dashboard/index.html" className="secondary-btn">
            Go to Dashboard
          </a>
        </div>
      </div>
    );
  };

  const renderTimeout = () => (
    <div className="timeout-container">
      <div className="timeout-icon-wrapper">
        <RefreshCw size={48} color="#aa00ff" strokeWidth={1.5} />
      </div>

      <h2 className="timeout-title">Payment Successful</h2>
      <p className="timeout-message">
        Your payment was successful and your subscription is being set up — 
        this can take up to a minute. You'll see it appear on your 
        <strong> My Subscriptions</strong> page shortly.
      </p>

      <div className="timeout-actions">
        <button className="primary-btn" onClick={handleManualRefresh}>
          <RefreshCw size={16} />
          <span>Check Again</span>
        </button>
        <a href="/MySubscriptions/index.html" className="secondary-btn">
          Go to My Subscriptions
        </a>
      </div>

      <p className="timeout-note">
        Attempt {pollingAttempts} of {MAX_ATTEMPTS} completed
      </p>
    </div>
  );

  return (
    <>
      <NavBar />
      <div className="checkout-page">
        <div className="bg-glow bg-glow-1" />
        <div className="bg-glow bg-glow-2" />

        <div className="checkout-container">
          {error && <div className="global-error">{error}</div>}

          {pollingState === 'loading' && renderLoading()}
          {pollingState === 'success' && renderSuccess()}
          {pollingState === 'timeout' && renderTimeout()}
        </div>
      </div>
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

  * { 
    margin: 0; 
    padding: 0; 
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; 
  }

  html, body, #app { 
    min-height: 100vh; 
    background-color: #0a0a0a; 
    color: #ffffff; 
  }

  .checkout-page {
    background-color: #0a0a0a;
    min-height: calc(100vh - 80px);
    padding: 60px 0 80px;
    display: flex;
    justify-content: center;
    position: relative;
    overflow: hidden;
  }

  .bg-glow { 
    position: absolute; 
    border-radius: 50%; 
    filter: blur(120px); 
    pointer-events: none; 
    opacity: 0.35; 
  }
  .bg-glow-1 { 
    width: 500px; 
    height: 500px; 
    background: #aa00ff; 
    top: -200px; 
    left: -150px; 
  }
  .bg-glow-2 { 
    width: 450px; 
    height: 450px; 
    background: #5500aa; 
    bottom: -150px; 
    right: -150px; 
  }

  .checkout-container {
    max-width: 640px;
    margin: 0 auto;
    padding: 0 40px;
    width: 100%;
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }

  .global-error {
    background: rgba(255,107,107,0.1);
    border: 1px solid #ff6b6b;
    color: #ff8888;
    padding: 14px 20px;
    border-radius: 12px;
    font-size: 14px;
    margin-bottom: 28px;
    text-align: center;
    width: 100%;
    max-width: 520px;
  }

  /* ── Loading state ── */
  .state-container {
    display: flex; 
    flex-direction: column; 
    align-items: center; 
    justify-content: center;
    min-height: 400px;
    width: 100%; 
    gap: 20px; 
    padding: 20px;
  }

  .spinner {
    width: 48px; 
    height: 48px;
    border: 4px solid #232323;
    border-top-color: #aa00ff; 
    border-right-color: #aa00ff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin { 
    to { transform: rotate(360deg); } 
  }

  .state-text { 
    color: #e0e0e0; 
    font-size: 18px; 
    font-weight: 600;
    letter-spacing: 0.3px;
  }

  .state-subtext {
    color: #888b99;
    font-size: 14px;
    margin-top: -8px;
  }

  /* ── Success state ── */
  .success-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    width: 100%;
    max-width: 520px;
    padding: 20px 0;
  }

  .success-icon-wrapper {
    position: relative;
    margin-bottom: 28px;
  }

  .success-icon-bg {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100px;
    height: 100px;
    background: rgba(0,224,122,0.08);
    border: 2px solid rgba(0,224,122,0.3);
    border-radius: 50%;
    position: relative;
    z-index: 2;
  }

  .success-ring {
    position: absolute;
    top: -8px;
    left: -8px;
    right: -8px;
    bottom: -8px;
    border-radius: 50%;
    border: 2px solid rgba(0,224,122,0.15);
    animation: ringPulse 2s ease-in-out infinite;
  }

  @keyframes ringPulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.15); opacity: 0.4; }
  }

  .success-title {
    font-size: 32px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 12px;
    background: linear-gradient(135deg, #ffffff, #00e07a);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .success-message {
    font-size: 16px;
    color: #b0b0b0;
    line-height: 1.6;
    margin-bottom: 32px;
  }

  .success-message strong {
    color: #ffffff;
    font-weight: 600;
  }

  .success-details {
    background: #14151c;
    border: 1px solid #2c2f3a;
    border-radius: 16px;
    padding: 20px 24px;
    width: 100%;
    margin-bottom: 32px;
  }

  .detail-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid rgba(44,47,58,0.5);
  }

  .detail-item:last-child {
    border-bottom: none;
  }

  .detail-label {
    font-size: 13px;
    color: #888b99;
    font-weight: 500;
  }

  .detail-value {
    font-size: 14px;
    color: #e0e0e0;
    font-weight: 500;
  }

  .detail-value.server-info {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .success-actions {
    display: flex;
    gap: 12px;
    width: 100%;
    flex-wrap: wrap;
    justify-content: center;
  }

  .primary-btn, .secondary-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 14px 28px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 700;
    text-decoration: none;
    transition: all 0.25s cubic-bezier(0.34,1.56,0.64,1);
    min-width: 200px;
    border: none;
    cursor: pointer;
  }

  .primary-btn {
    background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
    color: #ffffff;
    box-shadow: 0 4px 16px rgba(170,0,255,0.3);
  }

  .primary-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 28px rgba(170,0,255,0.45);
  }

  .secondary-btn {
    background: transparent;
    color: #d0d0d0;
    border: 1px solid #2c2f3a;
  }

  .secondary-btn:hover {
    border-color: rgba(170,0,255,0.4);
    color: #ffffff;
    background: rgba(170,0,255,0.05);
  }

  /* ── Timeout state ── */
  .timeout-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    width: 100%;
    max-width: 520px;
    padding: 20px 0;
  }

  .timeout-icon-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 80px;
    height: 80px;
    background: rgba(170,0,255,0.08);
    border: 2px solid rgba(170,0,255,0.3);
    border-radius: 50%;
    margin-bottom: 28px;
  }

  .timeout-title {
    font-size: 28px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 12px;
  }

  .timeout-message {
    font-size: 16px;
    color: #b0b0b0;
    line-height: 1.8;
    margin-bottom: 32px;
  }

  .timeout-message strong {
    color: #ffffff;
    font-weight: 600;
  }

  .timeout-actions {
    display: flex;
    gap: 12px;
    width: 100%;
    flex-wrap: wrap;
    justify-content: center;
  }

  .timeout-note {
    font-size: 13px;
    color: #555870;
    margin-top: 20px;
  }

  /* ── Login overlay ── */
  .login-overlay {
    position: relative; 
    min-height: calc(100vh - 200px); 
    width: 100%;
    display: flex; 
    align-items: center; 
    justify-content: center;
    padding: 40px 20px; 
    z-index: 10;
  }

  .login-modal {
    background: rgba(10,10,10,0.95); 
    backdrop-filter: blur(20px);
    border: 2px solid #aa00ff; 
    border-radius: 40px;
    padding: 60px 40px; 
    max-width: 500px; 
    width: 100%;
    text-align: center; 
    box-shadow: 0 30px 60px rgba(170,0,255,0.3);
    animation: modalAppear 0.5s ease; 
    position: relative; 
    z-index: 10;
  }

  @keyframes modalAppear {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .login-icon { 
    font-size: 80px; 
    margin-bottom: 30px; 
    animation: pulse 2s infinite; 
  }

  @keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
  }

  .login-modal h2 {
    font-size: 32px;
    font-weight: 800;
    margin-bottom: 16px;
    background: linear-gradient(135deg, #ffffff, #aa00ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .login-modal p { 
    color: #b0b0b0; 
    font-size: 16px; 
    margin-bottom: 32px; 
    line-height: 1.6; 
  }

  .login-button {
    background-image: linear-gradient(135deg, #aa00ff, #ff00aa);
    color: white; 
    border: none; 
    padding: 10px 28px; 
    border-radius: 50px;
    font-size: 14px; 
    font-weight: 600; 
    cursor: pointer;
    transition: all 0.2s ease; 
    box-shadow: 0 4px 12px rgba(170,0,255,0.3);
  }

  .login-button:hover { 
    transform: translateY(-2px); 
    box-shadow: 0 8px 20px rgba(170,0,255,0.4); 
  }

  /* ── Responsive ── */
  @media (max-width: 768px) {
    .checkout-page { padding: 40px 0 60px; }
    .checkout-container { padding: 0 20px; max-width: 100%; }
    
    .success-title { font-size: 26px; }
    .success-icon-bg { width: 80px; height: 80px; }
    .success-icon-bg svg { width: 48px; height: 48px; }
    
    .primary-btn, .secondary-btn {
      min-width: 160px;
      padding: 12px 20px;
      font-size: 13px;
    }

    .login-modal {
      padding: 40px 20px;
    }

    .login-modal h2 {
      font-size: 26px;
    }

    .login-icon {
      font-size: 60px;
    }
  }

  @media (max-width: 480px) {
    .success-title { font-size: 22px; }
    .success-message { font-size: 14px; }
    .success-details { padding: 16px 18px; }
    .detail-item { padding: 6px 0; }
    .detail-label { font-size: 12px; }
    .detail-value { font-size: 13px; }
    
    .primary-btn, .secondary-btn {
      min-width: 140px;
      padding: 10px 16px;
      font-size: 12px;
      width: 100%;
    }

    .timeout-title { font-size: 22px; }
    .timeout-message { font-size: 14px; }
  }
`;

const root = createRoot(document.getElementById('app'));
root.render(
  <React.StrictMode>
    <CheckoutSuccessPage />
  </React.StrictMode>
);

export default CheckoutSuccessPage;