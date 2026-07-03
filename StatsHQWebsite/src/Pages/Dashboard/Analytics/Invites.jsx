import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import Leaderboard from "../../../Components/Leaderboard.jsx";
import InteractiveLineChart from "../../../Components/Charts.jsx";

// API base URL - your FastAPI backend
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

// PUBLIC GUILD ID for unauthenticated users
const PUBLIC_GUILD_ID = '1424021358680998022';

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ============================================
// ADVANCED CACHING SYSTEM - FIXED
// ============================================

// Fixed ProfileCache - only caches valid names
class ProfileCache {
  constructor(maxSize = 1000) {
    this.cache = new Map();
    this.maxSize = maxSize;
  }

  get(key) {
    const value = this.cache.get(key);
    if (value) {
      if (value.name && !value.name.startsWith('User ')) {
        this.cache.delete(key);
        this.cache.set(key, value);
        return value;
      }
      this.cache.delete(key);
      return null;
    }
    return null;
  }

  set(key, value) {
    if (value.name && !value.name.startsWith('User ')) {
      if (this.cache.size >= this.maxSize) {
        const firstKey = this.cache.keys().next().value;
        this.cache.delete(firstKey);
      }
      this.cache.set(key, value);
    }
  }

  clear() {
    this.cache.clear();
  }
}

// Cache for user basic info (usernames without avatars)
const userBasicInfoCache = new Map();

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
const profileCache = new ProfileCache(500);
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);

// Helper to get the correct API endpoint based on mode - FIXED for public mode
const getApiEndpoint = (endpoint, isPublic) => {
  if (isPublic) {
    return endpoint.replace('/api/', '/api/public/');
  }
  return endpoint;
};

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

// Format number with commas (integer)
const formatNumber = (num) => {
  if (!num || num === 0) return "0";
  return num.toLocaleString();
};

// Format average values to one decimal place
const formatAverage = (value) => {
  if (value === 0) return "0";
  return value.toFixed(1);
};

// Format large values for leaderboard
const formatInviteValue = (value) => {
  if (!value) return "0";
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return formatNumber(value);
};

// ============================================
// LOADING COMPONENTS
// ============================================

const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '30px',
      gap: '12px',
      width: '100%',
      height: '100%',
      minHeight: '150px'
    }}>
      <div style={{
        width: spinnerSize,
        height: spinnerSize,
        border: '3px solid #2a2a2a',
        borderTop: '3px solid #aa00ff',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite'
      }} />
      {text && <span style={{ color: '#b0b0b0', fontSize: '14px' }}>{text}</span>}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

const LoadingCard = () => (
  <div className="leaderboard-wrapper">
    <LoadingSpinner size="medium" text="Loading data..." />
  </div>
);

const LoadingChart = () => (
  <div className="chart-wrapper">
    <LoadingSpinner size="large" text="Loading chart data..." />
  </div>
);

const AccessDenied = ({ accessLevel }) => {
  let requiredPermission = "Administrator";
  if (accessLevel === 'Member' || accessLevel === 'Moderator') {
    requiredPermission = "Manage Server or Administrator";
  } else if (accessLevel === 'Admin') {
    requiredPermission = "Administrator";
  } else {
    requiredPermission = "Manage Server or Administrator";
  }
  
  return (
    <div className="no-selection">
      <h2>🔒 Access Denied</h2>
      <p>You don't have permission to view this server's invite statistics.</p>
      <p>This server requires <strong>{requiredPermission}</strong> permissions.</p>
      <p className="setting-note" style={{ marginTop: '12px', fontSize: '12px', color: '#666' }}>
        Note: Server owners automatically have Administrator permission.
      </p>
    </div>
  );
};

// ============================================
// MAIN DASHBOARD COMPONENT
// ============================================

