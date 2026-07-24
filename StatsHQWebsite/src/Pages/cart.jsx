import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Trash2, ShoppingCart, Server, Settings } from 'lucide-react';
import NavBar from '../Components/NavBar.jsx';
import Footer from '../Components/Footer.jsx';

const API_URL = window.location.origin;

// ─── Module registry ───────────────────────────────────────────────────────────
// Add new modules here as you release them.
const MODULE_INFO = {
  'optimization-plus': {
    name: 'Optimization+',
    icon: <Settings size={28} color="#aa00ff" />,
    monthlyPrice: 2.49,
    yearlyPrice: 24.90,
  },
};

// ─── Discount tiers (must match server_count_discounts table + env discount IDs)
// Key = total active subs for this module across all user's servers (including this purchase)
const DISCOUNT_TIERS = {
  1:  0.00,
  2:  0.05,
  3:  0.10,
  4:  0.15,
  5:  0.20,
  6:  0.25,
  7:  0.30,
  8:  0.35,
  9:  0.40,
  10: 0.45,
  11: 0.50,
};

const getDiscountPct = (totalServerCount) => {
  const capped = Math.min(totalServerCount, 11);
  return DISCOUNT_TIERS[capped] ?? 0;
};

const MyCartPage = () => {
  const [user, setUser]               = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showLoginOverlay, setShowLoginOverlay] = useState(false);

  const [cart, setCart]               = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);

  const [servers, setServers]                 = useState([]);
  const [serversLoading, setServersLoading]   = useState(true);

  // How many active subs the user already has per module key
  // e.g. { 'optimization-plus': 2 }
  const [existingSubCounts, setExistingSubCounts] = useState({});

  // Which guild IDs already have an ACTIVE subscription for a given module_key.
  // e.g. { 'optimization-plus': Set('123', '456') }
  // Used to hide those servers from the assignment dropdown for that item —
  // assigning one would just 409 at checkout since it's already subscribed.
  const [subscribedGuildsByModule, setSubscribedGuildsByModule] = useState({});

  const [pendingCheckout, setPendingCheckout] = useState(null); // item_id being checked out
  const [removingItem, setRemovingItem]       = useState(null);

  const hasFetchedRef = useRef(false);

  useEffect(() => {
    if (window.Paddle) {
      if (import.meta.env.VITE_PADDLE_ENV === 'sandbox') {
        window.Paddle.Environment.set('sandbox');
      }
      window.Paddle.Setup({ token: import.meta.env.VITE_PADDLE_CLIENT_TOKEN });
    }
  }, []);

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

  // ─── Initial fetch once authenticated ─────────────────────────────────────
  useEffect(() => {
    if (!user || hasFetchedRef.current) return;
    hasFetchedRef.current = true;
    fetchCart();
    fetchServers();      // this now also kicks off fetchGuildModuleAccess once it has the server list
    fetchExistingSubs();
  }, [user]);

  const fetchCart = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/cart`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' },
      });
      if (!res.ok) throw new Error(`Failed to fetch cart: ${res.status}`);
      const data = await res.json();
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
      const res = await fetch(`${API_URL}/api/user/servers`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' },
      });
      if (!res.ok) throw new Error(`Failed to fetch servers: ${res.status}`);
      const data = await res.json();
      const mapped = data.map(s => ({
        ...s,
        id: String(s.id),
        iconUrl: s.icon
          ? `https://cdn.discordapp.com/icons/${s.id}/${s.icon}.png?size=64`
          : 'https://cdn.discordapp.com/embed/avatars/0.png',
      }));
      setServers(mapped);
      // Needs the resolved server list, not state (setState is async) —
      // pass it straight through instead of reading `servers` here.
      fetchGuildModuleAccess(mapped);
    } catch (err) {
      console.error('Error fetching servers:', err);
    } finally {
      setServersLoading(false);
    }
  };

  // existingSubCounts[module_key] -> how many of the user's OWN active subs
  // exist for that module, purely for discount-tier math (matches the
  // existing_count logic in /api/paddle/checkout).
  const fetchExistingSubs = async () => {
    try {
      const res = await fetch(`${API_URL}/api/paddle/subscriptions/user/me`, {
        credentials: 'include',
        headers: { 'Cache-Control': 'no-cache' },
      });
      if (!res.ok) return;
      const subs = await res.json();

      const counts = {};
      for (const sub of subs) {
        if (sub.status === 'active' && sub.module_key) {
          counts[sub.module_key] = (counts[sub.module_key] || 0) + 1;
        }
      }
      setExistingSubCounts(counts);
    } catch (err) {
      console.error('Error fetching existing sub counts:', err);
    }
  };

  // subscribedGuildsByModule[module_key] -> Set of guild_ids that ALREADY have
  // that module active, used to hide those servers from the assignment
  // dropdown. Deliberately checked at the GUILD level via
  // /api/paddle/guild-module-access/{guild_id}/active — same question
  // /api/paddle/checkout's duplicate-sub guard asks — rather than
  // /subscriptions/user/me, which only reflects subs *you* personally
  // bought. That matters for two reasons: (1) staff grants are owned by
  // the guild, not any individual user, so they'd never show up under
  // "your" subscriptions; (2) a co-admin on a shared server could have
  // bought the module without you knowing, and it should still be
  // excluded here.
  const fetchGuildModuleAccess = async (serverList) => {
    if (!serverList.length) return;
    try {
      const results = await Promise.all(
        serverList.map(async (s) => {
          try {
            const res = await fetch(
              `${API_URL}/api/paddle/guild-module-access/${s.id}/active`,
              { credentials: 'include', headers: { 'Cache-Control': 'no-cache' } }
            );
            if (!res.ok) return { guildId: s.id, modules: [] };
            const activeModules = await res.json(); // expected: array of module rows/keys
            return { guildId: s.id, modules: activeModules };
          } catch {
            return { guildId: s.id, modules: [] };
          }
        })
      );

      const guildsByModule = {};
      for (const { guildId, modules } of results) {
        for (const m of modules) {
          const key = typeof m === 'string' ? m : m.module_key;
          if (!key) continue;
          if (!guildsByModule[key]) guildsByModule[key] = new Set();
          guildsByModule[key].add(guildId);
        }
      }
      setSubscribedGuildsByModule(guildsByModule);
    } catch (err) {
      console.error('Error fetching guild module access:', err);
    }
  };

  const handleLogin = () => {
    window.location.href = `${API_URL}/api/auth/discord?returnTo=${encodeURIComponent(window.location.href)}`;
  };

  // ─── Server assignment (one server per cart item) ─────────────────────────
  const assignServer = async (item, guildId) => {
    const guildIdStr = String(guildId);
    // Optimistic update
    setCart(prev => prev.map(ci =>
      ci.item_id === item.item_id
        ? { ...ci, guild_id: guildIdStr }
        : ci
    ));
    try {
      const res = await fetch(`${API_URL}/api/cart/assign-server`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: item.item_id, guild_id: guildIdStr }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || data.message || 'Failed to assign server');
    } catch (err) {
      // Roll back
      setCart(prev => prev.map(ci =>
        ci.item_id === item.item_id
          ? { ...ci, guild_id: item.guild_id }
          : ci
      ));
      setError(err.message);
      setTimeout(() => setError(null), 4000);
    }
  };

  const unassignServer = async (item) => {
    const prevGuildId = item.guild_id;
    // Optimistic update
    setCart(prev => prev.map(ci =>
      ci.item_id === item.item_id
        ? { ...ci, guild_id: null }
        : ci
    ));
    try {
      const res = await fetch(`${API_URL}/api/cart/unassign-server`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: item.item_id, guild_id: prevGuildId }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || data.message || 'Failed to remove server');
    } catch (err) {
      // Roll back
      setCart(prev => prev.map(ci =>
        ci.item_id === item.item_id
          ? { ...ci, guild_id: prevGuildId }
          : ci
      ));
      setError(err.message);
      setTimeout(() => setError(null), 4000);
    }
  };

  // ─── Remove item ───────────────────────────────────────────────────────────
  const removeFromCart = async (item) => {
    setRemovingItem(item.item_id);
    try {
      const res = await fetch(`${API_URL}/api/cart/remove`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: item.item_id }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || data.message || 'Failed to remove item');
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

  // ─── Pricing helpers ───────────────────────────────────────────────────────
  // Position of this item in the checkout queue affects discount tier.
  // Items are sorted by item_id for a stable order.
  const getItemDiscount = (item, cartIndex) => {
    const existing = existingSubCounts[item.item_id] || 0;
    // cartIndex is 0-based position among items with the same module_key in this cart
    const totalServerCount = existing + cartIndex + 1;
    return getDiscountPct(totalServerCount);
  };

  const getBasePrice = (item) => {
    const info = MODULE_INFO[item.item_id];
    if (!info) return item.price_usd || 0;
    return item.billing_cycle === 'yearly' ? info.yearlyPrice : info.monthlyPrice;
  };

  const getEffectivePrice = (item, cartIndex) => {
    const base     = getBasePrice(item);
    const discount = getItemDiscount(item, cartIndex);
    return parseFloat((base * (1 - discount)).toFixed(2));
  };

  // Group cart items by module_key to assign per-module cartIndex for discount calc
  const getCartIndex = (item) => {
    return cart
      .filter(ci => ci.item_id === item.item_id)
      .findIndex(ci => ci.item_id === item.item_id && ci.cart_item_id === item.cart_item_id);
  };

  const totalPrice = cart.reduce((sum, item) => {
    const idx = getCartIndex(item);
    return sum + getEffectivePrice(item, idx);
  }, 0);

  // ─── Checkout ──────────────────────────────────────────────────────────────
  const handleCheckout = async (item) => {
    if (!item.guild_id) {
      setError('Please assign a server before checking out.');
      setTimeout(() => setError(null), 4000);
      return;
    }

    setPendingCheckout(item.item_id);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/paddle/checkout`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          module_key:    item.item_id,
          guild_id:      item.guild_id,
          billing_cycle: item.billing_cycle || 'monthly',
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 409) {
          throw new Error('This server already has an active subscription for this module.');
        }
        throw new Error(data.detail || 'Failed to create checkout session');
      }

      if (!data.transaction_id) {
        throw new Error('No transaction returned from server');
      }

      // Open Paddle's overlay right here instead of navigating away
      window.Paddle.Checkout.open({
        transactionId: data.transaction_id,
        settings: {
          successUrl: `${window.location.origin}/checkout/success/index.html`,
          displayMode: 'overlay',
        },
      });

    } catch (err) {
      setError(err.message);
      setTimeout(() => setError(null), 6000);
    } finally {
      setPendingCheckout(null);
    }
  };

  // ─── Render helpers ────────────────────────────────────────────────────────
  const getAssignedServer = (item) => {
    if (!item.guild_id) return null;
    return servers.find(s => s.id === String(item.guild_id)) || null;
  };

  const getAvailableServers = (item) => {
    // Exclude servers already assigned to another cart item with the same module
    const takenByOtherItems = cart
      .filter(ci => ci.item_id === item.item_id && ci.cart_item_id !== item.cart_item_id && ci.guild_id)
      .map(ci => String(ci.guild_id));

    // Exclude servers that already have an ACTIVE subscription for this module —
    // assigning one of these would just fail at checkout with a 409, so hide them
    // from the dropdown up front instead of letting the user hit the error.
    const alreadySubscribed = subscribedGuildsByModule[item.item_id] || new Set();

    return servers.filter(s =>
      !takenByOtherItems.includes(s.id) && !alreadySubscribed.has(s.id)
    );
  };

  // Whether the ONLY reason a server list is empty is because every server
  // the user administers already has this module — vs. genuinely having no
  // servers at all. Used to give a more useful empty-state message.
  const allServersAlreadySubscribed = (item) => {
    if (servers.length === 0) return false;
    const alreadySubscribed = subscribedGuildsByModule[item.item_id] || new Set();
    return servers.every(s => alreadySubscribed.has(s.id));
  };

  // ─── Login overlay ─────────────────────────────────────────────────────────
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
              <button className="login-button" onClick={handleLogin}>Log In with Discord</button>
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
          <div className="state-container"><div className="spinner" /></div>
        </div>
        <Footer />
        <style>{baseStyles + stateStyles}</style>
      </>
    );
  }

  // ─── Main render ───────────────────────────────────────────────────────────
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

          {error && <div className="global-error">{error}</div>}

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
                  const info           = MODULE_INFO[item.item_id] || { name: item.item_id, icon: <ShoppingCart size={28} color="#aa00ff" /> };
                  const cartIdx        = getCartIndex(item);
                  const discount       = getItemDiscount(item, cartIdx);
                  const basePrice      = getBasePrice(item);
                  const effectivePrice = getEffectivePrice(item, cartIdx);
                  const isYearly       = item.billing_cycle === 'yearly';
                  const assignedServer = getAssignedServer(item);
                  const availServers   = getAvailableServers(item);
                  const noEligibleServers = allServersAlreadySubscribed(item);
                  const isRemoving     = removingItem === item.item_id;
                  const isCheckingOut  = pendingCheckout === item.item_id;
                  const existing       = existingSubCounts[item.item_id] || 0;
                  const totalCount     = existing + cartIdx + 1;

                  return (
                    <div key={item.cart_item_id || item.item_id} className={`module-card ${isRemoving ? 'is-removing' : ''}`}>
                      <div className="card-sheen" />

                      {/* Header */}
                      <div className="module-header">
                        <div className="module-icon">{info.icon}</div>
                        <div className="module-title-group">
                          <h2 className="module-name">{info.name}</h2>
                          <span className="module-price">
                            <span className="price-amount" key={effectivePrice}>
                              ${effectivePrice.toFixed(2)}
                            </span>
                            {' '}/ {isYearly ? 'year' : 'month'}
                            {isYearly && (
                              <span className="discount-pill yearly-pill"> · 2 months free</span>
                            )}
                            {discount > 0 && (
                              <span className="discount-pill"> · {(discount * 100).toFixed(0)}% multi-server</span>
                            )}
                          </span>
                          {discount > 0 && (
                            <span className="base-price-strike">${basePrice.toFixed(2)} / {isYearly ? 'year' : 'month'}</span>
                          )}
                        </div>
                      </div>

                      <div className="module-divider" />

                      {/* Server assignment */}
                      <div className="server-section">
                        <p className="feature-group-label">Server</p>

                        {assignedServer ? (
                          <div className="server-chip">
                            <img
                              src={assignedServer.iconUrl}
                              alt={assignedServer.name}
                              className="server-chip-icon"
                              onError={(e) => { e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; }}
                            />
                            <span className="server-chip-name">{assignedServer.name}</span>
                            <button
                              className="server-chip-remove"
                              onClick={() => unassignServer(item)}
                              aria-label={`Remove ${assignedServer.name}`}
                            >
                              ×
                            </button>
                          </div>
                        ) : (
                          <div className="server-select-wrapper">
                            <Server size={14} className="server-select-icon" />
                            <select
                              className="server-select"
                              defaultValue=""
                              onChange={(e) => {
                                if (e.target.value) assignServer(item, e.target.value);
                              }}
                              disabled={serversLoading || availServers.length === 0}
                            >
                              <option value="" disabled>
                                {serversLoading
                                  ? 'Loading servers...'
                                  : availServers.length === 0
                                    ? (noEligibleServers
                                        ? 'All your servers already have this module'
                                        : 'No servers available')
                                    : 'Select a server'}
                              </option>
                              {availServers.map(s => (
                                <option key={s.id} value={s.id}>{s.name}</option>
                              ))}
                            </select>
                          </div>
                        )}

                        {/* Discount context note */}
                        {existing > 0 && (
                          <p className="discount-context-note">
                            {discount > 0
                              ? `${(discount * 100).toFixed(0)}% off — you have ${existing} active ${info.name} subscription${existing > 1 ? 's' : ''} (server ${totalCount} total)`
                              : `You have ${existing} active ${info.name} subscription${existing > 1 ? 's' : ''}`}
                          </p>
                        )}
                        {existing === 0 && discount === 0 && (
                          <p className="discount-context-note muted">
                            Add this module to more servers for up to 50% off each
                          </p>
                        )}
                        {noEligibleServers && !assignedServer && (
                          <p className="discount-context-note muted">
                            Every server you administer already has {info.name} active — remove it from one first if you want to move it.
                          </p>
                        )}
                      </div>

                      <div className="module-divider" />

                      {/* Footer actions */}
                      <div className="module-footer">
                        <button
                          className="checkout-item-btn"
                          onClick={() => handleCheckout(item)}
                          disabled={isCheckingOut || isRemoving || !item.guild_id}
                          title={!item.guild_id ? 'Assign a server first' : ''}
                        >
                          {isCheckingOut ? (
                            <>
                              <div className="btn-spinner" />
                              <span>Redirecting to Paddle...</span>
                            </>
                          ) : (
                            <>
                              <span>Checkout — ${effectivePrice.toFixed(2)}</span>
                            </>
                          )}
                        </button>

                        <button
                          className="remove-btn"
                          onClick={() => removeFromCart(item)}
                          disabled={isRemoving || isCheckingOut}
                        >
                          <Trash2 size={15} />
                          <span>{isRemoving ? 'Removing...' : 'Remove'}</span>
                        </button>
                      </div>

                      <p className="module-footnote">
                        Billed {isYearly ? 'yearly (2 months free)' : 'monthly'}, including VAT
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Cart total summary */}
              {cart.length > 1 && (
                <div className="cart-summary">
                  <div className="summary-row">
                    <span className="summary-label">Total across {cart.length} items</span>
                    <span className="summary-total" key={totalPrice}>${totalPrice.toFixed(2)}</span>
                  </div>
                  <p className="page-footnote">
                    Each item checks out separately through Paddle. Discounts are applied based on your total active subscriptions per module.
                  </p>
                </div>
              )}
            </>
          )}

          {/* Refund policy note */}
          <p className="refund-note">
            All purchases are subject to our{' '}
            <a href="/docs/?page=refund" className="refund-link">refund policy</a>.
          </p>
        </div>
      </div>
      <Footer />
      <style>{baseStyles + cartStyles + loginStyles + stateStyles}</style>
    </>
  );
};

// ─── Styles ────────────────────────────────────────────────────────────────────

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

  .bg-glow { position: absolute; border-radius: 50%; filter: blur(120px); pointer-events: none; opacity: 0.35; }
  .bg-glow-1 { width: 500px; height: 500px; background: #aa00ff; top: -200px; left: -150px; }
  .bg-glow-2 { width: 450px; height: 450px; background: #5500aa; bottom: -150px; right: -150px; }

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
    background: linear-gradient(to right, transparent 0%, rgba(255,255,255,0.06) 8%, rgba(255,255,255,0.3) 25%, rgba(255,255,255,0.7) 50%, rgba(255,255,255,0.3) 75%, transparent 100%);
  }

  .modules-divider .divider-line:last-child {
    background: linear-gradient(to left, transparent 0%, rgba(255,255,255,0.06) 8%, rgba(255,255,255,0.3) 25%, rgba(255,255,255,0.7) 50%, rgba(255,255,255,0.3) 75%, transparent 100%);
  }

  .modules-label {
    font-size: 32px;
    font-weight: 800;
    letter-spacing: 8px;
    color: #ffffff;
    text-shadow: 0 0 12px rgba(255,255,255,0.95), 0 0 28px rgba(255,255,255,0.6), 0 0 55px rgba(255,255,255,0.25);
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
    top: 0; left: -100%;
    width: 60%; height: 100%;
    background: linear-gradient(100deg, transparent 0%, rgba(170,0,255,0.06) 50%, transparent 100%);
    transition: left 0.8s ease;
    pointer-events: none;
  }
  .module-card:hover .card-sheen { left: 120%; }

  .module-header { display: flex; align-items: center; gap: 16px; position: relative; z-index: 1; }

  .module-icon {
    display: flex; align-items: center; justify-content: center;
    width: 52px; height: 52px;
    background: rgba(170,0,255,0.1);
    border: 1px solid rgba(170,0,255,0.25);
    border-radius: 12px;
    flex-shrink: 0;
    transition: transform 0.4s cubic-bezier(0.34,1.56,0.64,1), background 0.3s ease;
  }
  .module-card:hover .module-icon { transform: rotate(90deg); background: rgba(170,0,255,0.18); }

  .module-title-group { display: flex; flex-direction: column; gap: 4px; }

  .module-name { font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: 0.3px; }

  .module-price { font-size: 14px; color: #aa00ff; font-weight: 500; letter-spacing: 0.2px; }

  .base-price-strike {
    font-size: 12px;
    color: #555870;
    text-decoration: line-through;
    margin-top: 2px;
  }

  .price-amount {
    display: inline-block;
    animation: priceFade 0.35s ease;
  }

  @keyframes priceFade {
    0% { opacity: 0; transform: translateY(4px); filter: blur(2px); }
    100% { opacity: 1; transform: translateY(0); filter: blur(0); }
  }

  .module-divider { height: 1px; background-color: #2c2f3a; margin: 24px 0; position: relative; z-index: 1; }

  .feature-group-label {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 2px; color: #aa00ff;
    text-shadow: 0 0 10px rgba(170,0,255,0.45);
    margin-bottom: 14px;
  }

  .module-footnote {
    margin-top: 16px; font-size: 12px; color: #6e7180;
    text-align: center; font-style: italic; position: relative; z-index: 1;
  }

  .page-footnote {
    margin-top: 12px; font-size: 13px; color: #6e7180;
    text-align: center; line-height: 1.6;
    max-width: 480px; margin-left: auto; margin-right: auto;
  }

  .refund-note {
    margin-top: 40px;
    font-size: 13px;
    color: #6e7180;
    text-align: center;
    line-height: 1.6;
  }

  .refund-link {
    color: #aa00ff;
    text-decoration: none;
    font-weight: 600;
    transition: text-shadow 0.2s ease, color 0.2s ease;
  }

  .refund-link:hover {
    color: #bb33ff;
    text-shadow: 0 0 10px rgba(170,0,255,0.5);
    text-decoration: underline;
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
    background: rgba(255,107,107,0.1);
    border: 1px solid #ff6b6b;
    color: #ff8888;
    padding: 14px 20px;
    border-radius: 12px;
    font-size: 14px;
    margin-bottom: 28px;
    text-align: center;
  }

  .empty-cart {
    display: flex; flex-direction: column; align-items: center;
    gap: 16px; text-align: center; padding: 80px 20px;
    background-color: #14151c; border: 1px solid #2c2f3a; border-radius: 16px;
  }
  .empty-cart h2 { font-size: 22px; font-weight: 700; color: #ffffff; }
  .empty-cart p { font-size: 14px; color: #888b99; max-width: 320px; line-height: 1.6; }

  .browse-link {
    margin-top: 8px; padding: 12px 28px;
    background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
    color: #ffffff; font-size: 14px; font-weight: 600;
    border-radius: 8px; text-decoration: none;
    transition: transform 0.25s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.25s ease;
  }
  .browse-link:hover { transform: translateY(-2px) scale(1.01); box-shadow: 0 6px 24px rgba(170,0,255,0.45); }

  .server-section { position: relative; z-index: 2; }

  .server-chip {
    display: flex; align-items: center; gap: 8px;
    background: rgba(170,0,255,0.08);
    border: 1px solid rgba(170,0,255,0.25);
    border-radius: 30px;
    padding: 6px 10px 6px 6px;
    width: fit-content;
    animation: chipAppear 0.2s ease;
  }

  @keyframes chipAppear {
    from { opacity: 0; transform: scale(0.92); }
    to { opacity: 1; transform: scale(1); }
  }

  .server-chip-icon { width: 22px; height: 22px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }

  .server-chip-name {
    font-size: 13px; color: #e0e0e0; font-weight: 500;
    max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  .server-chip-remove {
    background: none; border: none; color: #888b99;
    font-size: 16px; line-height: 1; cursor: pointer; padding: 0 2px;
    transition: color 0.2s ease;
  }
  .server-chip-remove:hover { color: #ff6b6b; }

  .server-select-wrapper {
    position: relative;
    display: flex;
    align-items: center;
  }

  .server-select-icon {
    position: absolute;
    left: 12px;
    color: #888b99;
    pointer-events: none;
    flex-shrink: 0;
  }

  .server-select {
    width: 100%;
    padding: 10px 14px 10px 34px;
    background: #1a1b24;
    border: 1px solid #2c2f3a;
    border-radius: 8px;
    color: #d0d0d0;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    appearance: none;
    transition: border-color 0.2s ease, color 0.2s ease;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888b99' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
  }
  .server-select:hover:not(:disabled) { border-color: rgba(170,0,255,0.4); color: #ffffff; }
  .server-select:disabled { cursor: not-allowed; opacity: 0.5; }
  .server-select option { background: #1a1b24; color: #d0d0d0; }

  .discount-context-note {
    margin-top: 10px; font-size: 12px; color: #7ebd9e; line-height: 1.5;
  }
  .discount-context-note.muted { color: #555870; }

  .discount-pill { font-size: 12px; color: #00e07a; font-weight: 600; }
  .yearly-pill { color: #aa00ff; }

  .module-footer {
    display: flex;
    gap: 10px;
    position: relative;
    z-index: 1;
  }

  .checkout-item-btn {
    flex: 1;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    padding: 13px 20px;
    background: linear-gradient(135deg, #aa00ff 0%, #7700cc 100%);
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 14px; font-weight: 700;
    cursor: pointer;
    letter-spacing: 0.3px;
    transition: transform 0.25s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.25s ease, opacity 0.2s ease;
  }
  .checkout-item-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 6px 24px rgba(170,0,255,0.4);
  }
  .checkout-item-btn:active:not(:disabled) { transform: scale(0.98); }
  .checkout-item-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #ffffff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }

  .remove-btn {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    padding: 13px 16px;
    background: transparent;
    border: 1px solid rgba(255,107,107,0.35);
    color: #ff8888;
    font-size: 13px; font-weight: 600;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s ease, border-color 0.2s ease;
    white-space: nowrap;
  }
  .remove-btn:hover:not(:disabled) { background: rgba(255,107,107,0.1); border-color: #ff6b6b; }
  .remove-btn:disabled { cursor: wait; opacity: 0.6; }

  .cart-summary {
    margin-top: 36px;
    background: #14151c;
    border: 1px solid #2c2f3a;
    border-radius: 16px;
    padding: 24px 28px;
    max-width: 520px;
    width: 100%;
    margin-left: auto;
    margin-right: auto;
  }

  .summary-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }

  .summary-label { font-size: 15px; color: #888b99; font-weight: 500; }

  .summary-total {
    font-size: 24px; font-weight: 800; color: #ffffff;
    animation: priceFade 0.35s ease;
  }

  @media (max-width: 480px) {
    .server-chip-name { max-width: 130px; }
    .checkout-item-btn { font-size: 13px; padding: 12px 14px; }
    .cart-summary { padding: 20px; }
    .summary-total { font-size: 20px; }
  }
`;

const loginStyles = `
  .login-overlay {
    position: relative; min-height: calc(100vh - 200px); width: 100%;
    display: flex; align-items: center; justify-content: center;
    padding: 40px 20px; z-index: 10;
  }

  .login-modal {
    background: rgba(10,10,10,0.95); backdrop-filter: blur(20px);
    border: 2px solid #aa00ff; border-radius: 40px;
    padding: 60px 40px; max-width: 500px; width: 100%;
    text-align: center; box-shadow: 0 30px 60px rgba(170,0,255,0.3);
    animation: modalAppear 0.5s ease; position: relative; z-index: 10;
  }

  @keyframes modalAppear {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .login-icon { font-size: 80px; margin-bottom: 30px; animation: pulse 2s infinite; }

  @keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
  }

  .login-modal h2 {
    font-size: 36px; font-weight: 800; margin-bottom: 20px;
    background: linear-gradient(135deg, #ffffff, #aa00ff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }

  .login-modal p { color: #b0b0b0; font-size: 18px; margin-bottom: 40px; line-height: 1.6; }

  .login-button {
    background-image: linear-gradient(135deg, #aa00ff, #ff00aa);
    color: white; border: none; padding: 10px 24px; border-radius: 50px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(170,0,255,0.3);
    min-height: 36px; display: inline-flex; align-items: center; justify-content: center;
  }
  .login-button:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(170,0,255,0.4); background-image: linear-gradient(135deg, #bb00ff, #ff00bb); }
  .login-button:active { transform: translateY(0); box-shadow: 0 2px 8px rgba(170,0,255,0.3); }

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
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: calc(100vh - 200px); width: 100%; gap: 20px; padding: 20px;
  }

  .spinner {
    width: 48px; height: 48px;
    border: 4px solid #232323;
    border-top-color: #aa00ff; border-right-color: #aa00ff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .state-text { color: #b0b0b0; font-size: 14px; }
`;

const root = createRoot(document.getElementById('app'));
root.render(
  <React.StrictMode>
    <MyCartPage />
  </React.StrictMode>
);

export default MyCartPage;