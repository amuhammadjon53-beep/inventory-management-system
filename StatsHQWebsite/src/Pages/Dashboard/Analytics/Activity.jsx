import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import Leaderboard from "../../../Components/Leaderboard.jsx";
import EnhancedMultiLineChart from "../../../Components/EnhancedMultiLineChart.jsx";

// API base URL - your FastAPI backend
const API_BASE_URL = '';

// PUBLIC GUILD ID for unauthenticated users
const PUBLIC_GUILD_ID = '1424021358680998022';

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ============================================
// FIXED CACHING SYSTEM - Only caches valid names
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

// Fixed Cache for user basic info (usernames without avatars)
const userBasicInfoCache = new Map();

// Enhanced cache for server data with size limits and TTL
class ServerDataCache {
  constructor(maxSize = 50, ttl = 5 * 60 * 1000) {
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
}

// Initialize caches
const profileCache = new ProfileCache(500);
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);

// Cache key generator for consistent caching
const getCacheKey = (type, id, params) => {
  return `${type}:${id}:${JSON.stringify(params)}`;
};

// Format seconds to dynamic time string
const formatDynamicTime = (seconds) => {
  if (!seconds || seconds === 0) return "0s";
  
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  const parts = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);
  
  return parts.join(' ');
};

// Format large values for leaderboard
const formatActivityValue = (value) => {
  if (value >= 3600) {
    const hours = value / 3600;
    return `${hours.toFixed(1)} hrs`;
  }
  return formatDynamicTime(value);
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
      <p>You don't have permission to view this server's activity statistics.</p>
      <p>This server requires <strong>{requiredPermission}</strong> permissions.</p>
      <p className="setting-note" style={{ marginTop: '12px', fontSize: '12px', color: '#666' }}>
        Note: Server owners automatically have Administrator permission.
      </p>
    </div>
  );
};

// ============================================
// FIXED USERNAME FETCHING FUNCTIONS
// ============================================

