import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import Leaderboard from "../../../Components/Leaderboard.jsx";
import TimezonePieChart from "../../../Components/PieChart.jsx";
import InteractiveLineChart from "../../../Components/Charts.jsx";

// API base URL - your FastAPI backend
const API_BASE_URL = '';

// PUBLIC GUILD ID for unauthenticated users
const PUBLIC_GUILD_ID = '1424021358680998022';

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// Simple cache for user profiles with size limit
class ProfileCache {
  constructor(maxSize = 1000) {
    this.cache = new Map();
    this.maxSize = maxSize;
  }

  get(key) {
    const value = this.cache.get(key);
    if (value) {
      // Only return if it has a valid name (not a fallback)
      if (value.name && !value.name.startsWith('User ')) {
        this.cache.delete(key);
        this.cache.set(key, value);
        return value;
      }
      // Remove invalid cache entries
      this.cache.delete(key);
      return null;
    }
    return null;
  }

  set(key, value) {
    // Only cache if it has a valid name
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

// Cache for user basic info (usernames without avatars)
const userBasicInfoCache = new Map();

// Cache key generator
const getCacheKey = (type, id, params) => {
  return `${type}:${id}:${JSON.stringify(params)}`;
};

// Helper function to build URL with query parameters
const buildUrl = (baseUrl, params) => {
  const url = new URL(baseUrl, window.location.origin);
  Object.keys(params).forEach(key => {
    if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
      if (key === 'role_filter_ids' && Array.isArray(params[key]) && params[key].length > 0) {
        url.searchParams.append(key, params[key].join(','));
      } else if (Array.isArray(params[key])) {
        if (params[key].length > 0) {
          url.searchParams.append(key, params[key].join(','));
        }
      } else if (params[key] !== null && params[key] !== undefined) {
        url.searchParams.append(key, params[key]);
      }
    }
  });
  return url.toString();
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

const LoadingCard = () => (
  <div className="leaderboard-wrapper">
    <LoadingSpinner size="medium" text="Loading data..." />
  </div>
);

const AccessDenied = () => (
  <div className="no-selection">
    <h2>🔒 Access Denied</h2>
    <p>You don't have permission to view this server's statistics.</p>
    <p>This server requires <strong>{
      (window.accessLevel === 'Admin') ? 'Administrator' : 
      (window.accessLevel === 'Moderator') ? 'Manage Server or Administrator' : 
      'being a server member'
    }</strong> permissions.</p>
  </div>
);

const VoiceDashboard = () => {
  const [selectedView, setSelectedView] = useState("server");
  const [timePeriod, setTimePeriod] = useState("30");
  const [customDaysBack, setCustomDaysBack] = useState("");
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [channelSearch, setChannelSearch] = useState("");
  const [categorySearch, setCategorySearch] = useState("");
  const [roleSearch, setRoleSearch] = useState("");
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false);
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  
  const [tempRoleId, setTempRoleId] = useState("");
  const [tempRoleSearch, setTempRoleSearch] = useState("");
  const [showApplyButton, setShowApplyButton] = useState(false);
  
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [channels, setChannels] = useState([]);
  const [filteredChannels, setFilteredChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [filteredCategories, setFilteredCategories] = useState([]);
  const [roles, setRoles] = useState([]);
  const [filteredRoles, setFilteredRoles] = useState([]);
  
  const [loading, setLoading] = useState(true);
  const [serverData, setServerData] = useState(null);
  const [userData, setUserData] = useState(null);
  const [channelData, setChannelData] = useState(null);
  const [categoryData, setCategoryData] = useState(null);
  const [currentServer, setCurrentServer] = useState(null);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [isPublicMode, setIsPublicMode] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [currentUserId, setCurrentUserId] = useState(null);
  const [serverTimezone, setServerTimezone] = useState('UTC');
  
  const [loadingTopUsers, setLoadingTopUsers] = useState(true);
  const [loadingTopChannels, setLoadingTopChannels] = useState(true);
  const [loadingTopCategories, setLoadingTopCategories] = useState(true);
  const [loadingUserTopChannels, setLoadingUserTopChannels] = useState(true);
  const [loadingUserTopCategories, setLoadingUserTopCategories] = useState(true);
  const [loadingChannelTopUsers, setLoadingChannelTopUsers] = useState(true);
  const [loadingCategoryTopUsers, setLoadingCategoryTopUsers] = useState(true);
  const [loadingCategoryTopChannels, setLoadingCategoryTopChannels] = useState(true);
  const [loadingHourlyDistribution, setLoadingHourlyDistribution] = useState(true);
  const [loadingUserHourlyDistribution, setLoadingUserHourlyDistribution] = useState(true);
  const [loadingSummaryStats, setLoadingSummaryStats] = useState(true);
  const [loadingAverages, setLoadingAverages] = useState(true);
  const [loadingTimeseries, setLoadingTimeseries] = useState(true);
  const [loadingUserTimeseries, setLoadingUserTimeseries] = useState(true);
  const [loadingChannelTimeseries, setLoadingChannelTimeseries] = useState(true);
  const [loadingCategoryTimeseries, setLoadingCategoryTimeseries] = useState(true);
  
  const [averagesData, setAveragesData] = useState({
    avgPerUser: 0,
    avgPerDay: 0,
    avgPerMonth: 0,
    avgPerYear: 0,
    daysInPeriod: 0
  });
  
  const [timeseriesData, setTimeseriesData] = useState([]);
  const [userTimeseriesData, setUserTimeseriesData] = useState([]);
  const [channelTimeseriesData, setChannelTimeseriesData] = useState([]);
  const [categoryTimeseriesData, setCategoryTimeseriesData] = useState([]);
  
  const [topUsers, setTopUsers] = useState([]);
  const [topChannels, setTopChannels] = useState([]);
  const [topCategories, setTopCategories] = useState([]);
  const [userTopChannels, setUserTopChannels] = useState([]);
  const [userTopCategories, setUserTopCategories] = useState([]);
  const [channelTopUsers, setChannelTopUsers] = useState([]);
  const [categoryTopUsers, setCategoryTopUsers] = useState([]);
  const [categoryTopChannels, setCategoryTopChannels] = useState([]);
  
  const [hourlyDistribution, setHourlyDistribution] = useState([]);
  const [userHourlyDistribution, setUserHourlyDistribution] = useState([]);
  
  const [profilePictures, setProfilePictures] = useState({});
  const [userNames, setUserNames] = useState({});
  const [channelNames, setChannelNames] = useState({});
  const [categoryNames, setCategoryNames] = useState({});
  const [roleNames, setRoleNames] = useState({});
  const [roleColors, setRoleColors] = useState({});

  const [usersLoaded, setUsersLoaded] = useState(false);
  const [channelsLoaded, setChannelsLoaded] = useState(false);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [rolesLoaded, setRolesLoaded] = useState(false);
  
  const [rawUserIds, setRawUserIds] = useState([]);
  const [isFetchingUsernames, setIsFetchingUsernames] = useState(false);

  const fetchedRef = useRef(false);
  const prevFiltersRef = useRef(JSON.stringify({
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId
  }));

  const channelsRef = useRef([]);
  const categoriesRef = useRef([]);
  const rolesRef = useRef([]);
  const channelNamesRef = useRef({});
  const categoryNamesRef = useRef({});

  useEffect(() => {
    channelsRef.current = channels;
  }, [channels]);

  useEffect(() => {
    categoriesRef.current = categories;
  }, [categories]);

  useEffect(() => {
    rolesRef.current = roles;
  }, [roles]);

  useEffect(() => {
    channelNamesRef.current = channelNames;
  }, [channelNames]);

  useEffect(() => {
    categoryNamesRef.current = categoryNames;
  }, [categoryNames]);

  const NAVBAR_HEIGHT = "80px";

  const getApiEndpoint = (endpoint, isPublic) => {
    if (isPublic) {
      return endpoint.replace('/api/', '/api/public/');
    }
    return endpoint;
  };

  const isPrivilegedUser = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  // FIXED: Fetch single user's basic info (username only, no avatar)
  const fetchUserBasicInfo = async (userId, guildId) => {
    if (!userId) return null;
    
    const stringId = String(userId);
    const cacheKey = `${guildId}:${stringId}`;
    
    // Check cache first - only return valid cached entries
    if (userBasicInfoCache.has(cacheKey)) {
      const cached = userBasicInfoCache.get(cacheKey);
      if (cached.name && !cached.name.startsWith('User ')) {
        return cached;
      }
    }
    
    try {
      const isPublic = isPublicMode;
      // Use the any-table endpoint to get username
      const url = getApiEndpoint(`${API_BASE_URL}/api/username/any-table/${guildId}/${stringId}`, isPublic);
      
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
    
    // Fallback - DO NOT cache fallbacks
    const fallbackInfo = { id: stringId, name: `User ${stringId.slice(-4)}`, username: `User ${stringId.slice(-4)}` };
    return fallbackInfo;
  };

  // FIXED: Batch fetch user basic info (usernames only) using any-table endpoint
  const batchFetchUserBasicInfo = async (guildId, userIds) => {
    if (!guildId || !userIds || userIds.length === 0) return {};
    
    const uncachedUserIds = [];
    const results = {};
    
    // Check cache first - only accept valid cached entries
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
      // Fetch each user individually using any-table endpoint (tries all tables)
      const fetchPromises = uncachedUserIds.map(async (userId) => {
        const url = getApiEndpoint(`${API_BASE_URL}/api/username/any-table/${guildId}/${userId}`, isPublic);
        
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
    
    // Fill in any missing users with fallback - DO NOT cache these
    for (const userId of uncachedUserIds) {
      if (!results[userId]) {
        const fallbackInfo = { id: userId, name: `User ${userId.slice(-4)}`, username: `User ${userId.slice(-4)}` };
        results[userId] = fallbackInfo;
      }
    }
    
    return results;
  };

  // Fetch user avatar (only for top 3 users)
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

  // Fetch usernames when user dropdown opens
  useEffect(() => {
    if (showUserDropdown && rawUserIds.length > 0 && !isFetchingUsernames && currentServer) {
      const fetchUsernamesForDropdown = async () => {
        setIsFetchingUsernames(true);
        try {
          const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, rawUserIds);
          
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
  }, [showUserDropdown, rawUserIds, currentServer, isFetchingUsernames]);

  // Fetch server timezone
  useEffect(() => {
    const fetchServerTimezone = async () => {
      try {
        let url = `${API_BASE_URL}/api/user/timezone`;
        if (isPublicMode && currentServer?.id) {
          url += `?guild_id=${currentServer.id}`;
        }
        
        const response = await fetch(url, {
          credentials: isPublicMode ? 'omit' : 'include',
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
    
    if (currentServer) {
      fetchServerTimezone();
    }
  }, [currentServer, isPublicMode]);

  useEffect(() => {
    loadInitialData();
  }, []);

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
        
        let hasAccessFlag = false;
        
        if (accessLevel === 'Public') {
          hasAccessFlag = true;
        } else if (accessLevel === 'Member') {
          hasAccessFlag = true;
        } else if (accessLevel === 'Moderator') {
          hasAccessFlag = hasAdmin || hasManageServer;
        } else if (accessLevel === 'Admin') {
          hasAccessFlag = hasAdmin;
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
                if (!isPrivilegedUser(authData.user.id)) {
                  await checkServerAccess(
                    selectedServer.id,
                    selectedServer.has_admin || false,
                    selectedServer.has_manage_server || false
                  );
                }
              } else {
                setLoading(false);
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

  const getChannelName = (channelId) => {
    if (!channelId) return 'Unknown Channel';
    const stringId = String(channelId).trim();
    const channel = channelsRef.current.find(c => String(c.id) === stringId);
    if (channel) return channel.name;
    if (channelNamesRef.current[stringId]) return channelNamesRef.current[stringId];
    const channelFromState = channels.find(c => String(c.id) === stringId);
    if (channelFromState) return channelFromState.name;
    if (channelNames[stringId]) return channelNames[stringId];
    return `Channel ${stringId}`;
  };

  const getCategoryName = (categoryId) => {
    if (!categoryId) return 'Unknown Category';
    const stringId = String(categoryId).trim();
    const category = categoriesRef.current.find(c => String(c.id) === stringId);
    if (category) return category.name;
    if (categoryNamesRef.current[stringId]) return categoryNamesRef.current[stringId];
    const categoryFromState = categories.find(c => String(c.id) === stringId);
    if (categoryFromState) return categoryFromState.name;
    if (categoryNames[stringId]) return categoryNames[stringId];
    return `Category ${stringId}`;
  };

  const getRoleName = (roleId) => {
    if (!roleId) return 'Unknown Role';
    const stringId = String(roleId).trim();
    const role = rolesRef.current.find(r => String(r.id) === stringId);
    if (role) return role.name;
    const roleFromState = roles.find(r => String(r.id) === stringId);
    if (roleFromState) return roleFromState.name;
    return `Role ${stringId}`;
  };

  const getRoleColor = (roleId) => {
    if (!roleId) return '#99aab5';
    const stringId = String(roleId).trim();
    if (roleColors[stringId]) return roleColors[stringId];
    const role = rolesRef.current.find(r => String(r.id) === stringId);
    if (role) return role.color || '#99aab5';
    const roleFromState = roles.find(r => String(r.id) === stringId);
    if (roleFromState) return roleFromState.color || '#99aab5';
    return '#99aab5';
  };

  // FIXED: Fetch all users - stores only user IDs initially
  const fetchAllUsers = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setUsersLoaded(false);
    
    const cacheKey = getCacheKey('users', currentServer.id, { role: selectedRoleId, public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setUsers(cached.users);
      setFilteredUsers(cached.users);
      setUserNames(cached.userNames);
      setRawUserIds(cached.users.map(u => u.id));
      setUsersLoaded(true);
      return;
    }
    
    try {
      const endpoint = getApiEndpoint(`${API_BASE_URL}/api/voice/users?guild_id=${currentServer.id}`, isPublic);
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (!response.ok) {
        console.error('Failed to fetch users:', response.status);
        setUsersLoaded(true);
        return;
      }
      
      const data = await response.json();
      
      if (!data.user_ids || data.user_ids.length === 0) {
        setUsersLoaded(true);
        return;
      }
      
      const userIds = data.user_ids;
      // Store only user IDs initially with placeholder names
      const userList = userIds.map(userId => ({
        id: String(userId),
        name: `User ${userId}`, // Placeholder
        username: null,
        global_name: null,
        avatar: null
      }));
      
      setRawUserIds(userIds.map(id => String(id)));
      
      userList.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      
      serverDataCache.set(cacheKey, {
        users: userList,
        userNames: {},
        profilePictures: {}
      });
      
      setUsers(userList);
      setFilteredUsers(userList);
      setUserNames({});
      
    } catch (error) {
      console.error('Error fetching users:', error);
    } finally {
      setUsersLoaded(true);
    }
  };

  // Fetch all channels from voice data
  const fetchAllChannels = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setChannelsLoaded(false);
    
    const cacheKey = getCacheKey('channels', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setChannels(cached.channelList);
      setFilteredChannels(cached.channelList);
      setChannelNames(cached.nameMap);
      setChannelsLoaded(true);
      return;
    }
    
    try {
      const endpoint = getApiEndpoint(`${API_BASE_URL}/api/voice/channels?guild_id=${currentServer.id}`, isPublic);
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        
        const channelsData = data.channels || [];
        
        const channelList = [];
        const nameMap = {};
        
        channelsData.forEach(channel => {
          channelList.push({
            id: channel.id,
            name: channel.name,
            type: channel.type || 'voice',
            category_id: channel.category_id,
            searchString: `${channel.name} ${channel.id}`.toLowerCase()
          });
          nameMap[channel.id] = channel.name;
        });
        
        serverDataCache.set(cacheKey, {
          channelList,
          nameMap
        });
        
        setChannels(channelList);
        setFilteredChannels(channelList);
        setChannelNames(nameMap);
      }
    } catch (error) {
      console.error('Error fetching channels:', error);
    } finally {
      setChannelsLoaded(true);
    }
  };

  // Fetch all categories from voice data
  const fetchAllCategories = async () => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setCategoriesLoaded(false);
    
    const cacheKey = getCacheKey('categories', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setCategories(cached.categoryList);
      setFilteredCategories(cached.categoryList);
      setCategoryNames(cached.nameMap);
      setCategoriesLoaded(true);
      return;
    }
    
    try {
      const endpoint = getApiEndpoint(`${API_BASE_URL}/api/voice/categories?guild_id=${currentServer.id}`, isPublic);
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        
        const categoriesData = data.categories || [];
        
        const categoryList = [];
        const nameMap = {};
        
        categoriesData.forEach(category => {
          categoryList.push({
            id: category.id,
            name: category.name,
            searchString: `${category.name} ${category.id}`.toLowerCase()
          });
          nameMap[category.id] = category.name;
        });
        
        serverDataCache.set(cacheKey, {
          categoryList,
          nameMap
        });
        
        setCategories(categoryList);
        setFilteredCategories(categoryList);
        setCategoryNames(nameMap);
      }
    } catch (error) {
      console.error('Error fetching categories:', error);
    } finally {
      setCategoriesLoaded(true);
    }
  };

  // Fetch all roles
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
      const endpoint = getApiEndpoint(`${API_BASE_URL}/api/server/real-roles?guild_id=${currentServer.id}`, isPublic);
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include'
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
            colorMap[roleId] = role.color;
          });
          
          serverDataCache.set(cacheKey, {
            roleList,
            nameMap,
            colorMap
          });
          
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

  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    fetchedRef.current = false;
    
    setLoadingTopUsers(true);
    setLoadingTopChannels(true);
    setLoadingTopCategories(true);
    setLoadingUserTopChannels(true);
    setLoadingUserTopCategories(true);
    setLoadingChannelTopUsers(true);
    setLoadingCategoryTopUsers(true);
    setLoadingCategoryTopChannels(true);
    setLoadingHourlyDistribution(true);
    setLoadingUserHourlyDistribution(true);
    setLoadingSummaryStats(true);
    setLoadingTimeseries(true);
    setLoadingUserTimeseries(true);
    setLoadingChannelTimeseries(true);
    setLoadingCategoryTimeseries(true);
    
    setLoading(true);
    
    setUsersLoaded(false);
    setChannelsLoaded(false);
    setCategoriesLoaded(false);
    setRolesLoaded(false);
    
    setTopUsers([]);
    setTopChannels([]);
    setTopCategories([]);
    setUserTopChannels([]);
    setUserTopCategories([]);
    setChannelTopUsers([]);
    setCategoryTopUsers([]);
    setCategoryTopChannels([]);
    setServerData(null);
    
    profileCache.clear();
    userBasicInfoCache.clear();
    
    Promise.all([
      fetchAllUsers(),
      fetchAllChannels(),
      fetchAllCategories(),
      fetchAllRoles()
    ]).then(() => {
      fetchData();
    });
  }, [currentServer, hasAccess]);

  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    const currentFilters = JSON.stringify({
      selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId
    });
    
    if (prevFiltersRef.current !== currentFilters) {
      prevFiltersRef.current = currentFilters;
      fetchData();
    }
  }, [
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId
  ]);

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

  useEffect(() => {
    if (channelSearch.trim() === "") {
      setFilteredChannels(channels);
    } else {
      const searchLower = channelSearch.toLowerCase();
      const filtered = channels.filter(channel => 
        channel.searchString?.includes(searchLower) ||
        channel.id?.includes(searchLower)
      );
      setFilteredChannels(filtered);
    }
  }, [channelSearch, channels]);

  useEffect(() => {
    if (categorySearch.trim() === "") {
      setFilteredCategories(categories);
    } else {
      const searchLower = categorySearch.toLowerCase();
      const filtered = categories.filter(category => 
        category.searchString?.includes(searchLower) ||
        category.id?.includes(searchLower)
      );
      setFilteredCategories(filtered);
    }
  }, [categorySearch, categories]);

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
    if (timePeriod === "all") return { startDate: null, endDate: null };
    if (timePeriod === "custom-lookback") {
      if (!customDaysBack || parseInt(customDaysBack) <= 0) return { startDate: null, endDate: null };
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - parseInt(customDaysBack));
      return { startDate, endDate };
    }
    if (timePeriod === "custom-range") {
      if (!customStartDate || !customEndDate) return { startDate: null, endDate: null };
      return { startDate: new Date(customStartDate), endDate: new Date(customEndDate) };
    }
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - parseInt(timePeriod));
    return { startDate, endDate };
  };

  const calculateAverages = (totalSeconds, uniqueUsers, daysInPeriod) => {
    if (daysInPeriod === 0) return {
      avgPerUser: 0, avgPerDay: 0, avgPerMonth: 0, avgPerYear: 0, daysInPeriod: 0
    };
    const avgPerUser = uniqueUsers > 0 ? totalSeconds / uniqueUsers : 0;
    const avgPerDay = totalSeconds / daysInPeriod;
    const avgPerMonth = avgPerDay * 30;
    const avgPerYear = avgPerDay * 365;
    return {
      avgPerUser: Math.round(avgPerUser * 100) / 100,
      avgPerDay: Math.round(avgPerDay * 100) / 100,
      avgPerMonth: Math.round(avgPerMonth * 100) / 100,
      avgPerYear: Math.round(avgPerYear * 100) / 100,
      daysInPeriod
    };
  };

  const fetchTimeseriesData = async (requestBody) => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setLoadingTimeseries(true);
    
    const cacheKey = getCacheKey('timeseries', currentServer.id, requestBody);
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setTimeseriesData(cached);
      setLoadingTimeseries(false);
      return;
    }
    
    try {
      const { startDate, endDate } = getDateRange();
      
      const url = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/server/timeseries/voice/daily`, isPublic), {
        guild_id: currentServer.id,
        role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
        start_time: startDate?.toISOString(),
        end_time: endDate?.toISOString(),
        max_points: 90
      });
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
          serverDataCache.set(cacheKey, data);
          setTimeseriesData(data);
        } else {
          setTimeseriesData([]);
        }
      } else {
        setTimeseriesData([]);
      }
    } catch (error) {
      console.error('Error fetching timeseries data:', error);
      setTimeseriesData([]);
    } finally {
      setLoadingTimeseries(false);
    }
  };

  const fetchUserTimeseriesData = async (requestBody) => {
    if (!currentServer || !selectedUserId) return;
    
    const isPublic = isPublicMode;
    setLoadingUserTimeseries(true);
    
    const cacheKey = getCacheKey('user-timeseries', selectedUserId, requestBody);
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setUserTimeseriesData(cached);
      setLoadingUserTimeseries(false);
      return;
    }
    
    try {
      const { startDate, endDate } = getDateRange();
      
      const url = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/user/timeseries/voice/daily`, isPublic), {
        guild_id: currentServer.id,
        user_id: selectedUserId,
        role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
        start_time: startDate?.toISOString(),
        end_time: endDate?.toISOString(),
        max_points: 90
      });
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
          serverDataCache.set(cacheKey, data);
          setUserTimeseriesData(data);
        } else {
          setUserTimeseriesData([]);
        }
      } else {
        setUserTimeseriesData([]);
      }
    } catch (error) {
      console.error('Error fetching user timeseries data:', error);
      setUserTimeseriesData([]);
    } finally {
      setLoadingUserTimeseries(false);
    }
  };

  const fetchChannelTimeseriesData = async (requestBody) => {
    if (!currentServer || !selectedChannelId) return;
    
    const isPublic = isPublicMode;
    setLoadingChannelTimeseries(true);
    
    const cacheKey = getCacheKey('channel-timeseries', selectedChannelId, requestBody);
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setChannelTimeseriesData(cached);
      setLoadingChannelTimeseries(false);
      return;
    }
    
    try {
      const { startDate, endDate } = getDateRange();
      
      const url = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/channel/timeseries/voice/daily`, isPublic), {
        guild_id: currentServer.id,
        channel_id: selectedChannelId,
        role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
        start_time: startDate?.toISOString(),
        end_time: endDate?.toISOString(),
        max_points: 90
      });
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
          serverDataCache.set(cacheKey, data);
          setChannelTimeseriesData(data);
        } else {
          setChannelTimeseriesData([]);
        }
      } else {
        setChannelTimeseriesData([]);
      }
    } catch (error) {
      console.error('Error fetching channel timeseries data:', error);
      setChannelTimeseriesData([]);
    } finally {
      setLoadingChannelTimeseries(false);
    }
  };

  const fetchCategoryTimeseriesData = async (requestBody) => {
    if (!currentServer || !selectedCategoryId) return;
    
    const isPublic = isPublicMode;
    setLoadingCategoryTimeseries(true);
    
    const cacheKey = getCacheKey('category-timeseries', selectedCategoryId, requestBody);
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setCategoryTimeseriesData(cached);
      setLoadingCategoryTimeseries(false);
      return;
    }
    
    try {
      const { startDate, endDate } = getDateRange();
      
      const url = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/category/timeseries/voice/daily`, isPublic), {
        guild_id: currentServer.id,
        category_id: selectedCategoryId,
        role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
        start_time: startDate?.toISOString(),
        end_time: endDate?.toISOString(),
        max_points: 90
      });
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
          serverDataCache.set(cacheKey, data);
          setCategoryTimeseriesData(data);
        } else {
          setCategoryTimeseriesData([]);
        }
      } else {
        setCategoryTimeseriesData([]);
      }
    } catch (error) {
      console.error('Error fetching category timeseries data:', error);
      setCategoryTimeseriesData([]);
    } finally {
      setLoadingCategoryTimeseries(false);
    }
  };

  const fetchData = async () => {
    if (!currentServer || !hasAccess) return;
    
    setLoading(true);
    setApiError(null);
    const { startDate, endDate } = getDateRange();
    
    let daysInPeriod = 0;
    if (startDate && endDate) {
      daysInPeriod = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
    } else if (timePeriod !== "all" && timePeriod !== "custom-lookback" && timePeriod !== "custom-range") {
      daysInPeriod = parseInt(timePeriod);
    } else if (timePeriod === "custom-lookback" && customDaysBack) {
      daysInPeriod = parseInt(customDaysBack);
    } else {
      daysInPeriod = 30;
    }
    
    try {
      const roleFilterArray = selectedRoleId ? [String(selectedRoleId)] : null;
      
      const requestBody = {
        guild_id: currentServer.id,
        role_filter_ids: roleFilterArray,
        start_time: startDate?.toISOString(),
        end_time: endDate?.toISOString()
      };
      
      if (selectedView === 'server') {
        await fetchServerData(requestBody, daysInPeriod);
      } else if (selectedView === 'user' && selectedUserId) {
        await fetchUserData(requestBody, daysInPeriod);
      } else if (selectedView === 'channel' && selectedChannelId) {
        await fetchChannelData(requestBody, daysInPeriod);
      } else if (selectedView === 'category' && selectedCategoryId) {
        await fetchCategoryData(requestBody, daysInPeriod);
      }
      
    } catch (error) {
      console.error('Error fetching data:', error);
      setApiError(error.message);
    } finally {
      setLoading(false);
      fetchedRef.current = true;
    }
  };

  // FIXED: fetchServerData with proper username handling
  const fetchServerData = async (requestBody, daysInPeriod) => {
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('server', currentServer.id, requestBody);
    const cached = serverDataCache.get(cacheKey);
    
    if (cached) {
      setServerData(cached.serverData);
      setAveragesData(cached.averagesData);
      setTopUsers(cached.topUsers);
      setTopChannels(cached.topChannels);
      setTopCategories(cached.topCategories);
      setHourlyDistribution(cached.hourlyDistribution);
      setTimeseriesData(cached.timeseriesData || []);
      setLoadingSummaryStats(false);
      setLoadingTopUsers(false);
      setLoadingTopChannels(false);
      setLoadingTopCategories(false);
      setLoadingHourlyDistribution(false);
      setLoadingTimeseries(false);
      return;
    }
    
    const statsEndpoint = getApiEndpoint(`${API_BASE_URL}/api/server/stats/voice`, isPublic);
    const statsResponse = await fetch(statsEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: isPublic ? 'omit' : 'include',
      body: JSON.stringify(requestBody)
    });
    
    let totalSeconds = 0;
    let totalActiveUsers = 0;
    let sessionCount = 0;
    let averages = averagesData;
    
    if (statsResponse.ok) {
      const stats = await statsResponse.json();
      totalSeconds = stats.total_seconds || 0;
      totalActiveUsers = stats.unique_users || 0;
      sessionCount = stats.session_count || 0;
      
      setServerData({
        totalSeconds: totalSeconds,
        totalHours: stats.total_hours || 0,
        totalActiveUsers: totalActiveUsers,
        sessionCount: sessionCount
      });
      
      averages = calculateAverages(totalSeconds, totalActiveUsers, daysInPeriod);
      setAveragesData(averages);
    }
    setLoadingSummaryStats(false);
    
    // 2. Top users - Batch fetch usernames for all, avatars only for top 3
    const usersUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/server/top/users/voice`, isPublic), {
      guild_id: requestBody.guild_id,
      role_filter_ids: requestBody.role_filter_ids,
      limit: 100000000000,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time
    });
    
    const usersResponse = await fetch(usersUrl, {
      credentials: isPublic ? 'omit' : 'include',
      headers: { 'Accept': 'application/json' }
    });

    let formattedUsers = [];
    if (usersResponse.ok) {
      const usersData = await usersResponse.json();
      
      if (Array.isArray(usersData) && usersData.length > 0) {
        const allUserIds = usersData.map(user => String(user.user_id));
        const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds);
        
        formattedUsers = await Promise.all(usersData.map(async (user, index) => {
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
            value: user.total_seconds || 0,
            avatar: avatar
          };
        }));
        setTopUsers(formattedUsers);
      }
    }
    setLoadingTopUsers(false);
    
    // 3. Top voice channels
    const channelsUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/leaderboard/server/top/voice-channels`, isPublic), {
      guild_id: requestBody.guild_id,
      role_filter_ids: requestBody.role_filter_ids,
      limit: 100000000000,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time
    });
    
    try {
      const channelsResponse = await fetch(channelsUrl, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      
      if (channelsResponse.ok) {
        const channelsData = await channelsResponse.json();
        
        if (Array.isArray(channelsData) && channelsData.length > 0) {
          const formattedChannels = channelsData.map((channel) => {
            const channelId = String(channel.channel_id);
            const channelName = getChannelName(channelId);
            return {
              id: channelId,
              name: channelName,
              value: channel.total_seconds || 0,
              sessionCount: channel.session_count || 0
            };
          });
          setTopChannels(formattedChannels);
        } else {
          setTopChannels([]);
        }
      }
    } catch (error) {
      console.error('Error fetching top channels:', error);
      setTopChannels([]);
    } finally {
      setLoadingTopChannels(false);
    }
    
    // 4. Top categories
    try {
      const categoriesUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/leaderboard/server/top/categories/voice`, isPublic), {
        guild_id: requestBody.guild_id,
        role_filter_ids: requestBody.role_filter_ids,
        limit: 100000000000,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      });
      
      const categoriesResponse = await fetch(categoriesUrl, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (categoriesResponse.ok) {
        const categoriesData = await categoriesResponse.json();
        
        if (Array.isArray(categoriesData) && categoriesData.length > 0) {
          const formattedCategories = categoriesData.map((category) => {
            const categoryId = String(category.category_id);
            const categoryName = getCategoryName(categoryId);
            return {
              id: categoryId,
              name: categoryName,
              value: category.total_seconds || 0,
              sessionCount: category.session_count || 0,
              uniqueUsers: category.unique_users || 0
            };
          });
          setTopCategories(formattedCategories);
        } else {
          setTopCategories([]);
        }
      }
    } catch (error) {
      console.error('Error fetching top categories:', error);
      setTopCategories([]);
    } finally {
      setLoadingTopCategories(false);
    }
    
    // 5. Hourly distribution
    try {
      let daysBack = 30;
      if (timePeriod === "all") {
        daysBack = 0;
      } else if (timePeriod === "custom-lookback" && customDaysBack) {
        daysBack = parseInt(customDaysBack);
      } else if (timePeriod === "custom-range") {
        daysBack = daysInPeriod;
      } else {
        daysBack = parseInt(timePeriod);
      }
      
      const distEndpoint = getApiEndpoint(`${API_BASE_URL}/api/server/activity/distribution`, isPublic);
      const distResponse = await fetch(distEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify({
          guild_id: requestBody.guild_id,
          days_back: daysBack,
          role_filter_ids: requestBody.role_filter_ids,
          timezone_str: serverTimezone
        })
      });
      
      if (distResponse.ok) {
        const distData = await distResponse.json();
        
        if (distData.voice) {
          const distribution = [];
          let hasData = false;
          
          for (let i = 0; i < 24; i++) {
            const value = distData.voice[`hour_${i}`] || 0;
            if (value > 0) hasData = true;
            distribution.push({
              name: `${i.toString().padStart(2, '0')}:00`,
              value: value
            });
          }
          
          setHourlyDistribution(hasData ? distribution : []);
          await fetchTimeseriesData(requestBody);
        }
      }
    } catch (error) {
      console.error('Error fetching hourly distribution:', error);
    } finally {
      setLoadingHourlyDistribution(false);
    }
    
    serverDataCache.set(cacheKey, {
      serverData: {
        totalSeconds,
        totalHours: totalSeconds / 3600,
        totalActiveUsers,
        sessionCount
      },
      averagesData: averages,
      topUsers: formattedUsers,
      topChannels: topChannels,
      topCategories: topCategories,
      hourlyDistribution: hourlyDistribution,
      timeseriesData: timeseriesData
    });
  };

  // FIXED: fetchUserData with proper username handling
  const fetchUserData = async (requestBody, daysInPeriod) => {
    if (!selectedUserId) return;
    
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('user', selectedUserId, requestBody);
    const cached = serverDataCache.get(cacheKey);
    
    if (cached) {
      setUserData(cached.userData);
      setAveragesData(cached.averagesData);
      setUserTopChannels(cached.userTopChannels);
      setUserTopCategories(cached.userTopCategories);
      setUserHourlyDistribution(cached.userHourlyDistribution);
      setUserTimeseriesData(cached.userTimeseriesData || []);
      setLoadingSummaryStats(false);
      setLoadingUserTopChannels(false);
      setLoadingUserTopCategories(false);
      setLoadingUserHourlyDistribution(false);
      setLoadingUserTimeseries(false);
      return;
    }
    
    const userProfile = await fetchUserBasicInfo(selectedUserId, currentServer.id);
    
    const statsEndpoint = getApiEndpoint(`${API_BASE_URL}/api/user/stats/voice`, isPublic);
    const statsResponse = await fetch(statsEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: isPublic ? 'omit' : 'include',
      body: JSON.stringify({
        guild_id: requestBody.guild_id,
        user_id: selectedUserId,
        role_filter_ids: requestBody.role_filter_ids,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      })
    });
    
    let userSeconds = 0;
    let sessionCount = 0;
    let firstSession = null;
    let lastSession = null;
    let averages = averagesData;
    
    if (statsResponse.ok) {
      const stats = await statsResponse.json();
      userSeconds = stats.total_seconds || 0;
      sessionCount = stats.session_count || 0;
      firstSession = stats.first_session;
      lastSession = stats.last_session;
    }
    
    averages = calculateAverages(userSeconds, 1, daysInPeriod);
    setAveragesData(averages);
    setLoadingSummaryStats(false);
    
    // User top channels
    const channelsUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/user/top/voice-channels`, isPublic), {
      guild_id: requestBody.guild_id,
      user_id: selectedUserId,
      role_filter_ids: requestBody.role_filter_ids,
      limit: 100000000000,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time
    });
    
    const channelsResponse = await fetch(channelsUrl, {
      credentials: isPublic ? 'omit' : 'include',
      headers: { 'Accept': 'application/json' }
    });
    
    let formattedChannels = [];
    if (channelsResponse.ok) {
      const channelsData = await channelsResponse.json();
      
      if (Array.isArray(channelsData)) {
        formattedChannels = channelsData.map((channel) => {
          const channelId = String(channel.channel_id);
          const channelName = getChannelName(channelId);
          const totalSeconds = channel.total_seconds || 0;
          return {
            id: channelId,
            name: channelName,
            value: totalSeconds,
            sessionCount: channel.session_count || 0
          };
        });
        setUserTopChannels(formattedChannels);
      }
    }
    setLoadingUserTopChannels(false);
    
    // User top categories
    try {
      const categoriesUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/user/top/categories/voice`, isPublic), {
        guild_id: requestBody.guild_id,
        user_id: selectedUserId,
        role_filter_ids: requestBody.role_filter_ids,
        limit: 100000000000,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      });
      
      const categoriesResponse = await fetch(categoriesUrl, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (categoriesResponse.ok) {
        const categoriesData = await categoriesResponse.json();
        
        if (Array.isArray(categoriesData)) {
          const formattedCategories = categoriesData.map((category) => {
            const categoryId = String(category.category_id);
            const categoryName = getCategoryName(categoryId);
            return {
              id: categoryId,
              name: categoryName,
              value: category.total_seconds || 0,
              sessionCount: category.session_count || 0,
              uniqueChannels: category.unique_channels || 0
            };
          });
          setUserTopCategories(formattedCategories);
        }
      }
    } catch (error) {
      console.error('Error fetching user top categories:', error);
      setUserTopCategories([]);
    } finally {
      setLoadingUserTopCategories(false);
    }
    
    // User hourly distribution
    let daysBack = 30;
    if (timePeriod === "all") {
      daysBack = 0;
    } else if (timePeriod === "custom-lookback" && customDaysBack) {
      daysBack = parseInt(customDaysBack);
    } else if (timePeriod === "custom-range") {
      daysBack = daysInPeriod;
    } else {
      daysBack = parseInt(timePeriod);
    }
    
    const distEndpoint = getApiEndpoint(`${API_BASE_URL}/api/user/activity/distribution`, isPublic);
    const distResponse = await fetch(distEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: isPublic ? 'omit' : 'include',
      body: JSON.stringify({
        guild_id: requestBody.guild_id,
        user_id: selectedUserId,
        days_back: daysBack,
        role_filter_ids: requestBody.role_filter_ids,
        timezone_str: serverTimezone
      })
    });
    
    let userDistData = [];
    if (distResponse.ok) {
      const distData = await distResponse.json();
      
      if (distData.voice) {
        let hasData = false;
        
        for (let i = 0; i < 24; i++) {
          const value = distData.voice[`hour_${i}`] || 0;
          if (value > 0) hasData = true;
          userDistData.push({
            name: `${i.toString().padStart(2, '0')}:00`,
            value: value
          });
        }
        
        setUserHourlyDistribution(hasData ? userDistData : []);
        await fetchUserTimeseriesData(requestBody);
      }
    }
    setLoadingUserHourlyDistribution(false);
    
    const userName = userProfile?.name || `User ${selectedUserId.slice(-4)}`;
    
    const userDataResult = {
      userId: selectedUserId,
      name: userName,
      totalSeconds: userSeconds,
      totalHours: (userSeconds / 3600).toFixed(1),
      sessionCount: sessionCount,
      firstSession: firstSession,
      lastSession: lastSession
    };
    
    setUserData(userDataResult);
    
    serverDataCache.set(cacheKey, {
      userData: userDataResult,
      averagesData: averages,
      userTopChannels: formattedChannels,
      userTopCategories: userTopCategories,
      userHourlyDistribution: userDistData,
      userTimeseriesData: userTimeseriesData
    });
  };

  // FIXED: fetchChannelData with proper username handling
  const fetchChannelData = async (requestBody, daysInPeriod) => {
    if (!selectedChannelId) return;
    
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('channel', selectedChannelId, requestBody);
    const cached = serverDataCache.get(cacheKey);
    
    if (cached) {
      setChannelData(cached.channelData);
      setAveragesData(cached.averagesData);
      setChannelTopUsers(cached.channelTopUsers);
      setChannelTimeseriesData(cached.channelTimeseriesData || []);
      setLoadingSummaryStats(false);
      setLoadingChannelTopUsers(false);
      setLoadingChannelTimeseries(false);
      return;
    }
    
    const statsEndpoint = getApiEndpoint(`${API_BASE_URL}/api/channel/stats/voice`, isPublic);
    const statsResponse = await fetch(statsEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: isPublic ? 'omit' : 'include',
      body: JSON.stringify({
        guild_id: requestBody.guild_id,
        channel_id: selectedChannelId,
        role_filter_ids: requestBody.role_filter_ids, 
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      })
    });
    
    let totalSeconds = 0;
    let uniqueUsers = 0;
    let sessionCount = 0;
    let averages = averagesData;
    
    if (statsResponse.ok) {
      const stats = await statsResponse.json();
      totalSeconds = stats.total_seconds || 0;
      uniqueUsers = stats.unique_users || 0;
      sessionCount = stats.session_count || 0;
    }
    
    averages = calculateAverages(totalSeconds, uniqueUsers, daysInPeriod);
    setAveragesData(averages);
    setLoadingSummaryStats(false);
    
    // Top users in this channel
    const usersUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/channel/top/users/voice`, isPublic), {
      guild_id: requestBody.guild_id,
      channel_id: selectedChannelId,
      role_filter_ids: requestBody.role_filter_ids,
      limit: 100000000000,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time
    });
    
    const usersResponse = await fetch(usersUrl, {
      credentials: isPublic ? 'omit' : 'include'
    });
    
    let formattedUsers = [];
    if (usersResponse.ok) {
      const usersData = await usersResponse.json();
      
      if (Array.isArray(usersData) && usersData.length > 0) {
        const allUserIds = usersData.map(user => String(user.user_id));
        const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds);
        
        formattedUsers = await Promise.all(usersData.map(async (user, index) => {
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
            value: user.total_seconds || 0,
            avatar: avatar
          };
        }));
        setChannelTopUsers(formattedUsers);
      }
    }
    setLoadingChannelTopUsers(false);
    
    await fetchChannelTimeseriesData(requestBody);
    
    const channelName = getChannelName(selectedChannelId);
    
    const channelDataResult = {
      channelId: selectedChannelId,
      name: channelName,
      totalSeconds: totalSeconds,
      totalHours: (totalSeconds / 3600).toFixed(1),
      uniqueUsers: uniqueUsers,
      sessionCount: sessionCount,
      secondsPerUser: uniqueUsers > 0 ? (totalSeconds / uniqueUsers).toFixed(0) : 0
    };
    
    setChannelData(channelDataResult);
    
    serverDataCache.set(cacheKey, {
      channelData: channelDataResult,
      averagesData: averages,
      channelTopUsers: formattedUsers,
      channelTimeseriesData: channelTimeseriesData
    });
  };

  // FIXED: fetchCategoryData with proper username handling
  const fetchCategoryData = async (requestBody, daysInPeriod) => {
    if (!selectedCategoryId) return;
    
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('category', selectedCategoryId, requestBody);
    const cached = serverDataCache.get(cacheKey);
    
    if (cached) {
      setCategoryData(cached.categoryData);
      setAveragesData(cached.averagesData);
      setCategoryTopUsers(cached.categoryTopUsers);
      setCategoryTopChannels(cached.categoryTopChannels);
      setCategoryTimeseriesData(cached.categoryTimeseriesData || []);
      setLoadingSummaryStats(false);
      setLoadingCategoryTopUsers(false);
      setLoadingCategoryTopChannels(false);
      setLoadingCategoryTimeseries(false);
      return;
    }
    
    const statsEndpoint = getApiEndpoint(`${API_BASE_URL}/api/category/stats/voice`, isPublic);
    const statsResponse = await fetch(statsEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: isPublic ? 'omit' : 'include',
      body: JSON.stringify({
        guild_id: requestBody.guild_id,
        category_id: selectedCategoryId,
        role_filter_ids: requestBody.role_filter_ids,  
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      })
    });
    
    let totalSeconds = 0;
    let uniqueUsers = 0;
    let sessionCount = 0;
    let averages = averagesData;
    
    if (statsResponse.ok) {
      const stats = await statsResponse.json();
      totalSeconds = stats.total_seconds || 0;
      uniqueUsers = stats.unique_users || 0;
      sessionCount = stats.session_count || 0;
    }
    
    averages = calculateAverages(totalSeconds, uniqueUsers, daysInPeriod);
    setAveragesData(averages);
    setLoadingSummaryStats(false);
    
    // Top users in this category
    const usersUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/category/top/users/voice`, isPublic), {
      guild_id: requestBody.guild_id,
      category_id: selectedCategoryId,
      role_filter_ids: requestBody.role_filter_ids,
      limit: 100000000000,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time
    });
    
    const usersResponse = await fetch(usersUrl, {
      credentials: isPublic ? 'omit' : 'include'
    });
    
    let formattedUsers = [];
    if (usersResponse.ok) {
      const usersData = await usersResponse.json();
      
      if (Array.isArray(usersData) && usersData.length > 0) {
        const allUserIds = usersData.map(user => String(user.user_id));
        const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds);
        
        formattedUsers = await Promise.all(usersData.map(async (user, index) => {
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
            value: user.total_seconds || 0,
            avatar: avatar
          };
        }));
        setCategoryTopUsers(formattedUsers);
      }
    }
    setLoadingCategoryTopUsers(false);
    
    // Top channels in this category
    const channelsUrl = buildUrl(getApiEndpoint(`${API_BASE_URL}/api/category/top/channels/voice`, isPublic), {
      guild_id: requestBody.guild_id,
      category_id: selectedCategoryId,
      role_filter_ids: requestBody.role_filter_ids,
      limit: 100000000000,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time
    });
    
    const channelsResponse = await fetch(channelsUrl, {
      credentials: isPublic ? 'omit' : 'include'
    });
    
    let formattedChannels = [];
    if (channelsResponse.ok) {
      const channelsData = await channelsResponse.json();
      
      if (Array.isArray(channelsData)) {
        formattedChannels = channelsData.map((channel) => {
          const channelId = String(channel.channel_id);
          const channelName = getChannelName(channelId);
          return {
            id: channelId,
            name: channelName,
            value: channel.total_seconds || 0,
            sessionCount: channel.session_count || 0
          };
        });
        setCategoryTopChannels(formattedChannels);
      }
    }
    setLoadingCategoryTopChannels(false);
    
    await fetchCategoryTimeseriesData(requestBody);
    
    const categoryName = getCategoryName(selectedCategoryId);
    
    const categoryDataResult = {
      categoryId: selectedCategoryId,
      name: categoryName,
      totalSeconds: totalSeconds,
      totalHours: (totalSeconds / 3600).toFixed(1),
      uniqueUsers: uniqueUsers,
      sessionCount: sessionCount,
      secondsPerUser: uniqueUsers > 0 ? (totalSeconds / uniqueUsers).toFixed(0) : 0
    };
    
    setCategoryData(categoryDataResult);
    
    serverDataCache.set(cacheKey, {
      categoryData: categoryDataResult,
      averagesData: averages,
      categoryTopUsers: formattedUsers,
      categoryTopChannels: formattedChannels,
      categoryTimeseriesData: categoryTimeseriesData
    });
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

  const formatValue = (value) => formatDynamicTime(value);

  const handleUserSelect = (user) => {
    setSelectedUserId(user.id);
    setUserSearch(user.global_name || user.username || user.name || `User ${user.id}`);
    setShowUserDropdown(false);
  };

  const handleChannelSelect = (channel) => {
    setSelectedChannelId(channel.id);
    setChannelSearch(channel.name || `Channel ${channel.id}`);
    setShowChannelDropdown(false);
  };

  const handleCategorySelect = (category) => {
    setSelectedCategoryId(category.id);
    setCategorySearch(category.name || `Category ${category.id}`);
    setShowCategoryDropdown(false);
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
      min-height: 100vh;
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

    .entity-count {
      color: #aa00ff;
      font-size: 12px;
      font-weight: 600;
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

    .setting-note {
      color: #666;
      font-size: 12px;
      margin-top: 8px;
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

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 24px;
      margin-bottom: 40px;
    }

    .stats-card {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
    }

    .stats-card h3 {
      color: #ffffff;
      font-size: 18px;
      font-weight: 600;
      margin: 0 0 20px 0;
      padding-bottom: 12px;
      border-bottom: 1px solid #1a1a1a;
    }

    .stats-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .stat-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
    }

    .stat-label {
      color: #b0b0b0;
      font-size: 14px;
    }

    .stat-number {
      color: #ffffff;
      font-size: 16px;
      font-weight: 600;
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

    .leaderboards-section {
      margin-bottom: 40px;
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
      height: auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      width: 100%;
      overflow: visible;
    }

    .chart-wrapper > div {
      width: 100%;
      height: 100%;
      min-height: 400px;
    }

    .chart-wrapper:hover {
      border-color: #aa00ff;
      box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2);
    }

    .no-chart-data {
      color: #b0b0b0;
      font-size: 16px;
      text-align: center;
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
      
      .averages-grid {
        grid-template-columns: 1fr;
      }
      
      .summary-stats {
        grid-template-columns: 1fr;
      }
      
      .stats-grid {
        grid-template-columns: 1fr;
      }
      
      .section-title {
        font-size: 22px;
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
      
      .stat-value {
        font-size: 28px;
      }
      
      .average-value {
        font-size: 22px;
      }
      
      .stat-card, .average-card {
        padding: 16px;
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
      
      .stat-value {
        font-size: 24px;
      }
      
      .average-value {
        font-size: 20px;
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

    @supports (-webkit-touch-callout: none) {
      .stat-value,
      .average-value {
        background: none !important;
        -webkit-text-fill-color: #ffffff !important;
        color: #ffffff !important;
      }
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

  // Loading state
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

  // Permission checking in progress
  if (hasAccess === null && isAuthenticated && currentServer && !isPrivilegedUser(currentUserId) && !isPublicMode) {
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

  // Not authenticated - public mode WITH ROLE FILTER
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
                <p>Viewing statistics from the <strong>StatsHQ</strong> support server - <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server stats</p>
              </div>
              
              <div className="filters-section">
                <div className="filter-row">
                  <label>View:</label>
                  <select
                    value={selectedView}
                    onChange={(e) => setSelectedView(e.target.value)}
                    className="modern-select"
                  >
                    <option value="server">Server</option>
                    <option value="user">User</option>
                    <option value="channel">Channel</option>
                    <option value="category">Category</option>
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
                
                {/* ROLE FILTER - Available for ALL views in public mode */}
                <div className="filter-row entity-filter">
                  <label>Role Filter:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search role to filter all data..."
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
                                <span className="entity-name">{user.name || `User ${user.id.slice(-4)}`}</span>
                              </div>
                              <span className="entity-id">ID: {user.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                
                {selectedView === 'channel' && (
                  <div className="filter-row entity-filter">
                    <label>Channel:</label>
                    <div className="entity-selector">
                      <input
                        type="text"
                        placeholder="Search voice channel..."
                        value={channelSearch}
                        onChange={(e) => setChannelSearch(e.target.value)}
                        onFocus={() => setShowChannelDropdown(true)}
                        onBlur={() => setTimeout(() => setShowChannelDropdown(false), 200)}
                        className="modern-entity-search"
                      />
                      {showChannelDropdown && filteredChannels.length > 0 && (
                        <div className="entity-dropdown">
                          {filteredChannels.slice(0, 20).map(channel => (
                            <div
                              key={channel.id}
                              className={`entity-option ${selectedChannelId === channel.id ? 'selected' : ''}`}
                              onMouseDown={() => handleChannelSelect(channel)}
                            >
                              <div className="entity-info">
                                <span className="entity-name">{channel.name}</span>
                                <span className="entity-id">Voice Channel</span>
                              </div>
                              <span className="entity-id">ID: {channel.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                
                {selectedView === 'category' && (
                  <div className="filter-row entity-filter">
                    <label>Category:</label>
                    <div className="entity-selector">
                      <input
                        type="text"
                        placeholder="Search by name or ID..."
                        value={categorySearch}
                        onChange={(e) => setCategorySearch(e.target.value)}
                        onFocus={() => setShowCategoryDropdown(true)}
                        onBlur={() => setTimeout(() => setShowCategoryDropdown(false), 200)}
                        className="modern-entity-search"
                      />
                      {showCategoryDropdown && filteredCategories.length > 0 && (
                        <div className="entity-dropdown">
                          {filteredCategories.slice(0, 20).map(category => (
                            <div
                              key={category.id}
                              className={`entity-option ${selectedCategoryId === category.id ? 'selected' : ''}`}
                              onMouseDown={() => handleCategorySelect(category)}
                            >
                              <div className="entity-info">
                                <span className="entity-name">{category.name}</span>
                              </div>
                              <span className="entity-id">ID: {category.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {/* Server View */}
              {selectedView === 'server' && (
                <>
                  <div className="summary-stats">
                    {loadingSummaryStats ? (
                      <>
                        <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                      </>
                    ) : serverData && (
                      <>
                        <div className="stat-card">
                          <h3>Total Voice Time</h3>
                          <p className="stat-value">{formatDynamicTime(serverData.totalSeconds)}</p>
                          <div className="average-note">({serverData.totalHours} hours)</div>
                        </div>
                        <div className="stat-card">
                          <h3>Active Users</h3>
                          <p className="stat-value">{serverData.totalActiveUsers.toLocaleString()}</p>
                        </div>
                        <div className="stat-card">
                          <h3>Total Sessions</h3>
                          <p className="stat-value">{serverData.sessionCount.toLocaleString()}</p>
                        </div>
                      </>
                    )}
                  </div>
                  
                  {averagesData.daysInPeriod > 0 && (
                    <div className="averages-section">
                      <h2 className="section-title">Averages</h2>
                      <div className="averages-grid">
                        <div className="average-card"><h3>Per User</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerUser)}</p></div>
                        <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                        <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                        <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                      </div>
                    </div>
                  )}
                  
                  <div className="leaderboards-section">
                    <h2 className="section-title">Leaderboards</h2>
                    <div className="leaderboards-stack">
                      {loadingTopUsers ? <LoadingCard /> : topUsers.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <Leaderboard
                            data={topUsers}
                            title="Top Users by Voice"
                            valueLabel="Time"
                            valueFormatter={formatValue}
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
                          />
                        </div>
                      ) : <div className="no-data-message">No user data available</div>}
                      
                      {loadingTopChannels ? <LoadingCard /> : topChannels.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <Leaderboard data={topChannels} title="Top Voice Channels" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" />
                        </div>
                      ) : <div className="no-data-message">No channel data available</div>}

                      {loadingTopCategories ? <LoadingCard /> : topCategories.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <Leaderboard data={topCategories} title="Top Categories by Voice" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="category" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" />
                        </div>
                      ) : <div className="no-data-message">No category data available</div>}
                    </div>
                  </div>
                  
                  <div className="charts-section">
                    <h2 className="section-title">Voice Activity Over Time</h2>
                    <div className="chart-wrapper">
                      {loadingTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : timeseriesData.length > 0 ? (
                        <InteractiveLineChart data={timeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                      ) : <div className="no-chart-data">No timeseries data available</div>}
                    </div>
                  </div>
                  
                  <div className="charts-section">
                    <h2 className="section-title">Most Active Hours (Voice)</h2>
                    <div className="chart-wrapper">
                      {loadingHourlyDistribution ? <LoadingSpinner size="large" text="Loading hourly data..." /> : hourlyDistribution.length > 0 && hourlyDistribution.some(item => item.value > 0) ? (
                        <TimezonePieChart hourlyData={hourlyDistribution.map(item => item.value)} timezone={serverTimezone} activityType="Voice" valueFormatter={formatDynamicTime} guildName={currentServer?.name || "Server"} daysBack={timePeriod === "all" ? null : parseInt(timePeriod)} />
                      ) : <div className="no-chart-data">No hourly data available</div>}
                    </div>
                  </div>
                </>
              )}
              
              {/* User View */}
              {selectedView === 'user' && (
                <>
                  {!selectedUserId ? (
                    <div className="no-selection"><h2>Select a User</h2><p>Please select a user from the dropdown above to view their voice statistics.</p></div>
                  ) : (
                    <>
                      <div className="summary-stats">
                        {loadingSummaryStats ? (
                          <>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          </>
                        ) : userData && (
                          <>
                            <div className="stat-card"><h3>Total Voice Time</h3><p className="stat-value">{formatDynamicTime(userData.totalSeconds)}</p><div className="average-note">({userData.totalHours} hours)</div></div>
                            <div className="stat-card"><h3>Voice Sessions</h3><p className="stat-value">{userData.sessionCount.toLocaleString()}</p></div>
                          </>
                        )}
                      </div>
                      
                      {averagesData.daysInPeriod > 0 && (
                        <div className="averages-section">
                          <h2 className="section-title">Averages</h2>
                          <div className="averages-grid">
                            <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                            <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                            <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                          </div>
                        </div>
                      )}
                      
                      <div className="leaderboards-section">
                        <h2 className="section-title">{userData?.name || 'User'}'s Activity</h2>
                        <div className="leaderboards-stack">
                          {loadingUserTopChannels ? <LoadingCard /> : userTopChannels.length > 0 ? (
                            <div className="leaderboard-wrapper"><Leaderboard data={userTopChannels} title="Top Voice Channels" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                          ) : <div className="no-data-message">No channel data available for this user</div>}
                          
                          {loadingUserTopCategories ? <LoadingCard /> : userTopCategories.length > 0 ? (
                            <div className="leaderboard-wrapper"><Leaderboard data={userTopCategories} title="Top Categories by Voice" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="category" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                          ) : <div className="no-data-message">No category data available for this user</div>}
                        </div>
                      </div>
                      
                      <div className="charts-section">
                        <h2 className="section-title">{userData?.name || 'User'}'s Voice Activity Over Time</h2>
                        <div className="chart-wrapper">
                          {loadingUserTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : userTimeseriesData.length > 0 ? (
                            <InteractiveLineChart data={userTimeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                          ) : <div className="no-chart-data">No timeseries data available for this user</div>}
                        </div>
                      </div>
                    </>
                  )}
                </>
              )}
              
              {/* Channel View */}
              {selectedView === 'channel' && (
                <>
                  {!selectedChannelId ? (
                    <div className="no-selection"><h2>Select a Voice Channel</h2><p>Please select a voice channel from the dropdown above to view its statistics.</p></div>
                  ) : (
                    <>
                      <div className="summary-stats">
                        {loadingSummaryStats ? (
                          <>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          </>
                        ) : channelData && (
                          <>
                            <div className="stat-card"><h3>Total Voice Time</h3><p className="stat-value">{formatDynamicTime(channelData.totalSeconds)}</p><div className="average-note">({channelData.totalHours} hours)</div></div>
                            <div className="stat-card"><h3>Unique Users</h3><p className="stat-value">{channelData.uniqueUsers.toLocaleString()}</p></div>
                            <div className="stat-card"><h3>Total Sessions</h3><p className="stat-value">{channelData.sessionCount.toLocaleString()}</p></div>
                          </>
                        )}
                      </div>
                      
                      {averagesData.daysInPeriod > 0 && (
                        <div className="averages-section">
                          <h2 className="section-title">Averages</h2>
                          <div className="averages-grid">
                            <div className="average-card"><h3>Per User</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerUser)}</p></div>
                            <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                            <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                            <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                          </div>
                        </div>
                      )}
                      
                      <div className="leaderboards-section">
                        <h2 className="section-title">Top Users in {channelData?.name || 'Channel'}</h2>
                        <div className="leaderboards-stack">
                          {loadingChannelTopUsers ? <LoadingCard /> : channelTopUsers && channelTopUsers.length > 0 ? (
                            <div className="leaderboard-wrapper">
                              <Leaderboard
                                data={channelTopUsers}
                                title="Top Users by Voice"
                                valueLabel="Time"
                                valueFormatter={formatValue}
                                showProfilePictures={true}
                                itemType="user"
                                nameKey="name"
                                valueKey="value"
                                idKey="userId"
                                backgroundColor="transparent"
                                cardBackground="#1a1a1a"
                                accentColor="#aa00ff"
                                getProfilePicture={async (userId) => {
                                  const user = channelTopUsers.find(u => u.userId === userId);
                                  return user?.avatar || null;
                                }}
                              />
                            </div>
                          ) : <div className="no-data-message">No user data available for this channel</div>}
                        </div>
                      </div>
                      
                      <div className="charts-section">
                        <h2 className="section-title">Channel Voice Activity Over Time</h2>
                        <div className="chart-wrapper">
                          {loadingChannelTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : channelTimeseriesData.length > 0 ? (
                            <InteractiveLineChart data={channelTimeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                          ) : <div className="no-chart-data">No timeseries data available for this channel</div>}
                        </div>
                      </div>
                    </>
                  )}
                </>
              )}
              
              {/* Category View */}
              {selectedView === 'category' && (
                <>
                  {!selectedCategoryId ? (
                    <div className="no-selection"><h2>Select a Category</h2><p>Please select a category from the dropdown above to view its voice statistics.</p></div>
                  ) : (
                    <>
                      <div className="summary-stats">
                        {loadingSummaryStats ? (
                          <>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                            <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          </>
                        ) : categoryData && (
                          <>
                            <div className="stat-card"><h3>Total Voice Time</h3><p className="stat-value">{formatDynamicTime(categoryData.totalSeconds)}</p><div className="average-note">({categoryData.totalHours} hours)</div></div>
                            <div className="stat-card"><h3>Unique Users</h3><p className="stat-value">{categoryData.uniqueUsers.toLocaleString()}</p></div>
                            <div className="stat-card"><h3>Total Sessions</h3><p className="stat-value">{categoryData.sessionCount.toLocaleString()}</p></div>
                          </>
                        )}
                      </div>
                      
                      {averagesData.daysInPeriod > 0 && (
                        <div className="averages-section">
                          <h2 className="section-title">Averages</h2>
                          <div className="averages-grid">
                            <div className="average-card"><h3>Per User</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerUser)}</p></div>
                            <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                            <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                            <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                          </div>
                        </div>
                      )}
                      
                      <div className="leaderboards-section">
                        <h2 className="section-title">Top in {categoryData?.name || 'Category'}</h2>
                        <div className="leaderboards-stack">
                          {loadingCategoryTopUsers ? <LoadingCard /> : categoryTopUsers && categoryTopUsers.length > 0 ? (
                            <div className="leaderboard-wrapper">
                              <Leaderboard
                                data={categoryTopUsers}
                                title="Top Users by Voice"
                                valueLabel="Time"
                                valueFormatter={formatValue}
                                showProfilePictures={true}
                                itemType="user"
                                nameKey="name"
                                valueKey="value"
                                idKey="userId"
                                backgroundColor="transparent"
                                cardBackground="#1a1a1a"
                                accentColor="#aa00ff"
                                getProfilePicture={async (userId) => {
                                  const user = categoryTopUsers.find(u => u.userId === userId);
                                  return user?.avatar || null;
                                }}
                              />
                            </div>
                          ) : <div className="no-data-message">No user data available for this category</div>}
                          
                          {loadingCategoryTopChannels ? <LoadingCard /> : categoryTopChannels && categoryTopChannels.length > 0 ? (
                            <div className="leaderboard-wrapper"><Leaderboard data={categoryTopChannels} title="Top Voice Channels" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                          ) : <div className="no-data-message">No channel data available for this category</div>}
                        </div>
                      </div>
                      
                      <div className="charts-section">
                        <h2 className="section-title">Category Voice Activity Over Time</h2>
                        <div className="chart-wrapper">
                          {loadingCategoryTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : categoryTimeseriesData.length > 0 ? (
                            <InteractiveLineChart data={categoryTimeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                          ) : <div className="no-chart-data">No timeseries data available for this category</div>}
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

  // Authenticated but no server
  if (isAuthenticated && !currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="no-server">
                <h2>No Server Available</h2>
                <p>Add the bot to a Discord server to view voice statistics.</p>
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
  if (isAuthenticated && currentServer && hasAccess === false) {
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
              <AccessDenied />
            </div>
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
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => window.location.reload()} className="retry-button">Retry</button>
              </div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Authenticated user with access - full dashboard with role filter for all views
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
            <div className="filters-section">
              <div className="filter-row">
                <label>View:</label>
                <select
                  value={selectedView}
                  onChange={(e) => setSelectedView(e.target.value)}
                  className="modern-select"
                >
                  <option value="server">Server</option>
                  <option value="user">User</option>
                  <option value="channel">Channel</option>
                  <option value="category">Category</option>
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
              
              {/* Role Filter - Available for ALL views in authenticated mode */}
              <div className="filter-row entity-filter">
                <label>Role Filter:</label>
                <div className="entity-selector">
                  <input
                    type="text"
                    placeholder="Search role to filter all data..."
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
                              <span className="entity-name">{user.name || `User ${user.id.slice(-4)}`}</span>
                            </div>
                            <span className="entity-id">ID: {user.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
              
              {selectedView === 'channel' && (
                <div className="filter-row entity-filter">
                  <label>Channel:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search voice channel..."
                      value={channelSearch}
                      onChange={(e) => setChannelSearch(e.target.value)}
                      onFocus={() => setShowChannelDropdown(true)}
                      onBlur={() => setTimeout(() => setShowChannelDropdown(false), 200)}
                      className="modern-entity-search"
                    />
                    {showChannelDropdown && filteredChannels.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredChannels.slice(0, 20).map(channel => (
                          <div
                            key={channel.id}
                            className={`entity-option ${selectedChannelId === channel.id ? 'selected' : ''}`}
                            onMouseDown={() => handleChannelSelect(channel)}
                          >
                            <div className="entity-info">
                              <span className="entity-name">{channel.name}</span>
                              <span className="entity-id">Voice Channel</span>
                            </div>
                            <span className="entity-id">ID: {channel.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
              
              {selectedView === 'category' && (
                <div className="filter-row entity-filter">
                  <label>Category:</label>
                  <div className="entity-selector">
                    <input
                      type="text"
                      placeholder="Search by name or ID..."
                      value={categorySearch}
                      onChange={(e) => setCategorySearch(e.target.value)}
                      onFocus={() => setShowCategoryDropdown(true)}
                      onBlur={() => setTimeout(() => setShowCategoryDropdown(false), 200)}
                      className="modern-entity-search"
                    />
                    {showCategoryDropdown && filteredCategories.length > 0 && (
                      <div className="entity-dropdown">
                        {filteredCategories.slice(0, 20).map(category => (
                          <div
                            key={category.id}
                            className={`entity-option ${selectedCategoryId === category.id ? 'selected' : ''}`}
                            onMouseDown={() => handleCategorySelect(category)}
                          >
                            <div className="entity-info">
                              <span className="entity-name">{category.name}</span>
                            </div>
                            <span className="entity-id">ID: {category.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            
            {/* Server View */}
            {selectedView === 'server' && (
              <>
                <div className="summary-stats">
                  {loadingSummaryStats ? (
                    <>
                      <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                      <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                      <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                    </>
                  ) : serverData && (
                    <>
                      <div className="stat-card">
                        <h3>Total Voice Time</h3>
                        <p className="stat-value">{formatDynamicTime(serverData.totalSeconds)}</p>
                        <div className="average-note">({serverData.totalHours} hours)</div>
                      </div>
                      <div className="stat-card">
                        <h3>Active Users</h3>
                        <p className="stat-value">{serverData.totalActiveUsers.toLocaleString()}</p>
                      </div>
                      <div className="stat-card">
                        <h3>Total Sessions</h3>
                        <p className="stat-value">{serverData.sessionCount.toLocaleString()}</p>
                      </div>
                    </>
                  )}
                </div>
                
                {averagesData.daysInPeriod > 0 && (
                  <div className="averages-section">
                    <h2 className="section-title">Averages</h2>
                    <div className="averages-grid">
                      <div className="average-card"><h3>Per User</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerUser)}</p></div>
                      <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                      <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                      <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                    </div>
                  </div>
                )}
                
                <div className="leaderboards-section">
                  <h2 className="section-title">Leaderboards</h2>
                  <div className="leaderboards-stack">
                    {loadingTopUsers ? <LoadingCard /> : topUsers.length > 0 ? (
                      <div className="leaderboard-wrapper">
                        <Leaderboard
                          data={topUsers}
                          title="Top Users by Voice"
                          valueLabel="Time"
                          valueFormatter={formatValue}
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
                        />
                      </div>
                    ) : <div className="no-data-message">No user data available {selectedRoleId ? 'with this role filter' : ''}</div>}
                    
                    {loadingTopChannels ? <LoadingCard /> : topChannels.length > 0 ? (
                      <div className="leaderboard-wrapper"><Leaderboard data={topChannels} title="Top Voice Channels" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                    ) : <div className="no-data-message">No channel data available {selectedRoleId ? 'with this role filter' : ''}</div>}

                    {loadingTopCategories ? <LoadingCard /> : topCategories.length > 0 ? (
                      <div className="leaderboard-wrapper"><Leaderboard data={topCategories} title="Top Categories by Voice" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="category" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                    ) : <div className="no-data-message">No category data available {selectedRoleId ? 'with this role filter' : ''}</div>}
                  </div>
                </div>
                
                <div className="charts-section">
                  <h2 className="section-title">Voice Activity Over Time</h2>
                  <div className="chart-wrapper">
                    {loadingTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : timeseriesData.length > 0 ? (
                      <InteractiveLineChart data={timeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                    ) : <div className="no-chart-data">No timeseries data available {selectedRoleId ? 'with this role filter' : ''}</div>}
                  </div>
                </div>
                
                <div className="charts-section">
                  <h2 className="section-title">Most Active Hours (Voice)</h2>
                  <div className="chart-wrapper">
                    {loadingHourlyDistribution ? <LoadingSpinner size="large" text="Loading hourly data..." /> : hourlyDistribution.length > 0 && hourlyDistribution.some(item => item.value > 0) ? (
                      <TimezonePieChart hourlyData={hourlyDistribution.map(item => item.value)} timezone={serverTimezone} activityType="Voice" valueFormatter={formatDynamicTime} guildName={currentServer?.name || "Server"} daysBack={timePeriod === "all" ? null : parseInt(timePeriod)} />
                    ) : <div className="no-chart-data">No hourly data available {selectedRoleId ? 'with this role filter' : ''}</div>}
                  </div>
                </div>
              </>
            )}
            
            {/* User View */}
            {selectedView === 'user' && (
              <>
                {!selectedUserId ? (
                  <div className="no-selection"><h2>Select a User</h2><p>Please select a user from the dropdown above to view their voice statistics.</p></div>
                ) : (
                  <>
                    <div className="summary-stats">
                      {loadingSummaryStats ? (
                        <>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        </>
                      ) : userData && (
                        <>
                          <div className="stat-card"><h3>Total Voice Time</h3><p className="stat-value">{formatDynamicTime(userData.totalSeconds)}</p><div className="average-note">({userData.totalHours} hours)</div></div>
                          <div className="stat-card"><h3>Voice Sessions</h3><p className="stat-value">{userData.sessionCount.toLocaleString()}</p></div>
                        </>
                      )}
                    </div>
                    
                    {averagesData.daysInPeriod > 0 && (
                      <div className="averages-section">
                        <h2 className="section-title">Averages</h2>
                        <div className="averages-grid">
                          <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                          <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                          <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                        </div>
                      </div>
                    )}
                    
                    <div className="leaderboards-section">
                      <h2 className="section-title">{userData?.name || 'User'}'s Activity</h2>
                      <div className="leaderboards-stack">
                        {loadingUserTopChannels ? <LoadingCard /> : userTopChannels.length > 0 ? (
                          <div className="leaderboard-wrapper"><Leaderboard data={userTopChannels} title="Top Voice Channels" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                        ) : <div className="no-data-message">No channel data available for this user {selectedRoleId ? 'with this role filter' : ''}</div>}
                        
                        {loadingUserTopCategories ? <LoadingCard /> : userTopCategories.length > 0 ? (
                          <div className="leaderboard-wrapper"><Leaderboard data={userTopCategories} title="Top Categories by Voice" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="category" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                        ) : <div className="no-data-message">No category data available for this user {selectedRoleId ? 'with this role filter' : ''}</div>}
                      </div>
                    </div>
                    
                    <div className="charts-section">
                      <h2 className="section-title">{userData?.name || 'User'}'s Voice Activity Over Time</h2>
                      <div className="chart-wrapper">
                        {loadingUserTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : userTimeseriesData.length > 0 ? (
                          <InteractiveLineChart data={userTimeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                        ) : <div className="no-chart-data">No timeseries data available for this user {selectedRoleId ? 'with this role filter' : ''}</div>}
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
            
            {/* Channel View */}
            {selectedView === 'channel' && (
              <>
                {!selectedChannelId ? (
                  <div className="no-selection"><h2>Select a Voice Channel</h2><p>Please select a voice channel from the dropdown above to view its statistics.</p></div>
                ) : (
                  <>
                    <div className="summary-stats">
                      {loadingSummaryStats ? (
                        <>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        </>
                      ) : channelData && (
                        <>
                          <div className="stat-card"><h3>Total Voice Time</h3><p className="stat-value">{formatDynamicTime(channelData.totalSeconds)}</p><div className="average-note">({channelData.totalHours} hours)</div></div>
                          <div className="stat-card"><h3>Unique Users</h3><p className="stat-value">{channelData.uniqueUsers.toLocaleString()}</p></div>
                          <div className="stat-card"><h3>Total Sessions</h3><p className="stat-value">{channelData.sessionCount.toLocaleString()}</p></div>
                        </>
                      )}
                    </div>
                    
                    {averagesData.daysInPeriod > 0 && (
                      <div className="averages-section">
                        <h2 className="section-title">Averages</h2>
                        <div className="averages-grid">
                          <div className="average-card"><h3>Per User</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerUser)}</p></div>
                          <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                          <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                          <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                        </div>
                      </div>
                    )}
                    
                    <div className="leaderboards-section">
                      <h2 className="section-title">Top Users in {channelData?.name || 'Channel'}</h2>
                      <div className="leaderboards-stack">
                        {loadingChannelTopUsers ? <LoadingCard /> : channelTopUsers && channelTopUsers.length > 0 ? (
                          <div className="leaderboard-wrapper">
                            <Leaderboard
                              data={channelTopUsers}
                              title="Top Users by Voice"
                              valueLabel="Time"
                              valueFormatter={formatValue}
                              showProfilePictures={true}
                              itemType="user"
                              nameKey="name"
                              valueKey="value"
                              idKey="userId"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#aa00ff"
                              getProfilePicture={async (userId) => {
                                const user = channelTopUsers.find(u => u.userId === userId);
                                return user?.avatar || null;
                              }}
                            />
                          </div>
                        ) : <div className="no-data-message">No user data available for this channel {selectedRoleId ? 'with this role filter' : ''}</div>}
                      </div>
                    </div>
                    
                    <div className="charts-section">
                      <h2 className="section-title">Channel Voice Activity Over Time</h2>
                      <div className="chart-wrapper">
                        {loadingChannelTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : channelTimeseriesData.length > 0 ? (
                          <InteractiveLineChart data={channelTimeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                        ) : <div className="no-chart-data">No timeseries data available for this channel {selectedRoleId ? 'with this role filter' : ''}</div>}
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
            
            {/* Category View */}
            {selectedView === 'category' && (
              <>
                {!selectedCategoryId ? (
                  <div className="no-selection"><h2>Select a Category</h2><p>Please select a category from the dropdown above to view its voice statistics.</p></div>
                ) : (
                  <>
                    <div className="summary-stats">
                      {loadingSummaryStats ? (
                        <>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                        </>
                      ) : categoryData && (
                        <>
                          <div className="stat-card"><h3>Total Voice Time</h3><p className="stat-value">{formatDynamicTime(categoryData.totalSeconds)}</p><div className="average-note">({categoryData.totalHours} hours)</div></div>
                          <div className="stat-card"><h3>Unique Users</h3><p className="stat-value">{categoryData.uniqueUsers.toLocaleString()}</p></div>
                          <div className="stat-card"><h3>Total Sessions</h3><p className="stat-value">{categoryData.sessionCount.toLocaleString()}</p></div>
                        </>
                      )}
                    </div>
                    
                    {averagesData.daysInPeriod > 0 && (
                      <div className="averages-section">
                        <h2 className="section-title">Averages</h2>
                        <div className="averages-grid">
                          <div className="average-card"><h3>Per User</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerUser)}</p></div>
                          <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerDay)}</p></div>
                          <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerMonth)}</p></div>
                          <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatDynamicTime(averagesData.avgPerYear)}</p></div>
                        </div>
                      </div>
                    )}
                    
                    <div className="leaderboards-section">
                      <h2 className="section-title">Top in {categoryData?.name || 'Category'}</h2>
                      <div className="leaderboards-stack">
                        {loadingCategoryTopUsers ? <LoadingCard /> : categoryTopUsers && categoryTopUsers.length > 0 ? (
                          <div className="leaderboard-wrapper">
                            <Leaderboard
                              data={categoryTopUsers}
                              title="Top Users by Voice"
                              valueLabel="Time"
                              valueFormatter={formatValue}
                              showProfilePictures={true}
                              itemType="user"
                              nameKey="name"
                              valueKey="value"
                              idKey="userId"
                              backgroundColor="transparent"
                              cardBackground="#1a1a1a"
                              accentColor="#aa00ff"
                              getProfilePicture={async (userId) => {
                                const user = categoryTopUsers.find(u => u.userId === userId);
                                return user?.avatar || null;
                              }}
                            />
                          </div>
                        ) : <div className="no-data-message">No user data available for this category {selectedRoleId ? 'with this role filter' : ''}</div>}
                        
                        {loadingCategoryTopChannels ? <LoadingCard /> : categoryTopChannels && categoryTopChannels.length > 0 ? (
                          <div className="leaderboard-wrapper"><Leaderboard data={categoryTopChannels} title="Top Voice Channels" valueLabel="Time" valueFormatter={formatValue} showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff" /></div>
                        ) : <div className="no-data-message">No channel data available for this category {selectedRoleId ? 'with this role filter' : ''}</div>}
                      </div>
                    </div>
                    
                    <div className="charts-section">
                      <h2 className="section-title">Category Voice Activity Over Time</h2>
                      <div className="chart-wrapper">
                        {loadingCategoryTimeseries ? <LoadingSpinner size="large" text="Loading chart data..." /> : categoryTimeseriesData.length > 0 ? (
                          <InteractiveLineChart data={categoryTimeseriesData} lines={[{ name: 'Voice Time', dataKey: 'seconds', color: '#aa00ff' }]} title="Daily Voice Activity" valueFormatter={(seconds) => formatDynamicTime(seconds)} />
                        ) : <div className="no-chart-data">No timeseries data available for this category {selectedRoleId ? 'with this role filter' : ''}</div>}
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
    <VoiceDashboard />
  </React.StrictMode>
);

export default VoiceDashboard;