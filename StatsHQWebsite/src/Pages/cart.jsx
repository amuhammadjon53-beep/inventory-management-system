import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Trash2, ChevronDown, ShoppingCart, Server } from 'lucide-react';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const API_URL = window.location.origin;

const MODULE_INFO = {
  'optimization-plus': {
    name: 'Optimization+',
    icon: <ShoppingCart size={28} color="#aa00ff" />,
  },
};

const YEARLY_MULTIPLIER = 10;

const MyCartPage = () => {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showLoginOverlay, setShowLoginOverlay] = useState(false);

  const [cart, setCart] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [servers, setServers] = useState([]);
  const [serversLoading, setServersLoading] = useState(true);

  const [openDropdown, setOpenDropdown] = useState(null);
  const [pendingActions, setPendingActions] = useState({});
  const [removingItem, setRemovingItem] = useState(null);

  const hasFetchedRef = useRef(false);

  // ─── Auth check ───
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

  // ─── Fetch cart + servers once authenticated ───
  useEffect(() => {
    if (!user || hasFetchedRef.current) return;
    hasFetchedRef.current = true;
    fetchCart();
    fetchServers();
  }, [user]);

  const fetchCart = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/cart`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' }
      });
      if (!response.ok) throw new Error(`Failed to fetch cart: ${response.status}`);
      const data = await response.json();
      setCart(data.cart || []);
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const fetchServers = async () => {
    setServersLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/user/servers`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' }
      });
      if (!response.ok) throw new Error(`Failed to fetch servers: ${response.status}`);
      const data = await response.json();
      const processed = data.map(server => ({
        ...server,
        id: String(server.id),
        iconUrl: server.icon
          ? `https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png?size=64`
          : 'https://cdn.discordapp.com/embed/avatars/0.png'
      }));
      setServers(processed);
    } catch (err) {
      console.error('Error fetching servers:', err);
    } finally {
      setServersLoading(false);
    }
  };

  const handleLogin = () => {
    window.location.href = `${API_URL}/api/auth/discord?returnTo=${encodeURIComponent(window.location.href)}`;
  };

  const getAssignedGuildIds = (item) => {
    return (item.assigned_servers || [])
      .map(s => String(s.guild_id))
      .filter(id => id && id !== '0' && id !== 'null' && id !== 'undefined');
  };

  // ─── Optimistically update assigned_servers in cart state ───
  const optimisticallyAssign = (itemId, guildId) => {
    setCart(prev => prev.map(item => {
      if (item.item_id !== itemId) return item;
      const already = (item.assigned_servers || []).some(s => String(s.guild_id) === String(guildId));
      if (already) return item;
      return {
        ...item,
        assigned_servers: [...(item.assigned_servers || []), { guild_id: String(guildId) }]
      };
    }));
  };

  const optimisticallyUnassign = (itemId, guildId) => {
    setCart(prev => prev.map(item => {
      if (item.item_id !== itemId) return item;
      return {
        ...item,
        assigned_servers: (item.assigned_servers || []).filter(s => String(s.guild_id) !== String(guildId))
      };
    }));
  };

  // ─── Server assignment ───
  const assignServer = async (item, guildId) => {
    const guildIdStr = String(guildId);
    // Optimistic update — show the server immediately
    optimisticallyAssign(item.item_id, guildIdStr);
    setOpenDropdown(null);
    setPendingActions(prev => ({ ...prev, [item.item_id]: true }));
    try {
      const response = await fetch(`${API_URL}/api/cart/assign-server`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: item.item_id, guild_id: guildIdStr })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Failed to assign server');
      }
    } catch (err) {
      // Roll back the optimistic update on failure
      optimisticallyUnassign(item.item_id, guildIdStr);
      setError(err.message);
      setTimeout(() => setError(null), 4000);
    } finally {
      setPendingActions(prev => ({ ...prev, [item.item_id]: false }));
    }
  };

  const unassignServer = async (item, guildId) => {
    const guildIdStr = String(guildId);
    // Optimistic update — remove the server immediately
    optimisticallyUnassign(item.item_id, guildIdStr);
    setPendingActions(prev => ({ ...prev, [item.item_id]: true }));
    try {
      const response = await fetch(`${API_URL}/api/cart/unassign-server`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: item.item_id, guild_id: guildIdStr })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Failed to remove server');
      }
    } catch (err) {
      // Roll back the optimistic update on failure
      optimisticallyAssign(item.item_id, guildIdStr);
      setError(err.message);
      setTimeout(() => setError(null), 4000);
    } finally {
      setPendingActions(prev => ({ ...prev, [item.item_id]: false }));
    }
  };

  // ─── Remove item from cart ───
  const removeFromCart = async (item) => {
    setRemovingItem(item.item_id);
    try {
      const response = await fetch(`${API_URL}/api/cart/remove`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: item.item_id })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Failed to remove item');
      }
      setTimeout(() => {
        setCart(prev => prev.filter(ci => ci.item_id !== item.item_id));
        setRemovingItem(null);
      }, 250);
    } catch (err) {
      setError(err.message);
      setRemovingItem(null);
      setTimeout(() => setError(null), 4000);
    }
  };

  // ─── Pricing ───
  const MULTI_SERVER_DISCOUNT_STEP = 0.05;
  const MULTI_SERVER_DISCOUNT_MAX = 0.50;

  const getItemDiscount = (item) => {
    const assignedCount = getAssignedGuildIds(item).length;
    const extraServers = Math.max(0, assignedCount - 2);
    return Math.min(extraServers * MULTI_SERVER_DISCOUNT_STEP, MULTI_SERVER_DISCOUNT_MAX);
  };

  const getItemBasePrice = (item) => {
    return item.billing_cycle === 'yearly'
      ? item.price_usd * YEARLY_MULTIPLIER
      : item.price_usd;
  };

  const getItemEffectivePrice = (item) => {
    const discount = getItemDiscount(item);
    return getItemBasePrice(item) * (1 - discount);
  };

  const totalPrice = cart.reduce((sum, item) => sum + getItemEffectivePrice(item), 0);

  // ─── Render: Login overlay ───
  if (authChecked && showLoginOverlay) {
    return (
      <>
        <NavBar />
        <div className="cart-page">
          <div className="login-overlay">
            <div className="login-modal">
              <div className="login-icon">🔒</div>
              <h2>Sign in to view your cart</h2>
              <p>Log in with Discord to see what's waiting in your cart and assign it to your servers.</p>
              <button className="login-button" onClick={handleLogin}>
                Log In with Discord
              </button>
            </div>
          </div>
        </div>
        <Footer />
        <style>{baseStyles + loginStyles}</style>
      </>
    );
  }

  if (!authChecked) {
    return (
      <>
        <NavBar />
        <div className="cart-page">
          <div className="state-container">
            <div className="spinner" />
          </div>
        </div>
        <Footer />
        <style>{baseStyles + stateStyles}</style>
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

          <div className="modules-divider">
            <div className="divider-line" />
            <span className="modules-label">MY CART</span>
            <div className="divider-line" />
          </div>

          {error && (
            <div className="global-error">{error}</div>
          )}

          {loading ? (
            <div className="state-container">
              <div className="spinner" />
              <p className="state-text">Loading your cart...</p>
            </div>
          ) : cart.length === 0 ? (
            <div className="empty-cart">
              <ShoppingCart size={48} color="#aa00ff" />
              <h2>Your cart is empty</h2>
              <p>Browse modules in the Premium section and add what you need.</p>
              <a href="/Premium/index.html" className="browse-link">Browse Modules</a>
            </div>
          ) : (
            <>
              <div className="modules-grid">
                {cart.map((item) => {
                  const info = MODULE_INFO[item.item_id] || { name: item.item_id, icon: <ShoppingCart size={28} color="#aa00ff" /> };
                  const assignedIds = getAssignedGuildIds(item);
                  const assignedServers = servers.filter(s => assignedIds.includes(String(s.id)));
                  const availableServers = servers.filter(s => !assignedIds.includes(String(s.id)));
                  const discount = getItemDiscount(item);
                  const effectivePrice = getItemEffectivePrice(item);
                  const isYearly = item.billing_cycle === 'yearly';
                  const isPending = pendingActions[item.item_id];
                  const isRemoving = removingItem === item.item_id;
                  const isDropdownOpen = openDropdown === item.item_id;

                  return (
                    <div key={item.item_id} className={`module-card ${isRemoving ? 'is-removing' : ''}`}>
                      <div className="card-sheen" />

                      <div className="module-header">
                        <div className="module-icon">{info.icon}</div>
                        <div className="module-title-group">
                          <h2 className="module-name">{info.name}</h2>
                          <span className="module-price">
                            <span className="price-amount" key={effectivePrice}>${effectivePrice.toFixed(2)}</span>
                            {' '}/ {isYearly ? 'year' : 'month'}
                            {isYearly && (
                              <span className="discount-pill yearly-pill"> · 17% off</span>
                            )}
                            {discount > 0 && (
                              <span className="discount-pill"> · {(discount * 100).toFixed(0)}% multi-server</span>
                            )}
                          </span>
                        </div>
                      </div>

                      <div className="module-divider" />

                      <div className="server-section">
                        <p className="feature-group-label">Servers</p>

                        {assignedServers.length > 0 && (
                          <div className="assigned-servers">
                            {assignedServers.map(server => (
                              <div key={server.id} className="server-chip">
                                <img src={server.iconUrl} alt={server.name} className="server-chip-icon"
                                  onError={(e) => { e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; }}
                                />
                                <span className="server-chip-name">{server.name}</span>
                                <button
                                  className="server-chip-remove"
                                  onClick={() => unassignServer(item, server.id)}
                                  disabled={isPending}
                                  aria-label={`Remove ${server.name}`}
                                >
                                  ×
                                </button>
                              </div>
                            ))}
                          </div>
                        )}

                        {assignedServers.length === 0 && (
                          <p className="no-server-text">No server assigned yet — pick one below.</p>
                        )}

                        <div className="add-server-wrapper">
                          <button
                            className="add-server-btn"
                            onClick={() => setOpenDropdown(isDropdownOpen ? null : item.item_id)}
                            disabled={isPending || serversLoading || availableServers.length === 0}
                          >
                            <Server size={15} />
                            <span>
                              {serversLoading
                                ? 'Loading servers...'
                                : availableServers.length === 0
                                  ? 'All servers added'
                                  : assignedServers.length === 0
                                    ? 'Select a server'
                                    : 'Add another server'}
                            </span>
                            <ChevronDown size={15} className={`chevron ${isDropdownOpen ? 'open' : ''}`} />
                          </button>

                          {isDropdownOpen && availableServers.length > 0 && (
                            <div className="server-dropdown">
                              {availableServers.map(server => (
                                <button
                                  key={server.id}
                                  className="server-dropdown-item"
                                  onClick={() => assignServer(item, server.id)}
                                  disabled={isPending}
                                >
                                  <img src={server.iconUrl} alt={server.name} className="server-chip-icon"
                                    onError={(e) => { e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; }}
                                  />
                                  <span>{server.name}</span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>

                        {assignedServers.length > 0 && (
                          <p className="discount-note">
                            {discount > 0
                              ? `Multi-server discount applied: ${(discount * 100).toFixed(0)}% off`
                              : 'Add more servers for up to 50% off this item'}
                          </p>
                        )}
                      </div>

                      <div className="module-divider" />

                      <div className="module-footer">
                        <button
                          className="remove-btn"
                          onClick={() => removeFromCart(item)}
                          disabled={isRemoving}
                        >
                          <Trash2 size={16} />
                          <span>{isRemoving ? 'Removing...' : 'Remove from Cart'}</span>
                        </button>
                      </div>

                      <p className="module-footnote">
                        Billed {isYearly ? 'yearly (2 months free)' : 'monthly'}, excluding VAT
                      </p>
                    </div>
                  );
                })}
              </div>

              <div className="checkout-card">
                <button className="checkout-btn">
                  <span className="checkout-label">Checkout</span>
                  <span className="checkout-price" key={totalPrice}>${totalPrice.toFixed(2)}</span>
                </button>
                <p className="page-footnote">
                  Total reflects all multi-server discounts. Final billing is calculated at checkout, excluding VAT.
                </p>
              </div>
            </>
          )}

        </div>
      </div>

      <Footer />

      <style>{baseStyles + cartStyles + loginStyles + stateStyles}</style>
    </>
  );
};

const baseStyles = `
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

  .cart-page {
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

  .cart-container {
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
    transition: border-color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease, opacity 0.25s ease;
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

  .module-card.is-removing {
    opacity: 0;
    transform: scale(0.96) translateY(-6px);
    pointer-events: none;
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

  .feature-group-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #aa00ff;
    text-shadow: 0 0 10px rgba(170, 0, 255, 0.45);
    margin-bottom: 14px;
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
    margin-top: 16px;
    font-size: 13px;
    color: #6e7180;
    text-align: center;
    line-height: 1.6;
    max-width: 480px;
    margin-left: auto;
    margin-right: auto;
  }

  @media (max-width: 768px) {
    .cart-page { padding: 40px 0 60px; }
    .cart-container { padding: 0 20px; max-width: 100%; }
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
    .modules-divider { gap: 12px; }
  }
`;

const cartStyles = `
  .global-error {
    background: rgba(255, 107, 107, 0.1);
    border: 1px solid #ff6b6b;
    color: #ff8888;
    padding: 14px 20px;
    border-radius: 12px;
    font-size: 14px;
    margin-bottom: 28px;
    text-align: center;
  }

  .empty-cart {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    text-align: center;
    padding: 80px 20px;
    background-color: #14151c;
    border: 1px solid #2c2f3a;
    border-radius: 16px;
  }

  .empty-cart h2 {
    font-size: 22px;
    font-weight: 700;
    color: #ffffff;
  }

  .empty-cart p {
    font-size: 14px;
    color: #888b99;
    max-width: 320px;
    line-height: 1.6;
  }

  .browse-link {
    margin-top: 8px;
    padding: 12px 28px;
    background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    border-radius: 8px;
    text-decoration: none;
    transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
  }

  .browse-link:hover {
    transform: translateY(-2px) scale(1.01);
    box-shadow: 0 6px 24px rgba(170, 0, 255, 0.45);
  }

  .server-section {
    position: relative;
    z-index: 2;
  }

  .assigned-servers {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }

  .server-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(170, 0, 255, 0.08);
    border: 1px solid rgba(170, 0, 255, 0.25);
    border-radius: 30px;
    padding: 6px 10px 6px 6px;
    animation: chipAppear 0.2s ease;
  }

  @keyframes chipAppear {
    from { opacity: 0; transform: scale(0.92); }
    to { opacity: 1; transform: scale(1); }
  }

  .server-chip-icon {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
  }

  .server-chip-name {
    font-size: 13px;
    color: #e0e0e0;
    font-weight: 500;
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .server-chip-remove {
    background: none;
    border: none;
    color: #888b99;
    font-size: 16px;
    line-height: 1;
    cursor: pointer;
    padding: 0 2px;
    transition: color 0.2s ease;
  }

  .server-chip-remove:hover:not(:disabled) {
    color: #ff6b6b;
  }

  .server-chip-remove:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .no-server-text {
    font-size: 13px;
    color: #888b99;
    margin-bottom: 12px;
  }

  .add-server-wrapper {
    position: relative;
  }

  .add-server-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 10px 14px;
    background: #1a1b24;
    border: 1px solid #2c2f3a;
    border-radius: 8px;
    color: #d0d0d0;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: border-color 0.2s ease, color 0.2s ease;
  }

  .add-server-btn:hover:not(:disabled) {
    border-color: rgba(170, 0, 255, 0.4);
    color: #ffffff;
  }

  .add-server-btn:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .add-server-btn span {
    flex: 1;
    text-align: left;
  }

  .chevron {
    transition: transform 0.25s ease;
    flex-shrink: 0;
  }

  .chevron.open {
    transform: rotate(180deg);
  }

  .server-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    background: #1a1b24;
    border: 1px solid #2c2f3a;
    border-radius: 8px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.5);
    max-height: 220px;
    overflow-y: auto;
    z-index: 10;
    animation: dropdownOpen 0.2s ease;
  }

  @keyframes dropdownOpen {
    from { opacity: 0; transform: translateY(-6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .server-dropdown-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 14px;
    background: none;
    border: none;
    color: #d0d0d0;
    font-size: 13px;
    text-align: left;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .server-dropdown-item:hover:not(:disabled) {
    background: rgba(170, 0, 255, 0.1);
    color: #ffffff;
  }

  .server-dropdown-item:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .discount-note {
    margin-top: 10px;
    font-size: 12px;
    color: #888b99;
  }

  .discount-pill {
    font-size: 12px;
    color: #00e07a;
    font-weight: 600;
  }

  .yearly-pill {
    color: #aa00ff;
  }

  .module-footer {
    position: relative;
    z-index: 1;
  }

  .remove-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    padding: 12px 24px;
    background: transparent;
    border: 1px solid rgba(255, 107, 107, 0.35);
    color: #ff8888;
    font-size: 14px;
    font-weight: 600;
    border-radius: 8px;
    cursor: pointer;
    letter-spacing: 0.3px;
    transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
  }

  .remove-btn:hover:not(:disabled) {
    background: rgba(255, 107, 107, 0.1);
    border-color: #ff6b6b;
  }

  .remove-btn:active:not(:disabled) {
    transform: scale(0.98);
  }

  .remove-btn:disabled {
    cursor: wait;
    opacity: 0.6;
  }

  .checkout-card {
    margin-top: 36px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .checkout-btn {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    width: 100%;
    max-width: 520px;
    padding: 18px 32px;
    background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
  }

  .checkout-btn:hover {
    transform: translateY(-2px) scale(1.01);
    box-shadow: 0 8px 32px rgba(170, 0, 255, 0.4);
  }

  .checkout-btn:active {
    transform: translateY(0) scale(0.99);
  }

  .checkout-label {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }

  .checkout-price {
    font-size: 22px;
    font-weight: 800;
    animation: priceFade 0.35s ease;
  }

  @media (max-width: 480px) {
    .checkout-btn { padding: 16px 24px; }
    .checkout-label { font-size: 16px; }
    .checkout-price { font-size: 19px; }
    .server-chip-name { max-width: 110px; }
  }
`;

const loginStyles = `
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
    background: rgba(10, 10, 10, 0.95);
    backdrop-filter: blur(20px);
    border: 2px solid #aa00ff;
    border-radius: 40px;
    padding: 60px 40px;
    max-width: 500px;
    width: 100%;
    text-align: center;
    box-shadow: 0 30px 60px rgba(170, 0, 255, 0.3);
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
    font-size: 36px;
    font-weight: 800;
    margin-bottom: 20px;
    background: linear-gradient(135deg, #ffffff, #aa00ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .login-modal p {
    color: #b0b0b0;
    font-size: 18px;
    margin-bottom: 40px;
    line-height: 1.6;
  }

  .login-button {
    background-image: linear-gradient(135deg, #aa00ff, #ff00aa);
    color: white;
    border: none;
    padding: 10px 24px;
    border-radius: 50px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
    min-height: 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .login-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(170, 0, 255, 0.4);
    background-image: linear-gradient(135deg, #bb00ff, #ff00bb);
  }

  .login-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 8px rgba(170, 0, 255, 0.3);
  }

  @media (max-width: 768px) {
    .login-modal { padding: 40px 20px; }
    .login-icon { font-size: 60px; }
    .login-modal h2 { font-size: 28px; }
    .login-modal p { font-size: 16px; }
    .login-button { padding: 8px 20px; font-size: 13px; min-height: 32px; }
  }
`;

const stateStyles = `
  .state-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: calc(100vh - 200px);
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
    color: #b0b0b0;
    font-size: 14px;
  }
`;

const root = createRoot(document.getElementById('app'));
root.render(
  <React.StrictMode>
    <MyCartPage />
  </React.StrictMode>
);

export default MyCartPage;