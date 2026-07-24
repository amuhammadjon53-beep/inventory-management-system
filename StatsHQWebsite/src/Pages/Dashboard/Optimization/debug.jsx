import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const NAVBAR_HEIGHT = "80px";

const styles = `
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

  .navbar .logo span:last-child {
    font-family: 'Horndon', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    font-weight: normal;
    letter-spacing: 0.5px;
  }

  html, body, #app {
    min-height: 100vh;
    background-color: #0a0a0a;
    color: #ffffff;
  }

  .dashboard-page {
    max-width: 100%;
    margin: 0 auto;
    background-color: #0a0a0a;
    min-height: 100vh;
    display: flex;
    position: relative;
  }

  .dashboard-main {
    flex: 1;
    margin-left: 280px;
    background-color: #0a0a0a;
    min-height: calc(100vh - ${NAVBAR_HEIGHT});
  }

  .dashboard-content {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px 40px 40px 40px;
  }

  .page-header {
    margin-bottom: 30px;
  }

  .page-title {
    font-size: 32px;
    font-weight: 700;
    background: linear-gradient(135deg, #ffffff, #aa00ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 8px;
  }

  .page-subtitle {
    color: #b0b0b0;
    font-size: 14px;
  }

  .debug-section {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 32px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 16px;
  }

  .section-title {
    color: #aa00ff;
    font-size: 20px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .section-title::before {
    content: '';
    width: 4px;
    height: 24px;
    background-color: #aa00ff;
    border-radius: 2px;
  }

  /* Critical Permissions Checklist */
  .critical-permissions-card {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border: 2px solid #aa00ff;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 24px;
  }

  .checklist-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
  }

  .checklist-title {
    font-size: 18px;
    font-weight: 700;
    color: #aa00ff;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .score-badge {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    padding: 8px 16px;
    border-radius: 40px;
    font-size: 14px;
    font-weight: 700;
    color: white;
  }

  .score-badge.good {
    background: linear-gradient(135deg, #00c851, #007e33);
  }

  .score-badge.warning {
    background: linear-gradient(135deg, #ffaa00, #ff8800);
  }

  .score-badge.bad {
    background: linear-gradient(135deg, #ff4444, #cc0000);
  }

  .checklist-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
  }

  .checklist-item {
    background-color: #0a0a0a;
    border-radius: 10px;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: all 0.2s ease;
  }

  .checklist-item.highlight {
    border-left: 3px solid #aa00ff;
  }

  .checklist-item.granted {
    background-color: rgba(0, 200, 81, 0.1);
  }

  .checklist-item.missing {
    background-color: rgba(255, 68, 68, 0.05);
  }

  .checklist-info {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .checklist-icon {
    font-size: 20px;
  }

  .checklist-name {
    font-weight: 600;
    color: #ffffff;
  }

  .checklist-desc {
    font-size: 11px;
    color: #888;
  }

  .checklist-status {
    font-size: 24px;
  }

  .checklist-status.granted {
    color: #00c851;
  }

  .checklist-status.missing {
    color: #ff4444;
  }

  /* Regular Permissions Grid */
  .permissions-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
    margin-top: 16px;
  }

  .permission-item {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 12px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.2s ease;
  }

  .permission-item:hover {
    border-color: #aa00ff;
    transform: translateX(4px);
  }

  .permission-item.critical {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-left: 3px solid #aa00ff;
  }

  .permission-name {
    color: #ffffff;
    font-size: 13px;
    font-weight: 500;
    font-family: monospace;
  }

  .permission-value {
    color: #aa00ff;
    font-size: 12px;
    font-family: monospace;
    background-color: #0a0a0a;
    padding: 4px 8px;
    border-radius: 6px;
  }

  .admin-badge {
    background: linear-gradient(135deg, #ff4444, #cc0000);
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
  }

  .lookup-container {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
  }

  .lookup-box {
    flex: 1;
    min-width: 300px;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 20px;
  }

  .lookup-box h3 {
    color: #ffffff;
    font-size: 16px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .lookup-input-group {
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
  }

  .lookup-input {
    flex: 1;
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 10px 14px;
    color: #ffffff;
    font-size: 14px;
    font-family: monospace;
    outline: none;
    transition: all 0.2s ease;
  }

  .lookup-input:focus {
    border-color: #aa00ff;
  }

  .lookup-button {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .lookup-button:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
  }

  .lookup-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .lookup-result {
    margin-top: 16px;
    padding: 16px;
    background-color: #0a0a0a;
    border-radius: 10px;
    border-left: 3px solid #aa00ff;
  }

  .lookup-result h4 {
    color: #aa00ff;
    font-size: 14px;
    margin-bottom: 12px;
  }

  .lookup-error {
    margin-top: 16px;
    padding: 12px;
    background-color: rgba(255, 68, 68, 0.1);
    border: 1px solid #ff4444;
    border-radius: 8px;
    color: #ff8888;
    font-size: 13px;
  }

  .channel-info, .category-info, .user-settings-info {
    font-size: 13px;
    line-height: 1.6;
  }

  .channel-info p, .category-info p, .user-settings-info p {
    margin: 6px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .channel-info strong, .category-info strong, .user-settings-info strong {
    color: #aa00ff;
    min-width: 120px;
  }

  /* User Settings Lookup */
  .user-profile-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
    padding-bottom: 14px;
    border-bottom: 1px solid #1a1a1a;
  }

  .user-avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    object-fit: cover;
  }

  .user-avatar-fallback {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    font-weight: 700;
    color: white;
    flex-shrink: 0;
  }

  .user-profile-names {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .user-display-name {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
  }

  .user-username {
    font-size: 12px;
    color: #888;
    font-family: monospace;
  }

  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }

  .status-pill.on {
    background-color: rgba(255, 68, 68, 0.15);
    color: #ff6b6b;
  }

  .status-pill.off {
    background-color: rgba(0, 200, 81, 0.15);
    color: #00c851;
  }

  .status-pill.pending {
    background-color: rgba(255, 170, 0, 0.15);
    color: #ffaa00;
  }

  .not-in-guild-badge {
    background-color: rgba(255, 170, 0, 0.15);
    color: #ffaa00;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
    margin-left: 8px;
  }

  .channels-list {
    margin-top: 12px;
    max-height: 300px;
    overflow-y: auto;
  }

  .channel-item {
    background-color: #1a1a1a;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .channel-item.visible {
    border-left: 3px solid #00c851;
  }

  .channel-item.hidden {
    border-left: 3px solid #ff4444;
    opacity: 0.7;
  }

  .channel-name {
    color: #ffffff;
    font-weight: 500;
  }

  .channel-type {
    font-size: 11px;
    color: #888;
    background-color: #0a0a0a;
    padding: 2px 8px;
    border-radius: 12px;
  }

  .roles-table-wrapper {
    overflow-x: auto;
    margin-top: 16px;
  }

  .roles-table {
    width: 100%;
    border-collapse: collapse;
  }

  .roles-table th,
  .roles-table td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid #1a1a1a;
  }

  .roles-table th {
    background-color: #0f0f0f;
    color: #aa00ff;
    font-weight: 600;
    font-size: 13px;
  }

  .roles-table tr:hover {
    background-color: #1a1a1a;
  }

  .role-color-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 10px;
    vertical-align: middle;
  }

  .bot-role-badge {
    background-color: #aa00ff;
    color: white;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
    margin-left: 8px;
  }

  .everyone-badge {
    background-color: #666;
    color: white;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
    margin-left: 8px;
  }

  .role-hierarchy-note {
    margin-top: 16px;
    padding: 12px;
    background-color: rgba(170, 0, 255, 0.1);
    border-radius: 8px;
    font-size: 12px;
    color: #b0b0b0;
    text-align: center;
  }

  .loading-container {
    text-align: center;
    padding: 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
  }

  .loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #2a2a2a;
    border-top-color: #aa00ff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 20px;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .no-server {
    text-align: center;
    padding: 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    color: #b0b0b0;
  }

  .invite-button, .login-button {
    display: inline-block;
    background-color: #aa00ff;
    color: white;
    padding: 12px 28px;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 600;
    margin-top: 20px;
  }

  @media (max-width: 1024px) {
    .dashboard-main {
      margin-left: 250px;
    }
    .dashboard-content {
      padding: 20px;
    }
  }

  @media (max-width: 768px) {
    .dashboard-main {
      margin-left: 0;
    }
    .dashboard-content {
      padding: 16px;
    }
    .permissions-grid {
      grid-template-columns: 1fr;
    }
    .lookup-container {
      flex-direction: column;
    }
    .checklist-grid {
      grid-template-columns: 1fr;
    }
    .roles-table th, .roles-table td {
      padding: 8px 12px;
      font-size: 12px;
    }
  }
`;

