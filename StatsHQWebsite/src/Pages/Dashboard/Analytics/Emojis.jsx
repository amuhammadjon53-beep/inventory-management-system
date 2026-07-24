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
// FIXED CACHING SYSTEM - Only caches valid names
// ============================================

// NAVBAR HEIGHT
const NAVBAR_HEIGHT = "80px";

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

// Cache key generator
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

// Format number with commas
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
const formatEmojiValue = (value) => {
  if (!value) return "0";
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return formatNumber(value);
};

// Helper function to parse Discord custom emoji and get CDN URL
const parseDiscordEmoji = (emojiStr) => {
  if (!emojiStr || typeof emojiStr !== 'string') return null;
  
  const match = emojiStr.match(/^<(a?):(\w+):(\d+)>$/);
  
  if (match) {
    const isAnimated = match[1] === 'a';
    const name = match[2];
    const id = match[3];
    return {
      type: 'custom',
      isAnimated,
      name,
      id,
      url: `https://cdn.discordapp.com/emojis/${id}.${isAnimated ? 'gif' : 'png'}?size=48`
    };
  }
  
  return {
    type: 'standard',
    value: emojiStr
  };
};

// Component to render emoji
const EmojiRenderer = ({ emojiStr, size = '24px', className = '' }) => {
  const [imageError, setImageError] = useState(false);
  const parsed = parseDiscordEmoji(emojiStr);
  
  if (!parsed) return null;
  
  if (parsed.type === 'custom' && !imageError) {
    return (
      <img 
        src={parsed.url}
        alt={parsed.name}
        className={`custom-emoji ${className}`}
        style={{ 
          width: size, 
          height: size, 
          verticalAlign: 'middle',
          objectFit: 'contain'
        }}
        onError={() => setImageError(true)}
      />
    );
  }
  
  return <span className={className} style={{ fontSize: size }}>{parsed.value || emojiStr}</span>;
};

// Loading Components
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
      <p>You don't have permission to view this server's emoji statistics.</p>
      <p>This server requires <strong>{requiredPermission}</strong> permissions.</p>
      <p className="setting-note" style={{ marginTop: '12px', fontSize: '12px', color: '#666' }}>
        Note: Server owners automatically have Administrator permission.
      </p>
    </div>
  );
};

// Wrapper for Leaderboard that uses EmojiRenderer for emoji items
const LeaderboardWithEmojis = (props) => {
  if (props.itemType === 'emoji') {
    const { data, ...restProps } = props;
    
    const enhancedData = data.map(item => ({
      ...item,
      renderName: () => <EmojiRenderer emojiStr={item.name} size="24px" />
    }));
    
    return (
      <Leaderboard
        {...restProps}
        data={enhancedData}
        nameKey="name"
        renderName={(item) => item.renderName ? item.renderName() : item.name}
      />
    );
  }
  
  return <Leaderboard {...props} />;
};

// ============================================
// FIXED USERNAME FETCHING FUNCTIONS
// ============================================

// Fetch single user's basic info (username only, no avatar)
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

// Batch fetch user basic info (usernames only)
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

// Fetch user avatar (only for top 3 users)
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