const InviteDashboard = () => {
  // State
  const [timePeriod, setTimePeriod] = useState("30");
  const [customDaysBack, setCustomDaysBack] = useState("");
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [selectedFilterType, setSelectedFilterType] = useState("all");
  const [roleSearch, setRoleSearch] = useState("");
  const [tempRoleId, setTempRoleId] = useState("");
  const [tempRoleSearch, setTempRoleSearch] = useState("");
  const [showApplyButton, setShowApplyButton] = useState(false);
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  
  const [roles, setRoles] = useState([]);
  const [filteredRoles, setFilteredRoles] = useState([]);
  
  const [loading, setLoading] = useState(true);
  const [currentServer, setCurrentServer] = useState(null);
  const [currentUserId, setCurrentUserId] = useState("");
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isPublicMode, setIsPublicMode] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [apiError, setApiError] = useState(null);
  const [serverTimezone, setServerTimezone] = useState('UTC');
  const [retentionAlert, setRetentionAlert] = useState(null);
  const [retentionDismissed, setRetentionDismissed] = useState(false);
  
  // Individual loading states
  const [loadingSummaryStats, setLoadingSummaryStats] = useState(true);
  const [loadingAverages, setLoadingAverages] = useState(true);
  const [loadingChart, setLoadingChart] = useState(true);
  const [loadingUserLeaderboard, setLoadingUserLeaderboard] = useState(true);
  const [loadingCodeLeaderboard, setLoadingCodeLeaderboard] = useState(true);
  
  // Data states
  const [inviteStats, setInviteStats] = useState({
    total_invites: 0,
    valid_invites: 0,
    suspicious_invites: 0,
    left_invites: 0,
    unique_inviters: 0,
    unique_invitees: 0
  });
  
  // Averages data
  const [averagesData, setAveragesData] = useState({
    avgPerInviter: 0,
    avgPerDay: 0,
    avgPerMonth: 0,
    avgPerYear: 0,
    daysInPeriod: 30
  });
  
  // Leaderboard data
  const [topUsers, setTopUsers] = useState([]);
  const [topInviteCodes, setTopInviteCodes] = useState([]);
  
  // Timeseries data for chart
  const [timeseriesData, setTimeseriesData] = useState([]);
  
  // Profile pictures and names cache - ONLY for top 3 users
  const [profilePictures, setProfilePictures] = useState({});
  const [userNames, setUserNames] = useState({});
  const [roleNames, setRoleNames] = useState({});
  const [roleColors, setRoleColors] = useState({});

  // Loading states
  const [rolesLoaded, setRolesLoaded] = useState(false);

  // Flag to track if initial load is complete
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);
  const initialDataLoadedRef = useRef(false);

  // Use refs to prevent infinite loops
  const fetchedRef = useRef(false);
  const prevFiltersRef = useRef(JSON.stringify({
    timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedRoleId, selectedFilterType
  }));

  // Guards against StrictMode / remount double-firing the initial load
  const didInitRef = useRef(false);

  // Tracks in-flight data requests so overlapping triggers reuse the same promise
  // instead of firing duplicate API bursts
  const inFlightRequestsRef = useRef({});

  // Create refs for current data to use in callbacks
  const rolesRef = useRef([]);

  // Update refs when state changes
  useEffect(() => {
    rolesRef.current = roles;
  }, [roles]);

  const NAVBAR_HEIGHT = "80px";

  // Fetch server timezone from API (not device timezone)
  useEffect(() => {
    const fetchServerTimezone = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/user/timezone`, {
          credentials: 'include',
          headers: { 'Accept': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.timezone) {
            setServerTimezone(data.timezone);
          }
        }
      } catch (error) {
        console.error('Error fetching server timezone:', error);
        setServerTimezone('UTC');
      }
    };
    
    fetchServerTimezone();
  }, []);

  // Check if current user is privileged
  const isPrivilegedUser = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  // Load everything on mount - guarded so StrictMode's double-invoke
  // (or any remount) can't fire the whole init sequence twice
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!currentServer || isPublicMode || hasAccess === null) { setRetentionAlert(null); return; }
    let cancelled = false;
    const fetchRetentionStatus = async () => {
      try {
        const r = await fetch(`${API_BASE_URL}/api/retention/status?guild_id=${currentServer.id}`, {
          credentials: 'include',
          headers: { Accept: 'application/json' },
        });
        if (!r.ok) return;
        const d = await r.json();
        if (!cancelled) {
          setRetentionAlert(d.show_alert ? { message: d.message } : null);
          setRetentionDismissed(false);
        }
      } catch {
        if (!cancelled) setRetentionAlert(null);
      }
    };
    fetchRetentionStatus();
    return () => { cancelled = true; };
  }, [currentServer, isPublicMode, hasAccess]);

  // applyServerTimePeriod returns computed values synchronously so callers
  // can use the resolved period immediately instead of waiting on state
  const applyServerTimePeriod = (settings) => {
    const mode = settings.default_time_mode || 'days_back';
    const result = {};

    if (mode === 'all_time') {
      setTimePeriod('all');
      result.timePeriod = 'all';
    } else if (mode === 'days_back') {
      const days = settings.default_days_back || 14;
      const presets = ['7', '14', '30', '60', '90'];
      if (presets.includes(String(days))) {
        setTimePeriod(String(days));
        result.timePeriod = String(days);
      } else {
        setTimePeriod('custom-lookback');
        setCustomDaysBack(String(days));
        result.timePeriod = 'custom-lookback';
        result.customDaysBack = String(days);
      }
    } else if (mode === 'date_range') {
      setTimePeriod('custom-range');
      const today = new Date();
      const formattedToday = today.toISOString().split('T')[0];
      
      let fromDate = null;
      let toDate = null;
      
      if (settings.default_from_date) {
        fromDate = settings.default_from_date.split('T')[0];
        setCustomStartDate(fromDate);
      }
      if (settings.default_to_date) {
        toDate = settings.default_to_date.split('T')[0];
        setCustomEndDate(toDate);
      }
      
      if (fromDate && !toDate) {
        toDate = formattedToday;
        setCustomEndDate(toDate);
      } else if (!fromDate && toDate) {
        fromDate = '';
        setCustomStartDate('');
      }
      
      result.timePeriod = 'custom-range';
      result.customStartDate = fromDate || '';
      result.customEndDate = toDate || '';
    } else if (mode === 'rolling_window') {
      const today = new Date();
      const formattedToday = today.toISOString().split('T')[0];
      let startDate = null;
      
      if (settings.default_rolling_type === 'weekday' && settings.default_rolling_value !== null) {
        const targetWeekday = settings.default_rolling_value;
        const currentWeekday = today.getDay();
        const currentWeekdayMonday = currentWeekday === 0 ? 6 : currentWeekday - 1;
        
        let daysToSubtract;
        if (currentWeekdayMonday >= targetWeekday) {
          daysToSubtract = currentWeekdayMonday - targetWeekday;
        } else {
          daysToSubtract = currentWeekdayMonday + 7 - targetWeekday;
        }
        
        startDate = new Date(today);
        startDate.setDate(today.getDate() - daysToSubtract);
        
      } else if (settings.default_rolling_type === 'monthly' && settings.default_rolling_value !== null) {
        const targetDay = settings.default_rolling_value;
        const currentDate = today.getDate();
        
        startDate = new Date(today);
        
        if (currentDate >= targetDay) {
          startDate.setDate(targetDay);
        } else {
          startDate.setMonth(today.getMonth() - 1);
          const lastDayOfMonth = new Date(startDate.getFullYear(), startDate.getMonth() + 1, 0).getDate();
          startDate.setDate(Math.min(targetDay, lastDayOfMonth));
        }
      }
      
      if (startDate) {
        const formattedStartDate = startDate.toISOString().split('T')[0];
        setTimePeriod('custom-range');
        setCustomStartDate(formattedStartDate);
        setCustomEndDate(formattedToday);
        result.timePeriod = 'custom-range';
        result.customStartDate = formattedStartDate;
        result.customEndDate = formattedToday;
      } else {
        setTimePeriod('all');
        result.timePeriod = 'all';
      }
    }
    
    return result;
  };

  // ============================================
  // FIXED USERNAME FETCHING FUNCTIONS
  // ============================================

  // FIXED: Fetch single user's basic info (username only, no avatar)
  const fetchUserBasicInfo = async (userId, guildId) => {
    if (!userId) return null;
    
    const stringId = String(userId);
    const cacheKey = `${guildId}:${stringId}`;
    
    if (userBasicInfoCache.has(cacheKey)) {
      const cached = userBasicInfoCache.get(cacheKey);
      if (cached.name && !cached.name.startsWith('User ')) {
        return cached;
      }
      userBasicInfoCache.delete(cacheKey);
    }
    
    try {
      const isPublic = isPublicMode;
      // Use the any-table endpoint
      const url = isPublic 
        ? `${API_BASE_URL}/api/public/username/any-table/${guildId}/${stringId}`
        : `${API_BASE_URL}/api/username/any-table/${guildId}/${stringId}`;
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.username && !data.username.startsWith('User ')) {
          const userInfo = {
            id: stringId,
            name: data.username,
            username: data.username
          };
          userBasicInfoCache.set(cacheKey, userInfo);
          return userInfo;
        }
      }
    } catch (error) {
      console.error(`Error fetching user basic info for ${stringId}:`, error);
    }
    
    const fallbackInfo = { id: stringId, name: `User ${stringId.slice(-4)}`, username: `User ${stringId.slice(-4)}` };
    return fallbackInfo;
  };

  // FIXED: Batch fetch user basic info (usernames only) using any-table endpoint
  const batchFetchUserBasicInfo = async (guildId, userIds) => {
    if (!guildId || !userIds || userIds.length === 0) return {};
    
    const uncachedUserIds = [];
    const results = {};
    
    for (const userId of userIds) {
      const stringId = String(userId);
      const cacheKey = `${guildId}:${stringId}`;
      if (userBasicInfoCache.has(cacheKey)) {
        const cached = userBasicInfoCache.get(cacheKey);
        if (cached.name && !cached.name.startsWith('User ')) {
          results[stringId] = cached;
          continue;
        }
      }
      uncachedUserIds.push(stringId);
    }
    
    if (uncachedUserIds.length === 0) {
      return results;
    }
    
    try {
      const isPublic = isPublicMode;
      const fetchPromises = uncachedUserIds.map(async (userId) => {
        const url = isPublic
          ? `${API_BASE_URL}/api/public/username/any-table/${guildId}/${userId}`
          : `${API_BASE_URL}/api/username/any-table/${guildId}/${userId}`;
        
        const response = await fetch(url, {
          credentials: isPublic ? 'omit' : 'include',
          headers: { 'Accept': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.success && data.username && !data.username.startsWith('User ')) {
            return { userId, username: data.username };
          }
        }
        return { userId, username: null };
      });
      
      const fetchedResults = await Promise.all(fetchPromises);
      
      for (const { userId, username } of fetchedResults) {
        if (username) {
          const userInfo = {
            id: userId,
            name: username,
            username: username
          };
          const cacheKey = `${guildId}:${userId}`;
          userBasicInfoCache.set(cacheKey, userInfo);
          results[userId] = userInfo;
        }
      }
      
    } catch (error) {
      console.error('Error in batch fetch user basic info:', error);
    }
    
    for (const userId of uncachedUserIds) {
      if (!results[userId]) {
        const fallbackInfo = { id: userId, name: `User ${userId.slice(-4)}`, username: `User ${userId.slice(-4)}` };
        results[userId] = fallbackInfo;
      }
    }
    
    return results;
  };

  // FIXED: Fetch user avatar (only for top 3 users)
  const fetchUserAvatar = async (userId) => {
    if (!userId) return null;
    
    const stringId = String(userId);
    const cached = profileCache.get(stringId);
    if (cached && cached.avatar) return cached.avatar;
    
    try {
      const isPublic = isPublicMode;
      const url = `${API_BASE_URL}/api/user/profile-picture/${stringId}`;
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.avatar_url) {
          const userData = { id: stringId, avatar: data.avatar_url };
          profileCache.set(stringId, userData);
          return data.avatar_url;
        }
      }
    } catch (error) {
      console.error(`Error fetching avatar for ${stringId}:`, error);
    }
    return null;
  };

  // ============================================
  // FETCH ALL ROLES - FIXED
  // ============================================
  const fetchAllRoles = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setRolesLoaded(false);
    
    const cacheKey = getCacheKey('invite-roles', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    
    if (cached) {
      setRoles(cached.roleList);
      setFilteredRoles(cached.roleList);
      setRoleNames(cached.nameMap);
      setRoleColors(cached.colorMap);
      setRolesLoaded(true);
      return;
    }
    
    try {
      const url = isPublic 
        ? `${API_BASE_URL}/api/public/server/real-roles?guild_id=${currentServer.id}`
        : `${API_BASE_URL}/api/server/real-roles?guild_id=${currentServer.id}`;
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const rolesData = await response.json();
        
        if (Array.isArray(rolesData)) {
          const roleList = [];
          const nameMap = {};
          const colorMap = {};
          
          rolesData.forEach(role => {
            const roleId = String(role.id);
            roleList.push({
              id: roleId,
              name: role.name,
              color: role.color,
              searchString: `${role.name} ${roleId}`.toLowerCase()
            });
            nameMap[roleId] = role.name;
            colorMap[roleId] = role.color || '#99aab5';
          });
          
          roleList.sort((a, b) => a.name.localeCompare(b.name));
          
          const cacheData = { roleList, nameMap, colorMap };
          serverDataCache.set(cacheKey, cacheData);
          
          setRoles(roleList);
          setFilteredRoles(roleList);
          setRoleNames(nameMap);
          setRoleColors(colorMap);
        }
      }
    } catch (error) {
      console.error('Error fetching roles:', error);
    } finally {
      setRolesLoaded(true);
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
      
      if (authResponse.ok) {
        const authData = await authResponse.json();
        
        if (authData.authenticated && authData.user) {
          setIsAuthenticated(true);
          setCurrentUserId(authData.user.id);
          setIsPublicMode(false);
          
          if (isPrivilegedUser(authData.user.id)) {
            setHasAccess(true);
            setDashboardAccessLevel('Admin');
            window.accessLevel = 'Admin';
            
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
                } else {
                  setIsPublicMode(true);
                  setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
                }
              } else {
                setIsPublicMode(true);
                setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
              }
            } else {
              setIsPublicMode(true);
              setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
            }
            
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
                  selectedServer.permissions,
                  selectedServer.has_admin,
                  selectedServer.has_manage_server
                );
              } else {
                setLoadingServers(false);
              }
            } else {
              await loadPublicStats();
            }
          } else {
            await loadPublicStats();
          }
        } else {
          setIsAuthenticated(false);
          setIsPublicMode(true);
          setHasAccess(true);
          await loadPublicStats();
        }
      } else {
        setIsAuthenticated(false);
        setIsPublicMode(true);
        setHasAccess(true);
        await loadPublicStats();
      }
    } catch (error) {
      console.error('Error loading initial data:', error);
      setApiError('Failed to load servers. Please check your connection.');
      setIsPublicMode(true);
      setHasAccess(true);
      await loadPublicStats();
    } finally {
      setLoadingServers(false);
    }
  };

  const loadPublicStats = async () => {
    setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
    setIsPublicMode(true);
    setHasAccess(true);
    setLoading(false);
  };

  // Determines access only. Does NOT fetch settings/time-period or trigger
  // a data fetch itself — that all happens exactly once, in the unified
  // [currentServer, hasAccess] effect below, to avoid duplicate/racing fetches.
  const checkServerAccess = async (guildId, permissions, hasAdmin, hasManageServer) => {
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
          hasAccessFlag = true;
        } else if (accessLevel === 'Moderator') {
          hasAccessFlag = isAdmin || hasManageServerPerm;
        } else if (accessLevel === 'Admin') {
          hasAccessFlag = isAdmin;
        } else {
          hasAccessFlag = true;
        }
        
        setHasAccess(hasAccessFlag);
      } else {
        console.error('Failed to get settings for guild:', guildId);
        setHasAccess(false);
      }
    } catch (error) {
      console.error('Error checking server access:', error);
      setHasAccess(false);
    } finally {
      setLoading(false);
    }
  };

  // fetchDataWithParams - uses overrides instead of state, and dedupes
  // concurrent identical requests via inFlightRequestsRef so overlapping
  // triggers (double effects, fast re-renders, etc.) can't fire duplicate bursts
  const fetchDataWithParams = async (overrides = {}) => {
    if (!currentServer || !hasAccess) return;

    const requestKey = `${currentServer.id}:${JSON.stringify(overrides)}`;
    if (inFlightRequestsRef.current[requestKey]) {
      return inFlightRequestsRef.current[requestKey];
    }

    const requestPromise = (async () => {
      setLoading(true);
      setApiError(null);

      const effectiveTimePeriod = overrides.timePeriod ?? timePeriod;
      const effectiveCustomDaysBack = overrides.customDaysBack ?? customDaysBack;
      const effectiveCustomStartDate = overrides.customStartDate ?? customStartDate;
      const effectiveCustomEndDate = overrides.customEndDate ?? customEndDate;

      let startDate = null;
      let endDate = null;
      let daysBack = 30;

      if (effectiveTimePeriod === "all") {
        daysBack = 2000;
      } else if (effectiveTimePeriod === "custom-lookback") {
        if (effectiveCustomDaysBack && parseInt(effectiveCustomDaysBack) > 0) {
          daysBack = parseInt(effectiveCustomDaysBack);
          endDate = new Date();
          startDate = new Date();
          startDate.setDate(startDate.getDate() - daysBack);
        }
      } else if (effectiveTimePeriod === "custom-range") {
        if (effectiveCustomStartDate && effectiveCustomEndDate) {
          startDate = new Date(effectiveCustomStartDate);
          endDate = new Date(effectiveCustomEndDate);
          daysBack = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
        }
      } else {
        daysBack = parseInt(effectiveTimePeriod);
        endDate = new Date();
        startDate = new Date();
        startDate.setDate(startDate.getDate() - daysBack);
      }

      try {
        const roleFilterArray = selectedRoleId ? [String(selectedRoleId)] : null;

        await Promise.all([
          fetchTotalStatsWithDates(roleFilterArray, startDate, endDate, daysBack),
          fetchUserLeaderboardWithDates(roleFilterArray, startDate, endDate, daysBack),
          fetchCodeLeaderboardWithDates(roleFilterArray, startDate, endDate, daysBack),
          fetchTimeseriesDataWithDates(roleFilterArray, startDate, endDate, daysBack)
        ]);

      } catch (error) {
        console.error('Error fetching data:', error);
        setApiError(error.message);
      } finally {
        setLoading(false);
        fetchedRef.current = true;
        delete inFlightRequestsRef.current[requestKey];
      }
    })();

    inFlightRequestsRef.current[requestKey] = requestPromise;
    return requestPromise;
  };

  // Helper functions for fetchDataWithParams
  const fetchTotalStatsWithDates = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingSummaryStats(true);
    setLoadingAverages(true);
    
    const isPublic = isPublicMode;
    const daysInPeriod = daysBack;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack
      };
      
      if (currentUserId && !isPublic) {
        requestBody.user_id = currentUserId;
      }
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/stats/total`
        : `${API_BASE_URL}/api/invite/stats/total`;
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const stats = await response.json();
      
      setInviteStats(stats);
      
      const averages = {
        avgPerInviter: stats.unique_inviters > 0 ? stats.total_invites / stats.unique_inviters : 0,
        avgPerDay: daysInPeriod > 0 ? stats.total_invites / daysInPeriod : 0,
        avgPerMonth: daysInPeriod > 0 ? (stats.total_invites / daysInPeriod) * 30 : 0,
        avgPerYear: daysInPeriod > 0 ? (stats.total_invites / daysInPeriod) * 365 : 0,
        daysInPeriod: daysInPeriod
      };
      
      setAveragesData(averages);
    } catch (error) {
      console.error('Error fetching total stats:', error);
    } finally {
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
    }
  };

  const fetchUserLeaderboardWithDates = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingUserLeaderboard(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack,
        limit: 100000000000
      };
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/leaderboard/users`
        : `${API_BASE_URL}/api/invite/leaderboard/users`;
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('Failed to fetch user leaderboard:', response.status);
        setLoadingUserLeaderboard(false);
        return;
      }
      
      const data = await response.json();
      
      const allUserIds = data.map(user => String(user.user_id));
      const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds);
      
      const formattedUsers = await Promise.all(data.map(async (user, index) => {
        const userId = String(user.user_id);
        const isTop3 = index < 3;
        const userInfo = userInfoMap[userId] || { name: `User ${userId.slice(-4)}` };
        
        let avatar = null;
        if (isTop3) {
          avatar = await fetchUserAvatar(userId);
        }
        
        return {
          userId: userId,
          name: userInfo.name,
          value: user.total_invites || 0,
          validInvites: user.valid_invites || 0,
          suspiciousInvites: user.suspicious_invites || 0,
          leftInvites: user.left_invites || 0,
          percentageValid: user.percentage_valid || 0,
          rank: index + 1,
          avatar: avatar
        };
      }));
      
      setTopUsers(formattedUsers);
    } catch (error) {
      console.error('Error fetching user leaderboard:', error);
    } finally {
      setLoadingUserLeaderboard(false);
    }
  };

  const fetchCodeLeaderboardWithDates = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingCodeLeaderboard(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack,
        limit: 100000000000
      };
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/leaderboard/codes`
        : `${API_BASE_URL}/api/invite/leaderboard/codes`;
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('Failed to fetch code leaderboard:', response.status);
        setLoadingCodeLeaderboard(false);
        return;
      }
      
      const data = await response.json();
      
      const formattedCodes = data.map((code, index) => {
        const inviterId = code.inviter_id;
        
        return {
          id: code.invite_code,
          name: code.invite_code,
          inviterName: code.inviter_name || (inviterId ? `User ${inviterId}` : 'Unknown'),
          inviterId: inviterId,
          value: code.total_uses || 0,
          validUses: code.valid_uses || 0,
          suspiciousUses: code.suspicious_uses || 0,
          leftUses: code.left_uses || 0,
          percentageValid: code.percentage_valid || 0,
          created_at: code.created_at,
          last_used: code.last_used,
          rank: index + 1
        };
      });
      
      setTopInviteCodes(formattedCodes);
    } catch (error) {
      console.error('Error fetching code leaderboard:', error);
    } finally {
      setLoadingCodeLeaderboard(false);
    }
  };

  const fetchTimeseriesDataWithDates = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingChart(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack,
        interval: "day"
      };
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/timeseries`
        : `${API_BASE_URL}/api/invite/timeseries`;
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('Failed to fetch timeseries data:', response.status);
        setTimeseriesData([]);
        setLoadingChart(false);
        return;
      }
      
      const data = await response.json();
      
      const chartData = data.map(item => ({
        date: item.date,
        value: item.total_invites,
        valid: item.valid_invites,
        suspicious: item.suspicious_invites,
        left: item.left_invites
      })).sort((a, b) => new Date(a.date) - new Date(b.date));
      
      setTimeseriesData(chartData);
    } catch (error) {
      console.error('Error fetching timeseries data:', error);
      setTimeseriesData([]);
    } finally {
      setLoadingChart(false);
    }
  };

  // Helper function to get role name from ID
  const getRoleName = (roleId) => {
    if (!roleId) return 'Unknown Role';
    const stringId = String(roleId).trim();
    const role = rolesRef.current.find(r => String(r.id) === stringId);
    if (role) return role.name;
    return `Role ${stringId}`;
  };

  // Helper function to get role color from ID
  const getRoleColor = (roleId) => {
    if (!roleId) return '#99aab5';
    const stringId = String(roleId).trim();
    if (roleColors[stringId]) return roleColors[stringId];
    const role = rolesRef.current.find(r => String(r.id) === stringId);
    if (role) return role.color || '#99aab5';
    return '#99aab5';
  };

  // ============================================
  // UNIFIED SERVER-CHANGE LIFECYCLE
  // ============================================
  // Single effect that owns everything that needs to happen when the
  // active server (or access) changes: reset state -> fetch roles ->
  // fetch settings -> resolve the server's default time period -> fetch
  // data ONCE with the resolved params -> mark init complete.
  // This replaces three previously-separate effects that were racing each
  // other and causing the "shows default period, then reloads to the real
  // default" flash, as well as duplicate/triple API bursts.
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    if (initialDataLoadedRef.current === currentServer.id) return;

    initialDataLoadedRef.current = currentServer.id;
    fetchedRef.current = false;
    setInitialLoadComplete(false);

    setLoadingSummaryStats(true);
    setLoadingAverages(true);
    setLoadingChart(true);
    setLoadingUserLeaderboard(true);
    setLoadingCodeLeaderboard(true);
    setLoading(true);
    setRolesLoaded(false);

    setSelectedRoleId("");
    setRoleSearch("");

    setInviteStats({
      total_invites: 0,
      valid_invites: 0,
      suspicious_invites: 0,
      left_invites: 0,
      unique_inviters: 0,
      unique_invitees: 0
    });
    setTopUsers([]);
    setTopInviteCodes([]);
    setTimeseriesData([]);

    // Clear caches when server changes
    profileCache.clear();
    userBasicInfoCache.clear();

    const initializeServer = async () => {
      // Roles can load independently in parallel - they don't gate stats
      fetchAllRoles();

      // Resolve the server's configured default time period BEFORE any
      // stats/leaderboard/chart fetch, so we only ever fetch data once
      // with the correct params (no default-then-correct flash).
      let timeParams = {};
      try {
        const response = await fetch(`${API_BASE_URL}/api/settings/get`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublicMode ? 'omit' : 'include',
          body: JSON.stringify({ guild_id: currentServer.id })
        });
        if (response.ok) {
          const data = await response.json();
          timeParams = applyServerTimePeriod(data);
        }
      } catch (e) {
        console.error('Error fetching time period settings:', e);
      }

      await fetchDataWithParams(timeParams);

      // Sync prevFiltersRef to the values that will actually be reflected
      // in state once this render commits, so the filter-watcher effect
      // below sees no diff and doesn't fire a duplicate fetch right after init.
      const resolvedFilters = {
        timePeriod: timeParams.timePeriod ?? timePeriod,
        customDaysBack: timeParams.customDaysBack ?? customDaysBack,
        customStartDate: timeParams.customStartDate ?? customStartDate,
        customEndDate: timeParams.customEndDate ?? customEndDate,
        selectedRoleId: "",
        selectedFilterType
      };
      const sortedFilterObj = {};
      Object.keys(resolvedFilters).sort().forEach(key => {
        sortedFilterObj[key] = resolvedFilters[key];
      });
      prevFiltersRef.current = JSON.stringify(sortedFilterObj);

      setInitialLoadComplete(true);
      setLoading(false);
    };

    initializeServer();
  }, [currentServer, hasAccess]);

  // Fetch stats when filters change (user-driven changes only - init is
  // handled above and syncs prevFiltersRef so this won't double-fire on load)
  useEffect(() => {
    if (!currentServer || !initialLoadComplete || !hasAccess) return;
    
    const filterObj = {
      timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedRoleId, selectedFilterType
    };
    const sortedFilterObj = {};
    Object.keys(filterObj).sort().forEach(key => {
      sortedFilterObj[key] = filterObj[key];
    });
    const currentFilters = JSON.stringify(sortedFilterObj);
    
    if (fetchedRef.current && prevFiltersRef.current !== currentFilters) {
      prevFiltersRef.current = currentFilters;
      
      setLoadingSummaryStats(true);
      setLoadingAverages(true);
      setLoadingChart(true);
      setLoadingUserLeaderboard(true);
      setLoadingCodeLeaderboard(true);
      
      fetchData();
    }
  }, [
    timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedRoleId, selectedFilterType, initialLoadComplete, hasAccess
  ]);

  // Filter roles when search changes
  useEffect(() => {
    if (tempRoleSearch.trim() === "") {
      setFilteredRoles(roles);
    } else {
      const searchLower = tempRoleSearch.toLowerCase();
      const filtered = roles.filter(role => 
        role.searchString?.includes(searchLower) ||
        role.id?.includes(searchLower)
      );
      setFilteredRoles(filtered);
    }
  }, [tempRoleSearch, roles]);

  // Get days back value for API
  const getDaysBack = () => {
    if (timePeriod === "all") {
      return 2000;
    }
    
    if (timePeriod === "custom-lookback") {
      if (!customDaysBack || parseInt(customDaysBack) <= 0) {
        return 30;
      }
      return parseInt(customDaysBack);
    }
    
    if (timePeriod === "custom-range") {
      if (!customStartDate || !customEndDate) {
        return 30;
      }
      const start = new Date(customStartDate);
      const end = new Date(customEndDate);
      const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
      return days > 0 ? days : 30;
    }
    
    return parseInt(timePeriod);
  };

  const getDateRange = () => {
    if (timePeriod === "all") {
      return { startDate: null, endDate: null };
    }
    
    if (timePeriod === "custom-lookback") {
      if (!customDaysBack || parseInt(customDaysBack) <= 0) {
        return { startDate: null, endDate: null };
      }
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - parseInt(customDaysBack));
      return { startDate, endDate };
    }
    
    if (timePeriod === "custom-range") {
      if (!customStartDate || !customEndDate) {
        return { startDate: null, endDate: null };
      }
      return { 
        startDate: new Date(customStartDate), 
        endDate: new Date(customEndDate) 
      };
    }
    
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - parseInt(timePeriod));
    
    return { startDate, endDate };
  };

  const calculateAverages = (totalInvites, uniqueInviters, daysInPeriod) => {
    if (daysInPeriod === 0) {
      return {
        avgPerInviter: 0,
        avgPerDay: 0,
        avgPerMonth: 0,
        avgPerYear: 0,
        daysInPeriod: 0
      };
    }

    const avgPerInviter = uniqueInviters > 0 ? totalInvites / uniqueInviters : 0;
    const avgPerDay = totalInvites / daysInPeriod;
    const avgPerMonth = avgPerDay * 30;
    const avgPerYear = avgPerDay * 365;

    return {
      avgPerInviter,
      avgPerDay,
      avgPerMonth,
      avgPerYear,
      daysInPeriod
    };
  };

  // fetchData - used for filter-change-driven refetches (after initial load).
  // Also deduped through inFlightRequestsRef via the same request-key scheme.
  const fetchData = async () => {
    if (!currentServer || !hasAccess) return;

    const daysBackForKey = getDaysBack();
    const requestKey = `${currentServer.id}:filters:${JSON.stringify({
      timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedRoleId, selectedFilterType
    })}`;

    if (inFlightRequestsRef.current[requestKey]) {
      return inFlightRequestsRef.current[requestKey];
    }

    const requestPromise = (async () => {
      setApiError(null);
      const daysBack = getDaysBack();
      const { startDate, endDate } = getDateRange();
      const daysInPeriod = daysBack;

      try {
        const roleFilterArray = selectedRoleId ? [String(selectedRoleId)] : null;

        await Promise.all([
          fetchTotalStats(roleFilterArray, startDate, endDate, daysBack, daysInPeriod),
          fetchUserLeaderboard(roleFilterArray, startDate, endDate, daysBack),
          fetchCodeLeaderboard(roleFilterArray, startDate, endDate, daysBack),
          fetchTimeseriesData(roleFilterArray, startDate, endDate, daysBack)
        ]);

      } catch (error) {
        console.error('Error fetching data:', error);
        setApiError(error.message);
      } finally {
        fetchedRef.current = true;
        delete inFlightRequestsRef.current[requestKey];
      }
    })();

    inFlightRequestsRef.current[requestKey] = requestPromise;
    return requestPromise;
  };

  // Fetch total invite statistics
  const fetchTotalStats = async (roleFilterArray, startDate, endDate, daysBack, daysInPeriod) => {
    setLoadingSummaryStats(true);
    setLoadingAverages(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack
      };
      
      if (currentUserId && !isPublic) {
        requestBody.user_id = currentUserId;
      }
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/stats/total`
        : `${API_BASE_URL}/api/invite/stats/total`;
      
      const cacheKey = getCacheKey('invite-total', currentServer.id, { ...requestBody, public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setInviteStats(cached.stats);
        setAveragesData(cached.averages);
        setLoadingSummaryStats(false);
        setLoadingAverages(false);
        return;
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('❌ TOTAL STATS ERROR:', response.status);
        throw new Error(`API error: ${response.status}`);
      }
      
      const stats = await response.json();
      
      setInviteStats(stats);
      
      const averages = calculateAverages(
        stats.total_invites || 0,
        stats.unique_inviters || 0,
        daysInPeriod
      );
      
      setAveragesData(averages);
      
      serverDataCache.set(cacheKey, { stats, averages });
    } catch (error) {
      console.error('❌ TOTAL STATS CATCH ERROR:', error);
    } finally {
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
    }
  };

  // FIXED: Fetch user leaderboard - Batch fetch usernames for all, avatars only for top 3
  const fetchUserLeaderboard = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingUserLeaderboard(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack,
        limit: 100000000000
      };
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/leaderboard/users`
        : `${API_BASE_URL}/api/invite/leaderboard/users`;
      
      const cacheKey = getCacheKey('invite-users', currentServer.id, { ...requestBody, public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setTopUsers(cached);
        setLoadingUserLeaderboard(false);
        return;
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('Failed to fetch user leaderboard:', response.status);
        setLoadingUserLeaderboard(false);
        return;
      }
      
      const data = await response.json();
      
      const allUserIds = data.map(user => String(user.user_id));
      const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds);
      
      const formattedUsers = await Promise.all(data.map(async (user, index) => {
        const userId = String(user.user_id);
        const isTop3 = index < 3;
        const userInfo = userInfoMap[userId] || { name: `User ${userId.slice(-4)}` };
        
        let avatar = null;
        if (isTop3) {
          avatar = await fetchUserAvatar(userId);
        }
        
        return {
          userId: userId,
          name: userInfo.name,
          value: user.total_invites || 0,
          validInvites: user.valid_invites || 0,
          suspiciousInvites: user.suspicious_invites || 0,
          leftInvites: user.left_invites || 0,
          percentageValid: user.percentage_valid || 0,
          rank: index + 1,
          avatar: avatar
        };
      }));
      
      setTopUsers(formattedUsers);
      serverDataCache.set(cacheKey, formattedUsers);
    } catch (error) {
      console.error('Error fetching user leaderboard:', error);
    } finally {
      setLoadingUserLeaderboard(false);
    }
  };

  // Fetch invite code leaderboard (no avatars needed)
  const fetchCodeLeaderboard = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingCodeLeaderboard(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack,
        limit: 100000000000
      };
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/leaderboard/codes`
        : `${API_BASE_URL}/api/invite/leaderboard/codes`;
      
      const cacheKey = getCacheKey('invite-codes', currentServer.id, { ...requestBody, public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setTopInviteCodes(cached);
        setLoadingCodeLeaderboard(false);
        return;
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('Failed to fetch code leaderboard:', response.status);
        setLoadingCodeLeaderboard(false);
        return;
      }
      
      const data = await response.json();
      
      const formattedCodes = data.map((code, index) => {
        const inviterId = code.inviter_id;
        
        return {
          id: code.invite_code,
          name: code.invite_code,
          inviterName: code.inviter_name || (inviterId ? `User ${inviterId}` : 'Unknown'),
          inviterId: inviterId,
          value: code.total_uses || 0,
          validUses: code.valid_uses || 0,
          suspiciousUses: code.suspicious_uses || 0,
          leftUses: code.left_uses || 0,
          percentageValid: code.percentage_valid || 0,
          created_at: code.created_at,
          last_used: code.last_used,
          rank: index + 1
        };
      });
      
      setTopInviteCodes(formattedCodes);
      serverDataCache.set(cacheKey, formattedCodes);
    } catch (error) {
      console.error('Error fetching code leaderboard:', error);
    } finally {
      setLoadingCodeLeaderboard(false);
    }
  };

  // Fetch timeseries data
  const fetchTimeseriesData = async (roleFilterArray, startDate, endDate, daysBack) => {
    setLoadingChart(true);
    
    const isPublic = isPublicMode;
    
    try {
      const filterTypeString = String(selectedFilterType);
      
      const requestBody = {
        guild_id: currentServer.id,
        filter_type: filterTypeString,
        days: daysBack,
        interval: "day"
      };
      
      if (roleFilterArray && roleFilterArray.length > 0) {
        requestBody.role_filter_ids = roleFilterArray;
      }
      
      if (startDate) {
        requestBody.start_time = startDate.toISOString();
      }
      if (endDate) {
        requestBody.end_time = endDate.toISOString();
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/invite/timeseries`
        : `${API_BASE_URL}/api/invite/timeseries`;
      
      const cacheKey = getCacheKey('invite-timeseries', currentServer.id, { ...requestBody, public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setTimeseriesData(cached);
        setLoadingChart(false);
        return;
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        console.error('Failed to fetch timeseries data:', response.status);
        setTimeseriesData([]);
        setLoadingChart(false);
        return;
      }
      
      const data = await response.json();
      
      const chartData = data.map(item => ({
        date: item.date,
        value: item.total_invites,
        valid: item.valid_invites,
        suspicious: item.suspicious_invites,
        left: item.left_invites
      })).sort((a, b) => new Date(a.date) - new Date(b.date));
      
      setTimeseriesData(chartData);
      serverDataCache.set(cacheKey, chartData);
    } catch (error) {
      console.error('Error fetching timeseries data:', error);
      setTimeseriesData([]);
    } finally {
      setLoadingChart(false);
    }
  };

  // Handle temporary role selection
  const handleTempRoleSelect = (role) => {
    setTempRoleId(role.id);
    setTempRoleSearch(role.name || `Role ${role.id}`);
    setShowApplyButton(true);
    setShowRoleDropdown(false);
  };

  // Apply role filter
  const applyRoleFilter = () => {
    setSelectedRoleId(tempRoleId);
    setRoleSearch(tempRoleSearch);
    setShowApplyButton(false);
    setShowRoleDropdown(false);
    serverDataCache.clearPattern('invite-total');
    serverDataCache.clearPattern('invite-users');
    serverDataCache.clearPattern('invite-codes');
    serverDataCache.clearPattern('invite-timeseries');
  };

  // Clear role filter
  const clearRoleFilter = () => {
    setSelectedRoleId("");
    setRoleSearch("");
    setTempRoleId("");
    setTempRoleSearch("");
    setShowApplyButton(false);
    serverDataCache.clearPattern('invite-total');
    serverDataCache.clearPattern('invite-users');
    serverDataCache.clearPattern('invite-codes');
    serverDataCache.clearPattern('invite-timeseries');
  };

  const timePeriodOptions = [
    { value: '7', label: 'Last 7 days' },
    { value: '14', label: 'Last 14 days' },
    { value: '30', label: 'Last 30 days' },
    { value: '60', label: 'Last 60 days' },
    { value: '90', label: 'Last 90 days' },
    { value: 'all', label: 'All Time' },
    { value: 'custom-lookback', label: 'Custom lookback' },
    { value: 'custom-range', label: 'Custom date range' },
  ];

  const filterTypeOptions = [
    { value: 'all', label: 'All Invites' },
    { value: 'valid', label: 'Valid Invites Only' },
    { value: 'suspicious', label: 'Suspicious Invites Only' },
    { value: 'left', label: 'Left Users Only' }
  ];

  const styles = `
    @font-face {
      font-family: 'Horndon';
      src: url('/HorndonD.ttf') format('truetype');
      font-display: swap;
      font-weight: normal;
      font-style: normal;
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
      color: #ffffff;
      min-height: 100vh;
      display: flex;
      position: relative;
    }

    .dashboard-main {
      flex: 1;
      margin-left: 280px;
      background-color: #0a0a0a;
      min-height: calc(100vh - ${NAVBAR_HEIGHT});
      overflow-x: hidden;
      width: calc(100% - 280px);
    }

    .dashboard-content {
      max-width: 1600px;
      margin: 0 auto;
      padding: 20px 40px 40px 40px;
      background-color: #0a0a0a;
      width: 100%;
      overflow-x: visible;
    }

    .filters-section {
      background-color: #0a0a0a;
      padding: 24px;
      border-radius: 16px;
      margin-bottom: 20px;
      border: 1px solid #1a1a1a;
      display: flex;
      flex-wrap: wrap;
      gap: 24px;
      align-items: flex-start;
      backdrop-filter: blur(10px);
      width: 100%;
    }

    .filter-row {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 200px;
    }

    .filter-row label {
      color: #b0b0b0;
      font-size: 14px;
      font-weight: 500;
      white-space: nowrap;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      min-width: 80px;
    }

    .modern-select {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 12px 20px;
      font-size: 14px;
      cursor: pointer;
      outline: none;
      min-width: 200px;
      transition: all 0.2s ease;
      appearance: none;
      background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23aa00ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
      background-repeat: no-repeat;
      background-position: right 16px center;
      background-size: 16px;
    }

    .modern-select:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .modern-select:focus {
      border-color: #aa00ff;
      box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
    }

    .custom-date-range, .custom-lookback {
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
    }

    .custom-lookback input {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 12px 16px;
      font-size: 14px;
      outline: none;
      transition: all 0.2s ease;
      width: 150px;
    }

    .custom-lookback input:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .custom-lookback input:focus {
      border-color: #aa00ff;
      box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
    }

    .date-input {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .date-input label {
      color: #b0b0b0;
      font-size: 14px;
    }

    .modern-date-input {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 12px 16px;
      font-size: 14px;
      outline: none;
      transition: all 0.2s ease;
      cursor: pointer;
    }

    .modern-date-input:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .modern-date-input:focus {
      border-color: #aa00ff;
      box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
    }

    .modern-date-input::-webkit-calendar-picker-indicator {
      filter: invert(0.8);
      cursor: pointer;
    }

    .entity-filter {
      flex: 1;
      min-width: 250px;
      position: relative;
    }

    .entity-selector {
      position: relative;
      width: 100%;
    }

    .modern-entity-search {
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

    .modern-entity-search:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .modern-entity-search:focus {
      border-color: #aa00ff;
      box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
    }

    .modern-entity-search::placeholder {
      color: #666;
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
      backdrop-filter: blur(10px);
    }

    .entity-option {
      padding: 12px 16px;
      color: #ffffff;
      cursor: pointer;
      transition: all 0.2s ease;
      border-left: 3px solid transparent;
      font-size: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .entity-option:hover {
      background-color: #2a2a2a;
    }

    .entity-option.selected {
      background-color: #2a2a2a;
      border-left-color: #aa00ff;
    }

    .entity-info {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .entity-color-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
    }

    .retention-banner { width:100%; box-sizing:border-box; background:linear-gradient(135deg,#3a2f00 0%,#4a3a00 100%); border-bottom:1px solid #ffcc00; padding:12px 24px; display:flex; align-items:center; justify-content:center; gap:16px; position:relative; }
    .retention-banner-text { color:#ffe066; font-size:14px; font-weight:500; text-align:center; max-width:900px; }
    .retention-banner-close { background:none; border:none; color:#ffe066; font-size:14px; cursor:pointer; padding:4px 8px; border-radius:6px; line-height:1; flex-shrink:0; transition:background-color 0.15s,color 0.15s; }
    .retention-banner-close:hover { background-color:rgba(255,224,102,0.15); color:#fff; }

    .apply-button-container {
      display: flex;
      gap: 8px;
      margin-top: 8px;
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
      flex: 1;
    }

    .apply-button:hover {
      background-color: #8800cc;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
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
      transition: all 0.2s ease;
    }

    .clear-button:hover {
      border-color: #ff4444;
      color: #ff4444;
      background-color: #2a2a2a;
    }

    .active-role-filter {
      margin-top: 8px;
      padding: 8px 12px;
      background-color: rgba(170, 0, 255, 0.1);
      border: 1px solid #aa00ff;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .active-role-filter span {
      color: #aa00ff;
      font-size: 14px;
    }

    .active-role-filter button {
      background: none;
      border: none;
      color: #ff4444;
      cursor: pointer;
      font-size: 14px;
      padding: 4px 8px;
    }

    .active-role-filter button:hover {
      text-decoration: underline;
    }

    .loading {
      text-align: center;
      padding: 60px;
      color: #b0b0b0;
      font-size: 18px;
    }

    .error-message {
      text-align: center;
      padding: 60px;
      background-color: #0a0a0a;
      border: 1px solid #ff3333;
      border-radius: 16px;
      color: #ff3333;
    }

    .error-message h2 {
      color: #ff3333;
      margin-bottom: 16px;
    }

    .retry-button {
      background-color: #aa00ff;
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 12px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 20px;
      transition: all 0.2s ease;
    }

    .retry-button:hover {
      background-color: #8800cc;
      transform: translateY(-2px);
      box-shadow: 0 8px 16px rgba(170, 0, 255, 0.3);
    }

    .no-server {
      text-align: center;
      padding: 60px;
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      color: #b0b0b0;
    }

    .no-server h2 {
      color: #ffffff;
      margin-bottom: 16px;
    }

    .no-selection {
      text-align: center;
      padding: 100px;
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      color: #b0b0b0;
    }

    .invite-button, .login-button {
      display: inline-block;
      background-color: #aa00ff;
      color: white;
      padding: 14px 28px;
      border-radius: 12px;
      text-decoration: none;
      font-weight: 600;
      margin-top: 20px;
      transition: all 0.2s ease;
      border: 2px solid transparent;
    }

    .invite-button:hover, .login-button:hover {
      background-color: #8800cc;
      transform: translateY(-2px);
      box-shadow: 0 8px 16px rgba(170, 0, 255, 0.3);
    }

    .public-banner {
      margin-bottom: 20px;
      padding: 16px;
      background: linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%);
      border: 1px solid #aa00ff;
      border-radius: 12px;
      text-align: center;
    }

    .public-banner p {
      color: #b0b0b0;
      margin: 0;
    }

    .public-banner a {
      color: #aa00ff;
      text-decoration: none;
      font-weight: 600;
    }

    .public-banner a:hover {
      text-decoration: underline;
    }

    .setting-note {
      color: #666;
      font-size: 12px;
      margin-top: 8px;
    }

    .leaderboards-stack {
      display: flex;
      flex-direction: column;
      gap: 30px;
      margin-bottom: 40px;
      width: 100%;
    }

    .leaderboard-wrapper {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      overflow: visible;
      transition: all 0.2s ease;
      width: 100%;
      min-height: 300px;
    }

    .leaderboard-wrapper:hover {
      border-color: #aa00ff;
      box-shadow: 0 4px 20px rgba(170, 0, 255, 0.2);
    }

    .leaderboard-wrapper > div {
      transform: scale(0.95);
      transform-origin: top left;
      width: 105.26%;
    }

    .section-title {
      color: #ffffff;
      font-size: 28px;
      font-weight: 600;
      margin: 40px 0 24px 0;
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

    .summary-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 24px;
      margin-bottom: 40px;
    }

    .stat-card {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 28px;
      transition: all 0.2s ease;
      min-height: 150px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }

    .stat-card:hover {
      border-color: #aa00ff;
      box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2);
      transform: translateY(-2px);
    }

    .stat-card h3 {
      color: #b0b0b0;
      font-size: 16px;
      font-weight: 500;
      margin: 0 0 12px 0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .stat-value {
      color: #ffffff !important;
      font-size: 42px;
      font-weight: 700;
      margin: 0;
      background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.2;
    }

    .stat-note {
      color: #666;
      font-size: 14px;
      margin-top: 8px;
    }

    .averages-section {
      margin-bottom: 40px;
    }

    .averages-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px;
    }

    .average-card {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
      transition: all 0.2s ease;
      text-align: center;
    }

    .average-card:hover {
      border-color: #aa00ff;
      box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2);
      transform: translateY(-2px);
    }

    .average-card h3 {
      color: #b0b0b0;
      font-size: 14px;
      font-weight: 500;
      margin: 0 0 12px 0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .average-value {
      color: #ffffff !important;
      font-size: 28px;
      font-weight: 700;
      margin: 0;
      background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.2;
    }

    .average-note {
      color: #666;
      font-size: 12px;
      margin-top: 8px;
    }

    .leaderboard-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 20px;
      border-bottom: 1px solid #1a1a1a;
      flex-wrap: wrap;
      gap: 12px;
    }

    .leaderboard-header h3 {
      color: #ffffff;
      font-size: 18px;
      font-weight: 600;
      margin: 0;
    }

    .filter-badge {
      background-color: #1a1a1a;
      color: #aa00ff;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid #aa00ff;
    }

    .chart-wrapper {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
      transition: all 0.2s ease;
      min-height: 400px;
      margin-top: 40px;
      width: 100%;
      overflow: visible;
    }

    .chart-wrapper:hover {
      border-color: #aa00ff;
      box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2);
    }

    .chart-wrapper > div {
      width: 100%;
      height: 100%;
      min-height: 400px;
    }

    .no-data-message {
      text-align: center;
      padding: 60px;
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      color: #b0b0b0;
      font-size: 16px;
    }

    .no-chart-data {
      color: #b0b0b0;
      font-size: 16px;
      text-align: center;
      padding: 100px;
    }

    @media (max-width: 1024px) {
      .dashboard-main {
        margin-left: 250px;
        width: calc(100% - 250px);
      }
      
      .dashboard-content {
        padding: 16px;
      }
      
      .leaderboard-wrapper > div {
        transform: scale(0.92);
        transform-origin: top left;
        width: 108.7%;
      }
    }

    @media (max-width: 768px) {
      .dashboard-main {
        margin-left: 0;
        width: 100%;
      }
      
      .dashboard-content {
        padding: 12px;
      }
      
      .filters-section {
        flex-direction: column;
        align-items: stretch;
        padding: 16px;
      }
      
      .filter-row {
        flex-direction: column;
        align-items: flex-start;
        width: 100%;
      }
      
      .filter-row label {
        margin-bottom: 4px;
        min-width: auto;
      }
      
      .modern-select {
        width: 100%;
        min-width: auto;
      }
      
      .custom-date-range, .custom-lookback {
        flex-direction: column;
        align-items: stretch;
        width: 100%;
      }
      
      .custom-lookback input {
        width: 100%;
      }
      
      .date-input {
        flex-direction: column;
        align-items: flex-start;
        width: 100%;
      }
      
      .date-input input[type="date"] {
        width: 100%;
      }
      
      .entity-filter {
        width: 100%;
        min-width: auto;
      }
      
      .section-title {
        font-size: 24px;
      }
      
      .summary-stats {
        grid-template-columns: 1fr;
      }
      
      .averages-grid {
        grid-template-columns: 1fr 1fr;
      }
      
      .stat-value {
        font-size: 32px;
      }
      
      .average-value {
        font-size: 24px;
      }
      
      .leaderboard-header {
        flex-direction: column;
        align-items: flex-start;
      }
      
      .chart-wrapper {
        transform: none !important;
        margin: 0 !important;
        padding: 16px;
      }
      
      .chart-wrapper > div {
        width: 100% !important;
        min-height: 400px;
      }
      
      .leaderboard-wrapper {
        overflow: visible;
      }
      
      .leaderboard-wrapper > div {
        transform: scale(0.85);
        transform-origin: top left;
        width: 117.6%;
        margin-bottom: -30px;
      }
    }

    @media (max-width: 480px) {
      .dashboard-content {
        padding: 8px;
      }
      
      .averages-grid {
        grid-template-columns: 1fr;
      }
      
      .chart-wrapper {
        padding: 12px;
      }
      
      .chart-wrapper > div {
        min-height: 350px;
      }
      
      .leaderboard-wrapper > div {
        transform: scale(0.78);
        width: 128.2%;
        margin-bottom: -50px;
      }
      
      .section-title {
        font-size: 20px;
      }
    }

    .stat-value, 
    .average-value,
    .stat-number,
    .entity-name,
    .entity-option,
    .modern-select,
    .modern-entity-search,
    .modern-date-input,
    .custom-lookback input {
      color: #ffffff !important;
    }

    .entity-dropdown::-webkit-scrollbar {
      width: 8px;
    }

    .entity-dropdown::-webkit-scrollbar-track {
      background: #1a1a1a;
    }

    .entity-dropdown::-webkit-scrollbar-thumb {
      background: #2a2a2a;
      border-radius: 4px;
    }

    .entity-dropdown::-webkit-scrollbar-thumb:hover {
      background: #aa00ff;
    }
  `;

  // ============================================
  // PUBLIC MODE RENDER
  // ============================================

  if (!isAuthenticated && isPublicMode) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            topOffset={NAVBAR_HEIGHT}
            isPublicMode={true}
            publicGuildId={PUBLIC_GUILD_ID}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="public-banner">
                <p>Viewing invite statistics from the <strong>StatsHQ</strong> support server - <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server's invite stats</p>
              </div>
              
              <div className="filters-section">
                <div className="filter-row">
                  <label>Time Period:</label>
                  <select
                    value={timePeriod}
                    onChange={(e) => setTimePeriod(e.target.value)}
                    className="modern-select"
                  >
                    {timePeriodOptions.map(option => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                
                {timePeriod === 'custom-lookback' && (
                  <div className="custom-lookback">
                    <input
                      type="number"
                      placeholder="Days to look back"
                      value={customDaysBack}
                      onChange={(e) => setCustomDaysBack(e.target.value)}
                      min="1"
                    />
                  </div>
                )}
                
                {timePeriod === 'custom-range' && (
                  <div className="custom-date-range">
                    <div className="date-input">
                      <label>From:</label>
                      <input
                        type="date"
                        value={customStartDate}
                        onChange={(e) => setCustomStartDate(e.target.value)}
                        className="modern-date-input"
                      />
                    </div>
                    <div className="date-input">
                      <label>To:</label>
                      <input
                        type="date"
                        value={customEndDate}
                        onChange={(e) => setCustomEndDate(e.target.value)}
                        className="modern-date-input"
                      />
                    </div>
                  </div>
                )}
                
                <div className="filter-row">
                  <label>Type:</label>
                  <select
                    value={selectedFilterType}
                    onChange={(e) => setSelectedFilterType(e.target.value)}
                    className="modern-select"
                  >
                    {filterTypeOptions.map(option => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                
                <div className="filter-row entity-filter">
                  <label>Role Filter:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search role to filter inviters..."
                      value={tempRoleSearch}
                      onChange={(e) => setTempRoleSearch(e.target.value)}
                      onFocus={() => setShowRoleDropdown(true)}
                      onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
                      className="modern-entity-search"
                    />
                    {showRoleDropdown && filteredRoles.length > 0 && (
                      <div className="entity-dropdown">
                        <div
                          className="entity-option"
                          onMouseDown={() => {
                            clearRoleFilter();
                            setShowRoleDropdown(false);
                          }}
                        >
                          <div className="entity-info">
                            <span className="entity-name">Clear Role Filter</span>
                          </div>
                          <span className="entity-id">✕</span>
                        </div>
                        {filteredRoles.slice(0, 20).map(role => (
                          <div
                            key={role.id}
                            className={`entity-option ${tempRoleId === role.id ? 'selected' : ''}`}
                            onMouseDown={() => handleTempRoleSelect(role)}
                          >
                            <div className="entity-info">
                              <span 
                                className="entity-color-dot" 
                                style={{ backgroundColor: role.color || '#99aab5' }}
                              ></span>
                              <span className="entity-name">{role.name}</span>
                            </div>
                            <span className="entity-id">ID: {role.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    
                    {showApplyButton && (
                      <div className="apply-button-container">
                        <button 
                          className="apply-button"
                          onClick={applyRoleFilter}
                        >
                          Apply Role Filter
                        </button>
                        <button 
                          className="clear-button"
                          onClick={clearRoleFilter}
                        >
                          Clear
                        </button>
                      </div>
                    )}
                    
                    {selectedRoleId && !showApplyButton && (
                      <div className="active-role-filter">
                        <span>Active filter: {getRoleName(selectedRoleId)}</span>
                        <button onClick={clearRoleFilter}>✕</button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              
              {loadingServers ? (
                <div className="loading">Loading servers...</div>
              ) : apiError ? (
                <div className="error-message">
                  <h2>Error Loading Data</h2>
                  <p>{apiError}</p>
                  <button onClick={() => { serverDataCache.clear(); fetchData(); }} className="retry-button">
                    Clear Cache & Retry
                  </button>
                </div>
              ) : (
                <>
                  <div className="summary-stats">
                    {loadingSummaryStats ? (
                      <>
                        <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                      </>
                    ) : (
                      <>
                        <div className="stat-card">
                          <h3>Total Invites</h3>
                          <p className="stat-value">{formatNumber(inviteStats.total_invites)}</p>
                          <div className="stat-note">
                            {inviteStats.valid_invites} valid, {inviteStats.suspicious_invites} suspicious, {inviteStats.left_invites} left
                          </div>
                        </div>
                        <div className="stat-card">
                          <h3>Unique Inviters</h3>
                          <p className="stat-value">{formatNumber(inviteStats.unique_inviters)}</p>
                        </div>
                        <div className="stat-card">
                          <h3>Unique Invitees</h3>
                          <p className="stat-value">{formatNumber(inviteStats.unique_invitees)}</p>
                        </div>
                      </>
                    )}
                  </div>
                  
                  <div className="averages-section">
                    <h2 className="section-title">Averages</h2>
                    <div className="averages-grid">
                      <div className="average-card">
                        <h3>Per Inviter</h3>
                        <p className="average-value">{formatAverage(averagesData.avgPerInviter)}</p>
                      </div>
                      <div className="average-card">
                        <h3>Per Day</h3>
                        <p className="average-value">{formatAverage(averagesData.avgPerDay)}</p>
                      </div>
                      <div className="average-card">
                        <h3>Per Month</h3>
                        <p className="average-value">{formatAverage(averagesData.avgPerMonth)}</p>
                      </div>
                      <div className="average-card">
                        <h3>Per Year</h3>
                        <p className="average-value">{formatAverage(averagesData.avgPerYear)}</p>
                      </div>
                    </div>
                  </div>
                  
                  <div className="leaderboards-section">
                    <h2 className="section-title">Leaderboards</h2>
                    <div className="leaderboards-stack">
                      {loadingUserLeaderboard ? (
                        <LoadingCard />
                      ) : topUsers.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>Top Inviters</h3>
                            <span className="filter-badge">
                              {filterTypeOptions.find(f => f.value === selectedFilterType)?.label}
                            </span>
                          </div>
                          <Leaderboard
                            data={topUsers}
                            title=""
                            valueLabel="Invites"
                            valueFormatter={formatInviteValue}
                            showProfilePictures={true}
                            itemType="user"
                            nameKey="name"
                            valueKey="value"
                            idKey="userId"
                            backgroundColor="transparent"
                            cardBackground="#1a1a1a"
                            accentColor="#aa00ff"
                            getProfilePicture={async (userId) => {
                              const user = topUsers.find(u => u.userId === userId);
                              return user?.avatar || null;
                            }}
                            additionalInfo={(item) => {
                              const info = [];
                              if (selectedFilterType === 'all') {
                                info.push(`${item.validInvites} valid, ${item.suspiciousInvites} suspicious, ${item.leftInvites} left`);
                              } else if (selectedFilterType === 'valid') {
                                info.push(`Valid: ${item.validInvites}`);
                              } else if (selectedFilterType === 'suspicious') {
                                info.push(`Suspicious: ${item.suspiciousInvites}`);
                              } else if (selectedFilterType === 'left') {
                                info.push(`Left: ${item.leftInvites}`);
                              }
                              info.push(`${item.percentageValid}% valid rate`);
                              return info;
                            }}
                          />
                        </div>
                      ) : (
                        <div className="no-data-message">No user data available</div>
                      )}
                      
                      {loadingCodeLeaderboard ? (
                        <LoadingCard />
                      ) : topInviteCodes.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>Top Invite Codes</h3>
                            <span className="filter-badge">
                              {filterTypeOptions.find(f => f.value === selectedFilterType)?.label}
                            </span>
                          </div>
                          <Leaderboard
                            data={topInviteCodes}
                            title=""
                            valueLabel="Uses"
                            valueFormatter={formatInviteValue}
                            showProfilePictures={false}
                            itemType="invite"
                            nameKey="name"
                            valueKey="value"
                            idKey="id"
                            backgroundColor="transparent"
                            cardBackground="#1a1a1a"
                            accentColor="#aa00ff"
                            additionalInfo={(item) => {
                              const info = [];
                              if (selectedFilterType === 'all') {
                                info.push(`${item.validUses} valid, ${item.suspiciousUses} suspicious, ${item.leftUses} left`);
                              } else if (selectedFilterType === 'valid') {
                                info.push(`Valid: ${item.validUses}`);
                              } else if (selectedFilterType === 'suspicious') {
                                info.push(`Suspicious: ${item.suspiciousUses}`);
                              } else if (selectedFilterType === 'left') {
                                info.push(`Left: ${item.leftUses}`);
                              }
                              info.push(`Created by: ${item.inviterName}`);
                              info.push(`${item.percentageValid}% valid rate`);
                              return info;
                            }}
                          />
                        </div>
                      ) : (
                        <div className="no-data-message">No invite code data available</div>
                      )}
                    </div>
                  </div>
                  
                  <div className="charts-section">
                    <h2 className="section-title">Invites Over Time</h2>
                    <div className="chart-wrapper">
                      {loadingChart ? (
                        <LoadingChart />
                      ) : timeseriesData.length > 0 ? (
                        <InteractiveLineChart
                          data={timeseriesData}
                          lines={[
                            { name: 'Total Invites', dataKey: 'value', color: '#aa00ff' },
                            ...(selectedFilterType === 'all' ? [
                              { name: 'Valid', dataKey: 'valid', color: '#00ff88' },
                              { name: 'Suspicious', dataKey: 'suspicious', color: '#ffaa00' },
                              { name: 'Left', dataKey: 'left', color: '#ff4444' }
                            ] : [])
                          ]}
                          title=""
                          valueFormatter={formatInviteValue}
                        />
                      ) : (
                        <div className="no-chart-data">No chart data available</div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // ============================================
  // AUTHENTICATED BUT NO ACCESS RENDER
  // ============================================

  if (isAuthenticated && currentServer && !hasAccess) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            currentServerId={currentServer?.id} 
            topOffset={NAVBAR_HEIGHT}
            isPublicMode={false}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <AccessDenied accessLevel={dashboardAccessLevel} />
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // ============================================
  // LOADING SERVERS RENDER
  // ============================================

  if (loadingServers && !currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            topOffset={NAVBAR_HEIGHT}
            isPublicMode={isPublicMode}
            publicGuildId={PUBLIC_GUILD_ID}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading">
                <LoadingSpinner size="large" text="Loading dashboard..." />
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // ============================================
  // PERMISSION CHECKING IN PROGRESS RENDER
  // ============================================

  if (hasAccess === null && isAuthenticated && currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            currentServerId={currentServer?.id}
            topOffset={NAVBAR_HEIGHT}
            isPublicMode={false}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading">
                <LoadingSpinner size="large" text="Checking permissions..." />
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // ============================================
  // NO SERVER AVAILABLE RENDER
  // ============================================

  if (!loadingServers && !currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>No Server Available</h2>
                <p>Add the bot to a Discord server to get started.</p>
                <a href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands" 
                   className="invite-button" 
                   target="_blank" 
                   rel="noopener noreferrer">
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

  // ============================================
  // ERROR STATE RENDER
  // ============================================

  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            currentServerId={currentServer?.id} 
            topOffset={NAVBAR_HEIGHT}
            isPublicMode={isPublicMode}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => { serverDataCache.clear(); fetchData(); }} className="retry-button">
                  Clear Cache & Retry
                </button>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // ============================================
  // AUTHENTICATED USER WITH ACCESS - FULL DASHBOARD
  // ============================================

  return (
    <>
      <NavBar />
      {retentionAlert && !retentionDismissed && (
        <div className="retention-banner">
          <span className="retention-banner-text">⚠️ {retentionAlert.message}</span>
          <button
            className="retention-banner-close"
            onClick={() => setRetentionDismissed(true)}
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
      <div className="dashboard-page">
        <DashboardSidebar 
          currentServerId={currentServer?.id} 
          topOffset={NAVBAR_HEIGHT}
          isPublicMode={false}
        />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            
            <div className="filters-section">
              <div className="filter-row">
                <label>Time Period:</label>
                <select
                  value={timePeriod}
                  onChange={(e) => setTimePeriod(e.target.value)}
                  className="modern-select"
                >
                  {timePeriodOptions.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              
              {timePeriod === 'custom-lookback' && (
                <div className="custom-lookback">
                  <input
                    type="number"
                    placeholder="Days to look back"
                    value={customDaysBack}
                    onChange={(e) => setCustomDaysBack(e.target.value)}
                    min="1"
                  />
                </div>
              )}
              
              {timePeriod === 'custom-range' && (
                <div className="custom-date-range">
                  <div className="date-input">
                    <label>From:</label>
                    <input
                      type="date"
                      value={customStartDate}
                      onChange={(e) => setCustomStartDate(e.target.value)}
                      className="modern-date-input"
                    />
                  </div>
                  <div className="date-input">
                    <label>To:</label>
                    <input
                      type="date"
                      value={customEndDate}
                      onChange={(e) => setCustomEndDate(e.target.value)}
                      className="modern-date-input"
                    />
                  </div>
                </div>
              )}
              
              <div className="filter-row">
                <label>Type:</label>
                <select
                  value={selectedFilterType}
                  onChange={(e) => setSelectedFilterType(e.target.value)}
                  className="modern-select"
                >
                  {filterTypeOptions.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              
              <div className="filter-row entity-filter">
                <label>Role Filter:</label>
                <div className="entity-selector">
                  <input
                    type="text"
                    placeholder="Search role to filter inviters..."
                    value={tempRoleSearch}
                    onChange={(e) => setTempRoleSearch(e.target.value)}
                    onFocus={() => setShowRoleDropdown(true)}
                    onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
                    className="modern-entity-search"
                  />
                  {showRoleDropdown && filteredRoles.length > 0 && (
                    <div className="entity-dropdown">
                      <div
                        className="entity-option"
                        onMouseDown={() => {
                          clearRoleFilter();
                          setShowRoleDropdown(false);
                        }}
                      >
                        <div className="entity-info">
                          <span className="entity-name">Clear Role Filter</span>
                        </div>
                        <span className="entity-id">✕</span>
                      </div>
                      {filteredRoles.slice(0, 20).map(role => (
                        <div
                          key={role.id}
                          className={`entity-option ${tempRoleId === role.id ? 'selected' : ''}`}
                          onMouseDown={() => handleTempRoleSelect(role)}
                        >
                          <div className="entity-info">
                            <span 
                              className="entity-color-dot" 
                              style={{ backgroundColor: role.color || '#99aab5' }}
                            ></span>
                            <span className="entity-name">{role.name}</span>
                          </div>
                          <span className="entity-id">ID: {role.id}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {showApplyButton && (
                    <div className="apply-button-container">
                      <button 
                        className="apply-button"
                        onClick={applyRoleFilter}
                      >
                        Apply Role Filter
                      </button>
                      <button 
                        className="clear-button"
                        onClick={clearRoleFilter}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                  
                  {selectedRoleId && !showApplyButton && (
                    <div className="active-role-filter">
                      <span>Active filter: {getRoleName(selectedRoleId)}</span>
                      <button onClick={clearRoleFilter}>✕</button>
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {loadingServers ? (
              <div className="loading">Loading servers...</div>
            ) : !currentServer ? (
              <div className="no-server">
                <h2>No Server Available</h2>
                <p>Add the bot to a Discord server to get started.</p>
                <a href="https://discord.com/oauth2/authorize?client_id=1424327933417492480&permissions=352807976696992&integration_type=0&scope=bot+applications.commands" 
                   className="invite-button" 
                   target="_blank" 
                   rel="noopener noreferrer">
                  Invite Bot to Server
                </a>
              </div>
            ) : apiError ? (
              <div className="error-message">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => fetchData()} className="retry-button">
                  Retry
                </button>
              </div>
            ) : (
              <>
                <div className="summary-stats">
                  {loadingSummaryStats ? (
                    <>
                      <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                      <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                      <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                    </>
                  ) : (
                    <>
                      <div className="stat-card">
                        <h3>Total Invites</h3>
                        <p className="stat-value">{formatNumber(inviteStats.total_invites)}</p>
                        <div className="stat-note">
                          {inviteStats.valid_invites} valid, {inviteStats.suspicious_invites} suspicious, {inviteStats.left_invites} left
                        </div>
                      </div>
                      <div className="stat-card">
                        <h3>Unique Inviters</h3>
                        <p className="stat-value">{formatNumber(inviteStats.unique_inviters)}</p>
                      </div>
                      <div className="stat-card">
                        <h3>Unique Invitees</h3>
                        <p className="stat-value">{formatNumber(inviteStats.unique_invitees)}</p>
                      </div>
                    </>
                  )}
                </div>
                
                <div className="averages-section">
                  <h2 className="section-title">Averages</h2>
                  <div className="averages-grid">
                    <div className="average-card">
                      <h3>Per Inviter</h3>
                      <p className="average-value">{formatAverage(averagesData.avgPerInviter)}</p>
                    </div>
                    <div className="average-card">
                      <h3>Per Day</h3>
                      <p className="average-value">{formatAverage(averagesData.avgPerDay)}</p>
                    </div>
                    <div className="average-card">
                      <h3>Per Month</h3>
                      <p className="average-value">{formatAverage(averagesData.avgPerMonth)}</p>
                    </div>
                    <div className="average-card">
                      <h3>Per Year</h3>
                      <p className="average-value">{formatAverage(averagesData.avgPerYear)}</p>
                    </div>
                  </div>
                </div>
                
                <div className="leaderboards-section">
                  <h2 className="section-title">Leaderboards</h2>
                  <div className="leaderboards-stack">
                    {loadingUserLeaderboard ? (
                      <LoadingCard />
                    ) : topUsers.length > 0 ? (
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>Top Inviters</h3>
                          <span className="filter-badge">
                            {filterTypeOptions.find(f => f.value === selectedFilterType)?.label}
                          </span>
                        </div>
                        <Leaderboard
                          data={topUsers}
                          title=""
                          valueLabel="Invites"
                          valueFormatter={formatInviteValue}
                          showProfilePictures={true}
                          itemType="user"
                          nameKey="name"
                          valueKey="value"
                          idKey="userId"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#aa00ff"
                          getProfilePicture={async (userId) => {
                            const user = topUsers.find(u => u.userId === userId);
                            return user?.avatar || null;
                          }}
                          additionalInfo={(item) => {
                            const info = [];
                            if (selectedFilterType === 'all') {
                              info.push(`${item.validInvites} valid, ${item.suspiciousInvites} suspicious, ${item.leftInvites} left`);
                            } else if (selectedFilterType === 'valid') {
                              info.push(`Valid: ${item.validInvites}`);
                            } else if (selectedFilterType === 'suspicious') {
                              info.push(`Suspicious: ${item.suspiciousInvites}`);
                            } else if (selectedFilterType === 'left') {
                              info.push(`Left: ${item.leftInvites}`);
                            }
                            info.push(`${item.percentageValid}% valid rate`);
                            return info;
                          }}
                        />
                      </div>
                    ) : (
                      <div className="no-data-message">No user data available {selectedRoleId ? 'with this role filter' : ''}</div>
                    )}
                    
                    {loadingCodeLeaderboard ? (
                      <LoadingCard />
                    ) : topInviteCodes.length > 0 ? (
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>Top Invite Codes</h3>
                          <span className="filter-badge">
                            {filterTypeOptions.find(f => f.value === selectedFilterType)?.label}
                          </span>
                        </div>
                        <Leaderboard
                          data={topInviteCodes}
                          title=""
                          valueLabel="Uses"
                          valueFormatter={formatInviteValue}
                          showProfilePictures={false}
                          itemType="invite"
                          nameKey="name"
                          valueKey="value"
                          idKey="id"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#aa00ff"
                          additionalInfo={(item) => {
                            const info = [];
                            if (selectedFilterType === 'all') {
                              info.push(`${item.validUses} valid, ${item.suspiciousUses} suspicious, ${item.leftUses} left`);
                            } else if (selectedFilterType === 'valid') {
                              info.push(`Valid: ${item.validUses}`);
                            } else if (selectedFilterType === 'suspicious') {
                              info.push(`Suspicious: ${item.suspiciousUses}`);
                            } else if (selectedFilterType === 'left') {
                              info.push(`Left: ${item.leftUses}`);
                            }
                            info.push(`Created by: ${item.inviterName}`);
                            info.push(`${item.percentageValid}% valid rate`);
                            return info;
                          }}
                        />
                      </div>
                    ) : (
                      <div className="no-data-message">No invite code data available {selectedRoleId ? 'with this role filter' : ''}</div>
                    )}
                  </div>
                </div>
                
                <div className="charts-section">
                  <h2 className="section-title">Invites Over Time</h2>
                  <div className="chart-wrapper">
                    {loadingChart ? (
                      <LoadingChart />
                    ) : timeseriesData.length > 0 ? (
                      <InteractiveLineChart
                        data={timeseriesData}
                        lines={[
                          { name: 'Total Invites', dataKey: 'value', color: '#aa00ff' },
                          ...(selectedFilterType === 'all' ? [
                            { name: 'Valid', dataKey: 'valid', color: '#00ff88' },
                            { name: 'Suspicious', dataKey: 'suspicious', color: '#ffaa00' },
                            { name: 'Left', dataKey: 'left', color: '#ff4444' }
                          ] : [])
                        ]}
                        title=""
                        valueFormatter={formatInviteValue}
                      />
                    ) : (
                      <div className="no-chart-data">No chart data available</div>
                    )}
                  </div>
                </div>
              </>
            )}
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
  <InviteDashboard />
);

export default InviteDashboard;