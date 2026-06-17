import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Settings } from 'lucide-react';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const PremiumPage = () => {
  const [billingCycle, setBillingCycle] = useState('monthly');

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

  const YEARLY_DISCOUNT = 0.17;

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
              className={`toggle-btn ${billingCycle === 'yearly' ? 'active' : ''}`}
              onClick={() => setBillingCycle('yearly')}
            >
              Yearly
              <span className="discount-badge">-17%</span>
            </button>
          </div>

          {/* Module cards */}
          <div className="modules-grid">
            {modules.map((mod) => {
              const monthly = mod.monthlyPrice;
              const yearlyEffectiveMonthly = monthly * (1 - YEARLY_DISCOUNT);
              const yearlyTotal = yearlyEffectiveMonthly * 10;

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
                    <button className="coming-soon-btn" disabled>
                      <span className="coming-soon-dots">
                        <span /><span /><span />
                      </span>
                      Coming Soon
                    </button>
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
        }

        .toggle-btn.active {
          color: #ffffff;
        }

        .discount-badge {
          font-size: 11px;
          font-weight: 700;
          background: rgba(255, 255, 255, 0.18);
          padding: 2px 6px;
          border-radius: 6px;
          color: #ffffff;
          transition: background 0.25s ease, color 0.25s ease;
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

        /* ── Coming Soon button ── */
        .coming-soon-btn {
          width: 100%;
          padding: 12px 28px;
          background: #1a1a24;
          border: 1px solid #2c2f3a;
          border-radius: 8px;
          color: #555870;
          font-size: 15px;
          font-weight: 600;
          letter-spacing: 0.3px;
          cursor: not-allowed;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
        }

        .coming-soon-dots {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .coming-soon-dots span {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #3a3d50;
          animation: dotPulse 1.4s ease-in-out infinite;
        }

        .coming-soon-dots span:nth-child(1) { animation-delay: 0s; }
        .coming-soon-dots span:nth-child(2) { animation-delay: 0.2s; }
        .coming-soon-dots span:nth-child(3) { animation-delay: 0.4s; }

        @keyframes dotPulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.85); }
          40% { opacity: 1; transform: scale(1.15); background: #aa00ff; }
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