const EmojiDashboard = () => {
  // State
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
  
  const [usageType, setUsageType] = useState("all");
  const [userFilterType, setUserFilterType] = useState("none");
  const [userFilterId, setUserFilterId] = useState("");
  const [userFilterSearch, setUserFilterSearch] = useState("");
  const [showUserFilterDropdown, setShowUserFilterDropdown] = useState(false);
  const [userFilteredChannels, setUserFilteredChannels] = useState([]);
  const [userFilteredCategories, setUserFilteredCategories] = useState([]);
  
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
  const [currentServer, setCurrentServer] = useState(null);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isPublicMode, setIsPublicMode] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [currentUserId, setCurrentUserId] = useState(null);
  const [apiError, setApiError] = useState(null);
  const [serverTimezone, setServerTimezone] = useState('UTC');
  const [retentionAlert, setRetentionAlert] = useState(null);
  const [retentionDismissed, setRetentionDismissed] = useState(false);
  
  const [loadingSummaryStats, setLoadingSummaryStats] = useState(true);
  const [loadingAverages, setLoadingAverages] = useState(true);
  const [loadingChart, setLoadingChart] = useState(true);
  
  const [serverData, setServerData] = useState(null);
  const [userData, setUserData] = useState(null);
  const [channelData, setChannelData] = useState(null);
  const [categoryData, setCategoryData] = useState(null);
  const [timeseriesData, setTimeseriesData] = useState([]);
  
  const [averagesData, setAveragesData] = useState({
    avgPerUser: 0,
    avgPerDay: 0,
    avgPerMonth: 0,
    avgPerYear: 0,
    daysInPeriod: 30
  });
  
  const [topEmojis, setTopEmojis] = useState([]);
  const [topUsers, setTopUsers] = useState([]);
  const [topChannels, setTopChannels] = useState([]);
  const [topCategories, setTopCategories] = useState([]);
  
  const [userTopEmojis, setUserTopEmojis] = useState([]);
  const [userTopChannels, setUserTopChannels] = useState([]);
  const [userTopCategories, setUserTopCategories] = useState([]);
  
  const [channelTopEmojis, setChannelTopEmojis] = useState([]);
  const [channelTopUsers, setChannelTopUsers] = useState([]);
  
  const [categoryTopEmojis, setCategoryTopEmojis] = useState([]);
  const [categoryTopUsers, setCategoryTopUsers] = useState([]);
  const [categoryTopChannels, setCategoryTopChannels] = useState([]);
  
  const [userChannels, setUserChannels] = useState([]);
  const [userCategories, setUserCategories] = useState([]);
  
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

  const [loadingTopEmojis, setLoadingTopEmojis] = useState(true);
  const [loadingTopUsers, setLoadingTopUsers] = useState(true);
  const [loadingTopChannels, setLoadingTopChannels] = useState(true);
  const [loadingTopCategories, setLoadingTopCategories] = useState(true);
  const [loadingUserTopEmojis, setLoadingUserTopEmojis] = useState(true);
  const [loadingUserTopChannels, setLoadingUserTopChannels] = useState(true);
  const [loadingUserTopCategories, setLoadingUserTopCategories] = useState(true);
  const [loadingChannelTopEmojis, setLoadingChannelTopEmojis] = useState(true);
  const [loadingChannelTopUsers, setLoadingChannelTopUsers] = useState(true);
  const [loadingCategoryTopEmojis, setLoadingCategoryTopEmojis] = useState(true);
  const [loadingCategoryTopUsers, setLoadingCategoryTopUsers] = useState(true);
  const [loadingCategoryTopChannels, setLoadingCategoryTopChannels] = useState(true);
  const [loadingUserFilterLocations, setLoadingUserFilterLocations] = useState(false);

  const [initialLoadComplete, setInitialLoadComplete] = useState(false);
  const [rawUserIds, setRawUserIds] = useState([]);
  const [isFetchingUsernames, setIsFetchingUsernames] = useState(false);

  const fetchedRef = useRef(false);
  const initialDataLoadedRef = useRef(false);
  const didInitRef = useRef(false);
  const inFlightRequests = useRef({});
  const prevFiltersRef = useRef(JSON.stringify({
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId, usageType,
    userFilterType, userFilterId
  }));

  const channelsRef = useRef([]);
  const categoriesRef = useRef([]);
  const rolesRef = useRef([]);
  const channelNamesRef = useRef({});
  const categoryNamesRef = useRef({});

  useEffect(() => { channelsRef.current = channels; }, [channels]);
  useEffect(() => { categoriesRef.current = categories; }, [categories]);
  useEffect(() => { rolesRef.current = roles; }, [roles]);
  useEffect(() => { channelNamesRef.current = channelNames; }, [channelNames]);
  useEffect(() => { categoryNamesRef.current = categoryNames; }, [categoryNames]);

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

  // Fetch server timezone
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

  // FIX (Cause 1 from doc1): guard the mount effect so StrictMode's
  // intentional double-invoke in dev doesn't fire the whole init
  // sequence (auth -> servers -> settings -> stats fan-out) twice.
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

  // applyServerTimePeriod returns computed values synchronously (in
  // addition to calling setState), so callers can use the resolved
  // values immediately instead of waiting for a re-render.
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
      
      // Handle cases where one date is missing
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
                // NOTE: checkServerAccess only determines access/permissions now.
                // It no longer fetches settings/time period or triggers a data
                // fetch itself -- the unified [currentServer, hasAccess] effect
                // below owns that whole lifecycle exactly once.
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

  // FIX: checkServerAccess now ONLY determines access/permissions.
  // It used to also fetch settings a second time, apply the time period
  // again, and kick off its own data fetch -- racing with the
  // "fetchAndApplyTimePeriod" effect and the "load all data" effect.
  // All of that is now owned exclusively by the single unified
  // [currentServer, hasAccess] effect further down.
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
        // NOTE: no time-period application or data fetch here anymore --
        // the unified [currentServer, hasAccess] effect below handles that.
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

  // Shared helper: resolve the effective time-period params either from
  // explicit overrides (used right after settings resolve, before state
  // has re-rendered) or from current state (used for user-driven filter
  // changes after init, when state is already committed). Every fetch
  // function below goes through this instead of reading timePeriod /
  // customDaysBack / etc directly, so there is one source of truth for
  // "what time window are we querying".
  const computeTimeParams = (overrides = {}) => {
    const effectiveTimePeriod = overrides.timePeriod ?? timePeriod;
    const effectiveCustomDaysBack = overrides.customDaysBack ?? customDaysBack;
    const effectiveCustomStartDate = overrides.customStartDate ?? customStartDate;
    const effectiveCustomEndDate = overrides.customEndDate ?? customEndDate;

    let daysBack = 30;
    let startDate = null;
    let endDate = null;

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

    const daysInPeriod = daysBack === 2000 ? 2000 : daysBack;

    return {
      effectiveTimePeriod,
      effectiveCustomDaysBack,
      effectiveCustomStartDate,
      effectiveCustomEndDate,
      daysBack,
      startDate,
      endDate,
      daysInPeriod
    };
  };

  // fetchDataWithParams - uses overrides instead of stale state, and
  // dedupes in-flight requests so overlapping triggers (e.g. a fast
  // remount) reuse the same promise instead of firing twice.
  const fetchDataWithParams = async (overrides = {}) => {
    if (!currentServer || !hasAccess) return;

    const requestKey = `${currentServer.id}:${selectedView}:${JSON.stringify(overrides)}`;
    if (inFlightRequests.current[requestKey]) {
      return inFlightRequests.current[requestKey];
    }

    const promise = (async () => {
      setLoading(true);
      setApiError(null);

      const { effectiveTimePeriod, daysBack, startDate, endDate, daysInPeriod } = computeTimeParams(overrides);

      try {
        const roleFilterArray = (selectedView === 'server' || selectedView === 'channel' || selectedView === 'category') && selectedRoleId ? [String(selectedRoleId)] : null;

        const baseRequestBody = {
          guild_id: currentServer.id,
          role_filter_ids: roleFilterArray,
          usage_type: usageType === 'all' ? null : usageType,
          time_period: effectiveTimePeriod,
          days_back: daysBack
        };

        if (startDate) baseRequestBody.start_time = startDate.toISOString();
        if (endDate) baseRequestBody.end_time = endDate.toISOString();

        if (selectedView === 'server') await fetchServerData(baseRequestBody, daysInPeriod);
        else if (selectedView === 'user' && selectedUserId) await fetchUserData(baseRequestBody, daysInPeriod);
        else if (selectedView === 'channel' && selectedChannelId) await fetchChannelData(baseRequestBody, daysInPeriod);
        else if (selectedView === 'category' && selectedCategoryId) await fetchCategoryData(baseRequestBody, daysInPeriod);

        await fetchTimeseriesData(baseRequestBody);

      } catch (error) {
        console.error('Error fetching data:', error);
        setApiError(error.message);
      } finally {
        setLoading(false);
        fetchedRef.current = true;
        delete inFlightRequests.current[requestKey];
      }
    })();

    inFlightRequests.current[requestKey] = promise;
    return promise;
  };

  // ============================================
  // FETCH ALL ROLES
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

  // ============================================
  // FETCH ALL USERS
  // ============================================
  // Accepts optional time-period overrides so the unified init effect can
  // call this with the just-resolved server settings instead of the
  // default state (which hasn't committed yet).
  const fetchAllUsers = async (overrides = {}) => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setUsersLoaded(false);
    
    const { effectiveTimePeriod, effectiveCustomDaysBack, effectiveCustomStartDate, effectiveCustomEndDate, daysBack, startDate, endDate } = computeTimeParams(overrides);
    
    const cacheKey = getCacheKey('emoji-users', currentServer.id, { 
      timePeriod: effectiveTimePeriod,
      customDaysBack: effectiveCustomDaysBack,
      customStartDate: effectiveCustomStartDate,
      customEndDate: effectiveCustomEndDate,
      roleId: selectedRoleId,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setUsers(cached.users || []);
      setFilteredUsers(cached.users || []);
      setUserNames(cached.userNames || {});
      setProfilePictures(cached.profilePictures || {});
      setRawUserIds((cached.users || []).map(u => u.id));
      setUsersLoaded(true);
      return;
    }
    
    try {
      let url;
      if (isPublic) {
        url = `${API_BASE_URL}/api/public/emoji/users?guild_id=${currentServer.id}`;
      } else {
        url = `${API_BASE_URL}/api/emoji/users?guild_id=${currentServer.id}`;
      }
      
      if (startDate && endDate) {
        url += `&start_time=${startDate.toISOString()}&end_time=${endDate.toISOString()}`;
      } else if (startDate) {
        url += `&start_time=${startDate.toISOString()}`;
      } else if (endDate) {
        url += `&end_time=${endDate.toISOString()}`;
      } else if (daysBack && daysBack !== 2000) {
        url += `&days_back=${daysBack}`;
      }
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (!response.ok) {
        setUsersLoaded(true);
        return;
      }
      
      const data = await response.json();
      
      if (!data.user_ids || data.user_ids.length === 0) {
        serverDataCache.set(cacheKey, { users: [], userNames: {}, profilePictures: {} });
        setUsers([]);
        setFilteredUsers([]);
        setUserNames({});
        setProfilePictures({});
        setRawUserIds([]);
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
      
      userList.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      
      const cacheData = { users: userList, userNames: {}, profilePictures: {} };
      serverDataCache.set(cacheKey, cacheData);
      
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

  // ============================================
  // FETCH ALL CHANNELS
  // ============================================
  // Accepts optional time-period overrides, same reasoning as fetchAllUsers.
  const fetchAllChannels = async (overrides = {}) => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setChannelsLoaded(false);
    
    const { effectiveTimePeriod, effectiveCustomDaysBack, effectiveCustomStartDate, effectiveCustomEndDate, daysBack, startDate, endDate } = computeTimeParams(overrides);
    
    const cacheKey = getCacheKey('emoji-channels', currentServer.id, { 
      public: isPublic,
      timePeriod: effectiveTimePeriod,
      customDaysBack: effectiveCustomDaysBack,
      customStartDate: effectiveCustomStartDate,
      customEndDate: effectiveCustomEndDate
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setChannels(cached.channelList || []);
      setFilteredChannels(cached.channelList || []);
      setChannelNames(cached.nameMap || {});
      setChannelsLoaded(true);
      return;
    }
    
    try {
      let emojiChannelsUrl;
      if (isPublic) {
        emojiChannelsUrl = `${API_BASE_URL}/api/public/emoji/channels?guild_id=${currentServer.id}`;
      } else {
        emojiChannelsUrl = `${API_BASE_URL}/api/emoji/channels?guild_id=${currentServer.id}`;
      }
      
      if (startDate && endDate) {
        emojiChannelsUrl += `&start_time=${startDate.toISOString()}&end_time=${endDate.toISOString()}`;
      } else if (startDate) {
        emojiChannelsUrl += `&start_time=${startDate.toISOString()}`;
      } else if (endDate) {
        emojiChannelsUrl += `&end_time=${endDate.toISOString()}`;
      } else if (daysBack && daysBack !== 2000) {
        emojiChannelsUrl += `&days_back=${daysBack}`;
      }
      
      const response = await fetch(emojiChannelsUrl, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      let channelList = [];
      let nameMap = {};
      
      if (response.ok) {
        const data = await response.json();
        
        if (data.channel_ids && data.channel_ids.length > 0) {
          const channelsUrl = `${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`;
          
          const channelsResponse = await fetch(channelsUrl, {
            credentials: isPublic ? 'omit' : 'include'
          });
          
          if (channelsResponse.ok) {
            const allChannels = await channelsResponse.json();
            const channelMap = {};
            allChannels.forEach(ch => {
              channelMap[ch.id] = ch;
            });
            
            data.channel_ids.forEach(channelId => {
              const channel = channelMap[channelId];
              if (channel) {
                channelList.push({
                  id: channelId,
                  name: channel.name,
                  type: channel.type,
                  category_id: channel.category_id,
                  searchString: `${channel.name} ${channelId}`.toLowerCase()
                });
                nameMap[channelId] = channel.name;
              } else {
                channelList.push({
                  id: channelId,
                  name: `Channel ${channelId}`,
                  type: 'unknown',
                  category_id: null,
                  searchString: `${channelId}`.toLowerCase()
                });
                nameMap[channelId] = `Channel ${channelId}`;
              }
            });
          } else {
            data.channel_ids.forEach(channelId => {
              channelList.push({
                id: channelId,
                name: `Channel ${channelId}`,
                type: 'unknown',
                category_id: null,
                searchString: `${channelId}`.toLowerCase()
              });
              nameMap[channelId] = `Channel ${channelId}`;
            });
          }
        }
      }
      
      const cacheData = { channelList, nameMap };
      serverDataCache.set(cacheKey, cacheData);
      
      setChannels(channelList);
      setFilteredChannels(channelList);
      setChannelNames(nameMap);
      
    } catch (error) {
      console.error('Error fetching channels:', error);
      setChannels([]);
      setFilteredChannels([]);
      setChannelNames({});
    } finally {
      setChannelsLoaded(true);
    }
  };

  // ============================================
  // FETCH ALL CATEGORIES
  // ============================================
  // Accepts optional time-period overrides, same reasoning as fetchAllUsers.
  const fetchAllCategories = async (overrides = {}) => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setCategoriesLoaded(false);
    
    const { effectiveTimePeriod, effectiveCustomDaysBack, effectiveCustomStartDate, effectiveCustomEndDate, daysBack, startDate, endDate } = computeTimeParams(overrides);
    
    const cacheKey = getCacheKey('emoji-categories', currentServer.id, { 
      public: isPublic,
      timePeriod: effectiveTimePeriod,
      customDaysBack: effectiveCustomDaysBack,
      customStartDate: effectiveCustomStartDate,
      customEndDate: effectiveCustomEndDate
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setCategories(cached.categoryList || []);
      setFilteredCategories(cached.categoryList || []);
      setCategoryNames(cached.nameMap || {});
      setCategoriesLoaded(true);
      return;
    }
    
    try {
      let emojiCategoriesUrl;
      if (isPublic) {
        emojiCategoriesUrl = `${API_BASE_URL}/api/public/emoji/categories?guild_id=${currentServer.id}`;
      } else {
        emojiCategoriesUrl = `${API_BASE_URL}/api/emoji/categories?guild_id=${currentServer.id}`;
      }
      
      if (startDate && endDate) {
        emojiCategoriesUrl += `&start_time=${startDate.toISOString()}&end_time=${endDate.toISOString()}`;
      } else if (startDate) {
        emojiCategoriesUrl += `&start_time=${startDate.toISOString()}`;
      } else if (endDate) {
        emojiCategoriesUrl += `&end_time=${endDate.toISOString()}`;
      } else if (daysBack && daysBack !== 2000) {
        emojiCategoriesUrl += `&days_back=${daysBack}`;
      }
      
      const response = await fetch(emojiCategoriesUrl, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      let categoryList = [];
      let nameMap = {};
      
      if (response.ok) {
        const data = await response.json();
        
        if (data.category_ids && data.category_ids.length > 0) {
          const categoriesUrl = `${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`;
          
          const categoriesResponse = await fetch(categoriesUrl, {
            credentials: isPublic ? 'omit' : 'include'
          });
          
          if (categoriesResponse.ok) {
            const allCategories = await categoriesResponse.json();
            const categoryMap = {};
            allCategories.forEach(cat => {
              categoryMap[cat.id] = cat;
            });
            
            data.category_ids.forEach(categoryId => {
              const category = categoryMap[categoryId];
              if (category) {
                categoryList.push({
                  id: categoryId,
                  name: category.name,
                  searchString: `${category.name} ${categoryId}`.toLowerCase()
                });
                nameMap[categoryId] = category.name;
              } else {
                categoryList.push({
                  id: categoryId,
                  name: `Category ${categoryId}`,
                  searchString: `${categoryId}`.toLowerCase()
                });
                nameMap[categoryId] = `Category ${categoryId}`;
              }
            });
          } else {
            data.category_ids.forEach(categoryId => {
              categoryList.push({
                id: categoryId,
                name: `Category ${categoryId}`,
                searchString: `${categoryId}`.toLowerCase()
              });
              nameMap[categoryId] = `Category ${categoryId}`;
            });
          }
        }
      }
      
      const cacheData = { categoryList, nameMap };
      serverDataCache.set(cacheKey, cacheData);
      
      setCategories(categoryList);
      setFilteredCategories(categoryList);
      setCategoryNames(nameMap);
      
    } catch (error) {
      console.error('Error fetching categories:', error);
      setCategories([]);
      setFilteredCategories([]);
      setCategoryNames({});
    } finally {
      setCategoriesLoaded(true);
    }
  };

  // Fetch user locations
  const fetchUserLocations = async (userId) => {
    if (!currentServer || !userId) return;
    
    const isPublic = isPublicMode;
    setLoadingUserFilterLocations(true);
    
    try {
      const url = isPublic
        ? `${API_BASE_URL}/api/public/emoji/user/locations?guild_id=${currentServer.id}&user_id=${userId}`
        : `${API_BASE_URL}/api/emoji/user/locations?guild_id=${currentServer.id}&user_id=${userId}`;
      
      const response = await fetch(url, {
        credentials: isPublic ? 'omit' : 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        
        const channelsList = [];
        const categoriesList = [];
        
        if (data.channels?.ids) {
          data.channels.ids.forEach(channelId => {
            const channel = channelsRef.current.find(c => String(c.id) === String(channelId));
            const channelName = channel?.name || `Channel ${channelId}`;
            channelsList.push({
              id: channelId,
              name: channelName,
              type: 'channel',
              searchString: `${channelName} ${channelId}`.toLowerCase()
            });
          });
        }
        
        if (data.categories?.ids) {
          data.categories.ids.forEach(categoryId => {
            const category = categoriesRef.current.find(c => String(c.id) === String(categoryId));
            const categoryName = category?.name || `Category ${categoryId}`;
            categoriesList.push({
              id: categoryId,
              name: categoryName,
              type: 'category',
              searchString: `${categoryName} ${categoryId}`.toLowerCase()
            });
          });
        }
        
        setUserChannels(channelsList);
        setUserCategories(categoriesList);
        setUserFilteredChannels(channelsList);
        setUserFilteredCategories(categoriesList);
      }
    } catch (error) {
      console.error('Error fetching user locations:', error);
    } finally {
      setLoadingUserFilterLocations(false);
    }
  };

  const getDaysBack = () => {
    if (timePeriod === "all") return 2000;
    if (timePeriod === "custom-lookback") return parseInt(customDaysBack) || 30;
    if (timePeriod === "custom-range") {
      if (!customStartDate || !customEndDate) return 30;
      const start = new Date(customStartDate);
      const end = new Date(customEndDate);
      const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
      return days > 0 ? days : 30;
    }
    return parseInt(timePeriod);
  };

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

  const calculateAverages = (totalUsage, uniqueUsers, daysInPeriod) => {
    if (daysInPeriod === 0) return { avgPerUser: 0, avgPerDay: 0, avgPerMonth: 0, avgPerYear: 0, daysInPeriod: 0 };
    
    const avgPerUser = uniqueUsers > 0 ? totalUsage / uniqueUsers : 0;
    const avgPerDay = totalUsage / daysInPeriod;
    const avgPerMonth = avgPerDay * 30;
    const avgPerYear = avgPerDay * 365;
    
    return { avgPerUser, avgPerDay, avgPerMonth, avgPerYear, daysInPeriod };
  };

  // ============================================
  // UNIFIED "SERVER CHANGED" LIFECYCLE
  // ============================================
  // This single effect owns the entire "server changed" lifecycle:
  // reset -> fetch roles (parallel, doesn't gate anything) -> fetch
  // settings -> apply time period -> fetch users/channels/categories AND
  // the main dashboard data using the *resolved* time params -> sync the
  // filter-watcher's ref -> only then flip initialLoadComplete (which is
  // what arms the filter-watcher effect below).
  //
  // The old "fetchAndApplyTimePeriod" effect and the standalone
  // "fetch roles on currentServer change" effect have been removed
  // entirely and folded into this one, so settings are fetched exactly
  // once per server change and there's only ever one data-fetch wave.
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    
    if (initialDataLoadedRef.current === currentServer.id) return;
    
    fetchedRef.current = false;
    setInitialLoadComplete(false);
    
    setLoadingTopEmojis(true);
    setLoadingTopUsers(true);
    setLoadingTopChannels(true);
    setLoadingTopCategories(true);
    setLoadingUserTopEmojis(true);
    setLoadingUserTopChannels(true);
    setLoadingUserTopCategories(true);
    setLoadingChannelTopEmojis(true);
    setLoadingChannelTopUsers(true);
    setLoadingCategoryTopEmojis(true);
    setLoadingCategoryTopUsers(true);
    setLoadingCategoryTopChannels(true);
    setLoadingSummaryStats(true);
    setLoadingAverages(true);
    setLoadingChart(true);
    setLoading(true);
    
    setUsersLoaded(false);
    setChannelsLoaded(false);
    setCategoriesLoaded(false);
    setRolesLoaded(false);
    
    setSelectedUserId("");
    setSelectedChannelId("");
    setSelectedCategoryId("");
    setUserSearch("");
    setChannelSearch("");
    setCategorySearch("");
    setUserFilterType("none");
    setUserFilterId("");
    setUserFilterSearch("");
    
    setServerData(null);
    setUserData(null);
    setChannelData(null);
    setCategoryData(null);
    setTopEmojis([]);
    setTopUsers([]);
    setTopChannels([]);
    setTopCategories([]);
    setUserTopEmojis([]);
    setUserTopChannels([]);
    setUserTopCategories([]);
    setChannelTopEmojis([]);
    setChannelTopUsers([]);
    setCategoryTopEmojis([]);
    setCategoryTopUsers([]);
    setCategoryTopChannels([]);
    setTimeseriesData([]);
    
    profileCache.clear();
    userBasicInfoCache.clear();
    setRawUserIds([]);
    
    initialDataLoadedRef.current = currentServer.id;
    
    const initializeServer = async () => {
      // 1. roles can load in parallel, they don't gate the stats fetch
      fetchAllRoles();
      
      // 2. get the server's configured default time period BEFORE any
      //    other data fetch, so nothing below reads the stale default
      //    state (timePeriod: "30") instead of the real configured value.
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
      
      // 3. fetch users/channels/categories AND the main dashboard data,
      //    all using the resolved params directly (not stale state)
      await Promise.all([
        fetchAllUsers(timeParams),
        fetchAllChannels(timeParams),
        fetchAllCategories(timeParams)
      ]);
      
      await fetchDataWithParams(timeParams);
      
      // 4. sync prevFiltersRef to the resolved values so the
      //    filter-watcher effect below sees no diff once
      //    initialLoadComplete flips to true, and doesn't fire a
      //    duplicate fetch right after this one.
      const resolvedFilters = {
        selectedView,
        timePeriod: timeParams.timePeriod ?? timePeriod,
        customDaysBack: timeParams.customDaysBack ?? customDaysBack,
        customStartDate: timeParams.customStartDate ?? customStartDate,
        customEndDate: timeParams.customEndDate ?? customEndDate,
        selectedUserId: "",
        selectedChannelId: "",
        selectedCategoryId: "",
        selectedRoleId,
        usageType,
        userFilterType: "none",
        userFilterId: ""
      };
      const sorted = {};
      Object.keys(resolvedFilters).sort().forEach(k => { sorted[k] = resolvedFilters[k]; });
      prevFiltersRef.current = JSON.stringify(sorted);
      
      setInitialLoadComplete(true);
    };
    
    initializeServer();
  }, [currentServer, hasAccess]);

  useEffect(() => {
    if (selectedUserId) fetchUserLocations(selectedUserId);
  }, [selectedUserId]);

  // Filter change detection
  useEffect(() => {
    if (!currentServer || !initialLoadComplete || !hasAccess) return;
    
    const filterObj = {
      selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId, usageType,
      userFilterType, userFilterId
    };
    
    const sortedFilterObj = {};
    Object.keys(filterObj).sort().forEach(key => { sortedFilterObj[key] = filterObj[key]; });
    const currentFilters = JSON.stringify(sortedFilterObj);
    
    if (fetchedRef.current && prevFiltersRef.current !== currentFilters) {
      prevFiltersRef.current = currentFilters;
      
      setLoadingTopEmojis(true);
      setLoadingTopUsers(true);
      setLoadingTopChannels(true);
      setLoadingTopCategories(true);
      setLoadingUserTopEmojis(true);
      setLoadingUserTopChannels(true);
      setLoadingUserTopCategories(true);
      setLoadingChannelTopEmojis(true);
      setLoadingChannelTopUsers(true);
      setLoadingCategoryTopEmojis(true);
      setLoadingCategoryTopUsers(true);
      setLoadingCategoryTopChannels(true);
      setLoadingSummaryStats(true);
      setLoadingAverages(true);
      setLoadingChart(true);
      
      fetchDataWithParams();
    }
  }, [
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId, usageType,
    userFilterType, userFilterId, initialLoadComplete, hasAccess
  ]);
  
  useEffect(() => {
    if (currentServer && initialLoadComplete && selectedView === 'user') {
      const cacheKey = getCacheKey('emoji-users', currentServer.id, { 
        timePeriod,
        customDaysBack,
        customStartDate,
        customEndDate,
        roleId: selectedRoleId,
        public: isPublicMode
      });
      serverDataCache.clearPattern(cacheKey);
      fetchAllUsers();
    }
  }, [timePeriod, customDaysBack, customStartDate, customEndDate, currentServer, initialLoadComplete, selectedView, isPublicMode, selectedRoleId]);
  
  // Search filters
  useEffect(() => {
    if (userSearch.trim() === "") setFilteredUsers(users);
    else {
      const searchLower = userSearch.toLowerCase();
      setFilteredUsers(users.filter(user => 
        user.name?.toLowerCase().includes(searchLower) ||
        user.username?.toLowerCase().includes(searchLower) ||
        user.global_name?.toLowerCase().includes(searchLower) ||
        user.id?.includes(searchLower)
      ));
    }
  }, [userSearch, users]);

  useEffect(() => {
    if (channelSearch.trim() === "") setFilteredChannels(channels);
    else {
      const searchLower = channelSearch.toLowerCase();
      setFilteredChannels(channels.filter(channel => 
        channel.searchString?.includes(searchLower) ||
        channel.id?.includes(searchLower)
      ));
    }
  }, [channelSearch, channels]);

  useEffect(() => {
    if (categorySearch.trim() === "") setFilteredCategories(categories);
    else {
      const searchLower = categorySearch.toLowerCase();
      setFilteredCategories(categories.filter(category => 
        category.searchString?.includes(searchLower) ||
        category.id?.includes(searchLower)
      ));
    }
  }, [categorySearch, categories]);

  useEffect(() => {
    if (tempRoleSearch.trim() === "") setFilteredRoles(roles);
    else {
      const searchLower = tempRoleSearch.toLowerCase();
      setFilteredRoles(roles.filter(role => 
        role.searchString?.includes(searchLower) ||
        role.id?.includes(searchLower)
      ));
    }
  }, [tempRoleSearch, roles]);

  useEffect(() => {
    if (userFilterSearch.trim() === "") {
      setUserFilteredChannels(userChannels);
      setUserFilteredCategories(userCategories);
    } else {
      const searchLower = userFilterSearch.toLowerCase();
      setUserFilteredChannels(userChannels.filter(item => 
        item.searchString?.includes(searchLower) ||
        item.id?.includes(searchLower)
      ));
      setUserFilteredCategories(userCategories.filter(item => 
        item.searchString?.includes(searchLower) ||
        item.id?.includes(searchLower)
      ));
    }
  }, [userFilterSearch, userChannels, userCategories]);

  const fetchTimeseriesData = async (requestBody) => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    setLoadingChart(true);
    const { startDate, endDate } = getDateRange();
    
    try {
      let endpoint = '';
      let payload = {};
      
      if (selectedView === 'server') {
        endpoint = isPublic 
          ? `${API_BASE_URL}/api/public/emoji/server/timeseries`
          : `${API_BASE_URL}/api/emoji/server/timeseries`;
        payload = {
          guild_id: currentServer.id,
          role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
          usage_type: usageType === 'all' ? null : usageType,
          start_time: startDate?.toISOString(),
          end_time: endDate?.toISOString()
        };
      } else if (selectedView === 'user' && selectedUserId) {
        endpoint = isPublic 
          ? `${API_BASE_URL}/api/public/emoji/user/timeseries`
          : `${API_BASE_URL}/api/emoji/user/timeseries`;
        payload = {
          guild_id: currentServer.id,
          user_id: selectedUserId,
          usage_type: usageType === 'all' ? null : usageType,
          start_time: startDate?.toISOString(),
          end_time: endDate?.toISOString()
        };
        if (userFilterType === 'channel' && userFilterId) payload.channel_id = userFilterId;
        else if (userFilterType === 'category' && userFilterId) payload.category_id = userFilterId;
      } else if (selectedView === 'channel' && selectedChannelId) {
        endpoint = isPublic 
          ? `${API_BASE_URL}/api/public/emoji/channel/timeseries`
          : `${API_BASE_URL}/api/emoji/channel/timeseries`;
        payload = {
          guild_id: currentServer.id,
          channel_id: selectedChannelId,
          role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
          usage_type: usageType === 'all' ? null : usageType,
          start_time: startDate?.toISOString(),
          end_time: endDate?.toISOString()
        };
      } else if (selectedView === 'category' && selectedCategoryId) {
        endpoint = isPublic 
          ? `${API_BASE_URL}/api/public/emoji/category/timeseries`
          : `${API_BASE_URL}/api/emoji/category/timeseries`;
        payload = {
          guild_id: currentServer.id,
          category_id: selectedCategoryId,
          role_filter_ids: selectedRoleId ? [selectedRoleId] : null,
          usage_type: usageType === 'all' ? null : usageType,
          start_time: startDate?.toISOString(),
          end_time: endDate?.toISOString()
        };
      } else {
        setLoadingChart(false);
        return;
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublic ? 'omit' : 'include',
        body: JSON.stringify(payload)
      });
      
      if (response.ok) {
        const data = await response.json();
        const chartData = data.map(item => ({
          date: item.date,
          value: item.total_usage
        })).sort((a, b) => new Date(a.date) - new Date(b.date));
        setTimeseriesData(chartData);
      } else {
        setTimeseriesData([]);
      }
    } catch (error) {
      console.error('Error fetching timeseries data:', error);
      setTimeseriesData([]);
    } finally {
      setLoadingChart(false);
    }
  };

  // FIX: always use /api/server/real-channels -- the backend already handles
  // unauthenticated StatsHQ requests, so no separate public URL is needed.
  const getChannelNamesFromRealEndpoint = async (channelIds) => {
    if (!channelIds || channelIds.length === 0) return {};
    
    try {
      const url = `${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`;
      
      const response = await fetch(url, {
        credentials: isPublicMode ? 'omit' : 'include'
      });
      
      if (response.ok) {
        const channelsData = await response.json();
        const nameMap = {};
        channelsData.forEach(ch => {
          nameMap[ch.id] = ch.name;
        });
        return nameMap;
      }
    } catch (error) {
      console.error('Error fetching channel names:', error);
    }
    
    const fallbackMap = {};
    channelIds.forEach(id => { fallbackMap[id] = `Channel ${id}`; });
    return fallbackMap;
  };

  // FIX: always use /api/server/real-categories -- the backend already handles
  // unauthenticated StatsHQ requests, so no separate public URL is needed.
  const getCategoryNamesFromRealEndpoint = async (categoryIds) => {
    if (!categoryIds || categoryIds.length === 0) return {};
    
    try {
      const url = `${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`;
      
      const response = await fetch(url, {
        credentials: isPublicMode ? 'omit' : 'include'
      });
      
      if (response.ok) {
        const categoriesData = await response.json();
        const nameMap = {};
        categoriesData.forEach(cat => {
          nameMap[cat.id] = cat.name;
        });
        return nameMap;
      }
    } catch (error) {
      console.error('Error fetching category names:', error);
    }
    
    const fallbackMap = {};
    categoryIds.forEach(id => { fallbackMap[id] = `Category ${id}`; });
    return fallbackMap;
  };

  const fetchServerData = async (requestBody, daysInPeriod) => {
    if (!currentServer) return;
    
    const isPublic = isPublicMode;
    
    const cacheKey = getCacheKey('server-emoji', currentServer.id, {
      ...requestBody,
      timePeriod,
      customDaysBack,
      customStartDate,
      customEndDate,
      usageType,
      roleFilterId: selectedRoleId,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setServerData(cached.serverData);
      setAveragesData(cached.averagesData);
      setTopEmojis(cached.topEmojis);
      setTopUsers(cached.topUsers);
      setTopChannels(cached.topChannels);
      setTopCategories(cached.topCategories);
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingTopEmojis(false);
      setLoadingTopUsers(false);
      setLoadingTopChannels(false);
      setLoadingTopCategories(false);
      return;
    }
    
    let totalUsage = 0;
    let uniqueUsers = 0;
    let fetchedTopEmojis = [];
    let fetchedTopUsers = [];
    let fetchedTopChannels = [];
    let fetchedTopCategories = [];
    let fetchedAverages = { avgPerUser: 0, avgPerDay: 0, avgPerMonth: 0, avgPerYear: 0, daysInPeriod: 0 };
    
    try {
      const statsRequestBody = {
        guild_id: requestBody.guild_id,
        usage_type: requestBody.usage_type,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      };
      
      if (requestBody.role_filter_ids && requestBody.role_filter_ids.length > 0) {
        statsRequestBody.role_filter_ids = requestBody.role_filter_ids;
      }
      
      const leaderboardRequestBody = {
        guild_id: requestBody.guild_id,
        limit: 100000000000,
        usage_type: requestBody.usage_type,
        start_time: requestBody.start_time,
        end_time: requestBody.end_time
      };
      
      if (requestBody.role_filter_ids && requestBody.role_filter_ids.length > 0) {
        leaderboardRequestBody.role_filter_ids = requestBody.role_filter_ids;
      }
      
      const statsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/server/stats`
        : `${API_BASE_URL}/api/emoji/server/stats`;
      const topEmojisEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/server/top/emojis`
        : `${API_BASE_URL}/api/emoji/server/top/emojis`;
      const topUsersEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/server/top/users`
        : `${API_BASE_URL}/api/emoji/server/top/users`;
      const topChannelsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/server/top/channels`
        : `${API_BASE_URL}/api/emoji/server/top/channels`;
      const topCategoriesEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/server/top/categories`
        : `${API_BASE_URL}/api/emoji/server/top/categories`;
      
      const [statsResponse, topEmojisResponse, topUsersResponse, topChannelsResponse, topCategoriesResponse] = await Promise.all([
        fetch(statsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(statsRequestBody)
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topEmojisEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(leaderboardRequestBody)
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topUsersEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(leaderboardRequestBody)
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topChannelsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(leaderboardRequestBody)
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topCategoriesEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(leaderboardRequestBody)
        }).catch(err => ({ ok: false, error: err }))
      ]);
      
      if (statsResponse.ok) {
        const stats = await statsResponse.json();
        totalUsage = stats.total_usage || 0;
        uniqueUsers = stats.unique_users || 0;
        setServerData({ totalUsage, uniqueUsers });
        fetchedAverages = calculateAverages(totalUsage, uniqueUsers, daysInPeriod);
        setAveragesData(fetchedAverages);
      }
      
      if (topEmojisResponse.ok) {
        const data = await topEmojisResponse.json();
        if (Array.isArray(data)) {
          fetchedTopEmojis = data.map(emoji => ({
            id: emoji.emoji_str,
            name: emoji.emoji_str,
            value: emoji.usage_count || emoji.total_usage || 0,
            messageCount: emoji.message_count || 0,
            reactionCount: emoji.reaction_count || 0,
            uniqueUsers: emoji.unique_users || 0,
            percentage: emoji.percentage || 0
          }));
          setTopEmojis(fetchedTopEmojis);
        }
      }
      
      if (topUsersResponse.ok) {
        const data = await topUsersResponse.json();
        if (Array.isArray(data)) {
          const allUserIds = data.map(user => String(user.user_id));
          const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds, isPublic);
          
          const formattedUsers = await Promise.all(data.map(async (user, index) => {
            const userId = String(user.user_id);
            const isTop3 = index < 3;
            const userInfo = userInfoMap[userId] || { name: `User ${userId.slice(-4)}` };
            
            let avatar = null;
            if (isTop3) {
              avatar = await fetchUserAvatar(userId, isPublic);
            }
            
            return {
              userId: userId,
              name: userInfo.name,
              value: user.usage_count || user.total_usage || 0,
              avatar: avatar,
              messageUsage: user.message_usage || 0,
              reactionUsage: user.reaction_usage || 0
            };
          }));
          fetchedTopUsers = formattedUsers;
          setTopUsers(formattedUsers);
        }
      }
      
      if (topChannelsResponse.ok) {
        const data = await topChannelsResponse.json();
        if (Array.isArray(data) && data.length > 0) {
          const channelIds = data.map(channel => String(channel.channel_id));
          const channelNameMap = await getChannelNamesFromRealEndpoint(channelIds);
          
          fetchedTopChannels = data.map(channel => {
            const channelId = String(channel.channel_id);
            return {
              id: channelId,
              name: channelNameMap[channelId] || `Channel ${channelId}`,
              value: channel.total_usage || channel.usage_count || 0,
              messageUsage: channel.message_usage || 0,
              reactionUsage: channel.reaction_usage || 0,
              uniqueUsers: channel.unique_users || 0
            };
          });
          setTopChannels(fetchedTopChannels);
        } else {
          setTopChannels([]);
        }
      }
      
      if (topCategoriesResponse.ok) {
        const data = await topCategoriesResponse.json();
        if (Array.isArray(data) && data.length > 0) {
          const categoryIds = data.map(category => String(category.category_id));
          const categoryNameMap = await getCategoryNamesFromRealEndpoint(categoryIds);
          
          fetchedTopCategories = data.map(category => {
            const categoryId = String(category.category_id);
            return {
              id: categoryId,
              name: categoryNameMap[categoryId] || `Category ${categoryId}`,
              value: category.total_usage || category.usage_count || 0,
              messageUsage: category.message_usage || 0,
              reactionUsage: category.reaction_usage || 0,
              uniqueUsers: category.unique_users || 0,
              uniqueChannels: category.unique_channels || 0
            };
          });
          setTopCategories(fetchedTopCategories);
        } else {
          setTopCategories([]);
        }
      }
      
      const cacheData = {
        serverData: { totalUsage, uniqueUsers },
        averagesData: fetchedAverages,
        topEmojis: fetchedTopEmojis,
        topUsers: fetchedTopUsers,
        topChannels: fetchedTopChannels,
        topCategories: fetchedTopCategories
      };
      
      serverDataCache.set(cacheKey, cacheData);
      
    } catch (error) {
      console.error('Error in fetchServerData:', error);
      setApiError(error.message);
    } finally {
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingTopEmojis(false);
      setLoadingTopUsers(false);
      setLoadingTopChannels(false);
      setLoadingTopCategories(false);
    }
  };

  const fetchUserData = async (requestBody, daysInPeriod) => {
    if (!selectedUserId) return;
    const isPublic = isPublicMode;
    
    const userRequestBody = {
      guild_id: requestBody.guild_id,
      user_id: selectedUserId,
      usage_type: requestBody.usage_type,
      time_period: requestBody.time_period,
      days_back: requestBody.days_back
    };
    
    if (requestBody.start_time) userRequestBody.start_time = requestBody.start_time;
    if (requestBody.end_time) userRequestBody.end_time = requestBody.end_time;
    if (userFilterType === 'channel' && userFilterId) userRequestBody.channel_id = userFilterId;
    else if (userFilterType === 'category' && userFilterId) userRequestBody.category_id = userFilterId;
    if (requestBody.role_filter_ids) userRequestBody.role_filter_ids = requestBody.role_filter_ids;
    
    const cacheKey = getCacheKey('user-emoji', selectedUserId, {
      ...userRequestBody,
      timePeriod,
      customDaysBack,
      customStartDate,
      customEndDate,
      usageType,
      userFilterType,
      userFilterId,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setUserData(cached.userData);
      setAveragesData(cached.averagesData);
      setUserTopEmojis(cached.userTopEmojis);
      setUserTopChannels(cached.userTopChannels);
      setUserTopCategories(cached.userTopCategories);
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingUserTopEmojis(false);
      setLoadingUserTopChannels(false);
      setLoadingUserTopCategories(false);
      return;
    }
    
    const userProfile = await fetchUserBasicInfo(selectedUserId, currentServer.id, isPublic);
    let totalUsage = 0;
    let fetchedUserTopEmojis = [];
    let fetchedUserTopChannels = [];
    let fetchedUserTopCategories = [];
    let fetchedAverages = { avgPerUser: 0, avgPerDay: 0, avgPerMonth: 0, avgPerYear: 0, daysInPeriod: 0 };
    
    try {
      const statsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/user/stats`
        : `${API_BASE_URL}/api/emoji/user/stats`;
      const topEmojisEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/user/top/emojis`
        : `${API_BASE_URL}/api/emoji/user/top/emojis`;
      const topChannelsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/user/top/channels`
        : `${API_BASE_URL}/api/emoji/user/top/channels`;
      const topCategoriesEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/user/top/categories`
        : `${API_BASE_URL}/api/emoji/user/top/categories`;
      
      const [statsResponse, topEmojisResponse, topChannelsResponse, topCategoriesResponse] = await Promise.all([
        fetch(statsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(userRequestBody)
        }).catch(err => ({ ok: false })),
        
        fetch(topEmojisEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...userRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false })),
        
        fetch(topChannelsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...userRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false })),
        
        fetch(topCategoriesEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...userRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false }))
      ]);
      
      if (statsResponse.ok) {
        const stats = await statsResponse.json();
        totalUsage = stats.total_usage || 0;
        setUserData({ userId: selectedUserId, name: userProfile?.name || `User ${selectedUserId.slice(-4)}`, totalUsage });
        fetchedAverages = calculateAverages(totalUsage, 1, daysInPeriod);
        setAveragesData(fetchedAverages);
      }
      
      if (topEmojisResponse.ok) {
        const data = await topEmojisResponse.json();
        if (Array.isArray(data)) {
          fetchedUserTopEmojis = data.map(emoji => ({
            id: emoji.emoji_str,
            name: emoji.emoji_str,
            value: emoji.usage_count || 0,
            messageCount: emoji.message_count || 0,
            reactionCount: emoji.reaction_count || 0,
            uniqueChannels: emoji.unique_channels || 0,
            percentage: totalUsage > 0 ? Math.round((emoji.usage_count || 0) / totalUsage * 100) : 0
          }));
          setUserTopEmojis(fetchedUserTopEmojis);
        }
      }
      
      if (topChannelsResponse.ok) {
        const data = await topChannelsResponse.json();
        if (Array.isArray(data) && data.length > 0) {
          const channelIds = data.map(channel => String(channel.channel_id));
          const channelNameMap = await getChannelNamesFromRealEndpoint(channelIds);
          
          fetchedUserTopChannels = data.map(channel => {
            const channelId = String(channel.channel_id);
            return {
              id: channelId,
              name: channelNameMap[channelId] || `Channel ${channelId}`,
              value: channel.usage_count || channel.total_usage || 0,
              messageUsage: channel.message_usage || 0,
              reactionUsage: channel.reaction_usage || 0
            };
          });
          setUserTopChannels(fetchedUserTopChannels);
        }
      }
      
      if (topCategoriesResponse.ok) {
        const data = await topCategoriesResponse.json();
        if (Array.isArray(data) && data.length > 0) {
          const categoryIds = data.map(category => String(category.category_id));
          const categoryNameMap = await getCategoryNamesFromRealEndpoint(categoryIds);
          
          fetchedUserTopCategories = data.map(category => {
            const categoryId = String(category.category_id);
            return {
              id: categoryId,
              name: categoryNameMap[categoryId] || `Category ${categoryId}`,
              value: category.usage_count || category.total_usage || 0,
              messageUsage: category.message_usage || 0,
              reactionUsage: category.reaction_usage || 0,
              uniqueChannels: category.unique_channels || 0
            };
          });
          setUserTopCategories(fetchedUserTopCategories);
        }
      }
      
      const cacheData = {
        userData: { userId: selectedUserId, name: userProfile?.name || `User ${selectedUserId.slice(-4)}`, totalUsage },
        averagesData: fetchedAverages,
        userTopEmojis: fetchedUserTopEmojis,
        userTopChannels: fetchedUserTopChannels,
        userTopCategories: fetchedUserTopCategories
      };
      
      serverDataCache.set(cacheKey, cacheData);
      
    } catch (error) {
      console.error('Error in fetchUserData:', error);
      setApiError(error.message);
    } finally {
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingUserTopEmojis(false);
      setLoadingUserTopChannels(false);
      setLoadingUserTopCategories(false);
    }
  };

  const fetchChannelData = async (requestBody, daysInPeriod) => {
    if (!selectedChannelId) return;
    const isPublic = isPublicMode;
    
    const channelRequestBody = {
      guild_id: requestBody.guild_id,
      channel_id: selectedChannelId,
      usage_type: requestBody.usage_type,
      role_filter_ids: requestBody.role_filter_ids,
      time_period: requestBody.time_period,
      days_back: requestBody.days_back
    };
    
    if (requestBody.start_time) channelRequestBody.start_time = requestBody.start_time;
    if (requestBody.end_time) channelRequestBody.end_time = requestBody.end_time;
    
    const cacheKey = getCacheKey('channel-emoji', selectedChannelId, {
      ...channelRequestBody,
      timePeriod,
      customDaysBack,
      customStartDate,
      customEndDate,
      usageType,
      roleFilterId: selectedRoleId,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setChannelData(cached.channelData);
      setAveragesData(cached.averagesData);
      setChannelTopEmojis(cached.channelTopEmojis);
      setChannelTopUsers(cached.channelTopUsers);
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingChannelTopEmojis(false);
      setLoadingChannelTopUsers(false);
      return;
    }
    
    const channelNameMap = await getChannelNamesFromRealEndpoint([selectedChannelId]);
    const channelName = channelNameMap[selectedChannelId] || `Channel ${selectedChannelId}`;
    
    let totalUsage = 0;
    let uniqueUsers = 0;
    let fetchedChannelTopEmojis = [];
    let fetchedChannelTopUsers = [];
    let fetchedAverages = { avgPerUser: 0, avgPerDay: 0, avgPerMonth: 0, avgPerYear: 0, daysInPeriod: 0 };
    
    try {
      const statsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/channel/stats`
        : `${API_BASE_URL}/api/emoji/channel/stats`;
      const topEmojisEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/channel/top/emojis`
        : `${API_BASE_URL}/api/emoji/channel/top/emojis`;
      const topUsersEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/channel/top/users`
        : `${API_BASE_URL}/api/emoji/channel/top/users`;
      
      const [statsResponse, topEmojisResponse, topUsersResponse] = await Promise.all([
        fetch(statsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(channelRequestBody)
        }).catch(err => ({ ok: false })),
        
        fetch(topEmojisEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...channelRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false })),
        
        fetch(topUsersEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...channelRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false }))
      ]);
      
      if (statsResponse.ok) {
        const stats = await statsResponse.json();
        totalUsage = stats.total_usage || 0;
        uniqueUsers = stats.unique_users || 0;
        setChannelData({ channelId: selectedChannelId, name: channelName, totalUsage, uniqueUsers });
        fetchedAverages = calculateAverages(totalUsage, uniqueUsers, daysInPeriod);
        setAveragesData(fetchedAverages);
      }
      
      if (topEmojisResponse.ok) {
        const data = await topEmojisResponse.json();
        if (Array.isArray(data)) {
          fetchedChannelTopEmojis = data.map(emoji => ({
            id: emoji.emoji_str,
            name: emoji.emoji_str,
            value: emoji.total_usage || emoji.usage_count || 0,
            messageUsage: emoji.message_usage || 0,
            reactionUsage: emoji.reaction_usage || 0,
            uniqueUsers: emoji.unique_users || 0,
            percentage: emoji.percentage || 0
          }));
          setChannelTopEmojis(fetchedChannelTopEmojis);
        }
      }
      
      if (topUsersResponse.ok) {
        const data = await topUsersResponse.json();
        if (Array.isArray(data)) {
          const allUserIds = data.map(user => String(user.user_id));
          const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds, isPublic);
          
          const formattedUsers = await Promise.all(data.map(async (user, index) => {
            const userId = String(user.user_id);
            const isTop3 = index < 3;
            const userInfo = userInfoMap[userId] || { name: `User ${userId.slice(-4)}` };
            
            let avatar = null;
            if (isTop3) {
              avatar = await fetchUserAvatar(userId, isPublic);
            }
            
            return {
              userId: userId,
              name: userInfo.name,
              value: user.total_usage || user.usage_count || 0,
              avatar: avatar,
              messageUsage: user.message_usage || 0,
              reactionUsage: user.reaction_usage || 0
            };
          }));
          fetchedChannelTopUsers = formattedUsers;
          setChannelTopUsers(formattedUsers);
        }
      }
      
      const cacheData = {
        channelData: { channelId: selectedChannelId, name: channelName, totalUsage, uniqueUsers },
        averagesData: fetchedAverages,
        channelTopEmojis: fetchedChannelTopEmojis,
        channelTopUsers: fetchedChannelTopUsers
      };
      
      serverDataCache.set(cacheKey, cacheData);
      
    } catch (error) {
      console.error('Error in fetchChannelData:', error);
      setApiError(error.message);
    } finally {
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingChannelTopEmojis(false);
      setLoadingChannelTopUsers(false);
    }
  };

  const fetchCategoryData = async (requestBody, daysInPeriod) => {
    if (!selectedCategoryId) return;
    const isPublic = isPublicMode;
    
    const categoryRequestBody = {
      guild_id: requestBody.guild_id,
      category_id: selectedCategoryId,
      usage_type: requestBody.usage_type,
      role_filter_ids: requestBody.role_filter_ids,
      time_period: requestBody.time_period,
      days_back: requestBody.days_back
    };
    
    if (requestBody.start_time) categoryRequestBody.start_time = requestBody.start_time;
    if (requestBody.end_time) categoryRequestBody.end_time = requestBody.end_time;
    
    const cacheKey = getCacheKey('category-emoji', selectedCategoryId, {
      guild_id: requestBody.guild_id,
      category_id: selectedCategoryId,
      usage_type: usageType,
      role_filter_ids: requestBody.role_filter_ids,
      start_time: requestBody.start_time,
      end_time: requestBody.end_time,
      days_back: requestBody.days_back,
      time_period: timePeriod,
      public: isPublic
    });
    
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setCategoryData(cached.categoryData);
      setAveragesData(cached.averagesData);
      setCategoryTopEmojis(cached.categoryTopEmojis);
      setCategoryTopUsers(cached.categoryTopUsers);
      setCategoryTopChannels(cached.categoryTopChannels);
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingCategoryTopEmojis(false);
      setLoadingCategoryTopUsers(false);
      setLoadingCategoryTopChannels(false);
      return;
    }
    
    const categoryNameMap = await getCategoryNamesFromRealEndpoint([selectedCategoryId]);
    const categoryName = categoryNameMap[selectedCategoryId] || `Category ${selectedCategoryId}`;
    
    let totalUsage = 0;
    let uniqueUsers = 0;
    let fetchedCategoryTopEmojis = [];
    let fetchedCategoryTopUsers = [];
    let fetchedCategoryTopChannels = [];
    let fetchedAverages = { avgPerUser: 0, avgPerDay: 0, avgPerMonth: 0, avgPerYear: 0, daysInPeriod: 0 };
    
    try {
      const statsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/category/stats`
        : `${API_BASE_URL}/api/emoji/category/stats`;
      const topEmojisEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/category/top/emojis`
        : `${API_BASE_URL}/api/emoji/category/top/emojis`;
      const topUsersEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/category/top/users`
        : `${API_BASE_URL}/api/emoji/category/top/users`;
      const topChannelsEndpoint = isPublic 
        ? `${API_BASE_URL}/api/public/emoji/category/top/channels`
        : `${API_BASE_URL}/api/emoji/category/top/channels`;
      
      const [statsResponse, topEmojisResponse, topUsersResponse, topChannelsResponse] = await Promise.all([
        fetch(statsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify(categoryRequestBody)
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topEmojisEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...categoryRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topUsersEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...categoryRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false, error: err })),
        
        fetch(topChannelsEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublic ? 'omit' : 'include',
          body: JSON.stringify({ ...categoryRequestBody, limit: 100000000000 })
        }).catch(err => ({ ok: false, error: err }))
      ]);
      
      if (statsResponse.ok) {
        const stats = await statsResponse.json();
        totalUsage = stats.total_usage || 0;
        uniqueUsers = stats.unique_users || 0;
        setCategoryData({ categoryId: selectedCategoryId, name: categoryName, totalUsage, uniqueUsers });
        fetchedAverages = calculateAverages(totalUsage, uniqueUsers, daysInPeriod);
        setAveragesData(fetchedAverages);
      }
      
      if (topEmojisResponse.ok) {
        const data = await topEmojisResponse.json();
        if (Array.isArray(data)) {
          fetchedCategoryTopEmojis = data.map(emoji => ({
            id: emoji.emoji_str,
            name: emoji.emoji_str,
            value: emoji.total_usage || emoji.usage_count || 0,
            messageUsage: emoji.message_usage || 0,
            reactionUsage: emoji.reaction_usage || 0,
            uniqueUsers: emoji.unique_users || 0,
            uniqueChannels: emoji.unique_channels || 0,
            percentage: emoji.percentage || 0
          }));
          setCategoryTopEmojis(fetchedCategoryTopEmojis);
        }
      }
      
      if (topUsersResponse.ok) {
        const data = await topUsersResponse.json();
        if (Array.isArray(data)) {
          const allUserIds = data.map(user => String(user.user_id));
          const userInfoMap = await batchFetchUserBasicInfo(currentServer.id, allUserIds, isPublic);
          
          const formattedUsers = await Promise.all(data.map(async (user, index) => {
            const userId = String(user.user_id);
            const isTop3 = index < 3;
            const userInfo = userInfoMap[userId] || { name: `User ${userId.slice(-4)}` };
            
            let avatar = null;
            if (isTop3) {
              avatar = await fetchUserAvatar(userId, isPublic);
            }
            
            return {
              userId: userId,
              name: userInfo.name,
              value: user.total_usage || user.usage_count || 0,
              avatar: avatar,
              messageUsage: user.message_usage || 0,
              reactionUsage: user.reaction_usage || 0,
              uniqueChannels: user.unique_channels || 0
            };
          }));
          fetchedCategoryTopUsers = formattedUsers;
          setCategoryTopUsers(formattedUsers);
        }
      }
      
      if (topChannelsResponse.ok) {
        const data = await topChannelsResponse.json();
        
        if (Array.isArray(data) && data.length > 0) {
          const channelIds = data.map(channel => String(channel.channel_id));
          const channelNameMap = await getChannelNamesFromRealEndpoint(channelIds);
          
          fetchedCategoryTopChannels = data.map(channel => {
            const channelId = String(channel.channel_id);
            return {
              id: channelId,
              name: channelNameMap[channelId] || `Channel ${channelId}`,
              value: channel.total_usage || channel.usage_count || 0,
              messageUsage: channel.message_usage || 0,
              reactionUsage: channel.reaction_usage || 0,
              uniqueUsers: channel.unique_users || 0
            };
          });
          setCategoryTopChannels(fetchedCategoryTopChannels);
        } else {
          setCategoryTopChannels([]);
        }
      }
      
      const cacheData = {
        categoryData: { categoryId: selectedCategoryId, name: categoryName, totalUsage, uniqueUsers },
        averagesData: fetchedAverages,
        categoryTopEmojis: fetchedCategoryTopEmojis,
        categoryTopUsers: fetchedCategoryTopUsers,
        categoryTopChannels: fetchedCategoryTopChannels
      };
      
      serverDataCache.set(cacheKey, cacheData);
      
    } catch (error) {
      console.error('Error in fetchCategoryData:', error);
      setApiError(error.message);
    } finally {
      setLoadingSummaryStats(false);
      setLoadingAverages(false);
      setLoadingCategoryTopEmojis(false);
      setLoadingCategoryTopUsers(false);
      setLoadingCategoryTopChannels(false);
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
    serverDataCache.clearPattern('server-emoji');
    serverDataCache.clearPattern('channel-emoji');
    serverDataCache.clearPattern('category-emoji');
    serverDataCache.clearPattern('timeseries');
  };

  const handleUserSelect = (user) => {
    setSelectedUserId(user.id);
    setUserSearch(user.global_name || user.username || user.name || `User ${user.id}`);
    setShowUserDropdown(false);
    setUserFilterType("none");
    setUserFilterId("");
    setUserFilterSearch("");
    serverDataCache.clearPattern('user-emoji');
    serverDataCache.clearPattern('timeseries');
  };

  const handleChannelSelect = (channel) => {
    setSelectedChannelId(channel.id);
    setChannelSearch(channel.name || `Channel ${channel.id}`);
    setShowChannelDropdown(false);
    serverDataCache.clearPattern('channel-emoji');
    serverDataCache.clearPattern('timeseries');
  };

  const handleCategorySelect = (category) => {
    setSelectedCategoryId(category.id);
    setCategorySearch(category.name || `Category ${category.id}`);
    setShowCategoryDropdown(false);
    serverDataCache.clearPattern('category-emoji');
    serverDataCache.clearPattern('timeseries');
  };

  const handleUserFilterSelect = (type, id, name) => {
    setUserFilterType(type);
    setUserFilterId(id);
    setUserFilterSearch(name);
    setShowUserFilterDropdown(false);
    serverDataCache.clearPattern('user-emoji');
    serverDataCache.clearPattern('timeseries');
  };

  const clearUserFilter = () => {
    setUserFilterType("none");
    setUserFilterId("");
    setUserFilterSearch("");
    serverDataCache.clearPattern('user-emoji');
    serverDataCache.clearPattern('timeseries');
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

  const usageTypeOptions = [
    { value: 'all', label: 'All Usage' },
    { value: 'message', label: 'Messages Only' },
    { value: 'reaction', label: 'Reactions Only' }
  ];

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
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    .navbar .logo span:last-child {
      font-family: 'Horndon', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
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
      overflow-x: hidden;
      width: calc(100% - 280px);
    }

    .dashboard-content {
      max-width: 1600px;
      margin: 0 auto;
      padding: 20px 40px 40px 40px;
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

    .modern-select:hover { border-color: #aa00ff; background-color: #222; }
    .modern-select:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }

    .custom-lookback input {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 12px 16px;
      font-size: 14px;
      outline: none;
      width: 150px;
    }

    .custom-lookback input:hover { border-color: #aa00ff; background-color: #222; }

    .date-input { display: flex; align-items: center; gap: 8px; }

    .modern-date-input {
      background-color: #1a1a1a;
      color: #ffffff;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 12px 16px;
      font-size: 14px;
      outline: none;
      cursor: pointer;
    }

    .modern-date-input:hover { border-color: #aa00ff; background-color: #222; }
    .modern-date-input:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }

    .entity-filter { flex: 1; min-width: 250px; position: relative; }
    .entity-selector { position: relative; width: 100%; }

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

    .modern-entity-search:hover { border-color: #aa00ff; background-color: #222; }
    .modern-entity-search:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }

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
      border-left: 3px solid transparent;
      font-size: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .entity-option:hover { background-color: #2a2a2a; }
    .entity-option.selected { background-color: #2a2a2a; border-left-color: #aa00ff; }

    .entity-info { display: flex; align-items: center; gap: 8px; }
    .entity-avatar { width: 24px; height: 24px; border-radius: 50%; object-fit: cover; }
    .entity-name { font-weight: 500; }
    .entity-id { color: #888; font-size: 12px; }
    .entity-color-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }

    .apply-button-container { display: flex; gap: 8px; margin-top: 8px; }

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

    .apply-button:hover { background-color: #8800cc; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3); }

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

    .clear-button:hover { border-color: #ff4444; color: #ff4444; }

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

    .active-role-filter span { color: #aa00ff; font-size: 14px; }
    .active-role-filter button { background: none; border: none; color: #ff4444; cursor: pointer; }

    .error-message {
      text-align: center;
      padding: 60px;
      background-color: #0a0a0a;
      border: 1px solid #ff3333;
      border-radius: 16px;
      color: #ff3333;
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

    .retry-button:hover { background-color: #8800cc; transform: translateY(-2px); box-shadow: 0 8px 16px rgba(170, 0, 255, 0.3); }

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
      padding: 14px 28px;
      border-radius: 12px;
      text-decoration: none;
      font-weight: 600;
      margin-top: 20px;
      transition: all 0.2s ease;
    }

    .invite-button:hover, .login-button:hover { background-color: #8800cc; transform: translateY(-2px); box-shadow: 0 8px 16px rgba(170, 0, 255, 0.3); }

    .no-selection {
      text-align: center;
      padding: 100px;
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      color: #b0b0b0;
    }

    .leaderboards-stack { display: flex; flex-direction: column; gap: 30px; margin-bottom: 40px; width: 100%; }

    .leaderboard-wrapper {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      overflow: visible;
      transition: all 0.2s ease;
      width: 100%;
      min-height: 300px;
    }

    .leaderboard-wrapper:hover { border-color: #aa00ff; box-shadow: 0 4px 20px rgba(170, 0, 255, 0.2); }

    .custom-emoji { display: inline-block; vertical-align: middle; border-radius: 4px; }

    .leaderboard-wrapper > div { transform: scale(0.95); transform-origin: top left; width: 105.26%; }

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

    .summary-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; margin-bottom: 40px; }

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

    .stat-card:hover { border-color: #aa00ff; box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2); transform: translateY(-2px); }
    .stat-card h3 { color: #b0b0b0; font-size: 16px; font-weight: 500; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; }

    .stat-value {
      color: #ffffff;
      font-size: 42px;
      font-weight: 700;
      margin: 0;
      background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.2;
    }

    .stat-note { color: #666; font-size: 14px; margin-top: 8px; }
    .averages-section { margin-bottom: 40px; }
    .averages-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }

    .average-card {
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      padding: 24px;
      transition: all 0.2s ease;
      text-align: center;
    }

    .average-card:hover { border-color: #aa00ff; box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2); transform: translateY(-2px); }
    .average-card h3 { color: #b0b0b0; font-size: 14px; font-weight: 500; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; }

    .average-value {
      color: #ffffff;
      font-size: 28px;
      font-weight: 700;
      margin: 0;
      background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.2;
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

    .leaderboard-header h3 { color: #ffffff; font-size: 18px; font-weight: 600; margin: 0; }

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

    .retention-banner { width:100%; box-sizing:border-box; background:linear-gradient(135deg,#3a2f00 0%,#4a3a00 100%); border-bottom:1px solid #ffcc00; padding:12px 24px; display:flex; align-items:center; justify-content:center; gap:16px; position:relative; }
    .retention-banner-text { color:#ffe066; font-size:14px; font-weight:500; text-align:center; max-width:900px; }
    .retention-banner-close { background:none; border:none; color:#ffe066; font-size:14px; cursor:pointer; padding:4px 8px; border-radius:6px; line-height:1; flex-shrink:0; transition:background-color 0.15s,color 0.15s; }
    .retention-banner-close:hover { background-color:rgba(255,224,102,0.15); color:#fff; }

    .chart-wrapper:hover { border-color: #aa00ff; box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2); }
    .chart-wrapper > div { width: 100%; height: 100%; min-height: 400px; }

    .no-data-message {
      text-align: center;
      padding: 60px;
      background-color: #0a0a0a;
      border: 1px solid #1a1a1a;
      border-radius: 16px;
      color: #b0b0b0;
      font-size: 16px;
    }

    .no-chart-data { color: #b0b0b0; font-size: 16px; text-align: center; padding: 100px; }

    .public-banner {
      margin-bottom: 20px;
      padding: 16px;
      background: linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%);
      border: 1px solid #aa00ff;
      border-radius: 12px;
      text-align: center;
    }

    .public-banner p { color: #b0b0b0; margin: 0; }
    .public-banner a { color: #aa00ff; text-decoration: none; font-weight: 600; }
    .public-banner a:hover { text-decoration: underline; }

    .setting-note { color: #666; font-size: 12px; margin-top: 8px; }

    @media (max-width: 1024px) {
      .dashboard-main { margin-left: 250px; width: calc(100% - 250px); }
      .dashboard-content { padding: 16px; }
      .leaderboard-wrapper > div { transform: scale(0.92); transform-origin: top left; width: 108.7%; }
    }

    @media (max-width: 768px) {
      .dashboard-main { margin-left: 0; width: 100%; }
      .dashboard-content { padding: 12px; }
      .filters-section { flex-direction: column; align-items: stretch; padding: 16px; }
      .filter-row { flex-direction: column; align-items: flex-start; width: 100%; }
      .filter-row label { margin-bottom: 4px; min-width: auto; }
      .modern-select { width: 100%; min-width: auto; }
      .custom-lookback { flex-direction: column; width: 100%; }
      .custom-lookback input { width: 100%; }
      .date-input { flex-direction: column; align-items: flex-start; width: 100%; }
      .date-input input[type="date"] { width: 100%; }
      .entity-filter { width: 100%; min-width: auto; }
      .averages-grid { grid-template-columns: 1fr 1fr; }
      .summary-stats { grid-template-columns: 1fr; }
      .section-title { font-size: 24px; }
      .stat-value { font-size: 32px; }
      .average-value { font-size: 24px; }
      .chart-wrapper { transform: none !important; margin: 0 !important; padding: 16px; }
      .chart-wrapper > div { width: 100% !important; min-height: 400px; }
      .leaderboard-wrapper { overflow: visible; }
      .leaderboard-wrapper > div { transform: scale(0.85); transform-origin: top left; width: 117.6%; margin-bottom: -30px; }
    }

    @media (max-width: 480px) {
      .dashboard-content { padding: 8px; }
      .averages-grid { grid-template-columns: 1fr; }
      .chart-wrapper { padding: 12px; }
      .chart-wrapper > div { min-height: 350px; }
      .leaderboard-wrapper > div { transform: scale(0.78); width: 128.2%; margin-bottom: -50px; }
      .section-title { font-size: 20px; }
    }

    .stat-value, .average-value, .stat-number, .entity-name, .entity-option,
    .modern-select, .modern-entity-search, .modern-date-input, .custom-lookback input {
      color: #ffffff !important;
    }

    .entity-dropdown::-webkit-scrollbar { width: 8px; }
    .entity-dropdown::-webkit-scrollbar-track { background: #1a1a1a; }
    .entity-dropdown::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 4px; }
    .entity-dropdown::-webkit-scrollbar-thumb:hover { background: #aa00ff; }
  `;

  // ============================================
  // SHARED FILTER UI FRAGMENT
  // ============================================

  const renderFilters = () => (
    <div className="filters-section">
      <div className="filter-row">
        <label>View:</label>
        <select
          value={selectedView}
          onChange={(e) => {
            setSelectedView(e.target.value);
            if (e.target.value === 'server') {
              setSelectedUserId(""); setSelectedChannelId(""); setSelectedCategoryId("");
              setUserSearch(""); setChannelSearch(""); setCategorySearch("");
            } else if (e.target.value === 'user') {
              setSelectedChannelId(""); setSelectedCategoryId("");
              setChannelSearch(""); setCategorySearch("");
            } else if (e.target.value === 'channel') {
              setSelectedUserId(""); setSelectedCategoryId("");
              setUserSearch(""); setCategorySearch("");
            } else if (e.target.value === 'category') {
              setSelectedUserId(""); setSelectedChannelId("");
              setUserSearch(""); setChannelSearch("");
            }
            serverDataCache.clearPattern('server-emoji');
            serverDataCache.clearPattern('user-emoji');
            serverDataCache.clearPattern('channel-emoji');
            serverDataCache.clearPattern('category-emoji');
            serverDataCache.clearPattern('timeseries');
          }}
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
        <select value={timePeriod} onChange={(e) => setTimePeriod(e.target.value)} className="modern-select">
          {timePeriodOptions.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
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
            <input type="date" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} className="modern-date-input" />
          </div>
          <div className="date-input">
            <label>To:</label>
            <input type="date" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} className="modern-date-input" />
          </div>
        </div>
      )}
      
      <div className="filter-row">
        <label>Usage Type:</label>
        <select value={usageType} onChange={(e) => setUsageType(e.target.value)} className="modern-select">
          {usageTypeOptions.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      
      {(selectedView === 'server' || selectedView === 'channel' || selectedView === 'category') && (
        <div className="filter-row entity-filter">
          <label>Role Filter:</label>
          <div className="entity-selector">
            <input
              type="text"
              placeholder="Search role to filter users..."
              value={tempRoleSearch}
              onChange={(e) => setTempRoleSearch(e.target.value)}
              onFocus={() => { setShowRoleDropdown(true); if (filteredRoles.length === 0 && roles.length > 0) setFilteredRoles(roles); }}
              onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showRoleDropdown && filteredRoles.length > 0 && (
              <div className="entity-dropdown">
                <div className="entity-option" onMouseDown={() => { clearRoleFilter(); setShowRoleDropdown(false); }}>
                  <div className="entity-info"><span className="entity-name">Clear Role Filter</span></div>
                  <span className="entity-id">✕</span>
                </div>
                {filteredRoles.slice(0, 20).map(role => (
                  <div key={role.id} className={`entity-option ${tempRoleId === role.id ? 'selected' : ''}`} onMouseDown={() => handleTempRoleSelect(role)}>
                    <div className="entity-info">
                      <span className="entity-color-dot" style={{ backgroundColor: role.color || '#99aab5' }} />
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
                <span>Active filter: {roles.find(r => r.id === selectedRoleId)?.name || selectedRoleId}</span>
                <button onClick={clearRoleFilter}>✕</button>
              </div>
            )}
          </div>
        </div>
      )}
      
      {selectedView === 'user' && (
        <>
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
                    <div key={user.id} className={`entity-option ${selectedUserId === user.id ? 'selected' : ''}`} onMouseDown={() => handleUserSelect(user)}>
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
                  <div className="entity-option"><span className="entity-name">No users found</span></div>
                </div>
              )}
            </div>
          </div>
          
          {selectedUserId && (
            <div className="filter-row entity-filter">
              <label>Filter by:</label>
              <div className="entity-selector">
                <input
                  type="text"
                  placeholder="Search channel or category..."
                  value={userFilterSearch}
                  onChange={(e) => setUserFilterSearch(e.target.value)}
                  onFocus={() => setShowUserFilterDropdown(true)}
                  onBlur={() => setTimeout(() => setShowUserFilterDropdown(false), 200)}
                  className="modern-entity-search"
                />
                {showUserFilterDropdown && (
                  <div className="entity-dropdown">
                    <div className="entity-option" onMouseDown={() => clearUserFilter()}>
                      <div className="entity-info"><span className="entity-name">Clear Filter</span></div>
                      <span className="entity-id">✕</span>
                    </div>
                    {userFilteredChannels.length > 0 && (
                      <>
                        <div className="entity-option" style={{ backgroundColor: '#2a2a2a', cursor: 'default' }}>
                          <span className="entity-name" style={{ color: '#aa00ff' }}>Channels</span>
                        </div>
                        {userFilteredChannels.slice(0, 10).map(channel => (
                          <div key={`channel-${channel.id}`} className={`entity-option ${userFilterType === 'channel' && userFilterId === channel.id ? 'selected' : ''}`} onMouseDown={() => handleUserFilterSelect('channel', channel.id, channel.name)}>
                            <div className="entity-info"><span className="entity-name">#{channel.name}</span></div>
                            <span className="entity-id">Channel</span>
                          </div>
                        ))}
                      </>
                    )}
                    {userFilteredCategories.length > 0 && (
                      <>
                        <div className="entity-option" style={{ backgroundColor: '#2a2a2a', cursor: 'default' }}>
                          <span className="entity-name" style={{ color: '#aa00ff' }}>Categories</span>
                        </div>
                        {userFilteredCategories.slice(0, 10).map(category => (
                          <div key={`category-${category.id}`} className={`entity-option ${userFilterType === 'category' && userFilterId === category.id ? 'selected' : ''}`} onMouseDown={() => handleUserFilterSelect('category', category.id, category.name)}>
                            <div className="entity-info"><span className="entity-name">{category.name}</span></div>
                            <span className="entity-id">Category</span>
                          </div>
                        ))}
                      </>
                    )}
                    {userFilteredChannels.length === 0 && userFilteredCategories.length === 0 && (
                      <div className="entity-option"><span className="entity-name">No channels or categories found</span></div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
      
      {selectedView === 'channel' && (
        <div className="filter-row entity-filter">
          <label>Channel:</label>
          <div className="entity-selector">
            <input
              type="text"
              placeholder="Search channel..."
              value={channelSearch}
              onChange={(e) => setChannelSearch(e.target.value)}
              onFocus={() => setShowChannelDropdown(true)}
              onBlur={() => setTimeout(() => setShowChannelDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showChannelDropdown && filteredChannels.length > 0 && (
              <div className="entity-dropdown">
                {filteredChannels.slice(0, 20).map(channel => (
                  <div key={channel.id} className={`entity-option ${selectedChannelId === channel.id ? 'selected' : ''}`} onMouseDown={() => handleChannelSelect(channel)}>
                    <div className="entity-info"><span className="entity-name">#{channel.name}</span></div>
                    <span className="entity-id">ID: {channel.id}</span>
                  </div>
                ))}
              </div>
            )}
            {showChannelDropdown && filteredChannels.length === 0 && channelsLoaded && (
              <div className="entity-dropdown">
                <div className="entity-option"><span className="entity-name">No channels found</span></div>
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
              placeholder="Search category..."
              value={categorySearch}
              onChange={(e) => setCategorySearch(e.target.value)}
              onFocus={() => setShowCategoryDropdown(true)}
              onBlur={() => setTimeout(() => setShowCategoryDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showCategoryDropdown && filteredCategories.length > 0 && (
              <div className="entity-dropdown">
                {filteredCategories.slice(0, 20).map(category => (
                  <div key={category.id} className={`entity-option ${selectedCategoryId === category.id ? 'selected' : ''}`} onMouseDown={() => handleCategorySelect(category)}>
                    <div className="entity-info"><span className="entity-name">{category.name}</span></div>
                    <span className="entity-id">ID: {category.id}</span>
                  </div>
                ))}
              </div>
            )}
            {showCategoryDropdown && filteredCategories.length === 0 && categoriesLoaded && (
              <div className="entity-dropdown">
                <div className="entity-option"><span className="entity-name">No categories found</span></div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  // ============================================
  // SHARED DASHBOARD CONTENT FRAGMENT
  // ============================================

  const renderDashboardContent = () => (
    <>
      {loadingServers ? (
        <div className="loading">Loading servers...</div>
      ) : apiError ? (
        <div className="error-message">
          <h2>Error Loading Data</h2>
          <p>{apiError}</p>
          <button onClick={() => { serverDataCache.clear(); fetchDataWithParams(); }} className="retry-button">
            Clear Cache &amp; Retry
          </button>
        </div>
      ) : (
        <>
          {/* Server View */}
          {selectedView === 'server' && (
            <>
              <div className="summary-stats">
                {loadingSummaryStats ? (
                  <>
                    <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                    <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                  </>
                ) : serverData ? (
                  <>
                    <div className="stat-card">
                      <h3>Total Emoji Usage</h3>
                      <p className="stat-value">{formatNumber(serverData.totalUsage)}</p>
                    </div>
                    <div className="stat-card">
                      <h3>Active Users</h3>
                      <p className="stat-value">{formatNumber(serverData.uniqueUsers)}</p>
                    </div>
                  </>
                ) : (
                  <div className="stat-card">
                    <h3>Total Emoji Usage</h3>
                    <p className="stat-value">0</p>
                  </div>
                )}
              </div>
              
              <div className="averages-section">
                <h2 className="section-title">Averages</h2>
                <div className="averages-grid">
                  <div className="average-card"><h3>Per User</h3><p className="average-value">{formatAverage(averagesData.avgPerUser)}</p></div>
                  <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatAverage(averagesData.avgPerDay)}</p></div>
                  <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatAverage(averagesData.avgPerMonth)}</p></div>
                  <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatAverage(averagesData.avgPerYear)}</p></div>
                </div>
              </div>
              
              <div className="leaderboards-section">
                <h2 className="section-title">Leaderboards</h2>
                <div className="leaderboards-stack">
                  {loadingTopEmojis ? <LoadingCard /> : topEmojis.length > 0 ? (
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header"><h3>Top Emojis</h3></div>
                      <LeaderboardWithEmojis
                        data={topEmojis} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                        showProfilePictures={false} itemType="emoji" nameKey="name" valueKey="value" idKey="id"
                        backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                        additionalInfo={(item) => {
                          const info = [];
                          info.push(`${item.uniqueUsers || 0} users`);
                          if (usageType === 'all') info.push(`${item.messageCount || 0} msg, ${item.reactionCount || 0} react`);
                          return info;
                        }}
                      />
                    </div>
                  ) : <div className="no-data-message">No emoji data available {selectedRoleId ? 'with this role filter' : ''}</div>}

                  {loadingTopUsers ? <LoadingCard /> : topUsers.length > 0 ? (
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header"><h3>Top Emoji Users</h3></div>
                      <Leaderboard
                        data={topUsers} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                        showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId"
                        backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                        getProfilePicture={async (userId) => { const user = users.find(u => u.id === userId); return user?.avatar || null; }}
                        additionalInfo={(item) => { const info = []; if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`); return info; }}
                      />
                    </div>
                  ) : <div className="no-data-message">No user data available {selectedRoleId ? 'with this role filter' : ''}</div>}

                  {loadingTopChannels ? <LoadingCard /> : topChannels.length > 0 ? (
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header"><h3>Top Channels</h3></div>
                      <Leaderboard
                        data={topChannels} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                        showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id"
                        backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                        additionalInfo={(item) => {
                          const info = [];
                          info.push(`${item.uniqueUsers || 0} users`);
                          if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                          return info;
                        }}
                      />
                    </div>
                  ) : <div className="no-data-message">No channel data available {selectedRoleId ? 'with this role filter' : ''}</div>}

                  {loadingTopCategories ? <LoadingCard /> : topCategories.length > 0 ? (
                    <div className="leaderboard-wrapper">
                      <div className="leaderboard-header"><h3>Top Categories</h3></div>
                      <Leaderboard
                        data={topCategories} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                        showProfilePictures={false} itemType="category" nameKey="name" valueKey="value" idKey="id"
                        backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                        additionalInfo={(item) => {
                          const info = [];
                          info.push(`${item.uniqueUsers || 0} users, ${item.uniqueChannels || 0} channels`);
                          if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                          return info;
                        }}
                      />
                    </div>
                  ) : <div className="no-data-message">No category data available {selectedRoleId ? 'with this role filter' : ''}</div>}
                </div>
              </div>
              
              <div className="charts-section">
                <h2 className="section-title">Emoji Usage Over Time</h2>
                <div className="chart-wrapper">
                  {loadingChart ? <LoadingChart /> : timeseriesData.length > 0 ? (
                    <InteractiveLineChart data={timeseriesData} lines={[{ name: 'Emoji Usage', dataKey: 'value', color: '#aa00ff' }]} title="" valueFormatter={formatEmojiValue} />
                  ) : <div className="no-chart-data">No chart data available</div>}
                </div>
              </div>
            </>
          )}

          {/* User View */}
          {selectedView === 'user' && (
            <>
              {!selectedUserId ? (
                <div className="no-selection">
                  <h2>Select a User</h2>
                  <p>Please select a user from the dropdown above to view their emoji statistics.</p>
                </div>
              ) : (
                <>
                  <div className="summary-stats">
                    {loadingSummaryStats ? <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                    : userData ? (
                      <div className="stat-card">
                        <h3>Total Emoji Usage</h3>
                        <p className="stat-value">{formatNumber(userData.totalUsage)}</p>
                        <div className="stat-note">{userData.name}</div>
                      </div>
                    ) : <div className="stat-card"><h3>Total Emoji Usage</h3><p className="stat-value">0</p></div>}
                  </div>
                  
                  <div className="averages-section">
                    <h2 className="section-title">Averages</h2>
                    <div className="averages-grid">
                      <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatAverage(averagesData.avgPerDay)}</p></div>
                      <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatAverage(averagesData.avgPerMonth)}</p></div>
                      <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatAverage(averagesData.avgPerYear)}</p></div>
                    </div>
                  </div>
                  
                  <div className="leaderboards-section">
                    <h2 className="section-title">{userData?.name || 'User'}'s Activity</h2>
                    <div className="leaderboards-stack">
                      {userFilterType !== 'none' && userFilterId && (
                        <div className="active-role-filter" style={{ marginBottom: '20px' }}>
                          <span>Filtering by: {userFilterType === 'channel' ? 'Channel' : 'Category'} - {userFilterSearch}</span>
                          <button onClick={clearUserFilter}>✕</button>
                        </div>
                      )}

                      {loadingUserTopEmojis ? <LoadingCard /> : userTopEmojis.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Emojis</h3></div>
                          <LeaderboardWithEmojis
                            data={userTopEmojis} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={false} itemType="emoji" nameKey="name" valueKey="value" idKey="id"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            additionalInfo={(item) => {
                              const info = [];
                              info.push(`${item.uniqueChannels || 0} channels`);
                              info.push(`${item.percentage || 0}% of total`);
                              if (usageType === 'all') info.push(`${item.messageCount || 0} msg, ${item.reactionCount || 0} react`);
                              return info;
                            }}
                          />
                        </div>
                      ) : <div className="no-data-message">No emoji data available for this user</div>}

                      {loadingUserTopChannels ? <LoadingCard /> : userTopChannels.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Channels</h3></div>
                          <Leaderboard
                            data={userTopChannels} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            additionalInfo={(item) => { if (usageType === 'all') return [`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`]; return []; }}
                          />
                        </div>
                      ) : <div className="no-data-message">No channel data available for this user</div>}

                      {loadingUserTopCategories ? <LoadingCard /> : userTopCategories.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Categories</h3></div>
                          <Leaderboard
                            data={userTopCategories} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={false} itemType="category" nameKey="name" valueKey="value" idKey="id"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            additionalInfo={(item) => {
                              const info = [];
                              info.push(`${item.uniqueChannels || 0} channels`);
                              if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                              return info;
                            }}
                          />
                        </div>
                      ) : <div className="no-data-message">No category data available for this user</div>}
                    </div>
                  </div>
                  
                  <div className="charts-section">
                    <h2 className="section-title">{userData?.name || 'User'}'s Emoji Usage Over Time</h2>
                    <div className="chart-wrapper">
                      {loadingChart ? <LoadingChart /> : timeseriesData.length > 0 ? (
                        <InteractiveLineChart data={timeseriesData} lines={[{ name: 'Emoji Usage', dataKey: 'value', color: '#aa00ff' }]} title="" valueFormatter={formatEmojiValue} />
                      ) : <div className="no-chart-data">No chart data available</div>}
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
                <div className="no-selection">
                  <h2>Select a Channel</h2>
                  <p>Please select a channel from the dropdown above to view its emoji statistics.</p>
                </div>
              ) : (
                <>
                  <div className="summary-stats">
                    {loadingSummaryStats ? (
                      <><div className="stat-card"><LoadingSpinner size="small" text="" /></div><div className="stat-card"><LoadingSpinner size="small" text="" /></div></>
                    ) : channelData ? (
                      <>
                        <div className="stat-card"><h3>Total Emoji Usage</h3><p className="stat-value">{formatNumber(channelData.totalUsage)}</p><div className="stat-note">{channelData.name}</div></div>
                        <div className="stat-card"><h3>Unique Users</h3><p className="stat-value">{formatNumber(channelData.uniqueUsers)}</p></div>
                      </>
                    ) : <div className="stat-card"><h3>Total Emoji Usage</h3><p className="stat-value">0</p></div>}
                  </div>
                  
                  <div className="averages-section">
                    <h2 className="section-title">Averages</h2>
                    <div className="averages-grid">
                      <div className="average-card"><h3>Per User</h3><p className="average-value">{formatAverage(averagesData.avgPerUser)}</p></div>
                      <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatAverage(averagesData.avgPerDay)}</p></div>
                      <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatAverage(averagesData.avgPerMonth)}</p></div>
                      <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatAverage(averagesData.avgPerYear)}</p></div>
                    </div>
                  </div>
                  
                  <div className="leaderboards-section">
                    <h2 className="section-title">Channel Activity</h2>
                    <div className="leaderboards-stack">
                      {loadingChannelTopEmojis ? <LoadingCard /> : channelTopEmojis.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Emojis</h3></div>
                          <LeaderboardWithEmojis
                            data={channelTopEmojis} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={false} itemType="emoji" nameKey="name" valueKey="value" idKey="id"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            additionalInfo={(item) => {
                              const info = [];
                              info.push(`${item.uniqueUsers || 0} users`);
                              if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                              return info;
                            }}
                          />
                        </div>
                      ) : <div className="no-data-message">No emoji data available for this channel {selectedRoleId ? 'with this role filter' : ''}</div>}

                      {loadingChannelTopUsers ? <LoadingCard /> : channelTopUsers.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Users</h3></div>
                          <Leaderboard
                            data={channelTopUsers} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            getProfilePicture={async (userId) => { const user = users.find(u => u.id === userId); return user?.avatar || null; }}
                            additionalInfo={(item) => { if (usageType === 'all') return [`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`]; return []; }}
                          />
                        </div>
                      ) : <div className="no-data-message">No user data available for this channel {selectedRoleId ? 'with this role filter' : ''}</div>}
                    </div>
                  </div>
                  
                  <div className="charts-section">
                    <h2 className="section-title">{channelData?.name || 'Channel'} Emoji Usage Over Time</h2>
                    <div className="chart-wrapper">
                      {loadingChart ? <LoadingChart /> : timeseriesData.length > 0 ? (
                        <InteractiveLineChart data={timeseriesData} lines={[{ name: 'Emoji Usage', dataKey: 'value', color: '#aa00ff' }]} title="" valueFormatter={formatEmojiValue} />
                      ) : <div className="no-chart-data">No chart data available</div>}
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
                <div className="no-selection">
                  <h2>Select a Category</h2>
                  <p>Please select a category from the dropdown above to view its emoji statistics.</p>
                </div>
              ) : (
                <>
                  <div className="summary-stats">
                    {loadingSummaryStats ? (
                      <><div className="stat-card"><LoadingSpinner size="small" text="" /></div><div className="stat-card"><LoadingSpinner size="small" text="" /></div></>
                    ) : categoryData ? (
                      <>
                        <div className="stat-card"><h3>Total Emoji Usage</h3><p className="stat-value">{formatNumber(categoryData.totalUsage)}</p><div className="stat-note">{categoryData.name}</div></div>
                        <div className="stat-card"><h3>Unique Users</h3><p className="stat-value">{formatNumber(categoryData.uniqueUsers)}</p></div>
                      </>
                    ) : <div className="stat-card"><h3>Total Emoji Usage</h3><p className="stat-value">0</p></div>}
                  </div>
                  
                  <div className="averages-section">
                    <h2 className="section-title">Averages</h2>
                    <div className="averages-grid">
                      <div className="average-card"><h3>Per User</h3><p className="average-value">{formatAverage(averagesData.avgPerUser)}</p></div>
                      <div className="average-card"><h3>Per Day</h3><p className="average-value">{formatAverage(averagesData.avgPerDay)}</p></div>
                      <div className="average-card"><h3>Per Month</h3><p className="average-value">{formatAverage(averagesData.avgPerMonth)}</p></div>
                      <div className="average-card"><h3>Per Year</h3><p className="average-value">{formatAverage(averagesData.avgPerYear)}</p></div>
                    </div>
                  </div>
                  
                  <div className="leaderboards-section">
                    <h2 className="section-title">Category Activity</h2>
                    <div className="leaderboards-stack">
                      {loadingCategoryTopEmojis ? <LoadingCard /> : categoryTopEmojis.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Emojis</h3></div>
                          <LeaderboardWithEmojis
                            data={categoryTopEmojis} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={false} itemType="emoji" nameKey="name" valueKey="value" idKey="id"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            additionalInfo={(item) => {
                              const info = [];
                              info.push(`${item.uniqueUsers || 0} users, ${item.uniqueChannels || 0} channels`);
                              if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                              return info;
                            }}
                          />
                        </div>
                      ) : <div className="no-data-message">No emoji data available for this category {selectedRoleId ? 'with this role filter' : ''}</div>}

                      {loadingCategoryTopUsers ? <LoadingCard /> : categoryTopUsers.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Users</h3></div>
                          <Leaderboard
                            data={categoryTopUsers} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            getProfilePicture={async (userId) => { const user = users.find(u => u.id === userId); return user?.avatar || null; }}
                            additionalInfo={(item) => {
                              const info = [];
                              info.push(`${item.uniqueChannels || 0} channels`);
                              if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                              return info;
                            }}
                          />
                        </div>
                      ) : <div className="no-data-message">No user data available for this category {selectedRoleId ? 'with this role filter' : ''}</div>}

                      {loadingCategoryTopChannels ? <LoadingCard /> : categoryTopChannels.length > 0 ? (
                        <div className="leaderboard-wrapper">
                          <div className="leaderboard-header"><h3>Top Channels</h3></div>
                          <Leaderboard
                            data={categoryTopChannels} title="" valueLabel="Uses" valueFormatter={formatEmojiValue}
                            showProfilePictures={false} itemType="channel" nameKey="name" valueKey="value" idKey="id"
                            backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                            additionalInfo={(item) => {
                              const info = [];
                              info.push(`${item.uniqueUsers || 0} users`);
                              if (usageType === 'all') info.push(`${item.messageUsage || 0} msg, ${item.reactionUsage || 0} react`);
                              return info;
                            }}
                          />
                        </div>
                      ) : <div className="no-data-message">No channel data available for this category {selectedRoleId ? 'with this role filter' : ''}</div>}
                    </div>
                  </div>
                  
                  <div className="charts-section">
                    <h2 className="section-title">{categoryData?.name || 'Category'} Emoji Usage Over Time</h2>
                    <div className="chart-wrapper">
                      {loadingChart ? <LoadingChart /> : timeseriesData.length > 0 ? (
                        <InteractiveLineChart data={timeseriesData} lines={[{ name: 'Emoji Usage', dataKey: 'value', color: '#aa00ff' }]} title="" valueFormatter={formatEmojiValue} />
                      ) : <div className="no-chart-data">No chart data available</div>}
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}
    </>
  );

  // ============================================
  // RENDER LOGIC
  // ============================================

  // Public mode (no auth)
  if (!isAuthenticated && isPublicMode) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={true} publicGuildId={PUBLIC_GUILD_ID} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="public-banner">
                <p>Viewing emoji statistics from the <strong>StatsHQ</strong> support server - <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server stats</p>
              </div>
              {renderFilters()}
              {renderDashboardContent()}
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Authenticated but no access
  if (isAuthenticated && currentServer && !hasAccess) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={false} />
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

  // Loading servers
  if (loadingServers && !currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={isPublicMode} publicGuildId={PUBLIC_GUILD_ID} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading"><LoadingSpinner size="large" text="Loading dashboard..." /></div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // Permission check in progress
  if (hasAccess === null && isAuthenticated && currentServer) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={false} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="loading"><LoadingSpinner size="large" text="Checking permissions..." /></div>
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

  // No server available
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
                   className="invite-button" target="_blank" rel="noopener noreferrer">
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

  // Error
  if (apiError) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={isPublicMode} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="error-message">
                <h2>Error Loading Data</h2>
                <p>{apiError}</p>
                <button onClick={() => { serverDataCache.clear(); fetchDataWithParams(); }} className="retry-button">
                  Clear Cache &amp; Retry
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

  // Authenticated user with access - full dashboard
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
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={false} />
        <main className="dashboard-main">
          <div className="dashboard-content">
            {renderFilters()}
            {renderDashboardContent()}
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
    <EmojiDashboard />
  </React.StrictMode>
);

export default EmojiDashboard;