// FIXED: Fetch single user's basic info (username only, no avatar)
const fetchUserBasicInfo = async (userId, guildId, isPublicMode) => {
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
const batchFetchUserBasicInfo = async (guildId, userIds, isPublicMode) => {
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

// FIXED: Fetch user avatar (only for top 3 users - though activity dashboard doesn't need avatars)
const fetchUserAvatar = async (userId, isPublicMode) => {
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

const ActivityDashboard = () => {
  // State
  const [selectedView, setSelectedView] = useState("server");
  const [timePeriod, setTimePeriod] = useState("30");
  const [customDaysBack, setCustomDaysBack] = useState("");
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [roleSearch, setRoleSearch] = useState("");
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  
  const [serverChartSort, setServerChartSort] = useState("time");
  const [serverLeaderboardSort, setServerLeaderboardSort] = useState("time");
  const [userChartSort, setUserChartSort] = useState("time");
  const [userLeaderboardSort, setUserLeaderboardSort] = useState("time");
  
  const [tempRoleId, setTempRoleId] = useState("");
  const [tempRoleSearch, setTempRoleSearch] = useState("");
  const [showApplyButton, setShowApplyButton] = useState(false);
  
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [filteredRoles, setFilteredRoles] = useState([]);
  
  const [loading, setLoading] = useState(true);
  const [serverData, setServerData] = useState(null);
  const [userData, setUserData] = useState(null);
  const [currentServer, setCurrentServer] = useState(null);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [isPublicMode, setIsPublicMode] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [currentUserId, setCurrentUserId] = useState(null);
  const [serverTimezone, setServerTimezone] = useState('UTC');
  
  const [loadingServerStats, setLoadingServerStats] = useState(true);
  const [loadingUserStats, setLoadingUserStats] = useState(true);
  const [loadingServerChart, setLoadingServerChart] = useState(true);
  const [loadingUserChart, setLoadingUserChart] = useState(true);
  
  const [serverChartTimeSeries, setServerChartTimeSeries] = useState([]);
  const [userChartTimeSeries, setUserChartTimeSeries] = useState([]);
  
  const [serverAllActivities, setServerAllActivities] = useState([]);
  const [serverPlaying, setServerPlaying] = useState([]);
  const [serverStreaming, setServerStreaming] = useState([]);
  const [serverListening, setServerListening] = useState([]);
  const [serverWatching, setServerWatching] = useState([]);
  const [serverCompeting, setServerCompeting] = useState([]);
  const [serverCustom, setServerCustom] = useState([]);
  
  const [userAllActivities, setUserAllActivities] = useState([]);
  const [userPlaying, setUserPlaying] = useState([]);
  const [userStreaming, setUserStreaming] = useState([]);
  const [userListening, setUserListening] = useState([]);
  const [userWatching, setUserWatching] = useState([]);
  const [userCompeting, setUserCompeting] = useState([]);
  const [userCustom, setUserCustom] = useState([]);
  
  const [profilePictures, setProfilePictures] = useState({});
  const [userNames, setUserNames] = useState({});
  const [roleNames, setRoleNames] = useState({});
  const [roleColors, setRoleColors] = useState({});

  const [usersLoaded, setUsersLoaded] = useState(false);
  const [rolesLoaded, setRolesLoaded] = useState(false);
  
  const [rawUserIds, setRawUserIds] = useState([]);
  const [isFetchingUsernames, setIsFetchingUsernames] = useState(false);

  const fetchedRef = useRef(false);
  const initialDataLoadedRef = useRef(false);
  const prevFiltersRef = useRef(JSON.stringify({
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedRoleId,
    serverChartSort, serverLeaderboardSort, userChartSort, userLeaderboardSort
  }));

  const rolesRef = useRef([]);

  useEffect(() => {
    rolesRef.current = roles;
  }, [roles]);

  // Fetch usernames when user dropdown opens
  useEffect(() => {
    if (showUserDropdown && rawUserIds.length > 0 && !isFetchingUsernames && currentServer) {
      const fetchUsernamesForDropdown = async () => {
        setIsFetchingUsernames(true);
        try {
          const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, rawUserIds, isPublicMode);
          
          setUsers(prevUsers => 
            prevUsers.map(user => {
              const info = userInfoMap[user.id];
              if (info && info.name !== user.name) {
                return { ...user, name: info.name, username: info.username };
              }
              return user;
            })
          );
          
          setFilteredUsers(prev => 
            prev.map(user => {
              const info = userInfoMap[user.id];
              if (info && info.name !== user.name) {
                return { ...user, name: info.name, username: info.username };
              }
              return user;
            })
          );
          
          const newUserNames = {};
          for (const [userId, info] of Object.entries(userInfoMap)) {
            newUserNames[userId] = info.name;
          }
          setUserNames(prev => ({ ...prev, ...newUserNames }));
        } catch (error) {
          console.error('Error fetching usernames for dropdown:', error);
        } finally {
          setIsFetchingUsernames(false);
        }
      };
      
      fetchUsernamesForDropdown();
    }
  }, [showUserDropdown, rawUserIds, currentServer, isFetchingUsernames, isPublicMode]);

  // Fetch server timezone from API
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

  const isPrivilegedUser = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  const NAVBAR_HEIGHT = "80px";

  useEffect(() => {
    loadInitialData();
  }, []);

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
      setApiError('Failed to load data. Please check your connection.');
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
        setLoading(false);
      } else {
        console.error('Failed to get settings for guild:', guildId);
        setHasAccess(false);
        setLoading(false);
      }
    } catch (error) {
      console.error('Error checking server access:', error);
      setHasAccess(false);
      setLoading(false);
    }
  };

  const getRoleName = (roleId) => {
    if (!roleId) return 'Unknown Role';
    const stringId = String(roleId).trim();
    const role = rolesRef.current.find(r => String(r.id) === stringId);
    if (role) return role.name;
    return `Role ${stringId}`;
  };

  // ============================================
  // FETCH ALL ROLES - FIXED
  // ============================================
  const fetchAllRoles = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setRolesLoaded(false);
    
    const cacheKey = getCacheKey('roles', currentServer.id, { public: isPublic });
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
      // ✅ FIXED: Build URL directly with query parameter
      const url = isPublic 
        ? `${API_BASE_URL}/api/public/server/real-roles?guild_id=${currentServer.id}`
        : `${API_BASE_URL}/api/server/real-roles?guild_id=${currentServer.id}`;
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const rolesData = await response.json();
        
        if (Array.isArray(rolesData) && rolesData.length > 0) {
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
        } else {
          setRoles([]);
          setFilteredRoles([]);
          setRoleNames({});
          setRoleColors({});
        }
      } else {
        console.error('Failed to fetch roles:', response.status);
        setRoles([]);
        setFilteredRoles([]);
        setRoleNames({});
        setRoleColors({});
      }
    } catch (error) {
      console.error('Error fetching roles:', error);
      setRoles([]);
      setFilteredRoles([]);
      setRoleNames({});
      setRoleColors({});
    } finally {
      setRolesLoaded(true);
    }
  };

  // Fetch roles whenever currentServer changes
  useEffect(() => {
    if (currentServer) {
      fetchAllRoles();
    }
  }, [currentServer]);

  // ============================================
  // FETCH ALL USERS - FIXED
  // ============================================
  const fetchAllUsers = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setUsersLoaded(false);
    
    const cacheKey = getCacheKey('activity-users', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
        setUsers(cached.users);
        setFilteredUsers(cached.users);
        setUserNames(cached.userNames);
        setProfilePictures(cached.profilePictures);
        setRawUserIds((cached.users || []).map(u => u.id));
        setUsersLoaded(true);
        return;
    }
    
    try {
        // ✅ FIXED: Build URL directly
        let url;
        if (isPublic) {
          url = `${API_BASE_URL}/api/public/guild/activity-users`;
        } else {
          url = `${API_BASE_URL}/api/guild/activity-users`;
        }
        
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ guild_id: currentServer.id, limit: 100000000000 })
        });
        
        if (!response.ok) {
          setUsersLoaded(true);
          return;
        }
        
        const data = await response.json();
        
        if (!data.success || !data.user_ids || data.user_ids.length === 0) {
          setUsersLoaded(true);
          return;
        }
        
        const userIds = data.user_ids;
        const userList = userIds.map(userId => ({
          id: String(userId),
          name: `User ${userId}`,
          username: null,
          global_name: null,
          avatar: null
        }));
        
        setRawUserIds(userIds.map(id => String(id)));
        
        serverDataCache.set(cacheKey, {
          users: userList,
          userNames: {},
          profilePictures: {}
        });
        
        setUsers(userList);
        setFilteredUsers(userList);
        setUserNames({});
        setProfilePictures({});
        
    } catch (error) {
        console.error('Error fetching users:', error);
    } finally {
        setUsersLoaded(true);
    }
  };

  // Load all data when server changes
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    if (initialDataLoadedRef.current === currentServer.id) return;
    
    fetchedRef.current = false;
    
    setLoadingServerStats(true);
    setLoadingUserStats(true);
    setLoadingServerChart(true);
    setLoadingUserChart(true);
    
    setLoading(true);
    
    setUsersLoaded(false);
    setRolesLoaded(false);
    
    setServerAllActivities([]);
    setServerPlaying([]);
    setServerStreaming([]);
    setServerListening([]);
    setServerWatching([]);
    setServerCompeting([]);
    setServerCustom([]);
    setServerChartTimeSeries([]);
    
    setUserAllActivities([]);
    setUserPlaying([]);
    setUserStreaming([]);
    setUserListening([]);
    setUserWatching([]);
    setUserCompeting([]);
    setUserCustom([]);
    setUserChartTimeSeries([]);
    
    setServerData(null);
    setUserData(null);
    
    setSelectedUserId("");
    setUserSearch("");
    
    profileCache.clear();
    userBasicInfoCache.clear();
    setRawUserIds([]);
    
    clearRoleFilter();
    
    initialDataLoadedRef.current = currentServer.id;
    
    Promise.all([
      fetchAllUsers(),
      fetchAllRoles()
    ]).then(() => {
      fetchData();
    });
  }, [currentServer, hasAccess]);

  // Fetch stats when filters change
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    const currentFilters = JSON.stringify({
      selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedUserId, selectedRoleId,
      serverChartSort, serverLeaderboardSort, userChartSort, userLeaderboardSort
    });
    
    if (fetchedRef.current && prevFiltersRef.current !== currentFilters) {
      prevFiltersRef.current = currentFilters;
      fetchData();
    }
  }, [
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedRoleId,
    serverChartSort, serverLeaderboardSort, userChartSort, userLeaderboardSort
  ]);

  // Filter users when search changes
  useEffect(() => {
    if (userSearch.trim() === "") {
      setFilteredUsers(users);
    } else {
      const searchLower = userSearch.toLowerCase();
      const filtered = users.filter(user => 
        (user.name?.toLowerCase().includes(searchLower)) ||
        (user.username?.toLowerCase().includes(searchLower)) ||
        (user.global_name?.toLowerCase().includes(searchLower)) ||
        user.id?.includes(searchLower)
      );
      setFilteredUsers(filtered);
    }
  }, [userSearch, users]);

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

  const fetchData = async () => {
    if (!currentServer || !hasAccess) return;
    
    setLoading(true);
    setApiError(null);
    const { startDate, endDate } = getDateRange();
    
    try {
      const roleFilterArray = selectedRoleId ? [String(selectedRoleId)] : null;
      
      const requestBody = {
        guild_id: currentServer.id,
        role_filter_ids: roleFilterArray
      };
      
      if (startDate && endDate) {
        requestBody.start_time = startDate.toISOString();
        requestBody.end_time = endDate.toISOString();
        
        if (timePeriod !== "custom-range") {
          if (timePeriod === "custom-lookback" && customDaysBack) {
            requestBody.days = parseInt(customDaysBack);
          } else if (timePeriod !== "custom-lookback" && timePeriod !== "all") {
            requestBody.days = parseInt(timePeriod);
          } else if (timePeriod === "all") {
            requestBody.days = 2000;
          }
        }
      } else {
        if (timePeriod === "all") {
          requestBody.days = 2000;
        } else if (timePeriod === "custom-lookback" && customDaysBack) {
          requestBody.days = parseInt(customDaysBack);
        } else if (timePeriod !== "custom-lookback") {
          requestBody.days = parseInt(timePeriod);
        }
      }
      
      if (selectedView === 'server') {
        await fetchServerData(requestBody);
      } else if (selectedView === 'user' && selectedUserId) {
        await fetchUserData(requestBody);
      }
      
    } catch (error) {
      console.error('Error fetching data:', error);
      setApiError(error.message);
    } finally {
      setLoading(false);
      fetchedRef.current = true;
    }
  };

  // FIXED: fetchServerData
  const fetchServerData = async (requestBody) => {
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('server', currentServer.id, {
      ...requestBody,
      serverChartSort,
      serverLeaderboardSort,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setServerAllActivities(cached.serverAllActivities);
      setServerPlaying(cached.serverPlaying);
      setServerStreaming(cached.serverStreaming);
      setServerListening(cached.serverListening);
      setServerWatching(cached.serverWatching);
      setServerCompeting(cached.serverCompeting);
      setServerCustom(cached.serverCustom);
      setServerChartTimeSeries(cached.serverChartTimeSeries || []);
      setLoadingServerChart(false);
      setLoadingServerStats(false);
      return;
    }
    
    const getDaysValue = () => {
      if (requestBody.days) return requestBody.days;
      if (timePeriod === "all") return 2000;
      if (timePeriod === "custom-lookback" && customDaysBack) return parseInt(customDaysBack);
      if (timePeriod !== "custom-lookback" && timePeriod !== "custom-range") return parseInt(timePeriod);
      return 30;
    };
    
    const createCategoryRequestBody = (category) => {
      return {
        guild_id: requestBody.guild_id,
        category: category,
        days: getDaysValue(),
        sort_by: serverLeaderboardSort,
        role_filter_ids: requestBody.role_filter_ids,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      };
    };

    try {
      // ✅ FIXED: Use direct URLs for all endpoints
      const timeSeriesUrl = isPublic 
        ? `${API_BASE_URL}/api/public/activity/server/timeseries`
        : `${API_BASE_URL}/api/activity/server/timeseries`;
      
      const timeSeriesResponse = await fetch(timeSeriesUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify({
          guild_id: requestBody.guild_id,
          days: getDaysValue(),
          role_filter_ids: requestBody.role_filter_ids,
          start_time: requestBody.start_time,
          end_time: requestBody.end_time,
          limit: 100000000000
        })
      });

      let timeSeriesData = [];
      if (timeSeriesResponse.ok) {
        timeSeriesData = await timeSeriesResponse.json();
        setServerChartTimeSeries(timeSeriesData);
      }
      
      const allActivitiesUrl = isPublic 
        ? `${API_BASE_URL}/api/public/activity/server/top`
        : `${API_BASE_URL}/api/activity/server/top`;
      
      const allActivitiesResponse = await fetch(allActivitiesUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify({
          guild_id: requestBody.guild_id,
          days: getDaysValue(),
          sort_by: serverChartSort,
          role_filter_ids: requestBody.role_filter_ids,
          start_time: requestBody.start_time,
          end_time: requestBody.end_time
        })
      });

      let allActivities = [];
      if (allActivitiesResponse.ok) {
        const data = await allActivitiesResponse.json();
        allActivities = data.activities || [];
        setServerAllActivities(allActivities);
      }
      
      const categories = ['playing', 'streaming', 'listening', 'watching', 'competing', 'custom'];
      const categorySetters = {
        playing: setServerPlaying,
        streaming: setServerStreaming,
        listening: setServerListening,
        watching: setServerWatching,
        competing: setServerCompeting,
        custom: setServerCustom
      };
      
      for (const category of categories) {
        const url = isPublic 
          ? `${API_BASE_URL}/api/public/activity/server/${category}`
          : `${API_BASE_URL}/api/activity/server/${category}`;
        
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(createCategoryRequestBody(category))
        });
        
        if (response.ok) {
          const data = await response.json();
          categorySetters[category](data.activities || []);
        }
      }
      
      serverDataCache.set(cacheKey, {
        serverAllActivities: allActivities,
        serverPlaying: serverPlaying,
        serverStreaming: serverStreaming,
        serverListening: serverListening,
        serverWatching: serverWatching,
        serverCompeting: serverCompeting,
        serverCustom: serverCustom,
        serverChartTimeSeries: timeSeriesData
      });
      
    } catch (error) {
      console.error('Error in fetchServerData:', error);
    } finally {
      setLoadingServerChart(false);
      setLoadingServerStats(false);
    }
  };

  // FIXED: fetchUserData - Gets username using any-table endpoint
  const fetchUserData = async (requestBody) => {
    if (!selectedUserId) return;
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('user', selectedUserId, {
      ...requestBody,
      userChartSort,
      userLeaderboardSort,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setUserAllActivities(cached.userAllActivities);
      setUserPlaying(cached.userPlaying);
      setUserStreaming(cached.userStreaming);
      setUserListening(cached.userListening);
      setUserWatching(cached.userWatching);
      setUserCompeting(cached.userCompeting);
      setUserCustom(cached.userCustom);
      setUserChartTimeSeries(cached.userChartTimeSeries || []);
      setUserData(cached.userData);
      setLoadingUserChart(false);
      setLoadingUserStats(false);
      return;
    }
    
    // Get basic user info using any-table endpoint
    const userProfile = await fetchUserBasicInfo(selectedUserId, currentServer.id, isPublic);
    
    const getDaysValue = () => {
      if (requestBody.days) return requestBody.days;
      if (timePeriod === "all") return 2000;
      if (timePeriod === "custom-lookback" && customDaysBack) return parseInt(customDaysBack);
      if (timePeriod !== "custom-lookback" && timePeriod !== "custom-range") return parseInt(timePeriod);
      return 30;
    };
    
    const createUserCategoryRequestBody = (category) => {
      return {
        guild_id: requestBody.guild_id,
        user_id: selectedUserId,
        category: category,
        days: getDaysValue(),
        sort_by: userLeaderboardSort,
        role_filter_ids: requestBody.role_filter_ids,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      };
    };

    try {
      const timeSeriesUrl = isPublic 
        ? `${API_BASE_URL}/api/public/activity/user/timeseries`
        : `${API_BASE_URL}/api/activity/user/timeseries`;
      
      const timeSeriesResponse = await fetch(timeSeriesUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify({
          guild_id: requestBody.guild_id,
          user_id: selectedUserId,
          days: getDaysValue(),
          role_filter_ids: requestBody.role_filter_ids,
          start_time: requestBody.start_time,
          end_time: requestBody.end_time,
          limit: 100000000000
        })
      });

      let timeSeriesData = [];
      if (timeSeriesResponse.ok) {
        timeSeriesData = await timeSeriesResponse.json();
        setUserChartTimeSeries(timeSeriesData);
      }
      
      const allActivitiesUrl = isPublic 
        ? `${API_BASE_URL}/api/public/activity/user/top`
        : `${API_BASE_URL}/api/activity/user/top`;
      
      const allActivitiesResponse = await fetch(allActivitiesUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify({
          guild_id: requestBody.guild_id,
          user_id: selectedUserId,
          days: getDaysValue(),
          sort_by: userChartSort,
          role_filter_ids: requestBody.role_filter_ids,
          start_time: requestBody.start_time,
          end_time: requestBody.end_time
        })
      });

      let allActivities = [];
      if (allActivitiesResponse.ok) {
        const data = await allActivitiesResponse.json();
        allActivities = data.activities || [];
        setUserAllActivities(allActivities);
      }
      
      const categories = ['playing', 'streaming', 'listening', 'watching', 'competing', 'custom'];
      const categorySetters = {
        playing: setUserPlaying,
        streaming: setUserStreaming,
        listening: setUserListening,
        watching: setUserWatching,
        competing: setUserCompeting,
        custom: setUserCustom
      };
      
      for (const category of categories) {
        const url = isPublic 
          ? `${API_BASE_URL}/api/public/activity/user/${category}`
          : `${API_BASE_URL}/api/activity/user/${category}`;
        
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(createUserCategoryRequestBody(category))
        });
        
        if (response.ok) {
          const data = await response.json();
          categorySetters[category](data.activities || []);
        }
      }
      
      const userName = userProfile?.name || `User ${selectedUserId.slice(-4)}`;
      const userDataObj = {
        userId: selectedUserId,
        name: userName
      };
      setUserData(userDataObj);
      
      serverDataCache.set(cacheKey, {
        userAllActivities: allActivities,
        userPlaying: userPlaying,
        userStreaming: userStreaming,
        userListening: userListening,
        userWatching: userWatching,
        userCompeting: userCompeting,
        userCustom: userCustom,
        userChartTimeSeries: timeSeriesData,
        userData: userDataObj
      });
      
    } catch (error) {
      console.error('Error in fetchUserData:', error);
    } finally {
      setLoadingUserChart(false);
      setLoadingUserStats(false);
    }
  };

  const handleTempRoleSelect = (role) => {
    setTempRoleId(role.id);
    setTempRoleSearch(role.name || `Role ${role.id}`);
    setShowApplyButton(true);
    setShowRoleDropdown(false);
  };

  const applyRoleFilter = () => {
    setSelectedRoleId(tempRoleId);
    setRoleSearch(tempRoleSearch);
    setShowApplyButton(false);
    setShowRoleDropdown(false);
  };

  const clearRoleFilter = () => {
    setSelectedRoleId("");
    setRoleSearch("");
    setTempRoleId("");
    setTempRoleSearch("");
    setShowApplyButton(false);
  };

  const handleUserSelect = (user) => {
    setSelectedUserId(user.id);
    setUserSearch(user.global_name || user.username || user.name || `User ${user.id}`);
    setShowUserDropdown(false);
    fetchData();
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

  const sortOptions = [
    { value: 'time', label: 'Sort by Time' },
    { value: 'sessions', label: 'Sort by Sessions' }
  ];

  const serverSortOptions = [
    { value: 'time', label: 'Sort by Time' },
    { value: 'sessions', label: 'Sort by Sessions' },
    { value: 'users', label: 'Sort by Users' }
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
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    .navbar .logo span:last-child {
      font-family: 'Horndon', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
      font-weight: normal;
      letter-spacing: 0.5px;
    }

    html {
      min-height: 100%;
      background-color: #0a0a0a;
    }

    body {
      min-height: 100vh;
      margin: 0;
      padding: 0;
      background-color: #0a0a0a;
      color: #ffffff;
      overflow-y: auto;
    }

    #app {
      min-height: 100vh;
      background-color: #0a0a0a;
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
      min-height: calc(100vh - 80px);
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

    .entity-avatar {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      object-fit: cover;
    }

    .entity-name {
      font-weight: 500;
    }

    .entity-id {
      color: #888;
      font-size: 12px;
    }

    .entity-color-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
    }

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

    .chart-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 12px;
    }

    .chart-header h2 {
      color: #ffffff;
      font-size: 28px;
      font-weight: 600;
      margin: 0;
      position: relative;
      display: inline-block;
    }

    .chart-header h2::after {
      content: '';
      position: absolute;
      bottom: -8px;
      left: 0;
      width: 60px;
      height: 3px;
      background-color: #aa00ff;
      border-radius: 2px;
    }

    .chart-sort-select {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 10px 16px;
      font-size: 14px;
      cursor: pointer;
      outline: none;
      min-width: 150px;
      transition: all 0.2s ease;
      appearance: none;
      background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23aa00ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
      background-repeat: no-repeat;
      background-position: right 12px center;
      background-size: 14px;
    }

    .chart-sort-select:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .chart-wrapper {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
      transition: all 0.2s ease;
      min-height: 500px;
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

    .leaderboard-sort-select {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
      cursor: pointer;
      outline: none;
      min-width: 140px;
      transition: all 0.2s ease;
      appearance: none;
      background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23aa00ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
      background-repeat: no-repeat;
      background-position: right 10px center;
      background-size: 12px;
    }

    .leaderboard-sort-select:hover {
      border-color: #aa00ff;
      background-color: #222;
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

    .no-chart-data {
      color: #b0b0b0;
      font-size: 16px;
      text-align: center;
      padding: 100px;
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
      
      .chart-header {
        flex-direction: column;
        align-items: flex-start;
      }
      
      .leaderboard-header {
        flex-direction: column;
        align-items: flex-start;
      }
      
      .section-title {
        font-size: 24px;
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

  // Handle loading servers
  if (loadingServers && !currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            topOffset="80px"
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

  // Permission checking in progress
  if (hasAccess === null && isAuthenticated && currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            currentServerId={currentServer?.id}
            topOffset="80px"
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

  // Handle not authenticated but public mode - includes ALL leaderboards
  if (!isAuthenticated && isPublicMode) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            topOffset="80px"
            isPublicMode={true}
            publicGuildId={PUBLIC_GUILD_ID}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="public-banner">
                <p>Viewing statistics from the <strong>StatsHQ</strong> support server - <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server stats</p>
              </div>
              
              {/* Filters Section */}
              <div className="filters-section">
                <div className="filter-row">
                  <label>View:</label>
                  <select
                    value={selectedView}
                    onChange={(e) => {
                      setSelectedView(e.target.value);
                      if (e.target.value === 'server') {
                        setSelectedUserId("");
                        setUserSearch("");
                      }
                    }}
                    className="modern-select"
                  >
                    <option value="server">Server</option>
                    <option value="user">User</option>
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
                
                {/* Role Filter - Server View Only */}
                {selectedView === 'server' && (
                  <div className="filter-row entity-filter">
                    <label>Role Filter:</label>
                    <div className="entity-selector">
                      <input
                        type="text"
                        placeholder="Search role to filter users..."
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
                )}
                
                {/* User Selector - WITHOUT avatars */}
                {selectedView === 'user' && (
                  <div className="filter-row entity-filter">
                    <label>Select User:</label>
                    <div className="entity-selector">
                      <input
                        type="text"
                        placeholder="Search by name or ID..."
                        value={userSearch}
                        onChange={(e) => setUserSearch(e.target.value)}
                        onFocus={() => setShowUserDropdown(true)}
                        onBlur={() => setTimeout(() => setShowUserDropdown(false), 200)}
                        className="modern-entity-search"
                      />
                      {showUserDropdown && filteredUsers.length > 0 && (
                        <div className="entity-dropdown">
                          {filteredUsers.slice(0, 20).map(user => (
                            <div
                              key={user.id}
                              className={`entity-option ${selectedUserId === user.id ? 'selected' : ''}`}
                              onMouseDown={() => handleUserSelect(user)}
                            >
                              <div className="entity-info">
                                <span className="entity-name">{user.global_name || user.username || user.name || `User ${user.id}`}</span>
                              </div>
                              <span className="entity-id">ID: {user.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {showUserDropdown && filteredUsers.length === 0 && usersLoaded && (
                        <div className="entity-dropdown">
                          <div className="entity-option">
                            <span className="entity-name">No users found</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {/* Server View - Includes ALL activity leaderboards */}
              {selectedView === 'server' && (
                <>
                  <div className="charts-section">
                    <div className="chart-header">
                      <h2>Top Activities Over Time</h2>
                      <select
                        value={serverChartSort}
                        onChange={(e) => setServerChartSort(e.target.value)}
                        className="chart-sort-select"
                      >
                        {serverSortOptions.map(option => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    
                    <div className="chart-wrapper">
                      {loadingServerChart ? (
                        <LoadingChart />
                      ) : serverChartTimeSeries && serverChartTimeSeries.length > 0 ? (
                        (() => {
                          const activityNames = [...new Set(
                            serverChartTimeSeries.flatMap(point => 
                              point.activities.map(act => act.display_name)
                            )
                          )];
                          
                          const chartData = serverChartTimeSeries.map(point => {
                            const dataPoint = { date: point.date };
                            activityNames.forEach((name, index) => {
                              dataPoint[`activity_${index}`] = 0;
                            });
                            point.activities.forEach(act => {
                              const activityIndex = activityNames.indexOf(act.display_name);
                              if (activityIndex !== -1) {
                                let value = act.total_duration_seconds;
                                if (serverChartSort === "sessions") value = act.session_count;
                                else if (serverChartSort === "users") value = act.user_count;
                                dataPoint[`activity_${activityIndex}`] = value;
                              }
                            });
                            return dataPoint;
                          });
                          
                          const chartAvailableLines = activityNames.map((name, index) => ({
                            dataKey: `activity_${index}`,
                            name: name
                          }));
                          
                          return (
                            <EnhancedMultiLineChart
                              data={chartData}
                              availableLines={chartAvailableLines}
                              title={`Top Activities Over Time (sorted by ${serverChartSort})`}
                              valueFormatter={(value) => {
                                if (serverChartSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                            />
                          );
                        })()
                      ) : (
                        <div className="no-chart-data">
                          No activity data available {selectedRoleId ? 'with this role filter' : ''}
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <h2 className="section-title">Activity Leaderboards</h2>
                  <div className="leaderboards-stack">
                    {/* Playing Leaderboard */}
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header">
                        <h3>🎮 Playing Activities</h3>
                        <select
                          value={serverLeaderboardSort}
                          onChange={(e) => setServerLeaderboardSort(e.target.value)}
                          className="leaderboard-sort-select"
                        >
                          {serverSortOptions.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </div>
                      {loadingServerStats ? (
                        <LoadingSpinner size="medium" text="" />
                      ) : serverPlaying && serverPlaying.length > 0 ? (
                        <Leaderboard
                          data={serverPlaying.map(act => ({
                            id: act.display_name,
                            name: act.display_name,
                            value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds,
                            userCount: act.user_count,
                            sessionCount: act.session_count,
                            originalTime: act.total_duration_seconds
                          }))}
                          title=""
                          valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                          valueFormatter={(value) => {
                            if (serverLeaderboardSort === "time") return formatActivityValue(value);
                            else return value.toLocaleString();
                          }}
                          showProfilePictures={false}
                          itemType="activity"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#ff6b6b"
                          additionalInfo={(item) => {
                            const info = [];
                            if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                            if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                            if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`);
                            return info;
                          }}
                        />
                      ) : (
                        <div className="no-data-message">No playing activities {selectedRoleId ? 'with this role filter' : ''}</div>
                      )}
                    </div>
                    
                    {/* Streaming Leaderboard */}
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header">
                        <h3>📺 Streaming Activities</h3>
                      </div>
                      {loadingServerStats ? (
                        <LoadingSpinner size="medium" text="" />
                      ) : serverStreaming && serverStreaming.length > 0 ? (
                        <Leaderboard
                          data={serverStreaming.map(act => ({
                            id: act.display_name,
                            name: act.display_name,
                            value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds,
                            userCount: act.user_count,
                            sessionCount: act.session_count,
                            originalTime: act.total_duration_seconds
                          }))}
                          title=""
                          valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                          valueFormatter={(value) => {
                            if (serverLeaderboardSort === "time") return formatActivityValue(value);
                            else return value.toLocaleString();
                          }}
                          showProfilePictures={false}
                          itemType="activity"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#4ecdc4"
                          additionalInfo={(item) => {
                            const info = [];
                            if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                            if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                            if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`);
                            return info;
                          }}
                        />
                      ) : (
                        <div className="no-data-message">No streaming activities {selectedRoleId ? 'with this role filter' : ''}</div>
                      )}
                    </div>
                    
                    {/* Listening Leaderboard */}
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header">
                        <h3>🎧 Listening Activities</h3>
                      </div>
                      {loadingServerStats ? (
                        <LoadingSpinner size="medium" text="" />
                      ) : serverListening && serverListening.length > 0 ? (
                        <Leaderboard
                          data={serverListening.map(act => ({
                            id: act.display_name,
                            name: act.display_name,
                            value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds,
                            userCount: act.user_count,
                            sessionCount: act.session_count,
                            originalTime: act.total_duration_seconds
                          }))}
                          title=""
                          valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                          valueFormatter={(value) => {
                            if (serverLeaderboardSort === "time") return formatActivityValue(value);
                            else return value.toLocaleString();
                          }}
                          showProfilePictures={false}
                          itemType="activity"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#ffe66d"
                          additionalInfo={(item) => {
                            const info = [];
                            if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                            if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                            if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`);
                            return info;
                          }}
                        />
                      ) : (
                        <div className="no-data-message">No listening activities {selectedRoleId ? 'with this role filter' : ''}</div>
                      )}
                    </div>
                    
                    {/* Watching Leaderboard */}
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header">
                        <h3>👀 Watching Activities</h3>
                      </div>
                      {loadingServerStats ? (
                        <LoadingSpinner size="medium" text="" />
                      ) : serverWatching && serverWatching.length > 0 ? (
                        <Leaderboard
                          data={serverWatching.map(act => ({
                            id: act.display_name,
                            name: act.display_name,
                            value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds,
                            userCount: act.user_count,
                            sessionCount: act.session_count,
                            originalTime: act.total_duration_seconds
                          }))}
                          title=""
                          valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                          valueFormatter={(value) => {
                            if (serverLeaderboardSort === "time") return formatActivityValue(value);
                            else return value.toLocaleString();
                          }}
                          showProfilePictures={false}
                          itemType="activity"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#c3447a"
                          additionalInfo={(item) => {
                            const info = [];
                            if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                            if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                            if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`);
                            return info;
                          }}
                        />
                      ) : (
                        <div className="no-data-message">No watching activities {selectedRoleId ? 'with this role filter' : ''}</div>
                      )}
                    </div>
                    
                    {/* Competing Leaderboard */}
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header">
                        <h3>🏆 Competing Activities</h3>
                      </div>
                      {loadingServerStats ? (
                        <LoadingSpinner size="medium" text="" />
                      ) : serverCompeting && serverCompeting.length > 0 ? (
                        <Leaderboard
                          data={serverCompeting.map(act => ({
                            id: act.display_name,
                            name: act.display_name,
                            value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds,
                            userCount: act.user_count,
                            sessionCount: act.session_count,
                            originalTime: act.total_duration_seconds
                          }))}
                          title=""
                          valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                          valueFormatter={(value) => {
                            if (serverLeaderboardSort === "time") return formatActivityValue(value);
                            else return value.toLocaleString();
                          }}
                          showProfilePictures={false}
                          itemType="activity"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#6c5ce7"
                          additionalInfo={(item) => {
                            const info = [];
                            if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                            if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                            if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`);
                            return info;
                          }}
                        />
                      ) : (
                        <div className="no-data-message">No competing activities {selectedRoleId ? 'with this role filter' : ''}</div>
                      )}
                    </div>
                    
                    {/* Custom Leaderboard */}
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header">
                        <h3>✨ Custom Activities</h3>
                      </div>
                      {loadingServerStats ? (
                        <LoadingSpinner size="medium" text="" />
                      ) : serverCustom && serverCustom.length > 0 ? (
                        <Leaderboard
                          data={serverCustom.map(act => ({
                            id: act.display_name,
                            name: act.display_name,
                            value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds,
                            userCount: act.user_count,
                            sessionCount: act.session_count,
                            originalTime: act.total_duration_seconds
                          }))}
                          title=""
                          valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                          valueFormatter={(value) => {
                            if (serverLeaderboardSort === "time") return formatActivityValue(value);
                            else return value.toLocaleString();
                          }}
                          showProfilePictures={false}
                          itemType="activity"
                          backgroundColor="transparent"
                          cardBackground="#1a1a1a"
                          accentColor="#00b894"
                          additionalInfo={(item) => {
                            const info = [];
                            if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                            if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                            if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`);
                            return info;
                          }}
                        />
                      ) : (
                        <div className="no-data-message">No custom activities {selectedRoleId ? 'with this role filter' : ''}</div>
                      )}
                    </div>
                  </div>
                </>
              )}
              
              {/* User View - Includes ALL user activity leaderboards */}
              {selectedView === 'user' && (
                <>
                  {!selectedUserId ? (
                    <div className="no-selection">
                      <h2>Select a User</h2>
                      <p>Please select a user from the dropdown above to view their activity statistics.</p>
                    </div>
                  ) : (
                    <>
                      <div className="charts-section">
                        <div className="chart-header">
                          <h2>{userData?.name || 'User'}'s Activities Over Time</h2>
                          <select
                            value={userChartSort}
                            onChange={(e) => setUserChartSort(e.target.value)}
                            className="chart-sort-select"
                          >
                            {sortOptions.map(option => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </div>
                        
                        <div className="chart-wrapper">
                          {loadingUserChart ? (
                            <LoadingChart />
                          ) : userChartTimeSeries && userChartTimeSeries.length > 0 ? (
                            (() => {
                              const activityNames = [...new Set(
                                userChartTimeSeries.flatMap(point => 
                                  point.activities.map(act => act.display_name)
                                )
                              )];
                              
                              const chartData = userChartTimeSeries.map(point => {
                                const dataPoint = { date: point.date };
                                activityNames.forEach((name, index) => {
                                  dataPoint[`activity_${index}`] = 0;
                                });
                                point.activities.forEach(act => {
                                  const activityIndex = activityNames.indexOf(act.display_name);
                                  if (activityIndex !== -1) {
                                    let value = act.total_duration_seconds;
                                    if (userChartSort === "sessions") value = act.session_count;
                                    dataPoint[`activity_${activityIndex}`] = value;
                                  }
                                });
                                return dataPoint;
                              });
                              
                              const chartAvailableLines = activityNames.map((name, index) => ({
                                dataKey: `activity_${index}`,
                                name: name
                              }));
                              
                              return (
                                <EnhancedMultiLineChart
                                  data={chartData}
                                  availableLines={chartAvailableLines}
                                  title={`${userData?.name || 'User'}'s Top Activities Over Time (sorted by ${userChartSort})`}
                                  valueFormatter={(value) => {
                                    if (userChartSort === "time") return formatActivityValue(value);
                                    else return value.toLocaleString();
                                  }}
                                />
                              );
                            })()
                          ) : (
                            <div className="no-chart-data">No activity data available for this user</div>
                          )}
                        </div>
                      </div>
                      
                      <h2 className="section-title">{userData?.name || 'User'}'s Activity Leaderboards</h2>
                      <div className="leaderboards-stack">
                        {/* User Playing Leaderboard */}
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>🎮 Playing Activities</h3>
                            <select
                              value={userLeaderboardSort}
                              onChange={(e) => setUserLeaderboardSort(e.target.value)}
                              className="leaderboard-sort-select"
                            >
                              {sortOptions.map(option => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                              ))}
                            </select>
                          </div>
                          {loadingUserStats ? (
                            <LoadingSpinner size="medium" text="" />
                          ) : userPlaying && userPlaying.length > 0 ? (
                            <Leaderboard
                              data={userPlaying.map(act => ({
                                id: act.display_name,
                                name: act.display_name,
                                value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds,
                                sessionCount: act.session_count,
                                originalTime: act.total_duration_seconds
                              }))}
                              title=""
                              valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                              valueFormatter={(value) => {
                                if (userLeaderboardSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                              showProfilePictures={false}
                              itemType="activity"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#ff6b6b"
                              additionalInfo={(item) => {
                                const info = [];
                                if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                                if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                                return info;
                              }}
                            />
                          ) : (
                            <div className="no-data-message">No playing activities for this user</div>
                          )}
                        </div>
                        
                        {/* User Streaming Leaderboard */}
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>📺 Streaming Activities</h3>
                          </div>
                          {loadingUserStats ? (
                            <LoadingSpinner size="medium" text="" />
                          ) : userStreaming && userStreaming.length > 0 ? (
                            <Leaderboard
                              data={userStreaming.map(act => ({
                                id: act.display_name,
                                name: act.display_name,
                                value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds,
                                sessionCount: act.session_count,
                                originalTime: act.total_duration_seconds
                              }))}
                              title=""
                              valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                              valueFormatter={(value) => {
                                if (userLeaderboardSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                              showProfilePictures={false}
                              itemType="activity"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#4ecdc4"
                              additionalInfo={(item) => {
                                const info = [];
                                if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                                if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                                return info;
                              }}
                            />
                          ) : (
                            <div className="no-data-message">No streaming activities for this user</div>
                          )}
                        </div>
                        
                        {/* User Listening Leaderboard */}
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>🎧 Listening Activities</h3>
                          </div>
                          {loadingUserStats ? (
                            <LoadingSpinner size="medium" text="" />
                          ) : userListening && userListening.length > 0 ? (
                            <Leaderboard
                              data={userListening.map(act => ({
                                id: act.display_name,
                                name: act.display_name,
                                value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds,
                                sessionCount: act.session_count,
                                originalTime: act.total_duration_seconds
                              }))}
                              title=""
                              valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                              valueFormatter={(value) => {
                                if (userLeaderboardSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                              showProfilePictures={false}
                              itemType="activity"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#ffe66d"
                              additionalInfo={(item) => {
                                const info = [];
                                if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                                if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                                return info;
                              }}
                            />
                          ) : (
                            <div className="no-data-message">No listening activities for this user</div>
                          )}
                        </div>
                        
                        {/* User Watching Leaderboard */}
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>👀 Watching Activities</h3>
                          </div>
                          {loadingUserStats ? (
                            <LoadingSpinner size="medium" text="" />
                          ) : userWatching && userWatching.length > 0 ? (
                            <Leaderboard
                              data={userWatching.map(act => ({
                                id: act.display_name,
                                name: act.display_name,
                                value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds,
                                sessionCount: act.session_count,
                                originalTime: act.total_duration_seconds
                              }))}
                              title=""
                              valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                              valueFormatter={(value) => {
                                if (userLeaderboardSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                              showProfilePictures={false}
                              itemType="activity"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#c3447a"
                              additionalInfo={(item) => {
                                const info = [];
                                if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                                if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                                return info;
                              }}
                            />
                          ) : (
                            <div className="no-data-message">No watching activities for this user</div>
                          )}
                        </div>
                        
                        {/* User Competing Leaderboard */}
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>🏆 Competing Activities</h3>
                          </div>
                          {loadingUserStats ? (
                            <LoadingSpinner size="medium" text="" />
                          ) : userCompeting && userCompeting.length > 0 ? (
                            <Leaderboard
                              data={userCompeting.map(act => ({
                                id: act.display_name,
                                name: act.display_name,
                                value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds,
                                sessionCount: act.session_count,
                                originalTime: act.total_duration_seconds
                              }))}
                              title=""
                              valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                              valueFormatter={(value) => {
                                if (userLeaderboardSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                              showProfilePictures={false}
                              itemType="activity"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#6c5ce7"
                              additionalInfo={(item) => {
                                const info = [];
                                if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                                if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                                return info;
                              }}
                            />
                          ) : (
                            <div className="no-data-message">No competing activities for this user</div>
                          )}
                        </div>
                        
                        {/* User Custom Leaderboard */}
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header">
                            <h3>✨ Custom Activities</h3>
                          </div>
                          {loadingUserStats ? (
                            <LoadingSpinner size="medium" text="" />
                          ) : userCustom && userCustom.length > 0 ? (
                            <Leaderboard
                              data={userCustom.map(act => ({
                                id: act.display_name,
                                name: act.display_name,
                                value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds,
                                sessionCount: act.session_count,
                                originalTime: act.total_duration_seconds
                              }))}
                              title=""
                              valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                              valueFormatter={(value) => {
                                if (userLeaderboardSort === "time") return formatActivityValue(value);
                                else return value.toLocaleString();
                              }}
                              showProfilePictures={false}
                              itemType="activity"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#00b894"
                              additionalInfo={(item) => {
                                const info = [];
                                if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`);
                                if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`);
                                return info;
                              }}
                            />
                          ) : (
                            <div className="no-data-message">No custom activities for this user</div>
                          )}
                        </div>
                      </div>
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

  // Handle authenticated but no access
  if (isAuthenticated && currentServer && !hasAccess) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            currentServerId={currentServer?.id} 
            topOffset="80px"
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

  // Handle no server available
  if (!loadingServers && !currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset="80px" />
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

  // Handle error
  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar 
            currentServerId={currentServer?.id} 
            topOffset="80px"
            isPublicMode={isPublicMode}
          />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => fetchData()} className="retry-button">
                  Retry
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

  // Authenticated user with access - full dashboard with ALL leaderboards
  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar 
          currentServerId={currentServer?.id} 
          topOffset="80px"
          isPublicMode={false}
        />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            <div className="filters-section">
              <div className="filter-row">
                <label>View:</label>
                <select
                  value={selectedView}
                  onChange={(e) => {
                    setSelectedView(e.target.value);
                    if (e.target.value === 'server') {
                      setSelectedUserId("");
                      setUserSearch("");
                    }
                  }}
                  className="modern-select"
                >
                  <option value="server">Server</option>
                  <option value="user">User</option>
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
              
              {/* Role Filter - Server View Only */}
              {selectedView === 'server' && (
                <div className="filter-row entity-filter">
                  <label>Role Filter:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search role to filter users..."
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
                        <button className="apply-button" onClick={applyRoleFilter}>Apply Role Filter</button>
                        <button className="clear-button" onClick={clearRoleFilter}>Clear</button>
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
              )}
              
              {/* User Selector - WITHOUT avatars */}
              {selectedView === 'user' && (
                <div className="filter-row entity-filter">
                  <label>Select User:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search by name or ID..."
                      value={userSearch}
                      onChange={(e) => setUserSearch(e.target.value)}
                      onFocus={() => setShowUserDropdown(true)}
                      onBlur={() => setTimeout(() => setShowUserDropdown(false), 200)}
                      className="modern-entity-search"
                    />
                    {showUserDropdown && filteredUsers.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredUsers.slice(0, 20).map(user => (
                          <div
                            key={user.id}
                            className={`entity-option ${selectedUserId === user.id ? 'selected' : ''}`}
                            onMouseDown={() => handleUserSelect(user)}
                          >
                            <div className="entity-info">
                              <span className="entity-name">{user.global_name || user.username || user.name || `User ${user.id}`}</span>
                            </div>
                            <span className="entity-id">ID: {user.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {showUserDropdown && filteredUsers.length === 0 && usersLoaded && (
                      <div className="entity-dropdown">
                        <div className="entity-option">
                          <span className="entity-name">No users found</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            
            {/* Server View - Includes ALL activity leaderboards */}
            {selectedView === 'server' && (
              <>
                <div className="charts-section">
                  <div className="chart-header">
                    <h2>Top Activities Over Time</h2>
                    <select value={serverChartSort} onChange={(e) => setServerChartSort(e.target.value)} className="chart-sort-select">
                      {serverSortOptions.map(option => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div className="chart-wrapper">
                    {loadingServerChart ? (
                      <LoadingChart />
                    ) : serverChartTimeSeries && serverChartTimeSeries.length > 0 ? (
                      (() => {
                        const activityNames = [...new Set(serverChartTimeSeries.flatMap(point => point.activities.map(act => act.display_name)))];
                        const chartData = serverChartTimeSeries.map(point => {
                          const dataPoint = { date: point.date };
                          activityNames.forEach((name, index) => { dataPoint[`activity_${index}`] = 0; });
                          point.activities.forEach(act => {
                            const activityIndex = activityNames.indexOf(act.display_name);
                            if (activityIndex !== -1) {
                              let value = act.total_duration_seconds;
                              if (serverChartSort === "sessions") value = act.session_count;
                              else if (serverChartSort === "users") value = act.user_count;
                              dataPoint[`activity_${activityIndex}`] = value;
                            }
                          });
                          return dataPoint;
                        });
                        const chartAvailableLines = activityNames.map((name, index) => ({ dataKey: `activity_${index}`, name: name }));
                        return (
                          <EnhancedMultiLineChart
                            data={chartData}
                            availableLines={chartAvailableLines}
                            title={`Top Activities Over Time (sorted by ${serverChartSort})`}
                            valueFormatter={(value) => serverChartSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                          />
                        );
                      })()
                    ) : (
                      <div className="no-chart-data">No activity data available {selectedRoleId ? 'with this role filter' : ''}</div>
                    )}
                  </div>
                </div>
                
                <h2 className="section-title">Activity Leaderboards</h2>
                <div className="leaderboards-stack">
                  {/* Playing Leaderboard */}
                  <div className="leaderboard-wrapper">
                    <div className="leaderboard-header">
                      <h3>🎮 Playing Activities</h3>
                      <select value={serverLeaderboardSort} onChange={(e) => setServerLeaderboardSort(e.target.value)} className="leaderboard-sort-select">
                        {serverSortOptions.map(option => (<option key={option.value} value={option.value}>{option.label}</option>))}
                      </select>
                    </div>
                    {loadingServerStats ? <LoadingSpinner size="medium" text="" /> : serverPlaying && serverPlaying.length > 0 ? (
                      <Leaderboard
                        data={serverPlaying.map(act => ({ id: act.display_name, name: act.display_name, value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds, userCount: act.user_count, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                        title="" valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                        valueFormatter={(value) => serverLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                        showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#ff6b6b"
                        additionalInfo={(item) => { const info = []; if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`); return info; }}
                      />
                    ) : (<div className="no-data-message">No playing activities {selectedRoleId ? 'with this role filter' : ''}</div>)}
                  </div>
                  
                  {/* Streaming Leaderboard */}
                  <div className="leaderboard-wrapper">
                    <div className="leaderboard-header">
                      <h3>📺 Streaming Activities</h3>
                    </div>
                    {loadingServerStats ? <LoadingSpinner size="medium" text="" /> : serverStreaming && serverStreaming.length > 0 ? (
                      <Leaderboard
                        data={serverStreaming.map(act => ({ id: act.display_name, name: act.display_name, value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds, userCount: act.user_count, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                        title="" valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                        valueFormatter={(value) => serverLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                        showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#4ecdc4"
                        additionalInfo={(item) => { const info = []; if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`); return info; }}
                      />
                    ) : (<div className="no-data-message">No streaming activities {selectedRoleId ? 'with this role filter' : ''}</div>)}
                  </div>
                  
                  {/* Listening Leaderboard */}
                  <div className="leaderboard-wrapper">
                    <div className="leaderboard-header">
                      <h3>🎧 Listening Activities</h3>
                    </div>
                    {loadingServerStats ? <LoadingSpinner size="medium" text="" /> : serverListening && serverListening.length > 0 ? (
                      <Leaderboard
                        data={serverListening.map(act => ({ id: act.display_name, name: act.display_name, value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds, userCount: act.user_count, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                        title="" valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                        valueFormatter={(value) => serverLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                        showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#ffe66d"
                        additionalInfo={(item) => { const info = []; if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`); return info; }}
                      />
                    ) : (<div className="no-data-message">No listening activities {selectedRoleId ? 'with this role filter' : ''}</div>)}
                  </div>
                  
                  {/* Watching Leaderboard */}
                  <div className="leaderboard-wrapper">
                    <div className="leaderboard-header">
                      <h3>👀 Watching Activities</h3>
                    </div>
                    {loadingServerStats ? <LoadingSpinner size="medium" text="" /> : serverWatching && serverWatching.length > 0 ? (
                      <Leaderboard
                        data={serverWatching.map(act => ({ id: act.display_name, name: act.display_name, value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds, userCount: act.user_count, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                        title="" valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                        valueFormatter={(value) => serverLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                        showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#c3447a"
                        additionalInfo={(item) => { const info = []; if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`); return info; }}
                      />
                    ) : (<div className="no-data-message">No watching activities {selectedRoleId ? 'with this role filter' : ''}</div>)}
                  </div>
                  
                  {/* Competing Leaderboard */}
                  <div className="leaderboard-wrapper">
                    <div className="leaderboard-header">
                      <h3>🏆 Competing Activities</h3>
                    </div>
                    {loadingServerStats ? <LoadingSpinner size="medium" text="" /> : serverCompeting && serverCompeting.length > 0 ? (
                      <Leaderboard
                        data={serverCompeting.map(act => ({ id: act.display_name, name: act.display_name, value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds, userCount: act.user_count, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                        title="" valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                        valueFormatter={(value) => serverLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                        showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#6c5ce7"
                        additionalInfo={(item) => { const info = []; if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`); return info; }}
                      />
                    ) : (<div className="no-data-message">No competing activities {selectedRoleId ? 'with this role filter' : ''}</div>)}
                  </div>
                  
                  {/* Custom Leaderboard */}
                  <div className="leaderboard-wrapper">
                    <div className="leaderboard-header">
                      <h3>✨ Custom Activities</h3>
                    </div>
                    {loadingServerStats ? <LoadingSpinner size="medium" text="" /> : serverCustom && serverCustom.length > 0 ? (
                      <Leaderboard
                        data={serverCustom.map(act => ({ id: act.display_name, name: act.display_name, value: serverLeaderboardSort === "sessions" ? act.session_count : serverLeaderboardSort === "users" ? act.user_count : act.total_duration_seconds, userCount: act.user_count, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                        title="" valueLabel={serverLeaderboardSort === "sessions" ? "Sessions" : serverLeaderboardSort === "users" ? "Users" : "Time"}
                        valueFormatter={(value) => serverLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                        showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#00b894"
                        additionalInfo={(item) => { const info = []; if (serverLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (serverLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); if (serverLeaderboardSort !== "users") info.push(`${item.userCount || 0} users`); return info; }}
                      />
                    ) : (<div className="no-data-message">No custom activities {selectedRoleId ? 'with this role filter' : ''}</div>)}
                  </div>
                </div>
              </>
            )}
            
            {/* User View - Includes ALL user activity leaderboards */}
            {selectedView === 'user' && (
              <>
                {!selectedUserId ? (
                  <div className="no-selection"><h2>Select a User</h2><p>Please select a user from the dropdown above to view their activity statistics.</p></div>
                ) : (
                  <>
                    <div className="charts-section">
                      <div className="chart-header">
                        <h2>{userData?.name || 'User'}'s Activities Over Time</h2>
                        <select value={userChartSort} onChange={(e) => setUserChartSort(e.target.value)} className="chart-sort-select">
                          {sortOptions.map(option => (<option key={option.value} value={option.value}>{option.label}</option>))}
                        </select>
                      </div>
                      <div className="chart-wrapper">
                        {loadingUserChart ? <LoadingChart /> : userChartTimeSeries && userChartTimeSeries.length > 0 ? (
                          (() => {
                            const activityNames = [...new Set(userChartTimeSeries.flatMap(point => point.activities.map(act => act.display_name)))];
                            const chartData = userChartTimeSeries.map(point => {
                              const dataPoint = { date: point.date };
                              activityNames.forEach((name, index) => { dataPoint[`activity_${index}`] = 0; });
                              point.activities.forEach(act => {
                                const activityIndex = activityNames.indexOf(act.display_name);
                                if (activityIndex !== -1) {
                                  let value = act.total_duration_seconds;
                                  if (userChartSort === "sessions") value = act.session_count;
                                  dataPoint[`activity_${activityIndex}`] = value;
                                }
                              });
                              return dataPoint;
                            });
                            const chartAvailableLines = activityNames.map((name, index) => ({ dataKey: `activity_${index}`, name: name }));
                            return (<EnhancedMultiLineChart data={chartData} availableLines={chartAvailableLines} title={`${userData?.name || 'User'}'s Top Activities Over Time (sorted by ${userChartSort})`} valueFormatter={(value) => userChartSort === "time" ? formatActivityValue(value) : value.toLocaleString()} />);
                          })()
                        ) : (<div className="no-chart-data">No activity data available for this user</div>)}
                      </div>
                    </div>
                    
                    <h2 className="section-title">{userData?.name || 'User'}'s Activity Leaderboards</h2>
                    <div className="leaderboards-stack">
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>🎮 Playing Activities</h3>
                          <select value={userLeaderboardSort} onChange={(e) => setUserLeaderboardSort(e.target.value)} className="leaderboard-sort-select">
                            {sortOptions.map(option => (<option key={option.value} value={option.value}>{option.label}</option>))}
                          </select>
                        </div>
                        {loadingUserStats ? <LoadingSpinner size="medium" text="" /> : userPlaying && userPlaying.length > 0 ? (
                          <Leaderboard
                            data={userPlaying.map(act => ({ id: act.display_name, name: act.display_name, value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                            title="" valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                            valueFormatter={(value) => userLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                            showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#ff6b6b"
                            additionalInfo={(item) => { const info = []; if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); return info; }}
                          />
                        ) : (<div className="no-data-message">No playing activities for this user</div>)}
                      </div>
                      
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>📺 Streaming Activities</h3>
                        </div>
                        {loadingUserStats ? <LoadingSpinner size="medium" text="" /> : userStreaming && userStreaming.length > 0 ? (
                          <Leaderboard
                            data={userStreaming.map(act => ({ id: act.display_name, name: act.display_name, value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                            title="" valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                            valueFormatter={(value) => userLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                            showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#4ecdc4"
                            additionalInfo={(item) => { const info = []; if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); return info; }}
                          />
                        ) : (<div className="no-data-message">No streaming activities for this user</div>)}
                      </div>
                      
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>🎧 Listening Activities</h3>
                        </div>
                        {loadingUserStats ? <LoadingSpinner size="medium" text="" /> : userListening && userListening.length > 0 ? (
                          <Leaderboard
                            data={userListening.map(act => ({ id: act.display_name, name: act.display_name, value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                            title="" valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                            valueFormatter={(value) => userLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                            showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#ffe66d"
                            additionalInfo={(item) => { const info = []; if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); return info; }}
                          />
                        ) : (<div className="no-data-message">No listening activities for this user</div>)}
                      </div>
                      
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>👀 Watching Activities</h3>
                        </div>
                        {loadingUserStats ? <LoadingSpinner size="medium" text="" /> : userWatching && userWatching.length > 0 ? (
                          <Leaderboard
                            data={userWatching.map(act => ({ id: act.display_name, name: act.display_name, value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                            title="" valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                            valueFormatter={(value) => userLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                            showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#c3447a"
                            additionalInfo={(item) => { const info = []; if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); return info; }}
                          />
                        ) : (<div className="no-data-message">No watching activities for this user</div>)}
                      </div>
                      
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>🏆 Competing Activities</h3>
                        </div>
                        {loadingUserStats ? <LoadingSpinner size="medium" text="" /> : userCompeting && userCompeting.length > 0 ? (
                          <Leaderboard
                            data={userCompeting.map(act => ({ id: act.display_name, name: act.display_name, value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                            title="" valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                            valueFormatter={(value) => userLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                            showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#6c5ce7"
                            additionalInfo={(item) => { const info = []; if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); return info; }}
                          />
                        ) : (<div className="no-data-message">No competing activities for this user</div>)}
                      </div>
                      
                      <div className="leaderboard-wrapper">
                        <div className="leaderboard-header">
                          <h3>✨ Custom Activities</h3>
                        </div>
                        {loadingUserStats ? <LoadingSpinner size="medium" text="" /> : userCustom && userCustom.length > 0 ? (
                          <Leaderboard
                            data={userCustom.map(act => ({ id: act.display_name, name: act.display_name, value: userLeaderboardSort === "sessions" ? act.session_count : act.total_duration_seconds, sessionCount: act.session_count, originalTime: act.total_duration_seconds }))}
                            title="" valueLabel={userLeaderboardSort === "sessions" ? "Sessions" : "Time"}
                            valueFormatter={(value) => userLeaderboardSort === "time" ? formatActivityValue(value) : value.toLocaleString()}
                            showProfilePictures={false} itemType="activity" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#00b894"
                            additionalInfo={(item) => { const info = []; if (userLeaderboardSort !== "time") info.push(`Time: ${formatActivityValue(item.originalTime)}`); if (userLeaderboardSort !== "sessions") info.push(`${item.sessionCount || 0} sessions`); return info; }}
                          />
                        ) : (<div className="no-data-message">No custom activities for this user</div>)}
                      </div>
                    </div>
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
    <ActivityDashboard />
  </React.StrictMode>
);

export default ActivityDashboard;