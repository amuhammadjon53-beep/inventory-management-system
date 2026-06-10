import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const PremiumPage = () => {
  const [cartState, setCartState] = useState({}); // { moduleId: boolean }
  const [animatedButton, setAnimatedButton] = useState(null);

  const handleAddToCart = (moduleId) => {
    setAnimatedButton(moduleId);
    setCartState(prev => ({ ...prev, [moduleId]: true }));
    
    // Reset animation after it completes
    setTimeout(() => {
      setAnimatedButton(null);
    }, 600);
  };

  const modules = [
    {
      id: 'optimization-plus',
      name: 'Optimization+',
      price: '$2.49',
      iconPath: (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#aa00ff"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z" />
          <path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" />
          <path d="M12 2v2" />
          <path d="M12 20v2" />
          <path d="m4.93 4.93 1.41 1.41" />
          <path d="m17.66 17.66 1.41 1.41" />
          <path d="M2 12h2" />
          <path d="M20 12h2" />
          <path d="m6.34 17.66-1.41 1.41" />
          <path d="m19.07 4.93-1.41 1.41" />
        </svg>
      ),
      features: [
        {
          group: 'Storage',
          items: [
            'Upgraded time limit on data storage: From 6 months to indefinite storing',
            'Can enable tracking for more than 4 stat types',
          ],
        },
        {
          group: 'Reset & Sync',
          items: [
            'Access to scheduled resetting of stats',
            'Can set a custom time period',
            'Can sync multiple stat types at the same time in the history data sync',
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
        <div className="premium-container">

          {/* MODULES divider */}
          <div className="modules-divider">
            <div className="divider-line" />
            <span className="modules-label">MODULES</span>
            <div className="divider-line" />
          </div>

          {/* Module cards */}
          <div className="modules-grid">
            {modules.map((mod) => {
              const added = cartState[mod.id];
              const isAnimating = animatedButton === mod.id;
              
              return (
                <div key={mod.id} className="module-card">
                  {/* Card header */}
                  <div className="module-header">
                    <div className="module-icon">{mod.iconPath}</div>
                    <div className="module-title-group">
                      <h2 className="module-name">{mod.name}</h2>
                      <span className="module-price">{mod.price} / month</span>
                    </div>
                  </div>

                  <div className="module-divider" />

                  {/* Feature groups */}
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

                  {/* Add to cart */}
                  <div className="module-footer">
                    {added ? (
                      <div className="added-message-wrapper">
                        <div className="added-message-icon">✓</div>
                        <p className="added-message">
                          Added to{' '}
                          <a href="/My Cart/index.html" className="cart-link">
                            My Cart
                          </a>
                        </p>
                      </div>
                    ) : (
                      <button
                        className={`add-to-cart-btn ${isAnimating ? 'animate' : ''}`}
                        onClick={() => handleAddToCart(mod.id)}
                      >
                        <span className="btn-text">Add to Cart</span>
                        <span className="btn-icon">🛒</span>
                        <div className="btn-ripple"></div>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

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

        /* ── Page wrapper ── */
        .premium-page {
          background-color: #0a0a0a;
          min-height: calc(100vh - 80px);
          padding: 60px 0 80px;
          display: flex;
          justify-content: center;
        }

        .premium-container {
          max-width: 600px;
          margin: 0 auto;
          padding: 0 40px;
          width: 100%;
        }

        /* ── MODULES divider ── */
        .modules-divider {
          display: flex;
          align-items: center;
          gap: 24px;
          margin-bottom: 56px;
          width: 100%;
        }

        .divider-line {
          flex: 1;
          height: 2px;
          /* Extended fade - starts fading at 5% and stays bright until 95% */
          background: linear-gradient(
            to var(--dir, right),
            transparent 0%,
            rgba(255,255,255,0.08) 5%,
            rgba(255,255,255,0.4) 15%,
            rgba(255,255,255,0.85) 40%,
            rgba(255,255,255,0.95) 60%,
            rgba(255,255,255,0.85) 85%,
            rgba(255,255,255,0.4) 95%,
            transparent 100%
          );
          border-radius: 2px;
        }

        /* Left line */
        .modules-divider .divider-line:first-child {
          --dir: right;
        }

        /* Right line */
        .modules-divider .divider-line:last-child {
          background: linear-gradient(
            to left,
            transparent 0%,
            rgba(255,255,255,0.08) 5%,
            rgba(255,255,255,0.4) 15%,
            rgba(255,255,255,0.85) 40%,
            rgba(255,255,255,0.95) 60%,
            rgba(255,255,255,0.85) 85%,
            rgba(255,255,255,0.4) 95%,
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

        /* ── Module grid ── */
        .modules-grid {
          display: flex;
          flex-direction: column;
          gap: 28px;
          align-items: center;
        }

        /* ── Module card - Made taller and slimmer ── */
        .module-card {
          background-color: #1a1c24;
          border: 1px solid #2c2f3a;
          border-radius: 16px;
          padding: 32px 24px;
          transition: border-color 0.25s ease, box-shadow 0.25s ease;
          width: 100%;
          max-width: 520px;
          display: flex;
          flex-direction: column;
        }

        .module-card:hover {
          border-color: rgba(170, 0, 255, 0.45);
          box-shadow: 0 6px 32px rgba(170, 0, 255, 0.12);
        }

        /* Header */
        .module-header {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 0;
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

        /* Divider inside card */
        .module-divider {
          height: 1px;
          background-color: #2c2f3a;
          margin: 24px 0;
        }

        /* Features - Made more spacious vertically */
        .module-features {
          display: flex;
          flex-direction: column;
          gap: 28px;
          flex: 1;
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
        }

        .feature-bullet {
          color: #aa00ff;
          font-size: 11px;
          margin-top: 4px;
          flex-shrink: 0;
          opacity: 0.85;
        }

        /* Footer */
        .module-footer {
          display: flex;
          align-items: center;
          margin-top: 8px;
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
          transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
          letter-spacing: 0.3px;
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          justify-content: center;
        }

        .btn-text {
          position: relative;
          z-index: 1;
        }

        .btn-icon {
          position: relative;
          z-index: 1;
          font-size: 18px;
          transition: transform 0.3s ease;
        }

        .add-to-cart-btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(170, 0, 255, 0.4);
          background: linear-gradient(135deg, #bb33ff 0%, #9900ee 100%);
        }

        .add-to-cart-btn:hover .btn-icon {
          transform: translateX(3px);
        }

        .add-to-cart-btn:active {
          transform: translateY(0);
        }

        /* Ripple effect */
        .btn-ripple {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 0;
          height: 0;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.3);
          transform: translate(-50%, -50%);
          transition: width 0.6s ease-out, height 0.6s ease-out;
          pointer-events: none;
        }

        .add-to-cart-btn.animate .btn-ripple {
          width: 300px;
          height: 300px;
        }

        /* Animation for button click */
        .add-to-cart-btn.animate {
          animation: buttonPop 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }

        @keyframes buttonPop {
          0% {
            transform: scale(1);
          }
          50% {
            transform: scale(0.95);
          }
          100% {
            transform: scale(1);
          }
        }

        /* Added message animation */
        .added-message-wrapper {
          display: flex;
          align-items: center;
          gap: 12px;
          animation: slideInCart 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
          width: 100%;
          justify-content: center;
        }

        .added-message-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          background: linear-gradient(135deg, #aa00ff, #7700cc);
          border-radius: 50%;
          font-size: 20px;
          font-weight: bold;
          color: white;
          animation: checkSpin 0.5s ease-out;
        }

        @keyframes slideInCart {
          0% {
            opacity: 0;
            transform: translateX(-20px);
          }
          100% {
            opacity: 1;
            transform: translateX(0);
          }
        }

        @keyframes checkSpin {
          0% {
            transform: scale(0) rotate(-180deg);
            opacity: 0;
          }
          100% {
            transform: scale(1) rotate(0);
            opacity: 1;
          }
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

        /* ── Responsive ── */
        @media (max-width: 768px) {
          .premium-page {
            padding: 40px 0 60px;
          }

          .premium-container {
            padding: 0 20px;
            max-width: 100%;
          }

          .modules-label {
            font-size: 24px;
            letter-spacing: 6px;
          }

          .module-card {
            padding: 28px 20px;
            max-width: 100%;
          }

          .module-name {
            font-size: 19px;
          }
          
          .modules-divider {
            gap: 16px;
          }
        }

        @media (max-width: 480px) {
          .modules-label {
            font-size: 18px;
            letter-spacing: 4px;
          }

          .module-header {
            gap: 12px;
          }

          .module-icon {
            width: 44px;
            height: 44px;
          }

          .module-name {
            font-size: 17px;
          }

          .feature-item {
            font-size: 13px;
          }

          .add-to-cart-btn {
            width: 100%;
            justify-content: center;
          }
          
          .modules-divider {
            gap: 12px;
          }
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