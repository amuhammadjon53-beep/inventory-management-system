import React, { useState, useEffect, useRef, useMemo } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import MultiLineChart from "../../../Components/MultiLineChart.jsx";

// API base URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

// PUBLIC GUILD ID for unauthenticated users
const PUBLIC_GUILD_ID = '1424021358680998022';

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// Maximum forecast horizon, in days. The projected-growth charts previously
// used the *lookback* window (up to 2000/1825 days for "All Time" / custom
// ranges) as the forecast horizon too, which made the backend compute a
// multi-year projection on every load and made the page extremely slow.
// The forecast horizon now scales with the lookback but is capped here.
const PROJECTION_CAP_DAYS = 90;

// Scales the forecast horizon with the lookback, but never exceeds the cap.
// "all" and custom-range (where days is null) fall back to the full cap.
const getProjectionDays = (days) => {
  if (days !== null && days !== undefined && !isNaN(days)) {
    return Math.min(days, PROJECTION_CAP_DAYS);
  }
  return PROJECTION_CAP_DAYS;
};

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
const roleCache = new ServerDataCache(20, 10 * 60 * 1000);

// Helper to get the correct API endpoint based on mode
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

// Format number with K/M suffix
const formatNumber = (num) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

// Format percentage with +/-
const formatPercentage = (percent) => {
  if (percent > 0) return `+${percent.toFixed(1)}%`;
  if (percent < 0) return `${percent.toFixed(1)}%`;
  return '0%';
};

// Loading Spinner Component
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

// Loading Chart Component
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
      <p>You don't have permission to view this server's growth statistics.</p>
      <p>This server requires <strong>{requiredPermission}</strong> permissions.</p>
      <p className="setting-note" style={{ marginTop: '12px', fontSize: '12px', color: '#666' }}>
        Note: Server owners automatically have Administrator permission.
      </p>
    </div>
  );
};

