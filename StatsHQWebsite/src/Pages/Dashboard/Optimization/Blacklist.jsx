import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";

// API base URL
const API_BASE_URL = '';
const NAVBAR_HEIGHT = "80px";

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ============================================
// ADVANCED CACHING SYSTEM
// ============================================

// Enhanced cache for server data with size limits and TTL
class ServerDataCache {
  constructor(maxSize = 30, ttl = 5 * 60 * 1000) {
    this.cache = new Map();
    this.maxSize = maxSize;
    this.TTL = ttl;
  }

  set(key, value) {
    if (this.cache.size >= this.maxSize) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
    }
    this.cache.set(key, {
      data: value,
      timestamp: Date.now()
    });
  }

  get(key) {
    const entry = this.cache.get(key);
    if (entry && (Date.now() - entry.timestamp < this.TTL)) {
      return entry.data;
    }
    if (entry) {
      this.cache.delete(key);
    }
    return null;
  }

  clear() {
    this.cache.clear();
  }

  clearPattern(pattern) {
    for (const [key, value] of this.cache) {
      if (key.includes(pattern)) {
        this.cache.delete(key);
      }
    }
  }
}

// Initialize caches
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);
const blacklistCache = new ServerDataCache(20, 2 * 60 * 1000);

// Stable cache key generator
const getCacheKey = (type, id, params) => {
  const sortObject = (obj) => {
    if (!obj || typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) return obj.map(sortObject);
    
    return Object.keys(obj)
      .sort()
      .reduce((result, key) => {
        result[key] = sortObject(obj[key]);
        return result;
      }, {});
  };
  
  const sortedParams = sortObject(params || {});
  return `${type}:${id}:${JSON.stringify(sortedParams)}`;
};

// Access Denied Component - UPDATED TO MATCH SETTINGS STYLE
const AccessDenied = () => {
  let requiredPermission = "Administrator";
  const accessLevel = window.accessLevel || 'Member';
  
  if (accessLevel === 'Member' || accessLevel === 'Moderator') {
    requiredPermission = "Manage Server or Administrator";
  } else if (accessLevel === 'Admin') {
    requiredPermission = "Administrator";
  }
  
  return (
    <div className="dashboard-content">
      <div className="error-message-container">
        <div className="error-icon">🔒</div>
        <h2 className="error-title">Access Denied</h2>
        <p className="error-message">You don't have permission to manage blacklists for this server.</p>
        <p className="error-message">This server requires <strong>{requiredPermission}</strong> permission to manage blacklists.</p>
      </div>
    </div>
  );
};

// Loading spinner
const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '60px',
      gap: '16px',
      width: '100%',
      minHeight: '400px'
    }}>
      <div style={{
        width: spinnerSize,
        height: spinnerSize,
        border: '3px solid rgba(170, 0, 255, 0.2)',
        borderTop: `3px solid #aa00ff`,
        borderRadius: '50%',
        animation: 'spin 1s linear infinite'
      }} />
      {text && <span style={{ color: '#aa00ff', fontSize: '14px' }}>{text}</span>}
    </div>
  );
};

