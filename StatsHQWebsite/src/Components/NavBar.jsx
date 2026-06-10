import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import Login from '../Pages/login';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const NavBar = () => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState("");
  const [menuLevel, setMenuLevel] = useState("main");
  const [isSamsung, setIsSamsung] = useState(false);
  const [serverInfo, setServerInfo] = useState(null);
  const [loadingServer, setLoadingServer] = useState(false);
  const mobileMenuRef = useRef(null);
  const menuButtonRef = useRef(null);

  const getDecodedPath = () => {
    const rawPath = window.location.pathname;
    return decodeURIComponent(rawPath);
  };

  const fetchSelectedServer = async () => {
    setLoadingServer(true);
    try {
      const authResponse = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (authResponse.ok) {
        const authData = await authResponse.json();
        
        if (authData.authenticated && authData.user) {
          const serversResponse = await fetch(`${API_BASE_URL}/api/user/servers`, {
            credentials: 'include',
            headers: { 'Accept': 'application/json' }
          });
          
          if (serversResponse.ok) {
            const servers = await serversResponse.json();
            if (Array.isArray(servers) && servers.length > 0) {
              let selectedServer = null;
              if (authData.user.selected_server) {
                selectedServer = servers.find(s => s.id === authData.user.selected_server);
              }
              if (!selectedServer && servers.length > 0) {
                selectedServer = servers[0];
              }
              if (selectedServer) {
                setServerInfo({
                  id: selectedServer.id,
                  name: selectedServer.name,
                  avatarUrl: selectedServer.icon ? `https://cdn.discordapp.com/icons/${selectedServer.id}/${selectedServer.icon}.png?size=64` : null
                });
              } else {
                setServerInfo(null);
              }
            } else {
              setServerInfo(null);
            }
          } else {
            setServerInfo(null);
          }
        } else {
          const path = getDecodedPath();
          if (path.includes("/Dashboard/")) {
            setServerInfo({ id: "1424021358680998022", name: "StatsHQ", avatarUrl: null });
          } else {
            setServerInfo(null);
          }
        }
      } else {
        const path = getDecodedPath();
        if (path.includes("/Dashboard/")) {
          setServerInfo({ id: "1424021358680998022", name: "StatsHQ", avatarUrl: null });
        } else {
          setServerInfo(null);
        }
      }
    } catch (error) {
      console.error('Error fetching selected server:', error);
      const path = getDecodedPath();
      if (path.includes("/Dashboard/")) {
        setServerInfo({ id: "1424021358680998022", name: "StatsHQ", avatarUrl: null });
      } else {
        setServerInfo(null);
      }
    } finally {
      setLoadingServer(false);
    }
  };

  useEffect(() => {
    const font = new FontFace('Horndon', 'url(/HorndonD.ttf) format("truetype")');
    font.load().then(() => {
      document.fonts.add(font);
    }).catch(err => {
      console.log('Font loading failed:', err);
    });

    const determineCurrentPage = () => {
      const path = getDecodedPath();
      const searchParams = new URLSearchParams(window.location.search);
      const pageParam = searchParams.get('page');
      
      if (path.includes("/Dashboard/")) {
        setCurrentPage("Dashboard");
        fetchSelectedServer();
      } else if (path.includes("/docs/") || path === '/docs') {
        if (pageParam === 'setup') setCurrentPage("setup");
        else if (pageParam === 'faq') setCurrentPage("faq");
        else if (pageParam === 'privacy') setCurrentPage("privacy");
        else if (pageParam === 'terms') setCurrentPage("terms");
        else if (pageParam === 'cookies') setCurrentPage("cookies");
        else if (pageParam === 'invite-tracking') setCurrentPage("invite-tracking");
        else if (pageParam === 'distribution') setCurrentPage("distribution");
        else if (pageParam === 'ships') setCurrentPage("ships");
        else setCurrentPage("introduction");
        setServerInfo(null);
      } else if (path.includes("/Commands/") || path === '/Commands') {
        setCurrentPage("commands");
        setServerInfo(null);
      } else if (path.includes("/Manage Servers/") || path === '/Manage Servers') {
        setCurrentPage("manage-servers");
        setServerInfo(null);
      } else if (path.includes("/Premium/") || path === '/Premium') {
        setCurrentPage("premium");
        setServerInfo(null);
      } else {
        setCurrentPage("home");
        setServerInfo(null);
      }
    };

    determineCurrentPage();
    window.addEventListener('popstate', determineCurrentPage);
    const handleUrlChange = () => { determineCurrentPage(); };
    window.addEventListener('urlchange', handleUrlChange);

    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes('samsung') || ua.includes('samsungbrowser')) {
      setIsSamsung(true);
    }

    return () => {
      window.removeEventListener('popstate', determineCurrentPage);
      window.removeEventListener('urlchange', handleUrlChange);
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        mobileMenuRef.current &&
        !mobileMenuRef.current.contains(event.target) &&
        !menuButtonRef.current.contains(event.target)
      ) {
        setIsMobileMenuOpen(false);
        setMenuLevel("main");
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (isMobileMenuOpen) {
      if (currentPage === "Dashboard") {
        setMenuLevel("Dashboard");
      } else if (["introduction", "setup", "faq", "privacy", "terms", "cookies", "invite-tracking", "distribution", "ships"].includes(currentPage)) {
        setMenuLevel("docs");
      } else {
        setMenuLevel("main");
      }
    }
  }, [isMobileMenuOpen, currentPage]);

  const handleDashboardClick = (e) => {
    e.preventDefault();
    setMenuLevel("Dashboard");
  };

  const handleDocsClick = (e) => {
    e.preventDefault();
    setMenuLevel("docs");
  };

  const handleBackClick = () => { setMenuLevel("main"); };

  const handleMobileLogoClick = (e) => {
    e.preventDefault();
    window.location.href = '/';
  };

  const handleManageServersClick = (e) => {
    e.preventDefault();
    window.location.href = '/Manage Servers/';
  };

  const ServerInfoBox = () => (
    <div className="mobile-server-info">
      {loadingServer ? (
        <div className="mobile-server-loading">
          <div className="loading-spinner-small"></div>
          <span>Loading server...</span>
        </div>
      ) : serverInfo ? (
        <div className="mobile-server-details">
          {serverInfo.avatarUrl ? (
            <img 
              src={serverInfo.avatarUrl} 
              alt={serverInfo.name}
              className="mobile-server-avatar"
              onError={(e) => {
                e.target.onerror = null;
                e.target.style.display = 'none';
                if (e.target.nextSibling) {
                  e.target.nextSibling.style.display = 'flex';
                }
              }}
            />
          ) : (
            <div className="mobile-server-avatar-placeholder">
              {serverInfo.name?.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="mobile-server-text">
            <div className="mobile-server-name">{serverInfo.name}</div>
            <div className="mobile-server-edit">
              <a 
                href="/Manage Servers/"
                onClick={handleManageServersClick}
                className="mobile-edit-link"
              >
                Edit Server →
              </a>
            </div>
          </div>
        </div>
      ) : (
        <div className="mobile-server-not-found">No server selected</div>
      )}
    </div>
  );

  const isDashboardPageActive = (pageName) => {
    const path = getDecodedPath();
    return path.includes(`/Dashboard/${pageName}/`) || path.includes(`/Dashboard/${pageName}`);
  };

  const DashboardMenu = () => (
    <div className="mobile-submenu">
      <ServerInfoBox />
      <div className="submenu-category">
        <h3 className="category-title">ANALYTICS</h3>
        <a href="/Dashboard/Messages/" className={`mobile-nav-link ${isDashboardPageActive('Messages') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">💬</span>Messages
        </a>
        <a href="/Dashboard/Voice Activity/" className={`mobile-nav-link ${isDashboardPageActive('Voice Activity') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">🔊</span>Voice Activity
        </a>
        <a href="/Dashboard/Activity/" className={`mobile-nav-link ${isDashboardPageActive('Activity') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">🎮</span>Status Activity
        </a>
        <a href="/Dashboard/Distribution/" className={`mobile-nav-link ${isDashboardPageActive('Distribution') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">📊</span>Distribution
        </a>
        <a href="/Dashboard/Emoji Tracking/" className={`mobile-nav-link ${isDashboardPageActive('Emoji Tracking') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">😊</span>Emojis
        </a>
        <a href="/Dashboard/Invite Tracking/" className={`mobile-nav-link ${isDashboardPageActive('Invite Tracking') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">📨</span>Invites
        </a>
        <a href="/Dashboard/Mentions/" className={`mobile-nav-link ${isDashboardPageActive('Mentions') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">🔔</span>Mentions
        </a>
        <a href="/Dashboard/Growth/" className={`mobile-nav-link ${isDashboardPageActive('Growth') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">📈</span>Growth
        </a>
      </div>
      <div className="submenu-category">
        <h3 className="category-title">OPTIMIZATION</h3>
        <a href="/Dashboard/Settings/" className={`mobile-nav-link ${isDashboardPageActive('Settings') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">⚙️</span>Settings
        </a>
        <a href="/Dashboard/Blacklist/" className={`mobile-nav-link ${isDashboardPageActive('Blacklist') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">🚫</span>Blacklist
        </a>
        <a href="/Dashboard/Reset/" className={`mobile-nav-link ${isDashboardPageActive('Reset') ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          <span className="mobile-nav-icon">🗑️</span>Reset Stats
        </a>
      </div>
    </div>
  );

  const DocsMenu = () => (
    <div className="mobile-submenu">
      <div className="submenu-category">
        <h3 className="category-title">THE BASICS</h3>
        <a href="/docs/" className={`mobile-nav-link ${currentPage === 'introduction' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Introduction
        </a>
        <a href="/docs/?page=setup" className={`mobile-nav-link ${currentPage === 'setup' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Set Up
        </a>
        <a href="/docs/?page=faq" className={`mobile-nav-link ${currentPage === 'faq' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          FAQ
        </a>
      </div>
      <div className="submenu-category">
        <h3 className="category-title">FEATURES</h3>
        <a href="/docs/?page=invite-tracking" className={`mobile-nav-link ${currentPage === 'invite-tracking' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Invite Tracking
        </a>
        <a href="/docs/?page=distribution" className={`mobile-nav-link ${currentPage === 'distribution' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Distribution
        </a>
        <a href="/docs/?page=ships" className={`mobile-nav-link ${currentPage === 'ships' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Ships
        </a>
      </div>
      <div className="submenu-category">
        <h3 className="category-title">LEGAL</h3>
        <a href="/docs/?page=privacy" className={`mobile-nav-link ${currentPage === 'privacy' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Privacy Policy
        </a>
        <a href="/docs/?page=terms" className={`mobile-nav-link ${currentPage === 'terms' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Terms of Service
        </a>
        <a href="/docs/?page=cookies" className={`mobile-nav-link ${currentPage === 'cookies' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
          Cookie Policy
        </a>
      </div>
    </div>
  );

  const MainMenu = () => (
    <>
      <a href="/" className={`mobile-nav-link ${currentPage === 'home' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
        Home
      </a>
      <a href="#" className={`mobile-nav-link ${currentPage === 'Dashboard' ? 'active' : ''}`} onClick={handleDashboardClick}>
        Dashboard
      </a>
      <a href="/Commands/" className={`mobile-nav-link ${currentPage === 'commands' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
        Commands
      </a>
      <a href="/Premium/index.html" className={`mobile-nav-link ${currentPage === 'premium' ? 'active' : ''}`} onClick={() => setIsMobileMenuOpen(false)}>
        Premium
      </a>
      <a href="#" className={`mobile-nav-link ${['introduction', 'setup', 'faq', 'privacy', 'terms', 'cookies', 'invite-tracking', 'distribution', 'ships'].includes(currentPage) ? 'active' : ''}`} onClick={handleDocsClick}>
        Docs
      </a>
      <a href="https://discord.gg/hreJvck8cK" className="mobile-nav-link" target="_blank" rel="noopener noreferrer" onClick={() => setIsMobileMenuOpen(false)}>
        Support
      </a>
    </>
  );

  const isDashboardPage = currentPage === "Dashboard";

  return (
    <>
      <header className="desktop-header">
        <div className="header-left">
          <a href="/" className="logo-container">
            <img src="/Stats logo.png" alt="Stats Logo" className="logo-image" />
            <span className="logo-text">STATS</span>
          </a>
          <nav className="desktop-nav">
            <a href="/" className={`nav-link ${currentPage === 'home' ? 'active' : ''}`}>
              Home
            </a>
            <a href="/Dashboard/Messages/" className={`nav-link ${currentPage === 'Dashboard' ? 'active' : ''}`}>
              Dashboard
            </a>
            <a href="/Commands/" className={`nav-link ${currentPage === 'commands' ? 'active' : ''}`}>
              Commands
            </a>
            <a href="/Premium/index.html" className={`nav-link ${currentPage === 'premium' ? 'active' : ''}`}>
              Premium
            </a>
            <a href="/docs/" className={`nav-link ${['introduction', 'setup', 'faq', 'privacy', 'terms', 'cookies'].includes(currentPage) ? 'active' : ''}`}>
              Docs
            </a>
            <a href="https://discord.gg/hreJvck8cK" className="nav-link" target="_blank" rel="noopener noreferrer">
              Support
            </a>
          </nav>
        </div>
        <div className={`login-container desktop ${isDashboardPage ? 'dashboard-login' : ''}`}>
          <Login />
        </div>
      </header>

      <header className="mobile-header">
        <button 
          ref={menuButtonRef}
          className="menu-button" 
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          style={{ outline: 'none', WebkitTapHighlightColor: 'transparent' }}
        >
          <span className="menu-icon">☰</span>
        </button>
        <div 
          className={`mobile-logo-container ${isSamsung ? 'samsung-only' : ''}`} 
          onClick={handleMobileLogoClick}
          role="link"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') handleMobileLogoClick(e);
          }}
          style={{ outline: 'none', WebkitTapHighlightColor: 'transparent' }}
        >
          <img src="/Stats logo.png" alt="Stats Logo" className="logo-image" />
          {!isSamsung && <span className="mobile-logo-text">STATS</span>}
        </div>
        <div className={`login-container mobile ${isDashboardPage ? 'dashboard-login' : ''}`}>
          <Login />
        </div>
      </header>

      {isMobileMenuOpen && (
        <>
          <div className="mobile-menu-overlay" onClick={() => { setIsMobileMenuOpen(false); setMenuLevel("main"); }} />
          <div ref={mobileMenuRef} className="mobile-menu">
            <div className="mobile-menu-header">
              {menuLevel !== "main" ? (
                <button className="back-button" onClick={handleBackClick}>
                  <div className="back-button-inner">
                    <svg className="back-arrow" viewBox="0 0 24 24" width="24" height="24">
                      <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" fill="currentColor"/>
                    </svg>
                  </div>
                </button>
              ) : (
                <button className="close-menu" onClick={() => { setIsMobileMenuOpen(false); setMenuLevel("main"); }}>
                  <svg className="close-icon" viewBox="0 0 24 24" width="20" height="20">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" fill="currentColor"/>
                  </svg>
                </button>
              )}
              <h2 className="menu-title">
                {menuLevel === "Dashboard" ? "DASHBOARD" : menuLevel === "docs" ? "DOCS" : "MENU"}
              </h2>
            </div>
            <div className="mobile-menu-content">
              {menuLevel === "Dashboard" ? <DashboardMenu /> : menuLevel === "docs" ? <DocsMenu /> : <MainMenu />}
            </div>
          </div>
        </>
      )}

      <style jsx>{`
        @font-face {
          font-family: 'Horndon';
          src: url('/HorndonD.ttf') format('truetype');
          font-display: block;
        }

        header {
          background-color: #0a0b12;
          border-bottom: 1px solid #2c2f3a;
          padding: 0 32px;
          position: sticky;
          top: 0;
          z-index: 1000;
          height: 80px;
          min-height: 80px;
          max-height: 80px;
          box-sizing: border-box;
          display: flex;
          align-items: center;
        }

        .desktop-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          width: 100%;
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 48px;
          flex-shrink: 0;
        }

        .logo-container {
          display: flex;
          align-items: center;
          gap: 12px;
          text-decoration: none;
        }

        .logo-text {
          font-family: 'Horndon', serif;
          font-size: 32px;
          font-weight: 600;
          color: #aa00ff;
          letter-spacing: 1px;
          -webkit-text-stroke: 3px #000000;
          text-stroke: 3px #000000;
          paint-order: stroke fill;
          text-shadow: 0 0 20px #aa00ff;
          line-height: 1;
        }

        .logo-image {
          width: 40px;
          height: auto;
          object-fit: contain;
        }

        .desktop-nav {
          display: flex;
          gap: 32px;
        }

        .nav-link {
          color: #ffffff;
          text-decoration: none;
          font-size: 16px;
          font-weight: 500;
          transition: all 0.2s ease;
          white-space: nowrap;
        }

        .nav-link:hover,
        .nav-link.active {
          color: #aa00ff;
          text-shadow: 0 0 15px #aa00ff;
        }

        .login-container {
          display: flex;
          align-items: center;
          position: relative;
        }

        .login-container.desktop.dashboard-login {
          margin-top: -12px;
        }
        
        .login-container.desktop.dashboard-login > :global(*) {
          transform: scale(1.08);
          transform-origin: center;
        }
        
        .login-container.desktop.dashboard-login :global(button),
        .login-container.desktop.dashboard-login :global(a),
        .login-container.desktop.dashboard-login :global(div) {
          padding: 8px 18px !important;
          font-size: 14.5px !important;
          min-height: 40px !important;
          max-height: 40px !important;
        }

        .login-container.mobile.dashboard-login {
          margin-top: -8px;
        }
        
        .login-container.mobile.dashboard-login > :global(*) {
          transform: scale(0.96);
          transform-origin: center;
        }
        
        .login-container.mobile.dashboard-login :global(button),
        .login-container.mobile.dashboard-login :global(a),
        .login-container.mobile.dashboard-login :global(div) {
          padding: 6px 14px !important;
          font-size: 13.5px !important;
          min-height: 36px !important;
          max-height: 36px !important;
        }

        .mobile-header {
          display: none;
          justify-content: space-between;
          align-items: center;
          background-color: #0a0b12;
          border-bottom: 1px solid #2c2f3a;
          position: sticky;
          top: 0;
          z-index: 1000;
          height: 70px;
          min-height: 70px;
          max-height: 70px;
          padding: 0 16px;
          width: 100%;
        }

        .menu-button {
          background: none;
          border: none;
          cursor: pointer;
          padding: 8px;
          color: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .menu-icon { font-size: 28px; }

        .mobile-logo-container {
          display: flex;
          align-items: center;
          gap: 8px;
          text-decoration: none;
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
          cursor: pointer;
          transition: opacity 0.2s ease;
        }

        .mobile-logo-container.samsung-only { gap: 0 !important; }
        .mobile-logo-container.samsung-only .logo-image { width: 32px; }
        .mobile-logo-container:hover { opacity: 0.8; }
        .mobile-logo-container:active { opacity: 0.6; }

        .mobile-logo-text {
          font-family: 'Horndon', serif;
          font-size: 26px;
          font-weight: 600;
          color: #aa00ff;
          letter-spacing: 2px;
          -webkit-text-stroke: 2px #000000;
          text-stroke: 2px #000000;
          paint-order: stroke fill;
          text-shadow: 0 0 15px #aa00ff;
          line-height: 1;
        }

        .samsung-logo-text {
          font-family: 'Horndon', serif !important;
          font-weight: 600 !important;
          font-size: 26px !important;
          color: #aa00ff !important;
          letter-spacing: 2px !important;
          -webkit-text-stroke: 2px #000000 !important;
          text-stroke: 2px #000000 !important;
          paint-order: stroke fill !important;
          text-shadow: 0 0 15px #aa00ff !important;
          line-height: 1 !important;
        }

        .mobile-logo-container .logo-image {
          width: 32px;
          height: auto;
          object-fit: contain;
          pointer-events: none;
        }

        .menu-button:hover { color: #aa00ff; }

        .login-container.mobile {
          position: relative;
          z-index: 1001;
          overflow: visible !important;
        }

        .login-container.mobile :global(*) { overflow: visible !important; }

        .login-container.mobile :global(.dropdown-menu),
        .login-container.mobile :global(.user-menu),
        .login-container.mobile :global(.popup),
        .login-container.mobile :global([class*="dropdown"]),
        .login-container.mobile :global([class*="menu"]) {
          position: absolute !important;
          right: 0 !important;
          top: 100% !important;
          z-index: 1002 !important;
          overflow: visible !important;
        }

        .mobile-menu-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: rgba(0, 0, 0, 0.7);
          z-index: 1001;
        }

        .mobile-menu {
          position: fixed;
          top: 0;
          left: 0;
          width: 50%;
          max-width: 400px;
          height: 100vh;
          background-color: #0a0b12;
          z-index: 1002;
          overflow-y: auto;
          animation: slideIn 0.3s ease;
          border-right: 1px solid #2c2f3a;
        }

        @keyframes slideIn {
          from { transform: translateX(-100%); }
          to { transform: translateX(0); }
        }

        .mobile-menu-header {
          display: flex;
          align-items: center;
          padding: 20px;
          border-bottom: 1px solid #2c2f3a;
          position: relative;
        }

        .back-button {
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
          width: 48px;
          height: 48px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
          color: #ffffff;
          position: relative;
          z-index: 1;
        }

        .back-button-inner {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, #2c2f3a 0%, #1a1c24 100%);
          border-radius: 16px;
          box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(170, 0, 255, 0.2) inset, 0 0 15px rgba(170, 0, 255, 0.3);
          transition: all 0.3s ease;
        }

        .back-button:hover { transform: translateX(-3px); }

        .back-button:hover .back-button-inner {
          background: linear-gradient(135deg, #3a3d4a 0%, #2a2c34 100%);
          box-shadow: 0 6px 15px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(170, 0, 255, 0.4) inset, 0 0 20px rgba(170, 0, 255, 0.5);
        }

        .back-button:active { transform: translateX(0) scale(0.95); }

        .back-arrow {
          width: 22px;
          height: 22px;
          color: #aa00ff;
          filter: drop-shadow(0 0 5px rgba(170, 0, 255, 0.5));
          transition: all 0.3s ease;
        }

        .back-button:hover .back-arrow {
          color: #bb33ff;
          transform: scale(1.1);
        }

        .close-menu {
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, #2c2f3a 0%, #1a1c24 100%);
          border-radius: 50%;
          box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
          transition: all 0.3s ease;
          color: #ffffff;
        }

        .close-menu:hover {
          transform: rotate(90deg);
          background: linear-gradient(135deg, #3a3d4a 0%, #2a2c34 100%);
          box-shadow: 0 6px 15px rgba(170, 0, 255, 0.3);
        }

        .close-icon {
          width: 18px;
          height: 18px;
          color: #aa00ff;
          transition: all 0.3s ease;
        }

        .close-menu:hover .close-icon {
          color: #bb33ff;
          transform: scale(0.9);
        }

        .menu-title {
          color: #aa00ff;
          font-size: 18px;
          font-weight: 600;
          margin: 0;
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
          text-shadow: 0 0 15px #aa00ff;
          letter-spacing: 1px;
        }

        .mobile-menu-content { padding: 20px; }

        .mobile-nav-link {
          display: flex;
          align-items: center;
          gap: 12px;
          color: #ffffff;
          text-decoration: none;
          padding: 16px 0;
          font-size: 18px;
          border-bottom: 1px solid #2c2f3a;
          transition: all 0.2s ease;
        }

        .mobile-nav-icon {
          font-size: 20px;
          min-width: 28px;
          transition: transform 0.2s ease;
        }

        .mobile-nav-link:hover .mobile-nav-icon { transform: scale(1.1); }

        .mobile-nav-link:hover,
        .mobile-nav-link.active {
          color: #aa00ff;
          transform: translateX(5px);
        }

        .mobile-submenu { margin-top: 0; }
        .submenu-category { margin-bottom: 24px; }

        .category-title {
          color: #aa00ff;
          font-size: 14px;
          font-weight: 600;
          margin-bottom: 8px;
          padding-bottom: 4px;
          border-bottom: 1px solid #2c2f3a;
          text-shadow: 0 0 15px #aa00ff;
          letter-spacing: 1px;
        }

        .submenu-category .mobile-nav-link {
          padding: 12px 0 12px 16px;
          font-size: 16px;
          border-bottom: none;
          gap: 12px;
        }

        .submenu-category .mobile-nav-link .mobile-nav-icon {
          font-size: 18px;
          min-width: 24px;
        }

        .mobile-server-info {
          margin-bottom: 24px;
          padding-bottom: 16px;
          border-bottom: 1px solid #2c2f3a;
        }

        .mobile-server-details {
          display: flex;
          align-items: center;
          gap: 12px;
          background: linear-gradient(135deg, #1a1c24 0%, #14161c 100%);
          padding: 12px;
          border-radius: 12px;
          border: 1px solid #2c2f3a;
          transition: all 0.2s ease;
        }

        .mobile-server-avatar {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          object-fit: cover;
          border: 2px solid #aa00ff;
        }

        .mobile-server-avatar-placeholder {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: linear-gradient(135deg, #2a2a2a 0%, #1a1c24 100%);
          border: 2px solid #aa00ff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          font-weight: 600;
          color: #aa00ff;
        }

        .mobile-server-text { flex: 1; min-width: 0; }

        .mobile-server-name {
          color: #ffffff;
          font-size: 15px;
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          margin-bottom: 4px;
        }

        .mobile-server-edit { font-size: 12px; }

        .mobile-edit-link {
          color: #aa00ff;
          text-decoration: none;
          font-size: 12px;
          transition: all 0.2s ease;
        }

        .mobile-edit-link:hover {
          text-decoration: underline;
          text-shadow: 0 0 8px #aa00ff;
        }

        .mobile-server-loading {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          color: #b0b0b0;
          font-size: 14px;
          padding: 16px;
          background: #1a1c24;
          border-radius: 12px;
          border: 1px solid #2c2f3a;
        }

        .loading-spinner-small {
          width: 16px;
          height: 16px;
          border: 2px solid #2a2a2a;
          border-top: 2px solid #aa00ff;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }

        .mobile-server-not-found {
          color: #b0b0b0;
          font-size: 14px;
          padding: 16px;
          text-align: center;
          background: #1a1c24;
          border-radius: 12px;
          border: 1px solid #2c2f3a;
        }

        .menu-button,
        .mobile-logo-container,
        .back-button,
        .close-menu,
        .mobile-nav-link,
        .mobile-edit-link {
          outline: none !important;
          -webkit-tap-highlight-color: transparent !important;
        }

        .menu-button:focus,
        .mobile-logo-container:focus,
        .back-button:focus,
        .close-menu:focus,
        .mobile-nav-link:focus,
        .mobile-edit-link:focus {
          outline: none !important;
        }

        @media (max-width: 768px) {
          header { padding: 0; }
          .desktop-header { display: none; }
          .mobile-header { display: flex; }
        }

        @media (max-width: 480px) {
          .mobile-logo-text {
            font-size: 22px;
            letter-spacing: 1.8px;
            -webkit-text-stroke: 1.5px #000000;
            text-stroke: 1.5px #000000;
            text-shadow: 0 0 12px #aa00ff;
          }

          .samsung-logo-text {
            font-size: 22px !important;
            -webkit-text-stroke: 1.5px #000000 !important;
            text-stroke: 1.5px #000000 !important;
            text-shadow: 0 0 12px #aa00ff !important;
            letter-spacing: 1.8px !important;
          }

          .mobile-logo-container .logo-image { width: 28px; }
          .mobile-logo-container.samsung-only .logo-image { width: 28px; }
          .mobile-menu { width: 75%; }

          .back-button, .close-menu { width: 44px; height: 44px; }
          .back-button-inner { width: 36px; height: 36px; }
          .back-arrow { width: 20px; height: 20px; }

          .mobile-server-avatar,
          .mobile-server-avatar-placeholder {
            width: 40px;
            height: 40px;
            font-size: 18px;
          }

          .mobile-server-name { font-size: 14px; }
          .mobile-nav-link { padding: 14px 0; font-size: 16px; }
          .mobile-nav-icon { font-size: 18px; min-width: 24px; }
          .submenu-category .mobile-nav-link { padding: 10px 0 10px 12px; font-size: 14px; }
          .submenu-category .mobile-nav-link .mobile-nav-icon { font-size: 16px; min-width: 22px; }
        }
      `}</style>
    </>
  );
};

export default NavBar;