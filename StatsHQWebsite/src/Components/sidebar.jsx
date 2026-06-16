import React, { useState, useEffect } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

const DashboardSidebar = ({ 
  currentServerId, 
  topOffset = "80px",
  isPublicMode = false,
  publicGuildId = null 
}) => {
  const [currentPage, setCurrentPage] = useState("");
  const [serverInfo, setServerInfo] = useState(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const [isFadingOut, setIsFadingOut] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tooltipTimer, setTooltipTimer] = useState(null);
  const [fadeOutTimer, setFadeOutTimer] = useState(null);
  const [isPrivileged, setIsPrivileged] = useState(false);

  const fetchedRef = React.useRef(false);

  useEffect(() => {
    const styleId = 'dashboard-sidebar-styles';
    const existing = document.getElementById(styleId);
    if (existing) existing.remove();

    const styleEl = document.createElement('style');
    styleEl.id = styleId;
    styleEl.textContent = `
      @font-face {
        font-family: 'Horndon';
        src: url('/HorndonD.ttf') format('truetype');
        font-display: swap;
        font-weight: normal;
        font-style: normal;
      }

      .dashboard-sidebar {
        position: fixed;
        left: 0;
        width: 20%;
        min-width: 250px;
        max-width: 300px;
        height: calc(100vh - ${topOffset});
        background-color: #0a0b12;
        border-right: 1px solid #2a2a2a;
        overflow-y: auto;
        z-index: 900;
        display: flex;
        flex-direction: column;
        box-shadow: 2px 0 10px rgba(0, 0, 0, 0.3);
      }

      .dashboard-sidebar .sidebar-header {
        padding: 24px 20px 16px;
        border-bottom: 1px solid #2a2a2a;
      }

      .dashboard-sidebar .sidebar-title {
        color: #aa00ff !important;
        font-size: 24px !important;
        font-weight: 600 !important;
        margin: 0 !important;
        text-shadow: 0 0 15px #aa00ff !important;
        letter-spacing: 2px !important;
        font-family: 'Horndon', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        position: relative !important;
        display: inline-block !important;
      }

      .dashboard-sidebar .sidebar-title::after {
        content: '';
        position: absolute;
        bottom: -8px;
        left: 0;
        width: 40px;
        height: 3px;
        background-color: #aa00ff;
        border-radius: 2px;
        transition: width 0.3s ease;
      }

      .dashboard-sidebar .sidebar-title:hover::after { width: 100%; }

      .dashboard-sidebar .server-info-container {
        padding: 20px;
        border-bottom: 1px solid #2a2a2a;
      }

      .dashboard-sidebar .server-info-box {
        background-color: #1a1c24 !important;
        border-radius: 12px !important;
        padding: 16px !important;
        border: 1px solid #2a2a2a !important;
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
        cursor: pointer !important;
        position: relative !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
        min-height: 80px !important;
      }

      .dashboard-sidebar .server-info-box:hover {
        border-color: #aa00ff !important;
        box-shadow: 0 4px 16px rgba(170, 0, 255, 0.2) !important;
        transform: translateY(-2px) !important;
        background-color: #22242e !important;
      }

      .dashboard-sidebar .server-info-box:active { transform: translateY(0) !important; }

      .dashboard-sidebar .server-avatar {
        width: 48px !important;
        height: 48px !important;
        border-radius: 50% !important;
        object-fit: cover !important;
        border: 2px solid #aa00ff !important;
        transition: all 0.2s ease !important;
      }

      .dashboard-sidebar .server-info-box:hover .server-avatar {
        box-shadow: 0 0 15px rgba(170, 0, 255, 0.3) !important;
      }

      .dashboard-sidebar .server-avatar-placeholder {
        width: 48px !important;
        height: 48px !important;
        border-radius: 50% !important;
        background: linear-gradient(135deg, #2a2a2a 0%, #1a1c24 100%) !important;
        border: 2px solid #aa00ff !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 24px !important;
        font-weight: 600 !important;
        color: #aa00ff !important;
        text-shadow: 0 0 10px #aa00ff !important;
        transition: all 0.2s ease !important;
      }

      .dashboard-sidebar .server-info-box:hover .server-avatar-placeholder {
        box-shadow: 0 0 15px rgba(170, 0, 255, 0.3) !important;
      }

      .dashboard-sidebar .server-details { flex: 1 !important; min-width: 0 !important; }

      .dashboard-sidebar .server-name {
        color: #ffffff !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        margin-bottom: 4px !important;
      }

      .dashboard-sidebar .server-members { color: #b0b0b0 !important; font-size: 13px !important; }

      .dashboard-sidebar .server-loading {
        color: #b0b0b0 !important;
        font-size: 14px !important;
        text-align: center !important;
        width: 100% !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 8px !important;
      }

      .dashboard-sidebar .loading-spinner-small {
        width: 16px !important;
        height: 16px !important;
        border: 2px solid #2a2a2a !important;
        border-top: 2px solid #aa00ff !important;
        border-radius: 50% !important;
        animation: sidebar-spin 0.8s linear infinite !important;
      }

      @keyframes sidebar-spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }

      .dashboard-sidebar .server-not-found {
        color: #b0b0b0 !important;
        font-size: 14px !important;
        padding: 8px 0 !important;
        text-align: center !important;
        width: 100% !important;
      }

      .dashboard-sidebar .server-tooltip {
        position: absolute !important;
        bottom: 100% !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        background-color: #1a1c24 !important;
        border: 1px solid #aa00ff !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        margin-bottom: 12px !important;
        white-space: nowrap !important;
        color: #ffffff !important;
        font-size: 14px !important;
        box-shadow: 0 4px 20px rgba(170, 0, 255, 0.3) !important;
        z-index: 1000 !important;
        pointer-events: auto !important;
      }

      .dashboard-sidebar .server-tooltip.fade-in {
        animation: sidebar-fadeIn 0.3s ease forwards !important;
      }

      .dashboard-sidebar .server-tooltip.fade-out {
        animation: sidebar-fadeOut 0.3s ease forwards !important;
      }

      .dashboard-sidebar .server-tooltip::after {
        content: '';
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border-width: 8px;
        border-style: solid;
        border-color: #aa00ff transparent transparent transparent;
      }

      @keyframes sidebar-fadeIn {
        from { opacity: 0; transform: translateX(-50%) translateY(10px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
      }

      @keyframes sidebar-fadeOut {
        from { opacity: 1; transform: translateX(-50%) translateY(0); }
        to { opacity: 0; transform: translateX(-50%) translateY(-10px); }
      }

      .dashboard-sidebar .tooltip-link {
        color: #aa00ff !important;
        text-decoration: none !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
      }

      .dashboard-sidebar .tooltip-link:hover {
        text-decoration: underline !important;
        text-shadow: 0 0 8px #aa00ff !important;
      }

      .dashboard-sidebar .sidebar-nav {
        flex: 1 !important;
        padding: 20px !important;
        overflow-y: auto !important;
      }

      .dashboard-sidebar .nav-section { margin-bottom: 32px !important; }

      .dashboard-sidebar .section-title {
        color: #ffffff !important;
        font-size: 18px !important;
        font-weight: 700 !important;
        margin: 0 0 12px 0 !important;
        padding-bottom: 8px !important;
        border-bottom: 1px solid #2a2a2a !important;
        text-shadow: 0 0 20px #aa00ff, 0 0 40px #aa00ff !important;
        letter-spacing: 2px !important;
        text-transform: uppercase !important;
        position: relative !important;
        display: inline-block !important;
        width: 100% !important;
      }

      .dashboard-sidebar .section-title::after {
        content: '';
        position: absolute;
        bottom: -8px;
        left: 0;
        width: 30px;
        height: 3px;
        background-color: #ffffff;
        border-radius: 2px;
        transition: width 0.3s ease;
        box-shadow: 0 0 10px #aa00ff, 0 0 20px #aa00ff;
      }

      .dashboard-sidebar .section-title:hover::after { width: 100%; }

      .dashboard-sidebar .nav-item {
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
        color: #ffffff !important;
        text-decoration: none !important;
        padding: 12px 16px !important;
        margin-bottom: 4px !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
        font-size: 15px !important;
        border-left: 3px solid transparent !important;
        background-color: transparent !important;
      }

      .dashboard-sidebar .nav-item:hover {
        background-color: #1a1c24 !important;
        color: #aa00ff !important;
        transform: translateX(4px) !important;
        border-left-color: #aa00ff !important;
      }

      .dashboard-sidebar .nav-item.active {
        background-color: #1a1c24 !important;
        color: #aa00ff !important;
        border-left: 3px solid #aa00ff !important;
        font-weight: 600 !important;
        box-shadow: 0 0 15px rgba(170, 0, 255, 0.1) !important;
      }

      .dashboard-sidebar .nav-icon {
        font-size: 20px !important;
        min-width: 24px !important;
        transition: transform 0.2s ease !important;
      }

      .dashboard-sidebar .nav-item:hover .nav-icon { transform: scale(1.1) !important; }

      .dashboard-sidebar .privileged-indicator {
        margin: 16px 20px 20px !important;
        padding: 10px 12px !important;
        background: linear-gradient(135deg, rgba(255, 215, 0, 0.15), rgba(255, 215, 0, 0.05)) !important;
        border: 1px solid rgba(255, 215, 0, 0.3) !important;
        border-radius: 8px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 8px !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        color: #ffd700 !important;
        text-shadow: 0 0 5px rgba(255, 215, 0, 0.3) !important;
      }

      .dashboard-sidebar .privileged-icon { font-size: 14px !important; }
      .dashboard-sidebar .privileged-text { letter-spacing: 0.5px !important; }

      .dashboard-sidebar::-webkit-scrollbar { width: 8px; }
      .dashboard-sidebar::-webkit-scrollbar-track { background: #0a0b12; }
      .dashboard-sidebar::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 4px; }
      .dashboard-sidebar::-webkit-scrollbar-thumb:hover { background: #aa00ff; }

      @media (max-width: 1024px) { .dashboard-sidebar { width: 250px !important; } }

      @media (max-width: 768px) {
        .dashboard-sidebar {
          transform: translateX(-100%);
          transition: transform 0.3s ease;
        }
        .dashboard-sidebar.mobile-open { transform: translateX(0); }
      }
    `;
    document.head.appendChild(styleEl);

    return () => {
      const el = document.getElementById(styleId);
      if (el) el.remove();
    };
  }, [topOffset]);

  const checkPrivilegedStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json', 'Cache-Control': 'no-cache' }
      });
      if (response.ok) {
        const authData = await response.json();
        if (authData.authenticated && authData.user) {
          setIsPrivileged(PRIVILEGED_USERS.includes(authData.user.id));
        }
      }
    } catch (error) {
      console.error('Error checking privileged status:', error);
      setIsPrivileged(false);
    }
  };

  useEffect(() => {
    const rawPath = window.location.pathname;
    const path = decodeURIComponent(rawPath);
    
    if (path.includes('/Dashboard/Messages')) setCurrentPage('messages');
    else if (path.includes('/Dashboard/Voice Activity')) setCurrentPage('voice-activity');
    else if (path.includes('/Dashboard/Activity')) setCurrentPage('activity');
    else if (path.includes('/Dashboard/Distribution')) setCurrentPage('distribution');
    else if (path.includes('/Dashboard/Emoji Tracking')) setCurrentPage('emojis');
    else if (path.includes('/Dashboard/Invite Tracking')) setCurrentPage('invites');
    else if (path.includes('/Dashboard/Mentions')) setCurrentPage('mentions');
    else if (path.includes('/Dashboard/Growth')) setCurrentPage('growth');
    else if (path.includes('/Dashboard/Settings')) setCurrentPage('settings');
    else if (path.includes('/Dashboard/Blacklist')) setCurrentPage('blacklist');
    else if (path.includes('/Dashboard/Reset')) setCurrentPage('reset');
    else if (path.includes('/Dashboard/Debug')) setCurrentPage('debug');
    else if (path.includes('/Dashboard/Subscriptions')) setCurrentPage('subscriptions');
  }, []);

  useEffect(() => { checkPrivilegedStatus(); }, []);

  useEffect(() => {
    if (isPublicMode) {
      setServerInfo({
        id: publicGuildId || "1424021358680998022",
        name: "StatsHQ",
        member_count: null,
        icon: null,
        avatarUrl: null
      });
      setLoading(false);
      return;
    }

    if (!currentServerId) { setLoading(false); return; }

    if (fetchedRef.current && serverInfo?.id === currentServerId) return;

    const fetchServerInfo = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/user/servers`, {
          credentials: 'include',
          headers: { 'Accept': 'application/json', 'Cache-Control': 'no-cache' }
        });
        if (response.ok) {
          const servers = await response.json();
          const server = servers?.find(s => s.id === currentServerId);
          if (server) {
            setServerInfo({
              ...server,
              avatarUrl: server.icon 
                ? `https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png?size=256` 
                : null
            });
            fetchedRef.current = true;
          } else {
            setServerInfo(null);
          }
        } else {
          setServerInfo(null);
        }
      } catch (error) {
        console.error('Sidebar error fetching server info:', error);
        setServerInfo(null);
      } finally {
        setLoading(false);
      }
    };

    fetchServerInfo();
  }, [currentServerId, isPublicMode, publicGuildId]);

  const handleManageServersClick = (e) => {
    e.preventDefault();
    window.location.href = '/Manage Servers/';
  };

  const startFadeOut = () => {
    setIsFadingOut(true);
    if (fadeOutTimer) clearTimeout(fadeOutTimer);
    const timer = setTimeout(() => {
      setShowTooltip(false);
      setIsFadingOut(false);
      setFadeOutTimer(null);
    }, 300);
    setFadeOutTimer(timer);
  };

  const showTooltipWithTimer = () => {
    if (tooltipTimer) clearTimeout(tooltipTimer);
    if (fadeOutTimer) { clearTimeout(fadeOutTimer); setFadeOutTimer(null); }
    if (isFadingOut) setIsFadingOut(false);
    setShowTooltip(true);
    const timer = setTimeout(() => {
      startFadeOut();
      setTooltipTimer(null);
    }, 1500);
    setTooltipTimer(timer);
  };

  return (
    <div className="dashboard-sidebar" style={{ top: topOffset }}>
      <div className="sidebar-header">
        <h2 className="sidebar-title">DASHBOARD</h2>
      </div>
      
      <div className="server-info-container">
        <div 
          className="server-info-box"
          onMouseEnter={showTooltipWithTimer}
          onClick={showTooltipWithTimer}
        >
          {loading ? (
            <div className="server-loading">
              <div className="loading-spinner-small"></div>
              <span>Loading server...</span>
            </div>
          ) : serverInfo ? (
            <>
              {serverInfo.avatarUrl ? (
                <img 
                  src={serverInfo.avatarUrl} 
                  alt={serverInfo.name}
                  className="server-avatar"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.style.display = 'none';
                    if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                  }}
                />
              ) : (
                <div className="server-avatar-placeholder">
                  {serverInfo.name?.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="server-details">
                <div className="server-name">{serverInfo.name}</div>
                {serverInfo.member_count && (
                  <div className="server-members">
                    {serverInfo.member_count.toLocaleString()} members
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="server-not-found">No server selected</div>
          )}
          
          {showTooltip && serverInfo && (
            <div className={`server-tooltip ${isFadingOut ? 'fade-out' : 'fade-in'}`}>
              You can edit the server in{' '}
              <a 
                href="/Manage Servers/"
                onClick={handleManageServersClick}
                className="tooltip-link"
              >
                Manage Servers
              </a>
            </div>
          )}
        </div>
      </div>
      
      <nav className="sidebar-nav">
        <div className="nav-section">
          <h3 className="section-title">ANALYTICS</h3>
          <a href="/Dashboard/Messages/" className={`nav-item ${currentPage === 'messages' ? 'active' : ''}`}>
            <span className="nav-icon">💬</span>Messages
          </a>
          <a href="/Dashboard/Voice Activity/" className={`nav-item ${currentPage === 'voice-activity' ? 'active' : ''}`}>
            <span className="nav-icon">🔊</span>Voice Activity
          </a>
          <a href="/Dashboard/Activity/" className={`nav-item ${currentPage === 'activity' ? 'active' : ''}`}>
            <span className="nav-icon">🎮</span>Status Activity
          </a>
          <a href="/Dashboard/Distribution/" className={`nav-item ${currentPage === 'distribution' ? 'active' : ''}`}>
            <span className="nav-icon">📊</span>Distribution
          </a>
          <a href="/Dashboard/Emoji Tracking/" className={`nav-item ${currentPage === 'emojis' ? 'active' : ''}`}>
            <span className="nav-icon">😊</span>Emojis
          </a>
          <a href="/Dashboard/Invite Tracking/" className={`nav-item ${currentPage === 'invites' ? 'active' : ''}`}>
            <span className="nav-icon">📨</span>Invites
          </a>
          <a href="/Dashboard/Mentions/" className={`nav-item ${currentPage === 'mentions' ? 'active' : ''}`}>
            <span className="nav-icon">🔔</span>Mentions
          </a>
          <a href="/Dashboard/Growth/" className={`nav-item ${currentPage === 'growth' ? 'active' : ''}`}>
            <span className="nav-icon">📈</span>Growth
          </a>
        </div>
        
        <div className="nav-section">
          <h3 className="section-title">OPTIMIZATION</h3>
          <a href="/Dashboard/Settings/" className={`nav-item ${currentPage === 'settings' ? 'active' : ''}`}>
            <span className="nav-icon">⚙️</span>Settings
          </a>
          <a href="/Dashboard/Blacklist/" className={`nav-item ${currentPage === 'blacklist' ? 'active' : ''}`}>
            <span className="nav-icon">🚫</span>Blacklist
          </a>
          <a href="/Dashboard/Reset/" className={`nav-item ${currentPage === 'reset' ? 'active' : ''}`}>
            <span className="nav-icon">🗑️</span>Reset Stats
          </a>
          <a href="/Dashboard/Subscriptions/" className={`nav-item ${currentPage === 'subscriptions' ? 'active' : ''}`}>
            <span className="nav-icon">💎</span>Subscriptions
          </a>
          {isPrivileged && (
            <a href="/Dashboard/Debug/" className={`nav-item ${currentPage === 'debug' ? 'active' : ''}`}>
              <span className="nav-icon">🐛</span>Debug
            </a>
          )}
        </div>
      </nav>

      {isPrivileged && (
        <div className="privileged-indicator">
          <span className="privileged-icon">👑</span>
          <span className="privileged-text">Privileged Access</span>
        </div>
      )}
    </div>
  );
};

export default DashboardSidebar;