const GrowthDashboard = () => {
  // State
  const [selectedView, setSelectedView] = useState("server");
  const [timePeriod, setTimePeriod] = useState("30");
  const [customDaysBack, setCustomDaysBack] = useState("");
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [selectedRoleName, setSelectedRoleName] = useState("");
  const [roleSearch, setRoleSearch] = useState("");
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  
  const [roles, setRoles] = useState([]);
  const [filteredRoles, setFilteredRoles] = useState([]);
  
  const [loading, setLoading] = useState(true);
  const [currentServer, setCurrentServer] = useState(null);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isPublicMode, setIsPublicMode] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [apiError, setApiError] = useState(null);
  const [serverTimezone, setServerTimezone] = useState('UTC');
  const [retentionAlert, setRetentionAlert] = useState(null);
  const [retentionDismissed, setRetentionDismissed] = useState(false);
  
  // Loading states
  const [loadingServerStats, setLoadingServerStats] = useState(true);
  const [loadingRoleStats, setLoadingRoleStats] = useState(true);
  const [loadingMemberChart, setLoadingMemberChart] = useState(true);
  const [loadingJoinsLeavesChart, setLoadingJoinsLeavesChart] = useState(true);
  const [loadingProjectedChart, setLoadingProjectedChart] = useState(true);
  const [loadingRoleChart, setLoadingRoleChart] = useState(true);
  const [loadingRoleProjectedChart, setLoadingRoleProjectedChart] = useState(true);
  
  // Chart data
  const [memberTimeseries, setMemberTimeseries] = useState([]);
  const [joinsLeavesTimeseries, setJoinsLeavesTimeseries] = useState({ joins: [], leaves: [] });
  const [projectedTimeseries, setProjectedTimeseries] = useState({ data: [], joins: [], leaves: [] });
  const [roleTimeseries, setRoleTimeseries] = useState({ added: [], removed: [] });
  const [roleProjectedTimeseries, setRoleProjectedTimeseries] = useState({ data: [], added: [], removed: [] });
  
  // Stats
  const [serverStats, setServerStats] = useState({
    currentMembers: 0,
    totalJoins: 0,
    totalLeaves: 0,
    netGrowth: 0,
    growthPercentage: 0
  });
  
  const [roleStats, setRoleStats] = useState({
    totalAdded: 0,
    totalRemoved: 0,
    netGrowth: 0,
    growthPercentage: 0,
    roleName: "",
    roleColor: "#99aab5"
  });
  
  const [roleColors, setRoleColors] = useState({});

  const rolesRef = useRef([]);
  const fetchedRef = useRef(false);
  const initialDataLoadedRef = useRef(false);
  const didInitRef = useRef(false);
  const inFlightRequestsRef = useRef({});
  const prevFiltersRef = useRef(JSON.stringify({
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedRoleId
  }));

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

  // Load everything on mount
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

  // FIXED: applyServerTimePeriod now returns computed values
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
          setIsPublicMode(false);
          
          // Check if user is privileged
          if (isPrivilegedUser(authData.user.id)) {
            setHasAccess(true);
            setDashboardAccessLevel('Admin');
            window.accessLevel = 'Admin';
            
            // Load servers for privileged user
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
                  // Fallback to public stats if no server found
                  setIsPublicMode(true);
                  setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
                }
              } else {
                // No servers - show public stats
                setIsPublicMode(true);
                setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
              }
            } else {
              // Failed to fetch servers - show public stats
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
        // NOTE: time-period application and the data fetch now happen exactly
        // once, in the unified [currentServer, hasAccess] effect below —
        // this function's only job is to resolve access.
        
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

  // NEW: fetchDataWithParams - uses overrides instead of state, with in-flight dedup
  const fetchDataWithParams = async (overrides = {}) => {
    if (!currentServer || !hasAccess) return;
    
    const requestKey = `${currentServer.id}:${selectedView}:${JSON.stringify(overrides)}`;
    if (inFlightRequestsRef.current[requestKey]) {
      // An identical request is already in flight — reuse it instead of firing another
      return inFlightRequestsRef.current[requestKey];
    }
    
    const promise = (async () => {
      setLoading(true);
      setApiError(null);
      
      const effectiveTimePeriod = overrides.timePeriod ?? timePeriod;
      const effectiveCustomDaysBack = overrides.customDaysBack ?? customDaysBack;
      const effectiveCustomStartDate = overrides.customStartDate ?? customStartDate;
      const effectiveCustomEndDate = overrides.customEndDate ?? customEndDate;
      
      let startDate = null;
      let endDate = null;
      let days = null;
      
      if (effectiveTimePeriod === "all") {
        days = 2000;
      } else if (effectiveTimePeriod === "custom-lookback") {
        if (effectiveCustomDaysBack && parseInt(effectiveCustomDaysBack) > 0) {
          days = parseInt(effectiveCustomDaysBack);
          endDate = new Date();
          startDate = new Date();
          startDate.setDate(startDate.getDate() - days);
        }
      } else if (effectiveTimePeriod === "custom-range") {
        if (effectiveCustomStartDate && effectiveCustomEndDate) {
          startDate = new Date(effectiveCustomStartDate);
          endDate = new Date(effectiveCustomEndDate);
          days = null;
        }
      } else {
        days = parseInt(effectiveTimePeriod);
        endDate = new Date();
        startDate = new Date();
        startDate.setDate(startDate.getDate() - days);
      }
      
      try {
        if (selectedView === 'server') {
          await fetchServerDataWithDates(startDate, endDate, days);
        } else if (selectedView === 'role' && selectedRoleId) {
          await fetchRoleDataWithDates(startDate, endDate, days);
        }
      } catch (error) {
        console.error('Error fetching data:', error);
        setApiError(error.message);
      } finally {
        setLoading(false);
        fetchedRef.current = true;
        delete inFlightRequestsRef.current[requestKey];
      }
    })();
    
    inFlightRequestsRef.current[requestKey] = promise;
    return promise;
  };

  // Helper functions for fetchDataWithParams
  const fetchServerDataWithDates = async (startDate, endDate, days) => {
    setLoadingServerStats(true);
    setLoadingMemberChart(true);
    setLoadingJoinsLeavesChart(true);
    setLoadingProjectedChart(true);
    
    const isPublic = isPublicMode;
    
    try {
      // 1. Fetch member timeseries
      const memberRequestBody = { guild_id: currentServer.id };
      if (days !== null && days !== undefined && !isNaN(days)) {
        memberRequestBody.days = days;
      }
      if (startDate) memberRequestBody.start_time = startDate.toISOString();
      if (endDate) memberRequestBody.end_time = endDate.toISOString();
      
      const memberEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/server/members/timeseries`, isPublic);
      
      const memberResponse = await fetch(memberEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(memberRequestBody)
      });
      
      let memberData = [];
      let currentMembers = 0;
      
      if (memberResponse.ok) {
        const data = await memberResponse.json();
        memberData = data.timeseries || [];
        currentMembers = data.current_members || 0;
        setMemberTimeseries(memberData);
      }
      
      // 2. Fetch joins and leaves
      const joinsLeavesRequestBody = { guild_id: currentServer.id };
      if (days !== null && days !== undefined && !isNaN(days)) {
        joinsLeavesRequestBody.days = days;
      }
      if (startDate) joinsLeavesRequestBody.start_time = startDate.toISOString();
      if (endDate) joinsLeavesRequestBody.end_time = endDate.toISOString();
      
      const joinsLeavesEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/server/joins-leaves`, isPublic);
      
      const joinsLeavesResponse = await fetch(joinsLeavesEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(joinsLeavesRequestBody)
      });
      
      let totalJoins = 0;
      let totalLeaves = 0;
      let joinsSeries = [];
      let leavesSeries = [];
      
      if (joinsLeavesResponse.ok) {
        const data = await joinsLeavesResponse.json();
        totalJoins = data.total_joins || 0;
        totalLeaves = data.total_leaves || 0;
        joinsSeries = data.joins_timeseries || [];
        leavesSeries = data.leaves_timeseries || [];
        setJoinsLeavesTimeseries({ joins: joinsSeries, leaves: leavesSeries });
      }
      
      const growthPercent = calculateGrowthPercentage(memberData);
      
      const newServerStats = {
        currentMembers,
        totalJoins,
        totalLeaves,
        netGrowth: totalJoins - totalLeaves,
        growthPercentage: growthPercent
      };
      
      setServerStats(newServerStats);
      
      // 3. Fetch projected growth
      // Forecast horizon scales with the lookback but is capped at
      // PROJECTION_CAP_DAYS so "All Time" / large custom ranges don't
      // trigger a multi-year projection on every load.
      const projectedDays = getProjectionDays(days);
      const projectedRequestBody = {
        guild_id: currentServer.id,
        days: projectedDays
      };
      
      const projectedEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/server/projected`, isPublic);
      
      const projectedResponse = await fetch(projectedEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(projectedRequestBody)
      });
      
      let projectedData = { data: [], joins: [], leaves: [] };
      
      if (projectedResponse.ok) {
        const data = await projectedResponse.json();
        projectedData = {
          data: data.projected_data || [],
          joins: data.joins_forecast || [],
          leaves: data.leaves_forecast || []
        };
        setProjectedTimeseries(projectedData);
      }
      
    } catch (error) {
      console.error('Error fetching server data:', error);
      setApiError(error.message);
    } finally {
      setLoadingServerStats(false);
      setLoadingMemberChart(false);
      setLoadingJoinsLeavesChart(false);
      setLoadingProjectedChart(false);
    }
  };

  const fetchRoleDataWithDates = async (startDate, endDate, days) => {
    if (!selectedRoleId) return;
    
    setLoadingRoleStats(true);
    setLoadingRoleChart(true);
    setLoadingRoleProjectedChart(true);
    
    const isPublic = isPublicMode;
    
    try {
      const roleRequestBody = {
        guild_id: currentServer.id,
        role_id: selectedRoleId
      };
      
      if (days !== null && days !== undefined && !isNaN(days)) {
        roleRequestBody.days = days;
      }
      if (startDate) roleRequestBody.start_time = startDate.toISOString();
      if (endDate) roleRequestBody.end_time = endDate.toISOString();
      
      const roleEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/role/additions-removals`, isPublic);
      
      const roleResponse = await fetch(roleEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(roleRequestBody)
      });
      
      let addedSeries = [];
      let removedSeries = [];
      let totalAdded = 0;
      let totalRemoved = 0;
      
      if (roleResponse.ok) {
        const data = await roleResponse.json();
        totalAdded = data.total_added || 0;
        totalRemoved = data.total_removed || 0;
        addedSeries = data.added_timeseries || [];
        removedSeries = data.removed_timeseries || [];
        setRoleTimeseries({ added: addedSeries, removed: removedSeries });
      }
      
      const netGrowthArray = addedSeries.map((item, index) => ({
        count: (addedSeries[index]?.count || 0) - (removedSeries[index]?.count || 0)
      }));
      const growthPercent = calculateGrowthPercentage(netGrowthArray);
      
      const roleName = roles.find(r => r.id === selectedRoleId)?.name || `Role ${selectedRoleId}`;
      const roleColor = roleColors[selectedRoleId] || '#99aab5';
      
      const newRoleStats = {
        totalAdded,
        totalRemoved,
        netGrowth: totalAdded - totalRemoved,
        growthPercentage: growthPercent,
        roleName,
        roleColor
      };
      
      setRoleStats(newRoleStats);
      
      // Forecast horizon scales with the lookback but is capped at
      // PROJECTION_CAP_DAYS so "All Time" / large custom ranges don't
      // trigger a multi-year projection on every load.
      const projectedDays = getProjectionDays(days);
      const projectedRequestBody = {
        guild_id: currentServer.id,
        role_id: selectedRoleId,
        days: projectedDays
      };
      
      const projectedEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/role/projected`, isPublic);
      
      const projectedResponse = await fetch(projectedEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(projectedRequestBody)
      });
      
      let projectedData = { data: [], added: [], removed: [] };
      
      if (projectedResponse.ok) {
        const data = await projectedResponse.json();
        projectedData = {
          data: data.projected_data || [],
          added: data.added_forecast || [],
          removed: data.removed_forecast || []
        };
        setRoleProjectedTimeseries(projectedData);
      }
      
    } catch (error) {
      console.error('Error fetching role data:', error);
      setApiError(error.message);
    } finally {
      setLoadingRoleStats(false);
      setLoadingRoleChart(false);
      setLoadingRoleProjectedChart(false);
    }
  };

  // Fetch roles from growth table
  const fetchRoles = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('growth-roles', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    
    if (cached) {
      setRoles(cached.roleList);
      setFilteredRoles(cached.roleList);
      setRoleColors(cached.colorMap);
      return;
    }
    
    try {
      const endpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/roles`, isPublic);
      const url = new URL(endpoint);
      url.searchParams.append('guild_id', currentServer.id);
      
      const response = await fetch(url.toString(), {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        
        if (data.success && data.roles) {
          const roleList = [];
          const colorMap = {};
          
          data.roles.forEach(role => {
            const roleId = String(role.role_id);
            roleList.push({
              id: roleId,
              name: role.name,
              color: role.color,
              searchString: `${role.name} ${roleId}`.toLowerCase()
            });
            colorMap[roleId] = role.color;
          });
          
          serverDataCache.set(cacheKey, { roleList, colorMap });
          
          setRoles(roleList);
          setFilteredRoles(roleList);
          setRoleColors(colorMap);
        }
      }
    } catch (error) {
      console.error('Error fetching roles:', error);
    }
  };

  // Load data when server changes — single unified effect owns the whole
  // "server changed" lifecycle: reset -> fetch roles -> fetch settings ->
  // apply time period -> fetch data with the resolved params -> sync the
  // filter-watcher's ref so it doesn't fire a redundant extra fetch.
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    // Prevent re-running if already loaded for this server
    if (initialDataLoadedRef.current === currentServer.id) return;
    initialDataLoadedRef.current = currentServer.id;
    
    fetchedRef.current = false;
    
    setLoadingServerStats(true);
    setLoadingMemberChart(true);
    setLoadingJoinsLeavesChart(true);
    setLoadingProjectedChart(true);
    setLoading(true);
    
    setMemberTimeseries([]);
    setJoinsLeavesTimeseries({ joins: [], leaves: [] });
    setProjectedTimeseries({ data: [], joins: [], leaves: [] });
    setSelectedRoleId("");
    setSelectedRoleName("");
    setRoleSearch("");
    
    const initializeServer = async () => {
      // 1. roles can load in parallel, they don't gate the stats fetch
      fetchRoles();
      
      // 2. get the server's configured default time period BEFORE any data fetch
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
          timeParams = applyServerTimePeriod(data); // sets state AND returns the values synchronously
        }
      } catch (e) {
        console.error('Error fetching time period settings:', e);
      }
      
      // 3. sync prevFiltersRef to the resolved values BEFORE fetching, so the
      //    filter-watcher effect sees no diff once fetchedRef flips true and
      //    doesn't sneak in a redundant extra fetch right after init
      const resolvedFilters = {
        selectedView,
        timePeriod: timeParams.timePeriod ?? timePeriod,
        customDaysBack: timeParams.customDaysBack ?? customDaysBack,
        customStartDate: timeParams.customStartDate ?? customStartDate,
        customEndDate: timeParams.customEndDate ?? customEndDate,
        selectedRoleId: ""
      };
      prevFiltersRef.current = JSON.stringify(resolvedFilters);
      
      // 4. fetch data ONCE, using the resolved params directly (not stale state)
      await fetchDataWithParams(timeParams);
    };
    
    initializeServer();
  }, [currentServer, hasAccess]);

  // Fetch stats when filters change
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    const currentFilters = JSON.stringify({
      selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedRoleId
    });
    
    if (fetchedRef.current && prevFiltersRef.current !== currentFilters) {
      prevFiltersRef.current = currentFilters;
      if (selectedView === 'server') {
        fetchServerData();
      } else if (selectedView === 'role' && selectedRoleId) {
        fetchRoleData();
      }
    }
  }, [
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedRoleId, hasAccess
  ]);

  // Filter roles when search changes
  useEffect(() => {
    if (roleSearch.trim() === "") {
      setFilteredRoles(roles);
    } else {
      const searchLower = roleSearch.toLowerCase();
      const filtered = roles.filter(role => 
        role.searchString?.includes(searchLower) ||
        role.id?.includes(searchLower)
      );
      setFilteredRoles(filtered);
    }
  }, [roleSearch, roles]);

  const getDateRange = () => {
    if (timePeriod === "all") {
      return { startDate: null, endDate: null, days: null };
    }
    
    if (timePeriod === "custom-lookback") {
      if (!customDaysBack || parseInt(customDaysBack) <= 0) {
        return { startDate: null, endDate: null, days: 30 };
      }
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - parseInt(customDaysBack));
      return { startDate, endDate, days: parseInt(customDaysBack) };
    }
    
    if (timePeriod === "custom-range") {
      if (!customStartDate || !customEndDate) {
        return { startDate: null, endDate: null, days: 30 };
      }
      return { 
        startDate: new Date(customStartDate), 
        endDate: new Date(customEndDate),
        days: null
      };
    }
    
    const days = parseInt(timePeriod);
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    
    return { startDate, endDate, days };
  };

  const calculateGrowthPercentage = (timeseries) => {
    if (!timeseries || timeseries.length < 2) return 0;
    
    const firstValue = timeseries[0]?.count || 0;
    const lastValue = timeseries[timeseries.length - 1]?.count || 0;
    
    if (firstValue === 0) return lastValue > 0 ? 100 : 0;
    return ((lastValue - firstValue) / firstValue) * 100;
  };

  const fetchServerData = async () => {
    if (!currentServer || !hasAccess) return;
    
    setLoadingServerStats(true);
    setLoadingMemberChart(true);
    setLoadingJoinsLeavesChart(true);
    setLoadingProjectedChart(true);
    
    const { startDate, endDate, days } = getDateRange();
    const isPublic = isPublicMode;
    
    try {
      // Generate cache key
      const cacheKey = getCacheKey('growth-server', currentServer.id, {
        days, startDate, endDate, public: isPublic
      });
      
      const cached = serverDataCache.get(cacheKey);
      if (cached) {
        setMemberTimeseries(cached.memberTimeseries || []);
        setJoinsLeavesTimeseries(cached.joinsLeavesTimeseries || { joins: [], leaves: [] });
        setProjectedTimeseries(cached.projectedTimeseries || { data: [], joins: [], leaves: [] });
        setServerStats(cached.serverStats);
        setLoadingServerStats(false);
        setLoadingMemberChart(false);
        setLoadingJoinsLeavesChart(false);
        setLoadingProjectedChart(false);
        fetchedRef.current = true;
        return;
      }
      
      // 1. Fetch member timeseries
      const memberRequestBody = { guild_id: currentServer.id };
      if (days !== null && days !== undefined && !isNaN(days)) {
        memberRequestBody.days = days;
      }
      if (startDate) memberRequestBody.start_time = startDate.toISOString();
      if (endDate) memberRequestBody.end_time = endDate.toISOString();
      
      const memberEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/server/members/timeseries`, isPublic);
      
      const memberResponse = await fetch(memberEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(memberRequestBody)
      });
      
      let memberData = [];
      let currentMembers = 0;
      
      if (memberResponse.ok) {
        const data = await memberResponse.json();
        memberData = data.timeseries || [];
        currentMembers = data.current_members || 0;
        setMemberTimeseries(memberData);
      }
      
      // 2. Fetch joins and leaves
      const joinsLeavesRequestBody = { guild_id: currentServer.id };
      if (days !== null && days !== undefined && !isNaN(days)) {
        joinsLeavesRequestBody.days = days;
      }
      if (startDate) joinsLeavesRequestBody.start_time = startDate.toISOString();
      if (endDate) joinsLeavesRequestBody.end_time = endDate.toISOString();
      
      const joinsLeavesEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/server/joins-leaves`, isPublic);
      
      const joinsLeavesResponse = await fetch(joinsLeavesEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(joinsLeavesRequestBody)
      });
      
      let totalJoins = 0;
      let totalLeaves = 0;
      let joinsSeries = [];
      let leavesSeries = [];
      
      if (joinsLeavesResponse.ok) {
        const data = await joinsLeavesResponse.json();
        totalJoins = data.total_joins || 0;
        totalLeaves = data.total_leaves || 0;
        joinsSeries = data.joins_timeseries || [];
        leavesSeries = data.leaves_timeseries || [];
        setJoinsLeavesTimeseries({ joins: joinsSeries, leaves: leavesSeries });
      }
      
      const growthPercent = calculateGrowthPercentage(memberData);
      
      const newServerStats = {
        currentMembers,
        totalJoins,
        totalLeaves,
        netGrowth: totalJoins - totalLeaves,
        growthPercentage: growthPercent
      };
      
      setServerStats(newServerStats);
      
      // 3. Fetch projected growth
      // Forecast horizon scales with the lookback but is capped at
      // PROJECTION_CAP_DAYS so "All Time" / large custom ranges don't
      // trigger a multi-year projection on every load.
      const projectedDays = getProjectionDays(days);
      const projectedRequestBody = {
        guild_id: currentServer.id,
        days: projectedDays
      };
      
      const projectedEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/server/projected`, isPublic);
      
      const projectedResponse = await fetch(projectedEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(projectedRequestBody)
      });
      
      let projectedData = { data: [], joins: [], leaves: [] };
      
      if (projectedResponse.ok) {
        const data = await projectedResponse.json();
        projectedData = {
          data: data.projected_data || [],
          joins: data.joins_forecast || [],
          leaves: data.leaves_forecast || []
        };
        setProjectedTimeseries(projectedData);
      }
      
      // Cache the results
      serverDataCache.set(cacheKey, {
        memberTimeseries: memberData,
        joinsLeavesTimeseries: { joins: joinsSeries, leaves: leavesSeries },
        projectedTimeseries: projectedData,
        serverStats: newServerStats
      });
      
    } catch (error) {
      console.error('Error fetching server data:', error);
      setApiError(error.message);
    } finally {
      setLoadingServerStats(false);
      setLoadingMemberChart(false);
      setLoadingJoinsLeavesChart(false);
      setLoadingProjectedChart(false);
      fetchedRef.current = true;
    }
  };

  const fetchRoleData = async () => {
    if (!currentServer || !selectedRoleId || !hasAccess) return;
    
    setLoadingRoleStats(true);
    setLoadingRoleChart(true);
    setLoadingRoleProjectedChart(true);
    
    const { startDate, endDate, days } = getDateRange();
    const isPublic = isPublicMode;
    
    try {
      // Generate cache key
      const cacheKey = getCacheKey('growth-role', `${currentServer.id}:${selectedRoleId}`, {
        days, startDate, endDate, public: isPublic
      });
      
      const cached = roleCache.get(cacheKey);
      if (cached) {
        setRoleTimeseries(cached.roleTimeseries || { added: [], removed: [] });
        setRoleProjectedTimeseries(cached.roleProjectedTimeseries || { data: [], added: [], removed: [] });
        setRoleStats(cached.roleStats);
        setLoadingRoleStats(false);
        setLoadingRoleChart(false);
        setLoadingRoleProjectedChart(false);
        return;
      }
      
      const roleRequestBody = {
        guild_id: currentServer.id,
        role_id: selectedRoleId
      };
      
      if (days !== null && days !== undefined && !isNaN(days)) {
        roleRequestBody.days = days;
      }
      if (startDate) roleRequestBody.start_time = startDate.toISOString();
      if (endDate) roleRequestBody.end_time = endDate.toISOString();
      
      const roleEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/role/additions-removals`, isPublic);
      
      const roleResponse = await fetch(roleEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(roleRequestBody)
      });
      
      let addedSeries = [];
      let removedSeries = [];
      let totalAdded = 0;
      let totalRemoved = 0;
      
      if (roleResponse.ok) {
        const data = await roleResponse.json();
        totalAdded = data.total_added || 0;
        totalRemoved = data.total_removed || 0;
        addedSeries = data.added_timeseries || [];
        removedSeries = data.removed_timeseries || [];
        setRoleTimeseries({ added: addedSeries, removed: removedSeries });
      }
      
      const netGrowthArray = addedSeries.map((item, index) => ({
        count: (addedSeries[index]?.count || 0) - (removedSeries[index]?.count || 0)
      }));
      const growthPercent = calculateGrowthPercentage(netGrowthArray);
      
      const roleName = roles.find(r => r.id === selectedRoleId)?.name || `Role ${selectedRoleId}`;
      const roleColor = roleColors[selectedRoleId] || '#99aab5';
      
      const newRoleStats = {
        totalAdded,
        totalRemoved,
        netGrowth: totalAdded - totalRemoved,
        growthPercentage: growthPercent,
        roleName,
        roleColor
      };
      
      setRoleStats(newRoleStats);
      
      // Forecast horizon scales with the lookback but is capped at
      // PROJECTION_CAP_DAYS so "All Time" / large custom ranges don't
      // trigger a multi-year projection on every load.
      const projectedDays = getProjectionDays(days);
      const projectedRequestBody = {
        guild_id: currentServer.id,
        role_id: selectedRoleId,
        days: projectedDays
      };
      
      const projectedEndpoint = getApiEndpoint(`${API_BASE_URL}/api/growth/role/projected`, isPublic);
      
      const projectedResponse = await fetch(projectedEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(projectedRequestBody)
      });
      
      let projectedData = { data: [], added: [], removed: [] };
      
      if (projectedResponse.ok) {
        const data = await projectedResponse.json();
        projectedData = {
          data: data.projected_data || [],
          added: data.added_forecast || [],
          removed: data.removed_forecast || []
        };
        setRoleProjectedTimeseries(projectedData);
      }
      
      // Cache the results
      roleCache.set(cacheKey, {
        roleTimeseries: { added: addedSeries, removed: removedSeries },
        roleProjectedTimeseries: projectedData,
        roleStats: newRoleStats
      });
      
    } catch (error) {
      console.error('Error fetching role data:', error);
      setApiError(error.message);
    } finally {
      setLoadingRoleStats(false);
      setLoadingRoleChart(false);
      setLoadingRoleProjectedChart(false);
      fetchedRef.current = true;
    }
  };

  const handleRoleSelect = (role) => {
    setSelectedRoleId(role.id);
    setSelectedRoleName(role.name);
    setRoleSearch(role.name);
    setShowRoleDropdown(false);
    // No manual fetch here — the filter-watcher effect below fires
    // automatically when selectedRoleId changes. Calling fetchRoleData()
    // here too was firing a second, redundant request on every role pick.
  };

  const clearRoleSelection = () => {
    setSelectedRoleId("");
    setSelectedRoleName("");
    setRoleSearch("");
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

  // ============================================
  // MEMOIZED CHART DATA
  // ============================================
  // These used to be plain functions (prepareMemberChartData(), etc.)
  // called directly in JSX. That meant every render — including ones
  // triggered by hovering a legend chip, opening the export menu, or any
  // other unrelated state change — rebuilt these arrays from scratch as
  // brand-new object references. MultiLineChart/Recharts has no way to
  // know "this is the same data as before"; a new array reference looks
  // like new data, so it redid all its internal work (and replayed the
  // draw-in animation) on every incidental re-render. Wrapping these in
  // useMemo means they're only recalculated when the underlying timeseries
  // state actually changes.

  const memberChartData = useMemo(() => {
    if (!memberTimeseries.length) return [];

    const sorted = [...memberTimeseries].sort((a, b) => a.date.localeCompare(b.date));

    return sorted.map(point => ({
      date: point.date,
      count: point.count
    }));
  }, [memberTimeseries]);

  const joinsLeavesChartData = useMemo(() => {
    const { joins, leaves } = joinsLeavesTimeseries;
    if (joins.length === 0 && leaves.length === 0) return [];

    const dateMap = new Map();

    joins.forEach(j => {
      dateMap.set(j.date, { date: j.date, joins: j.count, leaves: 0 });
    });

    leaves.forEach(l => {
      const existing = dateMap.get(l.date);
      if (existing) {
        existing.leaves = l.count;
      } else {
        dateMap.set(l.date, { date: l.date, joins: 0, leaves: l.count });
      }
    });

    return Array.from(dateMap.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [joinsLeavesTimeseries]);

  const projectedChartData = useMemo(() => {
    const projectedData = projectedTimeseries.data || [];
    if (!projectedData.length) return [];

    return projectedData.map(point => ({
      date: point.date,
      joins: point.joins,
      leaves: point.leaves
    }));
  }, [projectedTimeseries]);

  const roleChartData = useMemo(() => {
    const { added, removed } = roleTimeseries;
    if (added.length === 0 && removed.length === 0) return [];

    const dateMap = new Map();

    added.forEach(a => {
      dateMap.set(a.date, { date: a.date, added: a.count, removed: 0 });
    });

    removed.forEach(r => {
      const existing = dateMap.get(r.date);
      if (existing) {
        existing.removed = r.count;
      } else {
        dateMap.set(r.date, { date: r.date, added: 0, removed: r.count });
      }
    });

    return Array.from(dateMap.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [roleTimeseries]);

  const roleProjectedChartData = useMemo(() => {
    const projectedData = roleProjectedTimeseries.data || [];
    if (!projectedData.length) return [];

    return projectedData.map(point => ({
      date: point.date,
      added: point.added,
      removed: point.removed
    }));
  }, [roleProjectedTimeseries]);

  const getDisplayDays = () => {
    if (timePeriod === "all") return "All Time";
    if (timePeriod === "custom-lookback" && customDaysBack) return customDaysBack;
    if (timePeriod === "custom-range") return "Custom Range";
    return timePeriod;
  };

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

    .retention-banner { width:100%; box-sizing:border-box; background:linear-gradient(135deg,#3a2f00 0%,#4a3a00 100%); border-bottom:1px solid #ffcc00; padding:12px 24px; display:flex; align-items:center; justify-content:center; gap:16px; position:relative; }
    .retention-banner-text { color:#ffe066; font-size:14px; font-weight:500; text-align:center; max-width:900px; }
    .retention-banner-close { background:none; border:none; color:#ffe066; font-size:14px; cursor:pointer; padding:4px 8px; border-radius:6px; line-height:1; flex-shrink:0; transition:background-color 0.15s,color 0.15s; }
    .retention-banner-close:hover { background-color:rgba(255,224,102,0.15); color:#fff; }

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

    .entity-name {
      font-weight: 500;
    }

    .entity-id {
      color: #888;
      font-size: 12px;
    }

    .selected-role {
      margin-top: 8px;
      padding: 8px 12px;
      background-color: rgba(170, 0, 255, 0.1);
      border: 1px solid #aa00ff;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .selected-role span {
      color: #aa00ff;
      font-size: 14px;
    }

    .selected-role button {
      background: none;
      border: none;
      color: #ff4444;
      cursor: pointer;
      font-size: 14px;
      padding: 4px 8px;
    }

    .selected-role button:hover {
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

    .no-selection h2 {
      color: #ffffff;
      margin-bottom: 16px;
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

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 24px;
      margin-bottom: 40px;
    }

    .stat-card {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
      transition: all 0.2s ease;
      text-align: center;
    }

    .stat-card:hover {
      border-color: #aa00ff;
      box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2);
      transform: translateY(-2px);
    }

    .stat-card h3 {
      color: #b0b0b0;
      font-size: 14px;
      font-weight: 500;
      margin: 0 0 12px 0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .stat-value {
      color: #ffffff !important;
      font-size: 36px;
      font-weight: 700;
      margin: 0;
      background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.2;
    }

    .stat-growth {
      font-size: 14px;
      margin-top: 8px;
      font-weight: 500;
    }

    .stat-growth.positive {
      color: #00ff00;
    }

    .stat-growth.negative {
      color: #ff0000;
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

    .charts-section {
      margin-bottom: 40px;
      width: 100%;
    }

    .chart-wrapper {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
      transition: all 0.2s ease;
      min-height: 450px;
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

    .no-chart-data {
      color: #b0b0b0;
      font-size: 16px;
      text-align: center;
      padding: 100px;
    }

    /* Responsive Styles - FIXED */
    @media (max-width: 1024px) {
      .dashboard-main {
        margin-left: 250px;
        width: calc(100% - 250px);
      }
      
      .dashboard-content {
        padding: 16px;
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
      
      .stats-grid {
        grid-template-columns: 1fr;
      }
      
      .section-title {
        font-size: 24px;
      }
      
      /* Charts remain normal size, no scaling */
      .chart-wrapper {
        transform: none !important;
        margin: 0 !important;
        padding: 16px;
      }
      
      .chart-wrapper > div {
        width: 100% !important;
        min-height: 400px;
      }
    }

    @media (max-width: 480px) {
      .dashboard-content {
        padding: 8px;
      }
      
      .chart-wrapper {
        padding: 12px;
      }
      
      .chart-wrapper > div {
        min-height: 350px;
      }
      
      .section-title {
        font-size: 20px;
      }
      
      .stat-value {
        font-size: 28px;
      }
    }

    /* Ensure text colors are visible on Samsung Internet and other browsers */
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
                <p>Viewing growth statistics from the <strong>StatsHQ</strong> support server - <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server's growth stats</p>
              </div>
              
              {/* Filters Section - Public version */}
              <div className="filters-section">
                <div className="filter-row">
                  <label>View:</label>
                  <select
                    value={selectedView}
                    onChange={(e) => {
                      setSelectedView(e.target.value);
                      if (e.target.value === 'server') {
                        clearRoleSelection();
                      }
                    }}
                    className="modern-select"
                  >
                    <option value="server">Server Growth</option>
                    <option value="role">Role Growth</option>
                  </select>
                </div>
                
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
                
                {/* Role Selector - Public */}
                {selectedView === 'role' && (
                  <div className="filter-row entity-filter">
                    <label>Select Role:</label>
                    <div className="entity-selector">
                      <input
                        type="text"
                        placeholder="Search role..."
                        value={roleSearch}
                        onChange={(e) => setRoleSearch(e.target.value)}
                        onFocus={() => setShowRoleDropdown(true)}
                        onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
                        className="modern-entity-search"
                      />
                      {showRoleDropdown && filteredRoles.length > 0 && (
                        <div className="entity-dropdown">
                          {filteredRoles.slice(0, 20).map(role => (
                            <div
                              key={role.id}
                              className={`entity-option ${selectedRoleId === role.id ? 'selected' : ''}`}
                              onMouseDown={() => handleRoleSelect(role)}
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
                      
                      {selectedRoleId && (
                        <div className="selected-role">
                          <span>Selected: {selectedRoleName}</span>
                          <button onClick={clearRoleSelection}>✕</button>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {loadingServers ? (
                <div className="loading">Loading servers...</div>
              ) : apiError ? (
                <div className="error-message">
                  <h2>Error Loading Data</h2>
                  <p>{apiError}</p>
                  <button onClick={() => { serverDataCache.clear(); selectedView === 'server' ? fetchServerData() : fetchRoleData(); }} className="retry-button">
                    Clear Cache & Retry
                  </button>
                </div>
              ) : (
                <>
                  {/* Server View - Public */}
                  {selectedView === 'server' && (
                    <>
                      {/* Stats Cards */}
                      <div className="stats-grid">
                        {loadingServerStats ? (
                          <>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          </>
                        ) : (
                          <>
                            <div className="stat-card">
                              <h3>Total Members</h3>
                              <p className="stat-value">{formatNumber(serverStats.currentMembers)}</p>
                              <div className={`stat-growth ${serverStats.growthPercentage >= 0 ? 'positive' : 'negative'}`}>
                                {formatPercentage(serverStats.growthPercentage)} over period
                              </div>
                            </div>
                            <div className="stat-card">
                              <h3>Total Joins</h3>
                              <p className="stat-value">+{formatNumber(serverStats.totalJoins)}</p>
                              <div className="stat-growth positive">Net: {formatNumber(serverStats.netGrowth)}</div>
                            </div>
                            <div className="stat-card">
                              <h3>Total Leaves</h3>
                              <p className="stat-value">-{formatNumber(serverStats.totalLeaves)}</p>
                            </div>
                          </>
                        )}
                      </div>
                      
                      {/* Member Count Chart */}
                      <div className="charts-section">
                        <h2 className="section-title">Server Member Count Over Time</h2>
                        <div className="chart-wrapper">
                          {loadingMemberChart ? (
                            <LoadingChart />
                          ) : memberTimeseries.length > 0 ? (
                            <MultiLineChart
                              data={memberChartData}
                              lines={[
                                { dataKey: 'count', name: 'Member Count', color: '#aa00ff' }
                              ]}
                              title="Member Count Over Time"
                              valueFormatter={(value) => formatNumber(value)}
                            />
                          ) : (
                            <div className="no-chart-data">No member count data available</div>
                          )}
                        </div>
                      </div>
                      
                      {/* Joins and Leaves Chart - GREEN for Joins, RED for Leaves */}
                      <div className="charts-section">
                        <h2 className="section-title">Joins vs Leaves</h2>
                        <div className="chart-wrapper">
                          {loadingJoinsLeavesChart ? (
                            <LoadingChart />
                          ) : joinsLeavesTimeseries.joins.length > 0 || joinsLeavesTimeseries.leaves.length > 0 ? (
                            <MultiLineChart
                              data={joinsLeavesChartData}
                              lines={[
                                { dataKey: 'joins', name: 'Joins', color: '#00ff00' },
                                { dataKey: 'leaves', name: 'Leaves', color: '#ff0000' }
                              ]}
                              title="Daily Joins and Leaves"
                              valueFormatter={(value) => formatNumber(value)}
                            />
                          ) : (
                            <div className="no-chart-data">No joins/leaves data available</div>
                          )}
                        </div>
                      </div>
                      
                      {/* Projected Growth Chart - GREEN for Joins, RED for Leaves */}
                      <div className="charts-section">
                        <h2 className="section-title">Projected Growth (Next {getProjectionDays(getDateRange().days)} Days)</h2>
                        <div className="chart-wrapper">
                          {loadingProjectedChart ? (
                            <LoadingChart />
                          ) : projectedTimeseries.data && projectedTimeseries.data.length > 0 ? (
                            <MultiLineChart
                              data={projectedChartData}
                              lines={[
                                { dataKey: 'joins', name: 'Projected Joins', color: '#00ff00' },
                                { dataKey: 'leaves', name: 'Projected Leaves', color: '#ff0000' }
                              ]}
                              title="Projected Joins and Leaves"
                              valueFormatter={(value) => formatNumber(Math.round(value))}
                            />
                          ) : (
                            <div className="no-chart-data">No projection data available</div>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                  
                  {/* Role View - Public - GREEN for Additions, RED for Removals */}
                  {selectedView === 'role' && (
                    <>
                      {!selectedRoleId ? (
                        <div className="no-selection">
                          <h2>Select a Role</h2>
                          <p>Please select a role from the dropdown above to view its growth statistics.</p>
                          {roles.length === 0 && (
                            <p style={{ marginTop: '20px', color: '#666' }}>No roles with growth data found. Roles will start tracking after members receive or lose them.</p>
                          )}
                        </div>
                      ) : (
                        <>
                          {/* Role Stats Cards */}
                          <div className="stats-grid">
                            {loadingRoleStats ? (
                              <>
                                <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                                <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                                <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                              </>
                            ) : (
                              <>
                                <div className="stat-card">
                                  <h3>Total Additions</h3>
                                  <p className="stat-value">+{formatNumber(roleStats.totalAdded)}</p>
                                </div>
                                <div className="stat-card">
                                  <h3>Total Removals</h3>
                                  <p className="stat-value">-{formatNumber(roleStats.totalRemoved)}</p>
                                </div>
                                <div className="stat-card">
                                  <h3>Net Growth</h3>
                                  <p className="stat-value" style={{ color: roleStats.netGrowth >= 0 ? '#00ff00' : '#ff0000' }}>
                                    {roleStats.netGrowth >= 0 ? '+' : ''}{formatNumber(roleStats.netGrowth)}
                                  </p>
                                  <div className={`stat-growth ${roleStats.growthPercentage >= 0 ? 'positive' : 'negative'}`}>
                                    {formatPercentage(roleStats.growthPercentage)} over period
                                  </div>
                                </div>
                              </>
                            )}
                          </div>
                          
                          {/* Additions and Removals Chart - GREEN for Additions, RED for Removals */}
                          <div className="charts-section">
                            <h2 className="section-title">{roleStats.roleName || 'Role'} - Additions vs Removals</h2>
                            <div className="chart-wrapper">
                              {loadingRoleChart ? (
                                <LoadingChart />
                              ) : roleTimeseries.added.length > 0 || roleTimeseries.removed.length > 0 ? (
                                <MultiLineChart
                                  data={roleChartData}
                                  lines={[
                                    { dataKey: 'added', name: 'Additions', color: '#00ff00' },
                                    { dataKey: 'removed', name: 'Removals', color: '#ff0000' }
                                  ]}
                                  title={`${roleStats.roleName || 'Role'} - Daily Additions and Removals`}
                                  valueFormatter={(value) => formatNumber(value)}
                                />
                              ) : (
                                <div className="no-chart-data">No role growth data available</div>
                              )}
                            </div>
                          </div>
                          
                          {/* Projected Role Growth Chart - GREEN for Additions, RED for Removals */}
                          <div className="charts-section">
                            <h2 className="section-title">Projected Role Growth (Next {getProjectionDays(getDateRange().days)} Days)</h2>
                            <div className="chart-wrapper">
                              {loadingRoleProjectedChart ? (
                                <LoadingChart />
                              ) : roleProjectedTimeseries.data && roleProjectedTimeseries.data.length > 0 ? (
                                <MultiLineChart
                                  data={roleProjectedChartData}
                                  lines={[
                                    { dataKey: 'added', name: 'Projected Additions', color: '#00ff00' },
                                    { dataKey: 'removed', name: 'Projected Removals', color: '#ff0000' }
                                  ]}
                                  title={`${roleStats.roleName || 'Role'} - Projected Additions and Removals`}
                                  valueFormatter={(value) => formatNumber(Math.round(value))}
                                />
                              ) : (
                                <div className="no-chart-data">No projection data available</div>
                              )}
                            </div>
                          </div>
                        </>
                      )}
                    </>
                  )}
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
                <button onClick={() => { serverDataCache.clear(); selectedView === 'server' ? fetchServerData() : fetchRoleData(); }} className="retry-button">
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
            
            {/* Filters */}
            <div className="filters-section">
              <div className="filter-row">
                <label>View:</label>
                <select
                  value={selectedView}
                  onChange={(e) => {
                    setSelectedView(e.target.value);
                    if (e.target.value === 'server') {
                      clearRoleSelection();
                    }
                  }}
                  className="modern-select"
                >
                  <option value="server">Server Growth</option>
                  <option value="role">Role Growth</option>
                </select>
              </div>
              
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
              
              {/* Role Selector */}
              {selectedView === 'role' && (
                <div className="filter-row entity-filter">
                  <label>Select Role:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search role..."
                      value={roleSearch}
                      onChange={(e) => setRoleSearch(e.target.value)}
                      onFocus={() => setShowRoleDropdown(true)}
                      onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
                      className="modern-entity-search"
                    />
                    {showRoleDropdown && filteredRoles.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredRoles.slice(0, 20).map(role => (
                          <div
                            key={role.id}
                            className={`entity-option ${selectedRoleId === role.id ? 'selected' : ''}`}
                            onMouseDown={() => handleRoleSelect(role)}
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
                    
                    {selectedRoleId && (
                      <div className="selected-role">
                        <span>Selected: {selectedRoleName}</span>
                        <button onClick={clearRoleSelection}>✕</button>
                      </div>
                    )}
                  </div>
                </div>
              )}
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
                <button onClick={() => selectedView === 'server' ? fetchServerData() : fetchRoleData()} className="retry-button">
                  Retry
                </button>
              </div>
            ) : (
              <>
                {/* Server View */}
                {selectedView === 'server' && (
                  <>
                    {/* Stats Cards */}
                    <div className="stats-grid">
                      {loadingServerStats ? (
                        <>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        </>
                      ) : (
                        <>
                          <div className="stat-card">
                            <h3>Total Members</h3>
                            <p className="stat-value">{formatNumber(serverStats.currentMembers)}</p>
                            <div className={`stat-growth ${serverStats.growthPercentage >= 0 ? 'positive' : 'negative'}`}>
                              {formatPercentage(serverStats.growthPercentage)} over period
                            </div>
                          </div>
                          <div className="stat-card">
                            <h3>Total Joins</h3>
                            <p className="stat-value">+{formatNumber(serverStats.totalJoins)}</p>
                            <div className="stat-growth positive">Net: {formatNumber(serverStats.netGrowth)}</div>
                          </div>
                          <div className="stat-card">
                            <h3>Total Leaves</h3>
                            <p className="stat-value">-{formatNumber(serverStats.totalLeaves)}</p>
                          </div>
                        </>
                      )}
                    </div>
                    
                    {/* Member Count Chart */}
                    <div className="charts-section">
                      <h2 className="section-title">Server Member Count Over Time</h2>
                      <div className="chart-wrapper">
                        {loadingMemberChart ? (
                          <LoadingChart />
                        ) : memberTimeseries.length > 0 ? (
                          <MultiLineChart
                            data={memberChartData}
                            lines={[
                              { dataKey: 'count', name: 'Member Count', color: '#aa00ff' }
                            ]}
                            title="Member Count Over Time"
                            valueFormatter={(value) => formatNumber(value)}
                          />
                        ) : (
                          <div className="no-chart-data">No member count data available</div>
                        )}
                      </div>
                    </div>
                    
                    {/* Joins and Leaves Chart - GREEN for Joins, RED for Leaves */}
                    <div className="charts-section">
                      <h2 className="section-title">Joins vs Leaves</h2>
                      <div className="chart-wrapper">
                        {loadingJoinsLeavesChart ? (
                          <LoadingChart />
                        ) : joinsLeavesTimeseries.joins.length > 0 || joinsLeavesTimeseries.leaves.length > 0 ? (
                          <MultiLineChart
                            data={joinsLeavesChartData}
                            lines={[
                              { dataKey: 'joins', name: 'Joins', color: '#00ff00' },
                              { dataKey: 'leaves', name: 'Leaves', color: '#ff0000' }
                            ]}
                            title="Daily Joins and Leaves"
                            valueFormatter={(value) => formatNumber(value)}
                          />
                        ) : (
                          <div className="no-chart-data">No joins/leaves data available</div>
                        )}
                      </div>
                    </div>
                    
                    {/* Projected Growth Chart - GREEN for Joins, RED for Leaves */}
                    <div className="charts-section">
                      <h2 className="section-title">Projected Growth (Next {getProjectionDays(getDateRange().days)} Days)</h2>
                      <div className="chart-wrapper">
                        {loadingProjectedChart ? (
                          <LoadingChart />
                        ) : projectedTimeseries.data && projectedTimeseries.data.length > 0 ? (
                          <MultiLineChart
                            data={projectedChartData}
                            lines={[
                              { dataKey: 'joins', name: 'Projected Joins', color: '#00ff00' },
                              { dataKey: 'leaves', name: 'Projected Leaves', color: '#ff0000' }
                            ]}
                            title="Projected Joins and Leaves"
                            valueFormatter={(value) => formatNumber(Math.round(value))}
                          />
                        ) : (
                          <div className="no-chart-data">No projection data available</div>
                        )}
                      </div>
                    </div>
                  </>
                )}
                
                {/* Role View - GREEN for Additions, RED for Removals */}
                {selectedView === 'role' && (
                  <>
                    {!selectedRoleId ? (
                      <div className="no-selection">
                        <h2>Select a Role</h2>
                        <p>Please select a role from the dropdown above to view its growth statistics.</p>
                        {roles.length === 0 && (
                          <p style={{ marginTop: '20px', color: '#666' }}>No roles with growth data found. Roles will start tracking after members receive or lose them.</p>
                        )}
                      </div>
                    ) : (
                      <>
                        {/* Role Stats Cards */}
                        <div className="stats-grid">
                          {loadingRoleStats ? (
                            <>
                              <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                              <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                              <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            </>
                          ) : (
                            <>
                              <div className="stat-card">
                                <h3>Total Additions</h3>
                                <p className="stat-value">+{formatNumber(roleStats.totalAdded)}</p>
                              </div>
                              <div className="stat-card">
                                <h3>Total Removals</h3>
                                <p className="stat-value">-{formatNumber(roleStats.totalRemoved)}</p>
                              </div>
                              <div className="stat-card">
                                <h3>Net Growth</h3>
                                <p className="stat-value" style={{ color: roleStats.netGrowth >= 0 ? '#00ff00' : '#ff0000' }}>
                                  {roleStats.netGrowth >= 0 ? '+' : ''}{formatNumber(roleStats.netGrowth)}
                                </p>
                                <div className={`stat-growth ${roleStats.growthPercentage >= 0 ? 'positive' : 'negative'}`}>
                                  {formatPercentage(roleStats.growthPercentage)} over period
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                        
                        {/* Additions and Removals Chart - GREEN for Additions, RED for Removals */}
                        <div className="charts-section">
                          <h2 className="section-title">{roleStats.roleName || 'Role'} - Additions vs Removals</h2>
                          <div className="chart-wrapper">
                            {loadingRoleChart ? (
                              <LoadingChart />
                            ) : roleTimeseries.added.length > 0 || roleTimeseries.removed.length > 0 ? (
                              <MultiLineChart
                                data={roleChartData}
                                lines={[
                                  { dataKey: 'added', name: 'Additions', color: '#00ff00' },
                                  { dataKey: 'removed', name: 'Removals', color: '#ff0000' }
                                ]}
                                title={`${roleStats.roleName || 'Role'} - Daily Additions and Removals`}
                                valueFormatter={(value) => formatNumber(value)}
                              />
                            ) : (
                              <div className="no-chart-data">No role growth data available</div>
                            )}
                          </div>
                        </div>
                        
                        {/* Projected Role Growth Chart - GREEN for Additions, RED for Removals */}
                        <div className="charts-section">
                          <h2 className="section-title">Projected Role Growth (Next {getProjectionDays(getDateRange().days)} Days)</h2>
                          <div className="chart-wrapper">
                            {loadingRoleProjectedChart ? (
                              <LoadingChart />
                            ) : roleProjectedTimeseries.data && roleProjectedTimeseries.data.length > 0 ? (
                              <MultiLineChart
                                data={roleProjectedChartData}
                                lines={[
                                  { dataKey: 'added', name: 'Projected Additions', color: '#00ff00' },
                                  { dataKey: 'removed', name: 'Projected Removals', color: '#ff0000' }
                                ]}
                                title={`${roleStats.roleName || 'Role'} - Projected Additions and Removals`}
                                valueFormatter={(value) => formatNumber(Math.round(value))}
                              />
                            ) : (
                              <div className="no-chart-data">No projection data available</div>
                            )}
                          </div>
                        </div>
                      </>
                    )}
                  </>
                )}
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
  <React.StrictMode>
    <GrowthDashboard />
  </React.StrictMode>
);

export default GrowthDashboard;