// Styles
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

  html {
    min-height: 100%;
    background-color: #0a0a0a;
    overflow-x: hidden;
  }

  body {
    min-height: 100vh;
    margin: 0;
    padding: 0;
    background-color: #0a0a0a;
    color: #ffffff;
    overflow-y: auto;
    overflow-x: hidden;
    width: 100%;
  }

  #app {
    min-height: 100vh;
    background-color: #0a0a0a;
    overflow-x: hidden;
    width: 100%;
  }

  .dashboard-page {
    max-width: 100%;
    margin: 0 auto;
    background-color: #0a0a0a;
    color: #ffffff;
    min-height: 100vh;
    display: flex;
    position: relative;
    overflow-x: hidden;
  }

  .dashboard-main {
    flex: 1;
    margin-left: 280px;
    background-color: #0a0a0a;
    min-height: 100vh;
    overflow-x: hidden;
    width: 100%;
  }

  .dashboard-content {
    max-width: 1600px;
    margin: 0 auto;
    padding: 20px 40px 40px 40px;
    background-color: #0a0a0a;
    overflow-x: hidden;
    width: 100%;
    box-sizing: border-box;
  }

  .view-selector {
    display: flex;
    gap: 12px;
    margin-bottom: 32px;
    flex-wrap: wrap;
  }

  .view-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 24px;
    font-size: 16px;
    font-weight: 500;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .view-button:hover {
    border-color: #aa00ff;
    color: #ffffff;
    transform: translateY(-2px);
  }

  .view-button.active {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border-color: #aa00ff;
    color: white;
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
  }

  .add-section {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 32px;
  }

  .section-title {
    color: #ffffff;
    font-size: 24px;
    font-weight: 600;
    margin: 0 0 20px 0;
    position: relative;
    display: inline-block;
  }

  .section-title::after {
    content: '';
    position: absolute;
    bottom: -8px;
    left: 0;
    width: 60px;
    height: 3px;
    background-color: #aa00ff;
    border-radius: 2px;
  }

  .entity-selector-wrapper {
    max-width: 500px;
  }

  .entity-selector-input-wrapper {
    position: relative;
  }

  .entity-search-input {
    width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    outline: none;
    transition: all 0.2s ease;
  }

  .entity-search-input:focus {
    border-color: #aa00ff;
    box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
  }

  .entity-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    margin-top: 8px;
    max-height: 300px;
    overflow-y: auto;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  }

  .entity-option {
    padding: 12px 16px;
    color: #ffffff;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .entity-option:hover {
    background-color: #2a2a2a;
  }

  .entity-option-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .entity-avatar {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    object-fit: cover;
  }

  .entity-name {
    font-weight: 500;
    word-break: break-word;
  }

  .entity-subtext {
    color: #888;
    font-size: 12px;
  }

  .apply-button-container {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }

  .apply-button {
    background-color: #aa00ff;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .apply-button:hover {
    background-color: #8800cc;
    transform: translateY(-2px);
  }

  .apply-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .clear-button {
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }

  .clear-button:hover {
    border-color: #ff4444;
    color: #ff4444;
  }

  .blacklist-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 40px 0 20px 0;
    flex-wrap: wrap;
    gap: 16px;
  }

  .title-section {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .filter-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .filter-button:hover {
    border-color: #aa00ff;
    color: #ffffff;
    background-color: #222;
  }

  .filter-dropdown {
    position: relative;
    display: inline-block;
  }

  .filter-menu {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 8px;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    min-width: 180px;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    overflow: hidden;
  }

  .filter-option {
    padding: 12px 16px;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 14px;
  }

  .filter-option:hover {
    background-color: #2a2a2a;
    color: #ffffff;
  }

  .filter-option.active {
    color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
  }

  .filter-option .radio-circle {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid #b0b0b0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .filter-option.active .radio-circle {
    border-color: #aa00ff;
  }

  .filter-option.active .radio-circle::after {
    content: '';
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #aa00ff;
    display: block;
  }

  .search-input-wrapper {
    position: relative;
    width: 300px;
  }

  .search-input {
    width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 10px 16px;
    padding-left: 36px;
    font-size: 14px;
    outline: none;
    transition: all 0.2s ease;
  }

  .search-input:focus {
    border-color: #aa00ff;
    box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
  }

  .search-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: #888;
    font-size: 14px;
  }

  .clear-search-button {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    font-size: 14px;
    padding: 0 4px;
  }

  .clear-search-button:hover {
    color: #ff4444;
  }

  .search-stats {
    margin-bottom: 16px;
    color: #888;
    font-size: 13px;
  }

  .blacklist-table-wrapper {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    overflow-x: auto;
    margin-top: 20px;
    width: 100%;
    max-width: 100%;
  }

  .blacklist-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: auto;
    min-width: 100%;
  }

  .blacklist-table th,
  .blacklist-table td {
    padding: 14px 16px;
    text-align: left;
    border-bottom: 1px solid #1a1a1a;
    word-break: break-word;
  }

  .blacklist-table th {
    background-color: #0f0f0f;
    color: #aa00ff;
    font-weight: 600;
    font-size: 14px;
    white-space: nowrap;
  }

  .blacklist-table tr:hover {
    background-color: #1a1a1a;
  }

  .user-cell {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .user-avatar-small {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
  }

  .role-color-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 8px;
    flex-shrink: 0;
  }

  .delete-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    color: #ff6666;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }

  .delete-button:hover {
    background-color: #ff4444;
    border-color: #ff4444;
    color: white;
  }

  .delete-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .no-data-message {
    text-align: center;
    padding: 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    color: #b0b0b0;
  }

  .loading-container {
    text-align: center;
    padding: 80px 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
  }

  .error-message-container {
    text-align: center;
    padding: 80px 40px;
    background-color: #1a1a1a;
    border: 1px solid #ff4444;
    border-radius: 16px;
    margin-top: 0;
  }

  .error-icon {
    font-size: 64px;
    margin-bottom: 20px;
  }

  .error-title {
    color: #ff4444;
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 16px;
  }

  .error-message {
    color: #b0b0b0;
    font-size: 16px;
    line-height: 1.6;
    margin-bottom: 8px;
  }

  .no-server {
    text-align: center;
    padding: 80px 60px;
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

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .toast-message {
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    z-index: 9999;
    animation: slideIn 0.3s ease;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    font-weight: 500;
  }

  @media (max-width: 1024px) {
    .dashboard-main {
      margin-left: 250px;
    }
    .dashboard-content {
      padding: 30px;
    }
    .blacklist-header {
      flex-direction: column;
      align-items: flex-start;
    }
    .title-section {
      width: 100%;
      justify-content: space-between;
    }
    .search-input-wrapper {
      width: 100%;
    }
  }

  @media (max-width: 768px) {
    .dashboard-main {
      margin-left: 0;
      width: 100%;
    }
    .dashboard-content {
      padding: 16px;
      width: 100%;
    }
    .view-selector {
      flex-direction: column;
    }
    .view-button {
      text-align: center;
    }
    .title-section {
      flex-wrap: wrap;
    }
    .blacklist-table-wrapper {
      margin-left: -16px;
      margin-right: -16px;
      width: calc(100% + 32px);
      border-radius: 0;
      border-left: none;
      border-right: none;
    }
    .blacklist-table th,
    .blacklist-table td {
      padding: 12px 12px;
      font-size: 13px;
    }
    .blacklist-table th:nth-child(2),
    .blacklist-table td:nth-child(2) {
      max-width: 120px;
    }
    .blacklist-table th:nth-child(3),
    .blacklist-table td:nth-child(3) {
      max-width: 130px;
    }
    .user-avatar-small {
      width: 28px;
      height: 28px;
    }
    .delete-button {
      padding: 4px 8px;
      font-size: 11px;
    }
    .add-section {
      padding: 16px;
    }
    .section-title {
      font-size: 20px;
    }
    .entity-selector-wrapper {
      max-width: 100%;
    }
  }

  @media (max-width: 480px) {
    .dashboard-content {
      padding: 12px;
    }
    .blacklist-table-wrapper {
      margin-left: -12px;
      margin-right: -12px;
      width: calc(100% + 24px);
    }
    .blacklist-table th,
    .blacklist-table td {
      padding: 10px 8px;
      font-size: 12px;
    }
    .blacklist-table th:nth-child(2),
    .blacklist-table td:nth-child(2) {
      display: none;
    }
    .user-cell {
      gap: 6px;
    }
    .user-avatar-small {
      width: 24px;
      height: 24px;
    }
    .title-section {
      gap: 8px;
    }
    .filter-button {
      padding: 6px 12px;
      font-size: 12px;
    }
  }
`;

const BlacklistDashboard = () => {
  const [selectedView, setSelectedView] = useState("user");
  const [currentServer, setCurrentServer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [actionLoading, setActionLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [toast, setToast] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);
  
  // Search and filter state
  const [blacklistSearch, setBlacklistSearch] = useState("");
  const [filterOption, setFilterOption] = useState("latest");
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  
  // Data states
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [channels, setChannels] = useState([]);
  const [filteredChannels, setFilteredChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [filteredCategories, setFilteredCategories] = useState([]);
  const [roles, setRoles] = useState([]);
  const [filteredRoles, setFilteredRoles] = useState([]);
  
  // Blacklist data
  const [blacklistedUsers, setBlacklistedUsers] = useState([]);
  const [blacklistedChannels, setBlacklistedChannels] = useState([]);
  const [blacklistedCategories, setBlacklistedCategories] = useState([]);
  const [blacklistedRoles, setBlacklistedRoles] = useState([]);
  
  // Filtered and sorted blacklist data
  const [filteredBlacklistedUsers, setFilteredBlacklistedUsers] = useState([]);
  const [filteredBlacklistedChannels, setFilteredBlacklistedChannels] = useState([]);
  const [filteredBlacklistedCategories, setFilteredBlacklistedCategories] = useState([]);
  const [filteredBlacklistedRoles, setFilteredBlacklistedRoles] = useState([]);
  
  // Selector temp states
  const [tempUserId, setTempUserId] = useState("");
  const [tempUserName, setTempUserName] = useState("");
  const [showApplyUser, setShowApplyUser] = useState(false);
  const [userSearch, setUserSearch] = useState("");
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  
  const [tempChannelId, setTempChannelId] = useState("");
  const [tempChannelName, setTempChannelName] = useState("");
  const [showApplyChannel, setShowApplyChannel] = useState(false);
  const [channelSearch, setChannelSearch] = useState("");
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  
  const [tempCategoryId, setTempCategoryId] = useState("");
  const [tempCategoryName, setTempCategoryName] = useState("");
  const [showApplyCategory, setShowApplyCategory] = useState(false);
  const [categorySearch, setCategorySearch] = useState("");
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false);
  
  const [tempRoleId, setTempRoleId] = useState("");
  const [tempRoleName, setTempRoleName] = useState("");
  const [showApplyRole, setShowApplyRole] = useState(false);
  const [roleSearch, setRoleSearch] = useState("");
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  
  // Loading flags
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [channelsLoaded, setChannelsLoaded] = useState(false);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [rolesLoaded, setRolesLoaded] = useState(false);
  const [blacklistLoaded, setBlacklistLoaded] = useState(false);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);

  // Filter options
  const filterOptions = [
    { value: "latest", label: "Latest First", icon: "🕒" },
    { value: "oldest", label: "Oldest First", icon: "⏰" },
    { value: "a-z", label: "A-Z", icon: "🔤" },
    { value: "z-a", label: "Z-A", icon: "🔠" }
  ];

  // Check if current user is privileged
  const isPrivilegedUser = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  // Apply search and filter to blacklisted items
  useEffect(() => {
    const applySearchAndFilter = (items) => {
      let filtered = items;
      if (blacklistSearch.trim() !== "") {
        const searchLower = blacklistSearch.toLowerCase();
        filtered = items.filter(item => 
          item.name?.toLowerCase().includes(searchLower) ||
          item.id?.toLowerCase().includes(searchLower)
        );
      }
      
      const sorted = [...filtered];
      switch (filterOption) {
        case "latest":
          sorted.sort((a, b) => new Date(b.added_at) - new Date(a.added_at));
          break;
        case "oldest":
          sorted.sort((a, b) => new Date(a.added_at) - new Date(b.added_at));
          break;
        case "a-z":
          sorted.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
          break;
        case "z-a":
          sorted.sort((a, b) => (b.name || "").localeCompare(a.name || ""));
          break;
        default:
          sorted.sort((a, b) => new Date(b.added_at) - new Date(a.added_at));
      }
      
      return sorted;
    };
    
    setFilteredBlacklistedUsers(applySearchAndFilter(blacklistedUsers));
    setFilteredBlacklistedChannels(applySearchAndFilter(blacklistedChannels));
    setFilteredBlacklistedCategories(applySearchAndFilter(blacklistedCategories));
    setFilteredBlacklistedRoles(applySearchAndFilter(blacklistedRoles));
    
  }, [blacklistSearch, filterOption, blacklistedUsers, blacklistedChannels, blacklistedCategories, blacklistedRoles]);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const ToastMessage = () => {
    if (!toast) return null;
    const colors = {
      success: { bg: '#00b894', icon: '✅' },
      error: { bg: '#ff7675', icon: '❌' },
      info: { bg: '#0984e3', icon: 'ℹ️' }
    };
    const color = colors[toast.type] || colors.info;
    
    return (
      <div className="toast-message" style={{ backgroundColor: color.bg }}>
        <span>{color.icon}</span>
        <span>{toast.message}</span>
        <button onClick={() => setToast(null)} style={{
          background: 'none',
          border: 'none',
          color: 'white',
          cursor: 'pointer',
          marginLeft: '10px',
          fontSize: '16px'
        }}>✕</button>
      </div>
    );
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (currentServer && hasAccess && initialLoadComplete) {
      loadData();
    }
  }, [currentServer, hasAccess]);

  // Search filters for available entities
  useEffect(() => {
    if (userSearch.trim() === "") {
      setFilteredUsers(users);
    } else {
      const searchLower = userSearch.toLowerCase();
      setFilteredUsers(users.filter(user => 
        (user.display_name?.toLowerCase().includes(searchLower) ||
         user.username?.toLowerCase().includes(searchLower) ||
         user.global_name?.toLowerCase().includes(searchLower) ||
         user.id?.includes(searchLower))
      ));
    }
  }, [userSearch, users]);

  useEffect(() => {
    if (channelSearch.trim() === "") {
      setFilteredChannels(channels);
    } else {
      const searchLower = channelSearch.toLowerCase();
      setFilteredChannels(channels.filter(channel => 
        channel.name?.toLowerCase().includes(searchLower) ||
        channel.id?.includes(searchLower)
      ));
    }
  }, [channelSearch, channels]);

  useEffect(() => {
    if (categorySearch.trim() === "") {
      setFilteredCategories(categories);
    } else {
      const searchLower = categorySearch.toLowerCase();
      setFilteredCategories(categories.filter(category => 
        category.name?.toLowerCase().includes(searchLower) ||
        category.id?.includes(searchLower)
      ));
    }
  }, [categorySearch, categories]);

  useEffect(() => {
    if (roleSearch.trim() === "") {
      setFilteredRoles(roles);
    } else {
      const searchLower = roleSearch.toLowerCase();
      setFilteredRoles(roles.filter(role => 
        role.name?.toLowerCase().includes(searchLower) ||
        role.id?.includes(searchLower)
      ));
    }
  }, [roleSearch, roles]);

  const checkServerAccess = async (guildId, hasAdmin, hasManageServer) => {
    try {
      const settingsResponse = await fetch(`${API_BASE_URL}/api/settings/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: guildId })
      });

      if (settingsResponse.ok) {
        const settingsData = await settingsResponse.json();
        const accessLevel = settingsData.dashboard_access_level || 'Member';
        setDashboardAccessLevel(accessLevel);
        window.accessLevel = accessLevel;
        
        const isAdmin = hasAdmin;
        const hasManageServerPerm = hasManageServer;
        
        let hasAccessFlag = false;
        
        if (accessLevel === 'Public') {
          hasAccessFlag = true;
        } else if (accessLevel === 'Member') {
          hasAccessFlag = isAdmin || hasManageServerPerm;
        } else if (accessLevel === 'Moderator') {
          hasAccessFlag = isAdmin || hasManageServerPerm;
        } else if (accessLevel === 'Admin') {
          hasAccessFlag = isAdmin;
        } else {
          hasAccessFlag = isAdmin || hasManageServerPerm;
        }
        
        setHasAccess(hasAccessFlag);
        
        
      } else {
        console.error('Failed to get settings for guild:', guildId);
        setHasAccess(false);
      }
    } catch (error) {
      console.error('Error checking server access:', error);
      setHasAccess(false);
    }
  };

  const loadInitialData = async () => {
    setLoadingServers(true);
    setApiError(null);
    setHasAccess(null);
    try {
      const authResponse = await fetch(`${API_BASE_URL}/api/auth/status`, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (!authResponse.ok) throw new Error('Auth failed');
      
      const authData = await authResponse.json();
      
      if (authData.authenticated && authData.user) {
        setIsAuthenticated(true);
        setCurrentUserId(authData.user.id);
        
        // Check if user is privileged
        if (isPrivilegedUser(authData.user.id)) {
          setHasAccess(true);
          setDashboardAccessLevel('Admin');
          window.accessLevel = 'Admin';
          
          // Still need to get servers for privileged user
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
          setInitialLoadComplete(true);
          setLoadingServers(false);
          return;
        }
        
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
              await checkServerAccess(
                selectedServer.id, 
                selectedServer.has_admin, 
                selectedServer.has_manage_server
              );
            }
            setInitialLoadComplete(true);
          } else {
            setInitialLoadComplete(true);
          }
        } else {
          setInitialLoadComplete(true);
        }
      } else {
        setInitialLoadComplete(true);
      }
    } catch (error) {
      console.error('Error loading initial data:', error);
      setApiError('Failed to load servers. Please check your connection.');
      setInitialLoadComplete(true);
    } finally {
      setLoadingServers(false);
    }
  };

  const loadData = async () => {
    if (!currentServer || !hasAccess) return;
    
    setLoading(true);
    setUsersLoaded(false);
    setChannelsLoaded(false);
    setCategoriesLoaded(false);
    setRolesLoaded(false);
    setBlacklistLoaded(false);
    
    await Promise.all([
      fetchAllUsers(),
      fetchAllChannels(),
      fetchAllCategories(),
      fetchAllRoles(),
      fetchBlacklistedData()
    ]);
    
    setLoading(false);
  };

  const fetchAllUsers = async () => {
    try {
      const cacheKey = getCacheKey('users', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setUsers(cached);
        setFilteredUsers(cached);
        setUsersLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-users?guild_id=${currentServer.id}&limit=500`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setUsers(data);
        setFilteredUsers(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching users:', error);
    } finally {
      setUsersLoaded(true);
    }
  };

  const fetchAllChannels = async () => {
    try {
      const cacheKey = getCacheKey('channels', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setChannels(cached);
        setFilteredChannels(cached);
        setChannelsLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setChannels(data);
        setFilteredChannels(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching channels:', error);
    } finally {
      setChannelsLoaded(true);
    }
  };

  const fetchAllCategories = async () => {
    try {
      const cacheKey = getCacheKey('categories', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setCategories(cached);
        setFilteredCategories(cached);
        setCategoriesLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setCategories(data);
        setFilteredCategories(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching categories:', error);
    } finally {
      setCategoriesLoaded(true);
    }
  };

  const fetchAllRoles = async () => {
    try {
      const cacheKey = getCacheKey('roles', currentServer.id, {});
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setRoles(cached);
        setFilteredRoles(cached);
        setRolesLoaded(true);
        return;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/server/real-roles?guild_id=${currentServer.id}`, {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setRoles(data);
        setFilteredRoles(data);
        serverDataCache.set(cacheKey, data);
      }
    } catch (error) {
      console.error('Error fetching roles:', error);
    } finally {
      setRolesLoaded(true);
    }
  };

  const fetchBlacklistedData = async () => {
    try {
      const cacheKey = getCacheKey('blacklist', currentServer.id, {});
      const cached = blacklistCache.get(cacheKey);
      
      if (cached) {
        setBlacklistedUsers(cached.users || []);
        setBlacklistedChannels(cached.channels || []);
        setBlacklistedCategories(cached.categories || []);
        setBlacklistedRoles(cached.roles || []);
        setBlacklistLoaded(true);
        return;
      }
      
      const [usersRes, channelsRes, categoriesRes, rolesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/blacklist/entities/users?guild_id=${currentServer.id}`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/blacklist/entities/channels?guild_id=${currentServer.id}`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/blacklist/entities/categories?guild_id=${currentServer.id}`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/blacklist/entities/roles?guild_id=${currentServer.id}`, { credentials: 'include' })
      ]);
      
      const usersData = usersRes.ok ? await usersRes.json() : [];
      const channelsData = channelsRes.ok ? await channelsRes.json() : [];
      const categoriesData = categoriesRes.ok ? await categoriesRes.json() : [];
      const rolesData = rolesRes.ok ? await rolesRes.json() : [];
      
      setBlacklistedUsers(usersData);
      setBlacklistedChannels(channelsData);
      setBlacklistedCategories(categoriesData);
      setBlacklistedRoles(rolesData);
      
      blacklistCache.set(cacheKey, {
        users: usersData,
        channels: channelsData,
        categories: categoriesData,
        roles: rolesData
      });
      
    } catch (error) {
      console.error('Error fetching blacklist:', error);
      showToast('Failed to load blacklist data', 'error');
    } finally {
      setBlacklistLoaded(true);
    }
  };

  const handleAddToBlacklist = async (type, entityId, entityName) => {
    if (!currentServer) return;
    
    setActionLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/blacklist/add-with-apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guild_id: currentServer.id,
          entity_type: type,
          entity_id: entityId,
          added_by: currentUserId || "0"
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        const cacheKey = getCacheKey('blacklist', currentServer.id, {});
        blacklistCache.cache.delete(cacheKey);
        
        await fetchBlacklistedData();
        showToast(`Successfully blacklisted ${entityName}`, 'success');
        
        if (type === 'user') {
          setTempUserId("");
          setTempUserName("");
          setUserSearch("");
          setShowApplyUser(false);
        } else if (type === 'channel') {
          setTempChannelId("");
          setTempChannelName("");
          setChannelSearch("");
          setShowApplyChannel(false);
        } else if (type === 'category') {
          setTempCategoryId("");
          setTempCategoryName("");
          setCategorySearch("");
          setShowApplyCategory(false);
        } else if (type === 'role') {
          setTempRoleId("");
          setTempRoleName("");
          setRoleSearch("");
          setShowApplyRole(false);
        }
      } else {
        showToast(result.message || `Failed to blacklist ${entityName}`, 'error');
      }
    } catch (error) {
      console.error('Error adding to blacklist:', error);
      showToast('Failed to add to blacklist', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveFromBlacklist = async (type, entityId, entityName) => {
    setActionLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/blacklist/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guild_id: currentServer.id,
          entity_type: type,
          entity_id: entityId
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        const cacheKey = getCacheKey('blacklist', currentServer.id, {});
        blacklistCache.cache.delete(cacheKey);
        
        await fetchBlacklistedData();
        showToast(`Removed ${entityName} from blacklist`, 'success');
      } else {
        showToast(result.message || 'Failed to remove', 'error');
      }
    } catch (error) {
      console.error('Error removing from blacklist:', error);
      showToast('Failed to remove from blacklist', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "Unknown";
    return new Date(dateString).toLocaleString();
  };

  const getCurrentFilteredBlacklist = () => {
    switch (selectedView) {
      case "user": return filteredBlacklistedUsers;
      case "channel": return filteredBlacklistedChannels;
      case "category": return filteredBlacklistedCategories;
      case "role": return filteredBlacklistedRoles;
      default: return [];
    }
  };

  const getCurrentTotalCount = () => {
    switch (selectedView) {
      case "user": return blacklistedUsers.length;
      case "channel": return blacklistedChannels.length;
      case "category": return blacklistedCategories.length;
      case "role": return blacklistedRoles.length;
      default: return 0;
    }
  };

  const getFilterLabel = () => {
    const option = filterOptions.find(opt => opt.value === filterOption);
    return option ? `${option.icon} ${option.label}` : "🕒 Latest First";
  };

  // Loading state
  if (loadingServers || (isAuthenticated && !currentServer && !apiError && !initialLoadComplete)) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading-container">
                <LoadingSpinner text="Loading servers..." />
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Permission checking in progress
  if (hasAccess === null && isAuthenticated && currentServer && !isPrivilegedUser(currentUserId)) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading-container">
                <LoadingSpinner text="Checking permissions..." />
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Not authenticated
  if (!isAuthenticated) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>Please Log In</h2>
                <p>You need to be logged in to manage blacklists.</p>
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

  // No server
  if (!currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>No Server Available</h2>
                <p>Add the bot to a Discord server to manage blacklists.</p>
                <a 
                  href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands" 
                  className="invite-button" 
                  target="_blank" 
                  rel="noopener noreferrer"
                >
                  Invite Bot to Server
                </a>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Access Denied
  if (hasAccess === false) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <AccessDenied />
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Error
  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message-container">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => window.location.reload()}>Retry</button>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  const currentItems = getCurrentFilteredBlacklist();
  const totalCount = getCurrentTotalCount();
  const filteredCount = currentItems.length;

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            {/* View Selector */}
            <div className="view-selector">
              <button 
                className={`view-button ${selectedView === "user" ? "active" : ""}`}
                onClick={() => setSelectedView("user")}
              >
                👤 Users
              </button>
              <button 
                className={`view-button ${selectedView === "channel" ? "active" : ""}`}
                onClick={() => setSelectedView("channel")}
              >
                📝 Channels
              </button>
              <button 
                className={`view-button ${selectedView === "category" ? "active" : ""}`}
                onClick={() => setSelectedView("category")}
              >
                📁 Categories
              </button>
              <button 
                className={`view-button ${selectedView === "role" ? "active" : ""}`}
                onClick={() => setSelectedView("role")}
              >
                🎭 Roles
              </button>
            </div>

            {/* Add Section */}
            <div className="add-section">
              <h2 className="section-title">Add to Blacklist</h2>
              
              {/* User Selector */}
              {selectedView === 'user' && (
                <div className="entity-selector-wrapper">
                  <div className="entity-selector-input-wrapper">
                    <input
                      type="text"
                      placeholder="Search users by name or ID..."
                      value={userSearch}
                      onChange={(e) => setUserSearch(e.target.value)}
                      onFocus={() => setShowUserDropdown(true)}
                      onBlur={() => setTimeout(() => setShowUserDropdown(false), 200)}
                      className="entity-search-input"
                    />
                    {showUserDropdown && filteredUsers.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredUsers.slice(0, 20).map(user => (
                          <div
                            key={user.id}
                            className="entity-option"
                            onMouseDown={() => {
                              setTempUserId(user.id);
                              setTempUserName(user.display_name || user.username || user.global_name || user.name);
                              setUserSearch(user.display_name || user.username || user.global_name || user.name);
                              setShowApplyUser(true);
                              setShowUserDropdown(false);
                            }}
                          >
                            <div className="entity-option-info">
                              {user.avatar && (
                                <img src={user.avatar} alt="" className="entity-avatar" />
                              )}
                              <span className="entity-name">
                                {user.display_name || user.global_name || user.username || `User ${user.id}`}
                              </span>
                            </div>
                            <span className="entity-subtext">ID: {user.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {showApplyUser && (
                    <div className="apply-button-container">
                      <button 
                        className="apply-button" 
                        onClick={() => handleAddToBlacklist('user', tempUserId, tempUserName)}
                        disabled={actionLoading}
                      >
                        {actionLoading ? 'Adding...' : 'Apply'}
                      </button>
                      <button 
                        className="clear-button" 
                        onClick={() => {
                          setTempUserId("");
                          setTempUserName("");
                          setUserSearch("");
                          setShowApplyUser(false);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Channel Selector */}
              {selectedView === 'channel' && (
                <div className="entity-selector-wrapper">
                  <div className="entity-selector-input-wrapper">
                    <input
                      type="text"
                      placeholder="Search channels by name or ID..."
                      value={channelSearch}
                      onChange={(e) => setChannelSearch(e.target.value)}
                      onFocus={() => setShowChannelDropdown(true)}
                      onBlur={() => setTimeout(() => setShowChannelDropdown(false), 200)}
                      className="entity-search-input"
                    />
                    {showChannelDropdown && filteredChannels.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredChannels.slice(0, 20).map(channel => (
                          <div
                            key={channel.id}
                            className="entity-option"
                            onMouseDown={() => {
                              setTempChannelId(channel.id);
                              setTempChannelName(channel.name);
                              setChannelSearch(channel.name);
                              setShowApplyChannel(true);
                              setShowChannelDropdown(false);
                            }}
                          >
                            <div className="entity-option-info">
                              <span className="entity-name">#{channel.name}</span>
                            </div>
                            <span className="entity-subtext">ID: {channel.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {showApplyChannel && (
                    <div className="apply-button-container">
                      <button 
                        className="apply-button" 
                        onClick={() => handleAddToBlacklist('channel', tempChannelId, tempChannelName)}
                        disabled={actionLoading}
                      >
                        {actionLoading ? 'Adding...' : 'Apply'}
                      </button>
                      <button 
                        className="clear-button" 
                        onClick={() => {
                          setTempChannelId("");
                          setTempChannelName("");
                          setChannelSearch("");
                          setShowApplyChannel(false);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Category Selector */}
              {selectedView === 'category' && (
                <div className="entity-selector-wrapper">
                  <div className="entity-selector-input-wrapper">
                    <input
                      type="text"
                      placeholder="Search categories by name or ID..."
                      value={categorySearch}
                      onChange={(e) => setCategorySearch(e.target.value)}
                      onFocus={() => setShowCategoryDropdown(true)}
                      onBlur={() => setTimeout(() => setShowCategoryDropdown(false), 200)}
                      className="entity-search-input"
                    />
                    {showCategoryDropdown && filteredCategories.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredCategories.slice(0, 20).map(category => (
                          <div
                            key={category.id}
                            className="entity-option"
                            onMouseDown={() => {
                              setTempCategoryId(category.id);
                              setTempCategoryName(category.name);
                              setCategorySearch(category.name);
                              setShowApplyCategory(true);
                              setShowCategoryDropdown(false);
                            }}
                          >
                            <div className="entity-option-info">
                              <span className="entity-name">{category.name}</span>
                            </div>
                            <span className="entity-subtext">ID: {category.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {showApplyCategory && (
                    <div className="apply-button-container">
                      <button 
                        className="apply-button" 
                        onClick={() => handleAddToBlacklist('category', tempCategoryId, tempCategoryName)}
                        disabled={actionLoading}
                      >
                        {actionLoading ? 'Adding...' : 'Apply'}
                      </button>
                      <button 
                        className="clear-button" 
                        onClick={() => {
                          setTempCategoryId("");
                          setTempCategoryName("");
                          setCategorySearch("");
                          setShowApplyCategory(false);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Role Selector */}
              {selectedView === 'role' && (
                <div className="entity-selector-wrapper">
                  <div className="entity-selector-input-wrapper">
                    <input
                      type="text"
                      placeholder="Search roles by name or ID..."
                      value={roleSearch}
                      onChange={(e) => setRoleSearch(e.target.value)}
                      onFocus={() => setShowRoleDropdown(true)}
                      onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
                      className="entity-search-input"
                    />
                    {showRoleDropdown && filteredRoles.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredRoles.slice(0, 20).map(role => (
                          <div
                            key={role.id}
                            className="entity-option"
                            onMouseDown={() => {
                              setTempRoleId(role.id);
                              setTempRoleName(role.name);
                              setRoleSearch(role.name);
                              setShowApplyRole(true);
                              setShowRoleDropdown(false);
                            }}
                          >
                            <div className="entity-option-info">
                              <span className="role-color-dot" style={{ backgroundColor: role.color }} />
                              <span className="entity-name">{role.name}</span>
                            </div>
                            <span className="entity-subtext">ID: {role.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {showApplyRole && (
                    <div className="apply-button-container">
                      <button 
                        className="apply-button" 
                        onClick={() => handleAddToBlacklist('role', tempRoleId, tempRoleName)}
                        disabled={actionLoading}
                      >
                        {actionLoading ? 'Adding...' : 'Apply'}
                      </button>
                      <button 
                        className="clear-button" 
                        onClick={() => {
                          setTempRoleId("");
                          setTempRoleName("");
                          setRoleSearch("");
                          setShowApplyRole(false);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Blacklist Header */}
            <div className="blacklist-header">
              <div className="title-section">
                <h2 className="section-title">
                  Blacklisted {selectedView.charAt(0).toUpperCase() + selectedView.slice(1)}s
                </h2>
                <div className="filter-dropdown">
                  <button 
                    className="filter-button"
                    onClick={() => setShowFilterMenu(!showFilterMenu)}
                  >
                    <span></span> {getFilterLabel()} <span>▼</span>
                  </button>
                  {showFilterMenu && (
                    <div className="filter-menu">
                      {filterOptions.map(option => (
                        <div
                          key={option.value}
                          className={`filter-option ${filterOption === option.value ? 'active' : ''}`}
                          onClick={() => {
                            setFilterOption(option.value);
                            setShowFilterMenu(false);
                          }}
                        >
                          <span className="radio-circle"></span>
                          <span>{option.icon} {option.label}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="search-input-wrapper">
                <span className="search-icon">🔍</span>
                <input
                  type="text"
                  placeholder={`Search blacklisted ${selectedView}s...`}
                  value={blacklistSearch}
                  onChange={(e) => setBlacklistSearch(e.target.value)}
                  className="search-input"
                />
                {blacklistSearch && (
                  <button 
                    className="clear-search-button"
                    onClick={() => setBlacklistSearch("")}
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* Search Stats */}
            {blacklistSearch && (
              <div className="search-stats">
                Found {filteredCount} of {totalCount} blacklisted {selectedView}s matching "{blacklistSearch}"
              </div>
            )}

            {/* Blacklist Table */}
            {!blacklistLoaded ? (
              <LoadingSpinner size="small" text="Loading blacklist..." />
            ) : currentItems.length > 0 ? (
              <div className="blacklist-table-wrapper">
                <table className="blacklist-table">
                  <thead>
                    <tr>
                      <th>{selectedView === 'user' ? 'User' : selectedView === 'channel' ? 'Channel' : selectedView === 'category' ? 'Category' : 'Role'}</th>
                      <th>ID</th>
                      <th>Blacklisted At</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedView === 'user' && currentItems.map(user => (
                      <tr key={user.id}>
                        <td>
                          <div className="user-cell">
                            {user.avatar && <img src={user.avatar} alt="" className="user-avatar-small" />}
                            <span style={{ wordBreak: 'break-word' }}>{user.name}</span>
                          </div>
                        </td>
                        <td style={{ wordBreak: 'break-all' }}>{user.id}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{formatDate(user.added_at)}</td>
                        <td>
                          <button 
                            className="delete-button"
                            onClick={() => handleRemoveFromBlacklist('user', user.id, user.name)}
                            disabled={actionLoading}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {selectedView === 'channel' && currentItems.map(channel => (
                      <tr key={channel.id}>
                        <td style={{ wordBreak: 'break-word' }}>#{channel.name}</td>
                        <td style={{ wordBreak: 'break-all' }}>{channel.id}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{formatDate(channel.added_at)}</td>
                        <td>
                          <button 
                            className="delete-button"
                            onClick={() => handleRemoveFromBlacklist('channel', channel.id, channel.name)}
                            disabled={actionLoading}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {selectedView === 'category' && currentItems.map(category => (
                      <tr key={category.id}>
                        <td style={{ wordBreak: 'break-word' }}>{category.name}</td>
                        <td style={{ wordBreak: 'break-all' }}>{category.id}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{formatDate(category.added_at)}</td>
                        <td>
                          <button 
                            className="delete-button"
                            onClick={() => handleRemoveFromBlacklist('category', category.id, category.name)}
                            disabled={actionLoading}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {selectedView === 'role' && currentItems.map(role => (
                      <tr key={role.id}>
                        <td>
                          <span className="role-color-dot" style={{ backgroundColor: role.color }} />
                          <span style={{ wordBreak: 'break-word' }}>{role.name}</span>
                        </td>
                        <td style={{ wordBreak: 'break-all' }}>{role.id}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{formatDate(role.added_at)}</td>
                        <td>
                          <button 
                            className="delete-button"
                            onClick={() => handleRemoveFromBlacklist('role', role.id, role.name)}
                            disabled={actionLoading}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="no-data-message">
                {blacklistSearch ? 
                  `No blacklisted ${selectedView}s found matching "${blacklistSearch}".` : 
                  `No blacklisted ${selectedView}s found.`
                }
              </div>
            )}
          </div>
          <Footer />
        </main>
      </div>
      <ToastMessage />
      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <BlacklistDashboard />
  </React.StrictMode>
);

export default BlacklistDashboard;