const LoadingSpinner = ({ text = "Loading..." }) => (
  <div className="loading-container">
    <div className="loading-spinner"></div>
    <p style={{ color: '#b0b0b0' }}>{text}</p>
  </div>
);

const DebugDashboard = () => {
  const [currentServer, setCurrentServer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [apiError, setApiError] = useState(null);
  
  const [permissions, setPermissions] = useState(null);
  const [loadingPermissions, setLoadingPermissions] = useState(true);
  
  const [channelId, setChannelId] = useState("");
  const [channelResult, setChannelResult] = useState(null);
  const [loadingChannel, setLoadingChannel] = useState(false);
  const [channelError, setChannelError] = useState(null);
  
  const [categoryId, setCategoryId] = useState("");
  const [categoryResult, setCategoryResult] = useState(null);
  const [loadingCategory, setLoadingCategory] = useState(false);
  const [categoryError, setCategoryError] = useState(null);

  // User Settings Lookup
  const [userLookupId, setUserLookupId] = useState("");
  const [userLookupResult, setUserLookupResult] = useState(null);
  const [loadingUserLookup, setLoadingUserLookup] = useState(false);
  const [userLookupError, setUserLookupError] = useState(null);
  
  const [roles, setRoles] = useState(null);
  const [loadingRoles, setLoadingRoles] = useState(true);

  // Critical permissions checklist
  const criticalPermissions = [
    { name: "SEND_MESSAGES", display: "Send Messages", description: "Send messages in channels", required: true },
    { name: "EMBED_LINKS", display: "Embed Links", description: "Post embedded links", required: true },
    { name: "ATTACH_FILES", display: "Attach Files", description: "Upload files", required: true },
    { name: "READ_MESSAGE_HISTORY", display: "Read Message History", description: "View message history", required: true },
    { name: "VIEW_CHANNEL", display: "View Channels", description: "Required to see channels", required: true },
    { name: "USE_APPLICATION_COMMANDS", display: "Use Application Commands", description: "Use slash commands", required: true },
    { name: "MANAGE_GUILD", display: "Manage Server", description: "Manage server settings", required: true },
    { name: "MANAGE_ROLES", display: "Manage Roles", description: "Create/edit roles", required: true },
    { name: "MANAGE_CHANNELS", display: "Manage Channels", description: "Create/edit channels", required: true }
  ];

  // Grouped message permissions (Send Messages, Embed Links, Attach Files, Read Message History)
  const messagePermissions = ["SEND_MESSAGES", "EMBED_LINKS", "ATTACH_FILES", "READ_MESSAGE_HISTORY"];

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (currentServer) {
      fetchPermissions();
      fetchRoles();
    }
  }, [currentServer]);

  const loadInitialData = async () => {
    setLoadingServers(true);
    setApiError(null);
    try {
      const authResponse = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (!authResponse.ok) throw new Error('Auth failed');
      
      const authData = await authResponse.json();
      
      if (authData.authenticated && authData.user) {
        setIsAuthenticated(true);
        
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
              setCurrentServer(selectedServer);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error loading initial data:', error);
      setApiError('Failed to load servers. Please check your connection.');
    } finally {
      setLoadingServers(false);
      setLoading(false);
    }
  };

  const fetchPermissions = async () => {
    if (!currentServer) return;
    
    setLoadingPermissions(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/debug/bot-permissions/${currentServer.id}`, {
        credentials: 'include'
      });
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        setPermissions(data);
      } else {
        setPermissions({ error: data.error, success: false });
      }
    } catch (error) {
      console.error('Error fetching permissions:', error);
      setPermissions({ error: error.message, success: false });
    } finally {
      setLoadingPermissions(false);
    }
  };

  const fetchRoles = async () => {
    if (!currentServer) return;
    
    setLoadingRoles(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/debug/roles/${currentServer.id}`, {
        credentials: 'include'
      });
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        setRoles(data);
      } else {
        setRoles({ error: data.error, success: false });
      }
    } catch (error) {
      console.error('Error fetching roles:', error);
      setRoles({ error: error.message, success: false });
    } finally {
      setLoadingRoles(false);
    }
  };

  const handleChannelLookup = async () => {
    if (!channelId.trim() || !currentServer) {
      setChannelError("Please enter a channel ID");
      return;
    }
    
    if (!/^\d+$/.test(channelId.trim())) {
      setChannelError("❌ Invalid ID format. Channel IDs should contain only numbers.");
      return;
    }
    
    setLoadingChannel(true);
    setChannelError(null);
    setChannelResult(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/debug/find-channel/${currentServer.id}/${channelId.trim()}`, {
        credentials: 'include'
      });
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        if (data.channel_found) {
          setChannelResult(data);
        } else {
          setChannelError(`❌ Channel with ID ${channelId.trim()} was not found in this server.`);
        }
      } else if (response.status === 403 || data.error?.includes("403")) {
        setChannelError(`🔒 Bot doesn't have permission to access channel ID ${channelId.trim()}.`);
      } else {
        setChannelError(data.error || "Failed to lookup channel");
      }
    } catch (error) {
      console.error('Error looking up channel:', error);
      setChannelError("Failed to lookup channel. Please check your connection.");
    } finally {
      setLoadingChannel(false);
    }
  };

  const handleCategoryLookup = async () => {
    if (!categoryId.trim() || !currentServer) {
      setCategoryError("Please enter a category ID");
      return;
    }
    
    if (!/^\d+$/.test(categoryId.trim())) {
      setCategoryError("❌ Invalid ID format. Category IDs should contain only numbers.");
      return;
    }
    
    setLoadingCategory(true);
    setCategoryError(null);
    setCategoryResult(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/debug/find-category/${currentServer.id}/${categoryId.trim()}`, {
        credentials: 'include'
      });
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        if (data.category_found) {
          setCategoryResult(data);
        } else {
          setCategoryError(`❌ Category with ID ${categoryId.trim()} was not found in this server.`);
        }
      } else if (response.status === 403 || data.error?.includes("403")) {
        setCategoryError(`🔒 Bot doesn't have permission to access category ID ${categoryId.trim()}.`);
      } else {
        setCategoryError(data.error || "Failed to lookup category");
      }
    } catch (error) {
      console.error('Error looking up category:', error);
      setCategoryError("Failed to lookup category. Please check your connection.");
    } finally {
      setLoadingCategory(false);
    }
  };

  const handleUserLookup = async () => {
    if (!userLookupId.trim() || !currentServer) {
      setUserLookupError("Please enter a user ID");
      return;
    }

    if (!/^\d+$/.test(userLookupId.trim())) {
      setUserLookupError("❌ Invalid ID format. User IDs should contain only numbers.");
      return;
    }

    setLoadingUserLookup(true);
    setUserLookupError(null);
    setUserLookupResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/debug/user-settings/${currentServer.id}/${userLookupId.trim()}`, {
        credentials: 'include'
      });

      const data = await response.json();

      if (response.ok && data.success) {
        if (data.user_found) {
          setUserLookupResult(data);
        } else {
          setUserLookupError(`❌ No Discord user found with ID ${userLookupId.trim()}.`);
        }
      } else if (response.status === 403 || data.error?.includes("403")) {
        setUserLookupError(`🔒 Access denied looking up user ID ${userLookupId.trim()}.`);
      } else {
        setUserLookupError(data.error || "Failed to lookup user settings");
      }
    } catch (error) {
      console.error('Error looking up user settings:', error);
      setUserLookupError("Failed to lookup user settings. Please check your connection.");
    } finally {
      setLoadingUserLookup(false);
    }
  };

  const getUserAvatarUrl = (discordUser) => {
    if (!discordUser?.avatar) return null;
    return `https://cdn.discordapp.com/avatars/${discordUser.id}/${discordUser.avatar}.png?size=64`;
  };

  const getUserInitial = (discordUser) => {
    const name = discordUser?.global_name || discordUser?.username || "?";
    return name.charAt(0).toUpperCase();
  };

  const formatTimestamp = (ts) => {
    if (!ts) return null;
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  // Calculate critical permissions status
  const getCriticalPermissionsStatus = () => {
    if (!permissions?.granted_permissions) return { granted: [], missing: [], score: 0, total: 0 };
    
    const grantedPerms = new Set(permissions.granted_permissions.map(p => p.name));
    const hasAdministrator = permissions.has_administrator;
    
    // If bot has Administrator, all permissions are granted
    if (hasAdministrator) {
      return {
        granted: criticalPermissions,
        missing: [],
        score: criticalPermissions.length,
        total: criticalPermissions.length,
        hasAdmin: true
      };
    }
    
    const granted = [];
    const missing = [];
    
    for (const perm of criticalPermissions) {
      // Special handling for message permissions group
      if (perm.name === "SEND_MESSAGES") {
        // Check if all message permissions are granted
        const allMessagePerms = messagePermissions.every(p => grantedPerms.has(p));
        if (allMessagePerms) {
          granted.push({ ...perm, note: "All message permissions granted" });
        } else {
          const missingMessagePerms = messagePermissions.filter(p => !grantedPerms.has(p));
          missing.push({ 
            ...perm, 
            note: `Missing: ${missingMessagePerms.join(", ")}`
          });
        }
      } else if (grantedPerms.has(perm.name)) {
        granted.push(perm);
      } else {
        missing.push(perm);
      }
    }
    
    return {
      granted,
      missing,
      score: granted.length,
      total: criticalPermissions.length,
      hasAdmin: false
    };
  };

  const permStatus = getCriticalPermissionsStatus();
  const scorePercent = (permStatus.score / permStatus.total) * 100;
  let scoreClass = "bad";
  if (scorePercent >= 80) scoreClass = "good";
  else if (scorePercent >= 50) scoreClass = "warning";

  if (loadingServers || (isAuthenticated && !currentServer && !apiError && !loadingServers)) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <LoadingSpinner text="Loading servers..." />
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
              <div className="no-server">
                <h2>🔐 Please Log In</h2>
                <p>You need to be logged in to access the debug dashboard.</p>
                <a href={`${API_BASE_URL}/api/auth/discord`} className="login-button">Login with Discord</a>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>⚠️ Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => window.location.reload()} className="invite-button">Retry</button>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  if (!currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>📋 No Server Selected</h2>
                <p>Please select a server from the Manage Servers page to view debug information.</p>
                <a href="/Manage Servers/index.html" className="invite-button">Go to Manage Servers</a>
              </div>
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
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            <div className="page-header">
              <h1 className="page-title">🐛 Debug Dashboard</h1>
              <p className="page-subtitle">Server: {currentServer.name} (ID: {currentServer.id})</p>
            </div>
            
            {/* Critical Permissions Checklist */}
            <div className="debug-section">
              <div className="section-header">
                <h2 className="section-title">✅ Required Permissions Checklist</h2>
                {permissions?.has_administrator && (
                  <span className="admin-badge">⚠️ ADMINISTRATOR (All permissions granted)</span>
                )}
              </div>
              
              <div className="critical-permissions-card">
                <div className="checklist-header">
                  <div className="checklist-title">
                    <span>📋</span> Bot Permission Status
                  </div>
                  <div className={`score-badge ${scoreClass}`}>
                    {permStatus.score}/{permStatus.total} Required Permissions
                  </div>
                </div>
                
                <div className="checklist-grid">
                  {criticalPermissions.map((perm) => {
                    const granted = permStatus.granted.some(p => p.name === perm.name);
                    const isMissing = permStatus.missing.some(p => p.name === perm.name);
                    const missingInfo = permStatus.missing.find(p => p.name === perm.name);
                    
                    return (
                      <div key={perm.name} className={`checklist-item ${granted ? 'granted' : 'missing'} highlight`}>
                        <div className="checklist-info">
                          <span className="checklist-icon">{granted ? '✅' : '❌'}</span>
                          <div>
                            <div className="checklist-name">{perm.display}</div>
                            <div className="checklist-desc">{perm.description}</div>
                            {missingInfo?.note && (
                              <div className="checklist-desc" style={{ color: '#ffaa00' }}>{missingInfo.note}</div>
                            )}
                          </div>
                        </div>
                        <div className={`checklist-status ${granted ? 'granted' : 'missing'}`}>
                          {granted ? '✓' : '✗'}
                        </div>
                      </div>
                    );
                  })}
                </div>
                
                {permStatus.score === permStatus.total && !permissions?.has_administrator && (
                  <div className="lookup-success" style={{ marginTop: '16px', textAlign: 'center' }}>
                    🎉 Perfect! The bot has all required permissions!
                  </div>
                )}
                
                {permStatus.score < permStatus.total && !permissions?.has_administrator && (
                  <div className="lookup-warning" style={{ marginTop: '16px', textAlign: 'center' }}>
                    ⚠️ The bot is missing {permStatus.total - permStatus.score} required permission(s). Some features may not work correctly.
                  </div>
                )}
              </div>
              
              {loadingPermissions ? (
                <LoadingSpinner text="Loading permissions..." />
              ) : permissions?.success ? (
                <>
                  <div style={{ marginBottom: '16px', padding: '12px', backgroundColor: '#1a1a1a', borderRadius: '8px' }}>
                    <p><strong>Permissions Bitfield:</strong> <code style={{ color: '#aa00ff' }}>{permissions.permissions_bitfield}</code> ({permissions.permissions_bitfield_hex})</p>
                    <p><strong>Total Granted Permissions:</strong> {permissions.total_permissions_count}</p>
                  </div>
                  
                  <div className="permissions-grid">
                    {permissions.granted_permissions?.map((perm, idx) => {
                      const isCritical = criticalPermissions.some(cp => cp.name === perm.name) || 
                                        messagePermissions.includes(perm.name);
                      return (
                        <div key={idx} className={`permission-item ${isCritical ? 'critical' : ''}`}>
                          <span className="permission-name">{perm.name}</span>
                          <span className="permission-value">{perm.bitwise}</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="lookup-error">
                  Failed to load permissions: {permissions?.error || "Unknown error"}
                </div>
              )}
            </div>
            
            {/* Channel & Category Lookup Section */}
            <div className="debug-section">
              <h2 className="section-title">🔍 Lookup Tools</h2>
              <p style={{ color: '#888', fontSize: '13px', marginBottom: '20px' }}>
                Enter a Discord channel or category ID to see detailed information. 
                To get an ID, enable Developer Mode in Discord → Right-click → Copy ID
              </p>
              <div className="lookup-container">
                <div className="lookup-box">
                  <h3>📡 Channel Lookup</h3>
                  <div className="lookup-input-group">
                    <input
                      type="text"
                      className="lookup-input"
                      placeholder="Enter Channel ID"
                      value={channelId}
                      onChange={(e) => setChannelId(e.target.value)}
                    />
                    <button 
                      className="lookup-button" 
                      onClick={handleChannelLookup}
                      disabled={loadingChannel || !channelId.trim()}
                    >
                      {loadingChannel ? 'Searching...' : 'Lookup'}
                    </button>
                  </div>
                  
                  {channelError && (
                    <div className="lookup-error">{channelError}</div>
                  )}
                  
                  {channelResult?.channel_found && channelResult.channel && (
                    <div className="lookup-result">
                      <h4>✅ Channel Found</h4>
                      <div className="channel-info">
                        <p><strong>Name:</strong> #{channelResult.channel.name}</p>
                        <p><strong>ID:</strong> {channelResult.channel.id}</p>
                        <p><strong>Type:</strong> {channelResult.channel.type}</p>
                        <p><strong>Position:</strong> {channelResult.channel.position}</p>
                        {channelResult.channel.parent_category && (
                          <p><strong>Parent Category:</strong> {channelResult.channel.parent_category.name}</p>
                        )}
                        <p><strong>NSFW:</strong> {channelResult.channel.nsfw ? 'Yes' : 'No'}</p>
                        
                        <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#0a0a0a', borderRadius: '8px' }}>
                          <strong>Bot Permissions:</strong>
                          <pre style={{ marginTop: '8px', fontSize: '11px', overflowX: 'auto' }}>{JSON.stringify(channelResult.bot_permissions, null, 2)}</pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                
                <div className="lookup-box">
                  <h3>📁 Category Lookup</h3>
                  <div className="lookup-input-group">
                    <input
                      type="text"
                      className="lookup-input"
                      placeholder="Enter Category ID"
                      value={categoryId}
                      onChange={(e) => setCategoryId(e.target.value)}
                    />
                    <button 
                      className="lookup-button" 
                      onClick={handleCategoryLookup}
                      disabled={loadingCategory || !categoryId.trim()}
                    >
                      {loadingCategory ? 'Searching...' : 'Lookup'}
                    </button>
                  </div>
                  
                  {categoryError && (
                    <div className="lookup-error">{categoryError}</div>
                  )}
                  
                  {categoryResult?.category_found && categoryResult.category && (
                    <div className="lookup-result">
                      <h4>✅ Category Found</h4>
                      <div className="category-info">
                        <p><strong>Name:</strong> {categoryResult.category.name}</p>
                        <p><strong>ID:</strong> {categoryResult.category.id}</p>
                        <p><strong>Position:</strong> {categoryResult.category.position}</p>
                        <p><strong>Total Channels:</strong> {categoryResult.total_channels} ({categoryResult.visible_channels} visible, {categoryResult.hidden_channels_count} hidden)</p>
                        
                        {categoryResult.channels_in_category && categoryResult.channels_in_category.length > 0 && (
                          <div className="channels-list">
                            <strong style={{ display: 'block', marginTop: '12px', marginBottom: '8px', color: '#00c851' }}>
                              ✅ Visible Channels:
                            </strong>
                            {categoryResult.channels_in_category.map((ch, idx) => (
                              <div key={idx} className="channel-item visible">
                                <span className="channel-name">#{ch.name}</span>
                                <span className="channel-type">{ch.type}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        
                        {categoryResult.hidden_channels && categoryResult.hidden_channels.length > 0 && (
                          <div className="channels-list">
                            <strong style={{ display: 'block', marginTop: '12px', marginBottom: '8px', color: '#ff4444' }}>
                              🔒 Hidden Channels:
                            </strong>
                            {categoryResult.hidden_channels.map((ch, idx) => (
                              <div key={idx} className="channel-item hidden">
                                <span className="channel-name">#{ch.name}</span>
                                <span className="channel-type">{ch.type}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="lookup-box">
                  <h3>👤 User Settings Lookup</h3>
                  <div className="lookup-input-group">
                    <input
                      type="text"
                      className="lookup-input"
                      placeholder="Enter User ID"
                      value={userLookupId}
                      onChange={(e) => setUserLookupId(e.target.value)}
                    />
                    <button
                      className="lookup-button"
                      onClick={handleUserLookup}
                      disabled={loadingUserLookup || !userLookupId.trim()}
                    >
                      {loadingUserLookup ? 'Searching...' : 'Lookup'}
                    </button>
                  </div>

                  {userLookupError && (
                    <div className="lookup-error">{userLookupError}</div>
                  )}

                  {userLookupResult?.user_found && (
                    <div className="lookup-result">
                      <h4>✅ User Found</h4>
                      <div className="user-settings-info">
                        <div className="user-profile-header">
                          {getUserAvatarUrl(userLookupResult.discord_user) ? (
                            <img
                              className="user-avatar"
                              src={getUserAvatarUrl(userLookupResult.discord_user)}
                              alt=""
                            />
                          ) : (
                            <div className="user-avatar-fallback">
                              {getUserInitial(userLookupResult.discord_user)}
                            </div>
                          )}
                          <div className="user-profile-names">
                            <span className="user-display-name">
                              {userLookupResult.discord_user?.nickname
                                || userLookupResult.discord_user?.global_name
                                || userLookupResult.discord_user?.username}
                              {!userLookupResult.discord_user?.in_guild && (
                                <span className="not-in-guild-badge">NOT IN SERVER</span>
                              )}
                            </span>
                            <span className="user-username">
                              @{userLookupResult.discord_user?.username} · {userLookupResult.discord_user?.id}
                            </span>
                          </div>
                        </div>

                        <p>
                          <strong>Privacy Mode:</strong>
                          <span className={`status-pill ${userLookupResult.user_settings?.privacy_enabled ? 'on' : 'off'}`}>
                            {userLookupResult.user_settings?.privacy_enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </p>

                        {userLookupResult.user_settings?.privacy_pending_delete && (
                          <p>
                            <strong>Deletion:</strong>
                            <span className="status-pill pending">Pending</span>
                          </p>
                        )}

                        {userLookupResult.discord_user?.joined_at && (
                          <p><strong>Joined Server:</strong> {formatTimestamp(userLookupResult.discord_user.joined_at)}</p>
                        )}

                        {userLookupResult.user_settings?.created_at && (
                          <p><strong>Settings Created:</strong> {formatTimestamp(userLookupResult.user_settings.created_at)}</p>
                        )}

                        {userLookupResult.user_settings?.updated_at && (
                          <p><strong>Settings Updated:</strong> {formatTimestamp(userLookupResult.user_settings.updated_at)}</p>
                        )}

                        {userLookupResult.pending_deletion && (
                          <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#0a0a0a', borderRadius: '8px' }}>
                            <strong style={{ color: '#ffaa00' }}>Pending Deletion Record:</strong>
                            <p style={{ marginTop: '6px' }}>
                              <strong>Requested:</strong> {formatTimestamp(userLookupResult.pending_deletion.requested_at)}
                            </p>
                            <p>
                              <strong>Processed:</strong> {userLookupResult.pending_deletion.processed ? 'Yes' : 'No'}
                            </p>
                            {userLookupResult.pending_deletion.processed_at && (
                              <p>
                                <strong>Processed At:</strong> {formatTimestamp(userLookupResult.pending_deletion.processed_at)}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {/* Roles Section */}
            <div className="debug-section">
              <div className="section-header">
                <h2 className="section-title">👥 Role Hierarchy</h2>
                <span style={{ fontSize: '12px', color: '#888' }}>Sorted from highest to lowest</span>
              </div>
              
              {loadingRoles ? (
                <LoadingSpinner text="Loading roles..." />
              ) : roles?.success ? (
                <>
                  <div className="roles-table-wrapper">
                    <table className="roles-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Role</th>
                          <th>ID</th>
                          <th>Color</th>
                          <th>Hoist</th>
                          <th>Mentionable</th>
                          <th>Managed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {roles.roles?.map((role, idx) => (
                          <tr key={role.id} style={{ 
                            backgroundColor: role.is_bot_role ? 'rgba(170, 0, 255, 0.1)' : 'transparent'
                          }}>
                            <td style={{ color: '#888', fontWeight: 'bold' }}>{role.position_order}</td>
                            <td>
                              <span className="role-color-dot" style={{ backgroundColor: role.color }} />
                              {role.name}
                              {role.is_bot_role && <span className="bot-role-badge">BOT</span>}
                              {role.is_everyone_role && <span className="everyone-badge">@everyone</span>}
                            </td>
                            <td style={{ fontFamily: 'monospace', fontSize: '12px' }}>{role.id}</td>
                            <td>
                              <span style={{ 
                                display: 'inline-block', 
                                padding: '2px 8px', 
                                backgroundColor: role.color, 
                                borderRadius: '12px',
                                fontSize: '11px',
                                color: '#fff'
                              }}>
                                {role.color}
                              </span>
                            </td>
                            <td>{role.hoist ? '✅' : '❌'}</td>
                            <td>{role.mentionable ? '✅' : '❌'}</td>
                            <td>{role.managed ? '✅' : '❌'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  
                  <div className="role-hierarchy-note">
                    <p>🤖 <strong>Bot's Highest Role:</strong> {roles.bot_role_summary?.highest_role?.name || 'None'}</p>
                    <p>Bot has {roles.bot_role_summary?.total_bot_roles || 0} role(s) assigned</p>
                    <p style={{ marginTop: '8px', fontSize: '11px', color: '#888' }}>
                      <strong>Hoist:</strong> Role appears in a separate group in member list | 
                      <strong> Mentionable:</strong> Anyone can @mention this role | 
                      <strong> Managed:</strong> Role is managed by a bot/integration
                    </p>
                  </div>
                </>
              ) : (
                <div className="lookup-error">
                  Failed to load roles: {roles?.error || "Unknown error"}
                </div>
              )}
            </div>
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
    <DebugDashboard />
  </React.StrictMode>
);

export default DebugDashboard;