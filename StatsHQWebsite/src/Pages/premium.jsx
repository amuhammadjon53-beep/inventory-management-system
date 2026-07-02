import React, { useState, useRef, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { Settings, Check, ShoppingCart } from 'lucide-react';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const API_URL = window.location.origin;

const PremiumPage = () => {
  const [cartState, setCartState] = useState({});
  const [animatedButton, setAnimatedButton] = useState(null);
  const [billingCycle, setBillingCycle] = useState('monthly');
  const [loadingButton, setLoadingButton] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  // Check auth status on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await fetch(`${API_URL}/api/auth/status`, {
          credentials: 'include',
          headers: { 'Cache-Control': 'no-cache' }
        });
        if (!response.ok) throw new Error('Auth check failed');
        const data = await response.json();
        if (data.authenticated) {
          setUser(data.user);
        } else {
          setUser(null);
        }
      } catch {
        setUser(null);
      } finally {
        setAuthChecked(true);
      }
    };
    checkAuth();
  }, []);

  const redirectToDiscordLogin = () => {
    const clientId = import.meta.env.VITE_CLIENT_ID || '1481328229909270568';
    const redirectUri = encodeURIComponent(
      import.meta.env.VITE_DISCORD_REDIRECT_URI || 'https://statshq.xyz/api/auth/discord/callback'
    );
    const currentOrigin = encodeURIComponent(window.location.origin);
    window.location.href = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&scope=identify%20guilds%20guilds.members.read&state=${currentOrigin}`;
  };

  const handleAddToCart = async (mod) => {
    // If not logged in, redirect to Discord auth
    if (!user) {
      redirectToDiscordLogin();
      return;
    }

    // Already in cart — do nothing
    if (cartState[mod.id]) return;

    setLoadingButton(mod.id);
    setErrorMessage(null);

    const monthly = mod.monthlyPrice;
    // Yearly = 2 months free: pay for 10 months, covered for 12.
    const yearlyEffectiveMonthly = (monthly * 10) / 12;
    const price = billingCycle === 'monthly' ? monthly : yearlyEffectiveMonthly;

    try {
      const response = await fetch(`${API_URL}/api/cart/add`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_type: 'module',
          item_id: mod.id,
          billing_cycle: billingCycle,
          price_usd: parseFloat(price.toFixed(2))
        })
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || data.detail || 'Failed to add to cart');
      }

      // Success — trigger animation then mark as added
      setAnimatedButton(mod.id);
      setTimeout(() => {
        setCartState(prev => ({ ...prev, [mod.id]: true }));
        setLoadingButton(null);
      }, 150);
      setTimeout(() => setAnimatedButton(null), 1000);

    } catch (err) {
      setLoadingButton(null);
      setErrorMessage({ id: mod.id, text: err.message });
      // Clear error after 4 seconds
      setTimeout(() => setErrorMessage(null), 4000);
    }
  };

  const modules = [
    {
      id: 'optimization-plus',
      name: 'Optimization+',
      monthlyPrice: 2.49,
      icon: <Settings size={28} color="#aa00ff" />,
      features: [
        {
          group: 'Storage',
          items: [
            'Upgraded time limit on data storage: From 6 months to indefinite storing',
            'Can enable simultaneous tracking for more than 4 stat types',
          ],
        },
        {
          group: 'Reset & Sync',
          items: [
            'Access to scheduled resetting of stats',
            'Can set a custom default time period',
            'Can sync multiple stat types simultaneously in the history data sync',
            'Can use the history data sync multiple times on the same server',
          ],
        },
      ],
    },
  ];

  return (
    <>
      <NavBar />

      <div className="premium-page">
        <div className="bg-glow bg-glow-1" />
        <div className="bg-glow bg-glow-2" />

        <div className="premium-container">

          {/* MODULES divider */}
          <div className="modules-divider">
            <div className="divider-line" />
            <span className="modules-label">MODULES</span>
            <div className="divider-line" />
          </div>

          {/* Billing toggle */}
          <div className="billing-toggle">
            <div
              className="toggle-pill"
              style={{ transform: billingCycle === 'monthly' ? 'translateX(0%)' : 'translateX(100%)' }}
            />
            <button
              className={`toggle-btn ${billingCycle === 'monthly' ? 'active' : ''}`}
              onClick={() => setBillingCycle('monthly')}
            >
              Monthly
            </button>
            <button
              className={`toggle-btn yearly-btn ${billingCycle === 'yearly' ? 'active' : ''}`}
              onClick={() => setBillingCycle('yearly')}
            >
              Yearly
              <span className="discount-badge">2 months free</span>
            </button>
          </div>

          {/* Module cards */}
          <div className="modules-grid">
            {modules.map((mod) => {
              const added = cartState[mod.id];
              const isAnimating = animatedButton === mod.id;
              const isLoading = loadingButton === mod.id;
              const hasError = errorMessage?.id === mod.id;

              const monthly = mod.monthlyPrice;
              // Yearly = 2 months free: total billed is monthly * 10,
              // and the displayed "per month" rate is that total spread over 12 months.
              const yearlyTotal = monthly * 10;
              const yearlyEffectiveMonthly = yearlyTotal / 12;

              const displayPrice = billingCycle === 'monthly' ? monthly : yearlyEffectiveMonthly;
              const footnote = billingCycle === 'monthly'
                ? `Billed $${monthly.toFixed(2)} monthly, excluding VAT`
                : `Billed $${yearlyTotal.toFixed(2)} yearly, excluding VAT`;

              return (
                <div key={mod.id} className="module-card">
                  <div className="card-sheen" />

                  <div className="module-header">
                    <div className="module-icon">{mod.icon}</div>
                    <div className="module-title-group">
                      <h2 className="module-name">{mod.name}</h2>
                      <span className="module-price">
                        <span className="price-amount" key={displayPrice}>${displayPrice.toFixed(2)}</span> / month
                      </span>
                    </div>
                  </div>

                  <div className="module-divider" />

                  <div className="module-features">
                    {mod.features.map((group) => (
                      <div key={group.group} className="feature-group">
                        <p className="feature-group-label">{group.group}</p>
                        <ul className="feature-list">
                          {group.items.map((item, i) => (
                            <li key={i} className="feature-item">
                              <span className="feature-bullet">✦</span>
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>

                  <div className="module-divider" />

                  <div className="module-footer">
                    <div className={`cart-action ${added ? 'is-added' : ''} ${isAnimating ? 'is-animating' : ''}`}>
                      <button
                        className={`add-to-cart-btn ${isLoading ? 'is-loading' : ''}`}
                        onClick={() => handleAddToCart(mod)}
                        disabled={added || isLoading}
                      >
                        {isLoading ? (
                          <>
                            <span className="btn-text">Adding...</span>
                            <span className="btn-spinner" />
                          </>
                        ) : !user && authChecked ? (
                          <>
                            <span className="btn-text">Log in to Purchase</span>
                            <ShoppingCart size={18} className="btn-icon" />
                          </>
                        ) : (
                          <>
                            <span className="btn-text">Add to Cart</span>
                            <ShoppingCart size={18} className="btn-icon" />
                          </>
                        )}
                      </button>

                      <div className="added-message-wrapper">
                        <div className="added-message-icon">
                          <Check size={16} strokeWidth={3} />
                        </div>
                        <p className="added-message">
                          Added to{' '}
                          <a href="/My Cart/index.html" className="cart-link">
                            My Cart
                          </a>
                        </p>
                      </div>

                      {/* Flying particles burst */}
                      {isAnimating && (
                        <div className="burst">
                          {Array.from({ length: 8 }).map((_, i) => (
                            <span
                              key={i}
                              className="burst-particle"
                              style={{ '--angle': `${i * 45}deg` }}
                            />
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Error message below button */}
                    {hasError && (
                      <p className="cart-error">{errorMessage.text}</p>
                    )}
                  </div>

                  <p className="module-footnote">{footnote}</p>
                </div>
              );
            })}
          </div>

          {/* Bottom page footnote */}
          <p className="page-footnote">
            All prices are in USD. Multi-server discounts are available for users
            planning to purchase a module for multiple servers.
          </p>

          {/* Learn more side note */}
          <p className="learn-more-note">
            Curious on how the billing system, modules and discounts work? Learn more {' '}
            <a href="/docs/?page=modules" className="learn-more-link">here</a>.
          </p>

        </div>
      </div>

      <Footer />

      <style>{`
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

        .premium-page {
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

        .premium-container {
          max-width: 600px;
          margin: 0 auto;
          padding: 0 40px;
          width: 100%;
          position: relative;
          z-index: 1;
        }

        .modules-divider {
          display: flex;
          align-items: center;
          gap: 24px;
          margin-bottom: 40px;
          width: 100vw;
          position: relative;
          left: 50%;
          right: 50%;
          margin-left: -50vw;
          margin-right: -50vw;
        }

        .divider-line {
          flex: 1;
          height: 1px;
          background: linear-gradient(
            to right,
            transparent 0%,
            rgba(255,255,255,0.06) 8%,
            rgba(255,255,255,0.3) 25%,
            rgba(255,255,255,0.7) 50%,
            rgba(255,255,255,0.3) 75%,
            transparent 100%
          );
        }

        .modules-divider .divider-line:last-child {
          background: linear-gradient(
            to left,
            transparent 0%,
            rgba(255,255,255,0.06) 8%,
            rgba(255,255,255,0.3) 25%,
            rgba(255,255,255,0.7) 50%,
            rgba(255,255,255,0.3) 75%,
            transparent 100%
          );
        }

        .modules-label {
          font-size: 32px;
          font-weight: 800;
          letter-spacing: 8px;
          color: #ffffff;
          text-shadow:
            0 0 12px rgba(255,255,255,0.95),
            0 0 28px rgba(255,255,255,0.6),
            0 0 55px rgba(255,255,255,0.25);
          white-space: nowrap;
          flex-shrink: 0;
        }

        .billing-toggle {
          position: relative;
          display: flex;
          justify-content: center;
          align-items: center;
          gap: 4px;
          margin-bottom: 40px;
          background: #14151c;
          border: 1px solid #2c2f3a;
          border-radius: 12px;
          padding: 6px;
          width: fit-content;
          margin-left: auto;
          margin-right: auto;
        }

        .toggle-pill {
          position: absolute;
          top: 6px;
          left: 6px;
          width: calc(50% - 6px);
          height: calc(100% - 12px);
          background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
          border-radius: 8px;
          box-shadow: 0 4px 16px rgba(170, 0, 255, 0.35);
          transition: transform 0.35s cubic-bezier(0.65, 0, 0.35, 1);
          z-index: 0;
        }

        .toggle-btn {
          position: relative;
          z-index: 1;
          padding: 10px 24px;
          border: none;
          border-radius: 8px;
          background: transparent;
          color: #888b99;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: color 0.25s ease;
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 110px;
          justify-content: center;
          white-space: nowrap;
        }

        .toggle-btn.active {
          color: #ffffff;
        }

        .toggle-btn.yearly-btn {
          padding-left: 72px;
        }

        .discount-badge {
          font-size: 11px;
          font-weight: 700;
          background: rgba(255, 255, 255, 0.18);
          padding: 2px 6px;
          border-radius: 6px;
          color: #ffffff;
          transition: background 0.25s ease, color 0.25s ease;
          white-space: nowrap;
        }

        .toggle-btn:not(.active) .discount-badge {
          background: rgba(170, 0, 255, 0.15);
          color: #aa00ff;
        }

        .modules-grid {
          display: flex;
          flex-direction: column;
          gap: 28px;
          align-items: center;
        }

        .module-card {
          position: relative;
          background-color: #14151c;
          border: 1px solid #2c2f3a;
          border-radius: 16px;
          padding: 32px 24px;
          transition: border-color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
          width: 100%;
          max-width: 520px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .module-card:hover {
          border-color: rgba(170, 0, 255, 0.4);
          box-shadow: 0 8px 40px rgba(170, 0, 255, 0.15);
          transform: translateY(-3px);
        }

        .card-sheen {
          position: absolute;
          top: 0;
          left: -100%;
          width: 60%;
          height: 100%;
          background: linear-gradient(
            100deg,
            transparent 0%,
            rgba(170, 0, 255, 0.06) 50%,
            transparent 100%
          );
          transition: left 0.8s ease;
          pointer-events: none;
        }

        .module-card:hover .card-sheen {
          left: 120%;
        }

        .module-header {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 0;
          position: relative;
          z-index: 1;
        }

        .module-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 52px;
          height: 52px;
          background: rgba(170, 0, 255, 0.1);
          border: 1px solid rgba(170, 0, 255, 0.25);
          border-radius: 12px;
          flex-shrink: 0;
          transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.3s ease;
        }

        .module-card:hover .module-icon {
          transform: rotate(90deg);
          background: rgba(170, 0, 255, 0.18);
        }

        .module-title-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .module-name {
          font-size: 22px;
          font-weight: 700;
          color: #ffffff;
          letter-spacing: 0.3px;
        }

        .module-price {
          font-size: 14px;
          color: #aa00ff;
          font-weight: 500;
          letter-spacing: 0.2px;
        }

        .price-amount {
          display: inline-block;
          animation: priceFade 0.35s ease;
        }

        @keyframes priceFade {
          0% { opacity: 0; transform: translateY(4px); filter: blur(2px); }
          100% { opacity: 1; transform: translateY(0); filter: blur(0); }
        }

        .module-divider {
          height: 1px;
          background-color: #2c2f3a;
          margin: 24px 0;
          position: relative;
          z-index: 1;
        }

        .module-features {
          display: flex;
          flex-direction: column;
          gap: 28px;
          flex: 1;
          position: relative;
          z-index: 1;
        }

        .feature-group-label {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: #aa00ff;
          text-shadow: 0 0 10px rgba(170, 0, 255, 0.45);
          margin-bottom: 14px;
        }

        .feature-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .feature-item {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          color: #b0b0b0;
          font-size: 14px;
          line-height: 1.6;
          transition: color 0.2s ease, transform 0.2s ease;
        }

        .feature-item:hover {
          color: #e0e0e0;
          transform: translateX(2px);
        }

        .feature-bullet {
          color: #aa00ff;
          font-size: 11px;
          margin-top: 4px;
          flex-shrink: 0;
          opacity: 0.85;
        }

        .module-footer {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 8px;
          position: relative;
          z-index: 1;
        }

        .cart-action {
          position: relative;
          width: 100%;
          min-height: 48px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .add-to-cart-btn {
          position: relative;
          padding: 12px 28px;
          background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
          color: #ffffff;
          font-size: 15px;
          font-weight: 600;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          overflow: hidden;
          letter-spacing: 0.3px;
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          justify-content: center;
          transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1),
                      box-shadow 0.25s ease,
                      background 0.25s ease,
                      opacity 0.25s ease;
        }

        .add-to-cart-btn:hover:not(:disabled) {
          transform: translateY(-2px) scale(1.01);
          box-shadow: 0 6px 24px rgba(170, 0, 255, 0.45);
          background: linear-gradient(135deg, #bb33ff 0%, #9900ee 100%);
        }

        .add-to-cart-btn:active:not(:disabled) {
          transform: translateY(0) scale(0.98);
        }

        .add-to-cart-btn:disabled:not(.is-loading) {
          cursor: not-allowed;
          opacity: 0.7;
        }

        .add-to-cart-btn.is-loading {
          cursor: wait;
          opacity: 0.85;
        }

        .btn-icon {
          transition: transform 0.3s ease;
        }

        .add-to-cart-btn:hover .btn-icon {
          transform: translateX(3px) rotate(-8deg);
        }

        /* Spinner for loading state */
        .btn-spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: #ffffff;
          border-radius: 50%;
          animation: spin 0.7s linear infinite;
          flex-shrink: 0;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        /* When clicked: punch + fly out */
        .cart-action.is-animating .add-to-cart-btn {
          animation: btnLaunch 0.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }

        @keyframes btnLaunch {
          0% { transform: scale(1) translateY(0); opacity: 1; }
          30% { transform: scale(1.06) translateY(0); opacity: 1; }
          60% { transform: scale(0.85) translateY(-14px); opacity: 0.4; }
          100% { transform: scale(0.7) translateY(-22px); opacity: 0; }
        }

        .added-message-wrapper {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          opacity: 0;
          transform: scale(0.85) translateY(10px);
          pointer-events: none;
          transition: opacity 0.3s ease, transform 0.3s ease;
        }

        .cart-action.is-added .added-message-wrapper {
          opacity: 1;
          transform: scale(1) translateY(0);
          transition: opacity 0.4s cubic-bezier(0.34, 1.56, 0.64, 1),
                      transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .cart-action.is-added .add-to-cart-btn {
          display: none;
        }

        .added-message-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          background: linear-gradient(135deg, #aa00ff, #7700cc);
          border-radius: 50%;
          color: white;
          flex-shrink: 0;
          box-shadow: 0 0 0 0 rgba(170, 0, 255, 0.5);
        }

        .cart-action.is-added .added-message-icon {
          animation: checkPulse 0.6s ease-out 0.3s;
        }

        @keyframes checkPulse {
          0% { transform: scale(0.4); box-shadow: 0 0 0 0 rgba(170, 0, 255, 0.6); }
          50% { transform: scale(1.15); box-shadow: 0 0 0 10px rgba(170, 0, 255, 0); }
          100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(170, 0, 255, 0); }
        }

        .added-message {
          font-size: 15px;
          font-weight: 500;
          color: #b0b0b0;
          margin: 0;
        }

        .cart-link {
          color: #aa00ff;
          text-decoration: none;
          font-weight: 600;
          transition: text-shadow 0.2s ease, color 0.2s ease;
        }

        .cart-link:hover {
          color: #bb33ff;
          text-shadow: 0 0 10px rgba(170, 0, 255, 0.5);
          text-decoration: underline;
        }

        /* Error message */
        .cart-error {
          font-size: 12px;
          color: #ff6b6b;
          text-align: center;
          margin: 0;
          animation: fadeIn 0.2s ease;
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* Particle burst on click */
        .burst {
          position: absolute;
          inset: 0;
          pointer-events: none;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .burst-particle {
          position: absolute;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #aa00ff;
          box-shadow: 0 0 8px rgba(170, 0, 255, 0.8);
          opacity: 0;
          animation: particleFly 0.7s ease-out forwards;
          transform: rotate(var(--angle));
        }

        @keyframes particleFly {
          0% {
            opacity: 1;
            transform: rotate(var(--angle)) translateX(0) scale(1);
          }
          100% {
            opacity: 0;
            transform: rotate(var(--angle)) translateX(60px) scale(0.3);
          }
        }

        .module-footnote {
          margin-top: 16px;
          font-size: 12px;
          color: #6e7180;
          text-align: center;
          font-style: italic;
          position: relative;
          z-index: 1;
        }

        .page-footnote {
          margin-top: 48px;
          font-size: 13px;
          color: #6e7180;
          text-align: center;
          line-height: 1.6;
          max-width: 480px;
          margin-left: auto;
          margin-right: auto;
        }

        .learn-more-note {
          margin-top: 20px;
          font-size: 13px;
          color: #6e7180;
          text-align: center;
          line-height: 1.6;
        }

        .learn-more-link {
          color: #aa00ff;
          text-decoration: none;
          font-weight: 600;
          transition: text-shadow 0.2s ease, color 0.2s ease;
        }

        .learn-more-link:hover {
          color: #bb33ff;
          text-shadow: 0 0 10px rgba(170, 0, 255, 0.5);
          text-decoration: underline;
        }

        /* ── Responsive ── */
        @media (max-width: 768px) {
          .premium-page { padding: 40px 0 60px; }
          .premium-container { padding: 0 20px; max-width: 100%; }
          .modules-divider { gap: 16px; }
          .modules-label { font-size: 24px; letter-spacing: 6px; }
          .module-card { padding: 28px 20px; max-width: 100%; }
          .module-name { font-size: 19px; }
        }

        @media (max-width: 480px) {
          .modules-label { font-size: 18px; letter-spacing: 4px; }
          .module-header { gap: 12px; }
          .module-icon { width: 44px; height: 44px; }
          .module-name { font-size: 17px; }
          .feature-item { font-size: 13px; }
          .modules-divider { gap: 12px; }
          .billing-toggle { width: 100%; }
          .toggle-btn { flex: 1; min-width: 0; }
        }
      `}</style>
    </>
  );
};

const root = createRoot(document.getElementById('app'));
root.render(
  <React.StrictMode>
    <PremiumPage />
  </React.StrictMode>
);

export default PremiumPage;