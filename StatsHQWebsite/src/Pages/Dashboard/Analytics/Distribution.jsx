import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import TimezonePieChart from "../../../Components/PieChart.jsx";
import ActivityHeatmap from "../../../Components/ActivityHeatmap.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const PUBLIC_GUILD_ID = '1424021358680998022';
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// ─── Caches ───────────────────────────────────────────────────────────────────

class ProfileCache {
  constructor(maxSize = 500) { this.cache = new Map(); this.maxSize = maxSize; }
  get(key) {
    const v = this.cache.get(key);
    if (v && v.name && !v.name.startsWith('User ')) { this.cache.delete(key); this.cache.set(key, v); return v; }
    if (v) this.cache.delete(key);
    return null;
  }
  set(key, value) {
    if (value.name && !value.name.startsWith('User ')) {
      if (this.cache.size >= this.maxSize) this.cache.delete(this.cache.keys().next().value);
      this.cache.set(key, value);
    }
  }
  clear() { this.cache.clear(); }
}

class ServerDataCache {
  constructor(maxSize = 50, ttl = 5 * 60 * 1000) { this.cache = new Map(); this.maxSize = maxSize; this.TTL = ttl; }
  set(key, value) {
    if (this.cache.size >= this.maxSize) this.cache.delete(this.cache.keys().next().value);
    this.cache.set(key, { data: value, timestamp: Date.now() });
  }
  get(key) {
    const e = this.cache.get(key);
    if (e && Date.now() - e.timestamp < this.TTL) return e.data;
    if (e) this.cache.delete(key);
    return null;
  }
  clear() { this.cache.clear(); }
}

const profileCache = new ProfileCache(500);
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);
const getCacheKey = (type, id, params) => `${type}:${id}:${JSON.stringify(params)}`;

// ─── Duration formatter ───────────────────────────────────────────────────────
// Formats seconds into SS / MM:SS / HH:MM:SS / D:HH:MM:SS

const formatDuration = (totalSeconds) => {
  const s = Math.round(totalSeconds);
  if (s < 60) return `${s}s`;
  const days = Math.floor(s / 86400);
  const hrs  = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (days > 0) return `${days}d ${String(hrs).padStart(2,'0')}:${String(mins).padStart(2,'0')}`;
  if (hrs  > 0) return `${String(hrs).padStart(2,'0')}:${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
  return `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
};

// ─── Stat type registry ───────────────────────────────────────────────────────
// format: 'count' | 'duration'
// dataKey: the field name in the hourly response (hour_0..hour_23 key base — always hour_N)
// totalKey: which key holds the total in the response

const STAT_TYPES = {
  server: [
    { value: 'messages',             label: 'Messages',                  endpoint: 'messages',            hasRoleFilter: true,  format: 'count'    },
    { value: 'voice',                label: 'Voice Activity',            endpoint: 'voice',               hasRoleFilter: true,  format: 'duration' },
    { value: 'activity',             label: 'Status Activity Time',      endpoint: 'activity',            hasRoleFilter: true,  format: 'duration' },
    { value: 'activity-sessions',    label: 'Status Activity Sessions',  endpoint: 'activity-sessions',   hasRoleFilter: true,  format: 'count'    },
    { value: 'invites',              label: 'Invites',                   endpoint: 'invites',             hasRoleFilter: true,  format: 'count'    },
    { value: 'emoji-usage',          label: 'Emoji Usage',               endpoint: 'emoji-usage',         hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-sent',        label: 'Mentions Sent',             endpoint: 'mentions-sent',       hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-received',    label: 'Mentions Received',         endpoint: 'mentions-received',   hasRoleFilter: true,  format: 'count'    },
    { value: 'joins',                label: 'Joins',                     endpoint: 'joins',               hasRoleFilter: false, format: 'count'    },
    { value: 'leaves',               label: 'Leaves',                    endpoint: 'leaves',              hasRoleFilter: false, format: 'count'    },
  ],
  user: [
    { value: 'messages',             label: 'Messages',                  endpoint: 'messages',            hasRoleFilter: true,  format: 'count'    },
    { value: 'voice',                label: 'Voice Activity',            endpoint: 'voice',               hasRoleFilter: true,  format: 'duration' },
    { value: 'activity',             label: 'Status Activity Time',      endpoint: 'activity',            hasRoleFilter: true,  format: 'duration' },
    { value: 'activity-sessions',    label: 'Status Activity Sessions',  endpoint: 'activity-sessions',   hasRoleFilter: true,  format: 'count'    },
    { value: 'invites-sent',         label: 'Invites Sent',              endpoint: 'invites-sent',        hasRoleFilter: true,  format: 'count'    },
    { value: 'emoji-usage',          label: 'Emoji Usage',               endpoint: 'emoji-usage',         hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-sent',        label: 'Mentions Sent',             endpoint: 'mentions-sent',       hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-received',    label: 'Mentions Received',         endpoint: 'mentions-received',   hasRoleFilter: true,  format: 'count'    },
  ],
  channel: [
    { value: 'messages',             label: 'Messages',                  endpoint: 'messages',            hasRoleFilter: true,  format: 'count'    },
    { value: 'voice',                label: 'Voice Activity',            endpoint: 'voice',               hasRoleFilter: true,  format: 'duration' },
    { value: 'emoji-usage',          label: 'Emoji Usage',               endpoint: 'emoji-usage',         hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-sent',        label: 'Mentions Sent',             endpoint: 'mentions-sent',       hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-received',    label: 'Mentions Received',         endpoint: 'mentions-received',   hasRoleFilter: true,  format: 'count'    },
  ],
  category: [
    { value: 'messages',             label: 'Messages',                  endpoint: 'messages',            hasRoleFilter: true,  format: 'count'    },
    { value: 'voice',                label: 'Voice Activity',            endpoint: 'voice',               hasRoleFilter: true,  format: 'duration' },
    { value: 'emoji-usage',          label: 'Emoji Usage',               endpoint: 'emoji-usage',         hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-sent',        label: 'Mentions Sent',             endpoint: 'mentions-sent',       hasRoleFilter: true,  format: 'count'    },
    { value: 'mentions-received',    label: 'Mentions Received',         endpoint: 'mentions-received',   hasRoleFilter: true,  format: 'count'    },
  ],
};

// ─── Heatmap view from time period ────────────────────────────────────────────

const getHeatmapView = (timePeriod, customDaysBack) => {
  if (timePeriod === 'all') return 'yearly';
  if (timePeriod === 'custom-lookback') {
    const d = parseInt(customDaysBack) || 30;
    if (d <= 14) return 'weekly';
    if (d <= 60) return 'month';
    return 'yearly';
  }
  if (timePeriod === 'custom-range') return 'month';
  const d = parseInt(timePeriod);
  if (d <= 14) return 'weekly';
  if (d <= 60) return 'month';
  return 'yearly';
};

// ─── Small UI bits ────────────────────────────────────────────────────────────

const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
  const sz = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', padding:'30px', gap:'12px', width:'100%', minHeight:'150px' }}>
      <div style={{ width:sz, height:sz, border:'3px solid #2a2a2a', borderTop:'3px solid #aa00ff', borderRadius:'50%', animation:'spin 1s linear infinite' }} />
      {text && <span style={{ color:'#b0b0b0', fontSize:'14px' }}>{text}</span>}
      <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    </div>
  );
};

const AccessDenied = ({ accessLevel }) => (
  <div className="no-selection">
    <h2>🔒 Access Denied</h2>
    <p>You don't have permission to view this server's distribution data.</p>
    <p>This server requires <strong>{accessLevel === 'Admin' ? 'Administrator' : 'Manage Server or Administrator'}</strong> permissions.</p>
  </div>
);

// ─── Main component ───────────────────────────────────────────────────────────

const DistributionDashboard = () => {

  // Auth
  const [isAuthenticated, setIsAuthenticated]       = useState(false);
  const [isPublicMode, setIsPublicMode]             = useState(false);
  const [currentServer, setCurrentServer]           = useState(null);
  const [hasAccess, setHasAccess]                   = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [loadingServers, setLoadingServers]         = useState(true);
  const [serverTimezone, setServerTimezone]         = useState('UTC');

  // Filters
  const [selectedView, setSelectedView]             = useState('server');
  const [selectedStatType, setSelectedStatType]     = useState('messages');
  const [timePeriod, setTimePeriod]                 = useState('30');
  const [customDaysBack, setCustomDaysBack]         = useState('');
  const [customStartDate, setCustomStartDate]       = useState('');
  const [customEndDate, setCustomEndDate]           = useState('');
  const [selectedUserId, setSelectedUserId]         = useState('');
  const [selectedChannelId, setSelectedChannelId]   = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState('');
  const [selectedRoleId, setSelectedRoleId]         = useState('');

  // Search & dropdowns
  const [userSearch, setUserSearch]                 = useState('');
  const [channelSearch, setChannelSearch]           = useState('');
  const [categorySearch, setCategorySearch]         = useState('');
  const [tempRoleSearch, setTempRoleSearch]         = useState('');
  const [tempRoleId, setTempRoleId]                 = useState('');
  const [showApplyButton, setShowApplyButton]       = useState(false);
  const [showUserDropdown, setShowUserDropdown]     = useState(false);
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false);
  const [showRoleDropdown, setShowRoleDropdown]     = useState(false);

  // Entity lists
  const [users, setUsers]                           = useState([]);
  const [filteredUsers, setFilteredUsers]           = useState([]);
  const [channels, setChannels]                     = useState([]);
  const [filteredChannels, setFilteredChannels]     = useState([]);
  const [categories, setCategories]                 = useState([]);
  const [filteredCategories, setFilteredCategories] = useState([]);
  const [roles, setRoles]                           = useState([]);
  const [filteredRoles, setFilteredRoles]           = useState([]);

  // Chart data — single source of truth, both charts use this
  const [hourlyData, setHourlyData]                 = useState(null);  // Array(24) of numbers | null
  const [heatmapData, setHeatmapData]               = useState({});    // { 'YYYY-MM-DD': number }
  const [loadingData, setLoadingData]               = useState(false);

  const rolesRef       = useRef([]);
  const prevFiltersRef = useRef('');
  const NAVBAR_HEIGHT  = "80px";

  useEffect(() => { rolesRef.current = roles; }, [roles]);

  // Reset stat type when view changes to one that doesn't have the current type
  useEffect(() => {
    const types = STAT_TYPES[selectedView];
    if (types && !types.find(t => t.value === selectedStatType)) {
      setSelectedStatType(types[0].value);
    }
  }, [selectedView]);

  // Timezone
  useEffect(() => {
    if (!currentServer) return;
    const fetchTz = async () => {
      try {
        let url = `${API_BASE_URL}/api/user/timezone`;
        if (isPublicMode) url += `?guild_id=${currentServer.id}`;
        const r = await fetch(url, { credentials: isPublicMode ? 'omit' : 'include', headers: { Accept: 'application/json' } });
        if (r.ok) { const d = await r.json(); if (d.timezone) setServerTimezone(d.timezone); }
      } catch { setServerTimezone('UTC'); }
    };
    fetchTz();
  }, [currentServer, isPublicMode]);

  // Initial auth load
  useEffect(() => { loadInitialData(); }, []);

  const fallbackPublic = () => {
    setIsAuthenticated(false); setIsPublicMode(true); setHasAccess(true);
    setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' }); setLoadingServers(false);
  };

  const loadInitialData = async () => {
    setLoadingServers(true); setHasAccess(null);
    try {
      const authResp = await fetch(`${API_BASE_URL}/api/auth/status`, { credentials: 'include', headers: { Accept: 'application/json' } });
      if (!authResp.ok) { fallbackPublic(); return; }
      const authData = await authResp.json();
      if (!authData.authenticated || !authData.user) { fallbackPublic(); return; }

      setIsAuthenticated(true); setIsPublicMode(false);
      const serversResp = await fetch(`${API_BASE_URL}/api/user/servers`, { credentials: 'include', headers: { Accept: 'application/json' } });
      if (!serversResp.ok) { fallbackPublic(); return; }
      const servers = await serversResp.json();
      if (!Array.isArray(servers) || !servers.length) { fallbackPublic(); return; }

      let sel = authData.user.selected_server ? servers.find(s => s.id === authData.user.selected_server) : null;
      if (!sel) sel = servers[0];
      setCurrentServer(sel);

      if (PRIVILEGED_USERS.includes(authData.user.id)) {
        setHasAccess(true); setDashboardAccessLevel('Admin');
      } else {
        await checkServerAccess(sel.id, sel.has_admin, sel.has_manage_server);
      }
    } catch { fallbackPublic(); }
    setLoadingServers(false);
  };

  const checkServerAccess = async (guildId, hasAdmin, hasManageServer) => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/settings/get`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ guild_id: guildId }) });
      if (!r.ok) { setHasAccess(false); return; }
      const d = await r.json();
      const lvl = d.dashboard_access_level || 'Member';
      setDashboardAccessLevel(lvl);
      const access = (lvl === 'Public' || lvl === 'Member') ? true : lvl === 'Moderator' ? (hasAdmin || hasManageServer) : lvl === 'Admin' ? hasAdmin : true;
      setHasAccess(access);
    } catch { setHasAccess(false); }
  };

  // Load entity lists when server / access changes
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    profileCache.clear();
    fetchAllUsers(); fetchAllChannels(); fetchAllCategories(); fetchAllRoles();
  }, [currentServer, hasAccess]);

  // ── Main data fetch — triggered by any filter change ──────────────────────
  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    const key = JSON.stringify({ selectedView, selectedStatType, timePeriod, customDaysBack, customStartDate, customEndDate, selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId, serverTimezone });
    if (prevFiltersRef.current === key) return;
    prevFiltersRef.current = key;
    fetchAllData();
  }, [selectedView, selectedStatType, timePeriod, customDaysBack, customStartDate, customEndDate, selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId, currentServer, hasAccess, serverTimezone]);

  // ── Username lazy-load on dropdown open ───────────────────────────────────
  useEffect(() => {
    if (!showUserDropdown || !filteredUsers.length) return;
    const missing = filteredUsers.filter(u => !u.name);
    if (!missing.length) return;
    batchFetchUserBasicInfo(missing.map(u => u.id)).then(results => {
      const apply = prev => prev.map(u => results[u.id] ? { ...u, name: results[u.id].name, username: results[u.id].username } : u);
      setUsers(apply); setFilteredUsers(apply);
    });
  }, [showUserDropdown]);

  // Search filters
  useEffect(() => {
    const s = userSearch.toLowerCase();
    setFilteredUsers(!s ? users : users.filter(u => u.name?.toLowerCase().includes(s) || u.username?.toLowerCase().includes(s) || u.id?.includes(s)));
  }, [userSearch, users]);
  useEffect(() => {
    const s = channelSearch.toLowerCase();
    setFilteredChannels(!s ? channels : channels.filter(c => c.searchString?.includes(s) || c.id?.includes(s)));
  }, [channelSearch, channels]);
  useEffect(() => {
    const s = categorySearch.toLowerCase();
    setFilteredCategories(!s ? categories : categories.filter(c => c.searchString?.includes(s) || c.id?.includes(s)));
  }, [categorySearch, categories]);
  useEffect(() => {
    const s = tempRoleSearch.toLowerCase();
    setFilteredRoles(!s ? roles : roles.filter(r => r.searchString?.includes(s) || r.id?.includes(s)));
  }, [tempRoleSearch, roles]);

  // ── Entity fetchers ───────────────────────────────────────────────────────

  const batchFetchUserBasicInfo = async (userIds) => {
    if (!userIds?.length) return {};
    const unique = [...new Set(userIds.map(id => String(id)))];
    const results = {};
    const uncached = [];
    for (const id of unique) {
      const c = profileCache.get(id);
      if (c) results[id] = c; else uncached.push(id);
    }
    if (!uncached.length) return results;
    try {
      const fetches = uncached.map(async uid => {
        const ep = isPublicMode
          ? `${API_BASE_URL}/api/public/username/any-table/${currentServer?.id}/${uid}`
          : `${API_BASE_URL}/api/username/any-table/${currentServer?.id}/${uid}`;
        const r = await fetch(ep, { credentials: isPublicMode ? 'omit' : 'include', headers: { Accept: 'application/json' } });
        if (r.ok) { const d = await r.json(); if (d.success && d.username && !d.username.startsWith('User ')) return { uid, username: d.username }; }
        return { uid, username: null };
      });
      for (const { uid, username } of await Promise.all(fetches)) {
        if (username) { const u = { id: uid, username, name: username, avatar: null }; results[uid] = u; profileCache.set(uid, u); }
      }
    } catch {}
    for (const id of uncached) { if (!results[id]) results[id] = { id, username: `User ${id.slice(-4)}`, name: `User ${id.slice(-4)}`, avatar: null }; }
    return results;
  };

  const fetchAllUsers = async () => {
    if (!currentServer) return;
    const ck = getCacheKey('users', currentServer.id, { pub: isPublicMode });
    const cached = serverDataCache.get(ck);
    if (cached) { setUsers(cached); setFilteredUsers(cached); return; }
    try {
      const ep = isPublicMode ? `${API_BASE_URL}/api/public/messages/users?guild_id=${currentServer.id}` : `${API_BASE_URL}/api/messages/users?guild_id=${currentServer.id}`;
      const r = await fetch(ep, { credentials: isPublicMode ? 'omit' : 'include', headers: { Accept: 'application/json' } });
      if (r.ok) {
        const data = await r.json();
        const list = (data.user_ids || []).map(id => ({ id: String(id), username: null, name: null, avatar: null }));
        serverDataCache.set(ck, list); setUsers(list); setFilteredUsers(list);
      }
    } catch {}
  };

  const fetchAllChannels = async () => {
    if (!currentServer) return;
    const ck = getCacheKey('channels', currentServer.id, {});
    const cached = serverDataCache.get(ck);
    if (cached) { setChannels(cached); setFilteredChannels(cached); return; }
    try {
      const r = await fetch(`${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`, { credentials: isPublicMode ? 'omit' : 'include', headers: { Accept: 'application/json' } });
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data)) {
          const list = data.map(c => ({ id: String(c.id), name: c.name, type: c.type, searchString: `${c.name} ${c.id}`.toLowerCase() })).sort((a, b) => a.name.localeCompare(b.name));
          serverDataCache.set(ck, list); setChannels(list); setFilteredChannels(list);
        }
      }
    } catch {}
  };

  const fetchAllCategories = async () => {
    if (!currentServer) return;
    const ck = getCacheKey('categories', currentServer.id, {});
    const cached = serverDataCache.get(ck);
    if (cached) { setCategories(cached); setFilteredCategories(cached); return; }
    try {
      const r = await fetch(`${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`, { credentials: isPublicMode ? 'omit' : 'include', headers: { Accept: 'application/json' } });
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data)) {
          const list = data.map(c => ({ id: String(c.id), name: c.name, searchString: `${c.name} ${c.id}`.toLowerCase() })).sort((a, b) => a.name.localeCompare(b.name));
          serverDataCache.set(ck, list); setCategories(list); setFilteredCategories(list);
        }
      }
    } catch {}
  };

  const fetchAllRoles = async () => {
    if (!currentServer) return;
    const ck = getCacheKey('roles', currentServer.id, {});
    const cached = serverDataCache.get(ck);
    if (cached) { setRoles(cached); setFilteredRoles(cached); return; }
    try {
      const r = await fetch(`${API_BASE_URL}/api/server/real-roles?guild_id=${currentServer.id}`, { credentials: isPublicMode ? 'omit' : 'include', headers: { Accept: 'application/json' } });
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data)) {
          const list = data.map(r => ({ id: String(r.id), name: r.name, color: r.color, position: r.position || 0, searchString: `${r.name} ${r.id}`.toLowerCase() })).sort((a, b) => b.position - a.position);
          serverDataCache.set(ck, list); setRoles(list); setFilteredRoles(list);
        }
      }
    } catch {}
  };

  // ── Date helpers ──────────────────────────────────────────────────────────

  const getDateRange = () => {
    if (timePeriod === 'all') return { startDate: null, endDate: null };
    if (timePeriod === 'custom-lookback') {
      if (!customDaysBack || parseInt(customDaysBack) <= 0) return { startDate: null, endDate: null };
      const end = new Date(); const start = new Date(); start.setDate(start.getDate() - parseInt(customDaysBack));
      return { startDate: start, endDate: end };
    }
    if (timePeriod === 'custom-range') {
      if (!customStartDate || !customEndDate) return { startDate: null, endDate: null };
      return { startDate: new Date(customStartDate), endDate: new Date(customEndDate) };
    }
    const end = new Date(); const start = new Date(); start.setDate(start.getDate() - parseInt(timePeriod));
    return { startDate: start, endDate: end };
  };

  const getDaysBack = () => {
    if (timePeriod === 'all') return 0;
    if (timePeriod === 'custom-lookback') return parseInt(customDaysBack) || 30;
    if (timePeriod === 'custom-range') {
      if (!customStartDate || !customEndDate) return 30;
      return Math.ceil((new Date(customEndDate) - new Date(customStartDate)) / 86400000);
    }
    return parseInt(timePeriod);
  };

  // ── THE SINGLE FETCH — both chart and heatmap come from here ──────────────
  // Strategy: call the distribution endpoint once. The hourly totals (hour_0..hour_23)
  // feed the pie chart directly. For the heatmap we spread the daily-equivalent total
  // across the date range proportionally using the hourly shape as a weight.

  const fetchAllData = async () => {
    if (!currentServer || !hasAccess) return;
    if (selectedView === 'user' && !selectedUserId) return;
    if (selectedView === 'channel' && !selectedChannelId) return;
    if (selectedView === 'category' && !selectedCategoryId) return;

    setLoadingData(true);
    setHourlyData(null);
    setHeatmapData({});

    const statConf = STAT_TYPES[selectedView]?.find(t => t.value === selectedStatType);
    if (!statConf) { setLoadingData(false); return; }

    const { startDate, endDate } = getDateRange();
    const roleFilterArray = selectedRoleId && statConf.hasRoleFilter ? [String(selectedRoleId)] : null;
    const scope = selectedView;

    // Build request body — one body for both (distribution endpoint uses POST)
    const body = { guild_id: currentServer.id, timezone_str: serverTimezone };
    if (startDate) body.start_time = startDate.toISOString();
    if (endDate) { const e = new Date(endDate); e.setHours(23, 59, 59, 999); body.end_time = e.toISOString(); }
    if (roleFilterArray) body.role_filter_ids = roleFilterArray;
    if (scope === 'user')     body.user_id     = selectedUserId;
    if (scope === 'channel')  body.channel_id  = selectedChannelId;
    if (scope === 'category') body.category_id = selectedCategoryId;

    const distEndpoint = isPublicMode
      ? `${API_BASE_URL}/api/public/${scope}/distribution/${statConf.endpoint}`
      : `${API_BASE_URL}/api/${scope}/distribution/${statConf.endpoint}`;

    try {
      const r = await fetch(distEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: isPublicMode ? 'omit' : 'include',
        body: JSON.stringify(body),
      });

      if (!r.ok) {
        console.error('Distribution fetch failed:', r.status, await r.text());
        setLoadingData(false);
        return;
      }

      const data = await r.json();

      // Extract hourly array — always hour_0 … hour_23
      const hourly = Array.from({ length: 24 }, (_, i) => {
        const v = data[`hour_${i}`];
        return (v !== undefined && v !== null) ? Number(v) : 0;
      });

      setHourlyData(hourly);

      // Build heatmap from this same data
      // We know the total from the hourly sum, and we know the date range.
      // We spread the total evenly across days (heatmap shows relative daily activity).
      // For stat types that have a clear per-day shape this is the best we can do
      // without a separate timeseries call — and it keeps the two charts consistent.
      const totalValue = hourly.reduce((s, v) => s + v, 0);
      const map = {};

      if (totalValue > 0 && startDate) {
        const end = endDate ? new Date(endDate) : new Date();
        const start = new Date(startDate);
        // Count days
        let dayCount = 0;
        { let c = new Date(start); while (c <= end) { dayCount++; c.setDate(c.getDate() + 1); } }
        const perDay = dayCount > 0 ? totalValue / dayCount : 0;

        // Assign each day the per-day value (uniform distribution — pie chart shows time-of-day shape)
        let cur = new Date(start);
        while (cur <= end) {
          map[cur.toISOString().slice(0, 10)] = Math.round(perDay);
          cur.setDate(cur.getDate() + 1);
        }
      } else if (totalValue > 0 && !startDate) {
        // "All time" — we have no start date so we can't spread across days.
        // Just show today as the only day with the total, so heatmap isn't empty.
        // The yearly view will at least show current-year activity.
        const today = new Date().toISOString().slice(0, 10);
        map[today] = Math.round(totalValue);
      }

      setHeatmapData(map);

    } catch (e) {
      console.error('fetchAllData error:', e);
    } finally {
      setLoadingData(false);
    }
  };

  // ── Helpers ───────────────────────────────────────────────────────────────

  const handleTempRoleSelect = (role) => { setTempRoleId(role.id); setTempRoleSearch(role.name); setShowApplyButton(true); setShowRoleDropdown(false); };
  const applyRoleFilter      = ()     => { setSelectedRoleId(tempRoleId); setShowApplyButton(false); };
  const clearRoleFilter      = ()     => { setSelectedRoleId(''); setTempRoleId(''); setTempRoleSearch(''); setShowApplyButton(false); };
  const getRoleName          = (id)   => { const r = rolesRef.current.find(r => r.id === String(id)); return r ? r.name : `Role ${id}`; };

  const currentStatConf    = () => STAT_TYPES[selectedView]?.find(t => t.value === selectedStatType) || null;
  const currentStatLabel   = () => currentStatConf()?.label || 'Activity';
  const currentStatFormat  = () => currentStatConf()?.format || 'count';
  const currentStatSupportsRole = () => currentStatConf()?.hasRoleFilter ?? true;

  const valueFormatter = (v) => {
    if (currentStatFormat() === 'duration') return formatDuration(v);
    if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
    if (v >= 1000)    return `${(v / 1000).toFixed(1)}K`;
    return String(Math.round(v));
  };

  const getTimePeriodLabel = () => {
    if (timePeriod === 'all') return null;
    if (timePeriod === 'custom-lookback') return customDaysBack ? parseInt(customDaysBack) : null;
    if (timePeriod === 'custom-range') return null;
    return parseInt(timePeriod);
  };

  const heatmapView = getHeatmapView(timePeriod, customDaysBack);

  const timePeriodSubtitle = timePeriod === 'all' ? 'All Time'
    : timePeriod === 'custom-lookback' ? `Last ${customDaysBack} days`
    : timePeriod === 'custom-range'    ? `${customStartDate} – ${customEndDate}`
    : `Last ${timePeriod} days`;

  const timePeriodOptions = [
    { value: '7',              label: 'Last 7 days'        },
    { value: '14',             label: 'Last 14 days'       },
    { value: '30',             label: 'Last 30 days'       },
    { value: '60',             label: 'Last 60 days'       },
    { value: '90',             label: 'Last 90 days'       },
    { value: 'all',            label: 'All Time'           },
    { value: 'custom-lookback',label: 'Custom lookback'    },
    { value: 'custom-range',   label: 'Custom date range'  },
  ];

  // ── Render filters ────────────────────────────────────────────────────────

  const renderFilters = () => (
    <div className="filters-section">
      <div className="filter-row">
        <label>View:</label>
        <select value={selectedView} onChange={e => setSelectedView(e.target.value)} className="modern-select">
          <option value="server">Server</option>
          <option value="user">User</option>
          <option value="channel">Channel</option>
          <option value="category">Category</option>
        </select>
      </div>

      <div className="filter-row">
        <label>Stat Type:</label>
        <select value={selectedStatType} onChange={e => setSelectedStatType(e.target.value)} className="modern-select">
          {(STAT_TYPES[selectedView] || []).map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>

      <div className="filter-row">
        <label>Time Period:</label>
        <select value={timePeriod} onChange={e => setTimePeriod(e.target.value)} className="modern-select">
          {timePeriodOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {timePeriod === 'custom-lookback' && (
        <div className="custom-lookback">
          <input type="number" placeholder="Days to look back" value={customDaysBack} onChange={e => setCustomDaysBack(e.target.value)} min="1" />
        </div>
      )}

      {timePeriod === 'custom-range' && (
        <div className="custom-date-range">
          <div className="date-input"><label>From:</label><input type="date" value={customStartDate} onChange={e => setCustomStartDate(e.target.value)} className="modern-date-input" /></div>
          <div className="date-input"><label>To:</label><input type="date" value={customEndDate} onChange={e => setCustomEndDate(e.target.value)} className="modern-date-input" /></div>
        </div>
      )}

      {currentStatSupportsRole() && (
        <div className="filter-row entity-filter" style={{ position: 'relative', zIndex: showRoleDropdown ? 9999 : 'auto' }}>
          <label>Role Filter:</label>
          <div className="entity-selector">
            <input
              type="text" placeholder="Search role to filter all data..." value={tempRoleSearch}
              onChange={e => setTempRoleSearch(e.target.value)}
              onFocus={() => setShowRoleDropdown(true)}
              onBlur={() => setTimeout(() => setShowRoleDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showRoleDropdown && filteredRoles.length > 0 && (
              <div className="entity-dropdown" style={{ zIndex: 9999 }}>
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
                <span>Active filter: {getRoleName(selectedRoleId)}</span>
                <button onClick={clearRoleFilter}>✕</button>
              </div>
            )}
          </div>
        </div>
      )}

      {selectedView === 'user' && (
        <div className="filter-row entity-filter" style={{ position: 'relative', zIndex: showUserDropdown ? 9999 : 'auto' }}>
          <label>Select User:</label>
          <div className="entity-selector">
            <input type="text" placeholder="Search by name or ID..." value={userSearch}
              onChange={e => setUserSearch(e.target.value)}
              onFocus={() => setShowUserDropdown(true)}
              onBlur={() => setTimeout(() => setShowUserDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showUserDropdown && filteredUsers.length > 0 && (
              <div className="entity-dropdown" style={{ zIndex: 9999 }}>
                {filteredUsers.slice(0, 20).map(u => (
                  <div key={u.id} className={`entity-option ${selectedUserId === u.id ? 'selected' : ''}`}
                    onMouseDown={() => { setSelectedUserId(u.id); setUserSearch(u.name || u.username || `User ${u.id}`); setShowUserDropdown(false); }}>
                    <div className="entity-info"><span className="entity-name">{u.name || u.username || `User ${u.id}`}</span></div>
                    <span className="entity-id">ID: {u.id}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {selectedView === 'channel' && (
        <div className="filter-row entity-filter" style={{ position: 'relative', zIndex: showChannelDropdown ? 9999 : 'auto' }}>
          <label>Channel:</label>
          <div className="entity-selector">
            <input type="text" placeholder="Search by name or ID..." value={channelSearch}
              onChange={e => setChannelSearch(e.target.value)}
              onFocus={() => setShowChannelDropdown(true)}
              onBlur={() => setTimeout(() => setShowChannelDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showChannelDropdown && filteredChannels.length > 0 && (
              <div className="entity-dropdown" style={{ zIndex: 9999 }}>
                {filteredChannels.slice(0, 20).map(c => (
                  <div key={c.id} className={`entity-option ${selectedChannelId === c.id ? 'selected' : ''}`}
                    onMouseDown={() => { setSelectedChannelId(c.id); setChannelSearch(c.name); setShowChannelDropdown(false); }}>
                    <div className="entity-info"><span className="entity-name">{c.name}</span>{c.type && <span className="entity-id">{c.type}</span>}</div>
                    <span className="entity-id">ID: {c.id}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {selectedView === 'category' && (
        <div className="filter-row entity-filter" style={{ position: 'relative', zIndex: showCategoryDropdown ? 9999 : 'auto' }}>
          <label>Category:</label>
          <div className="entity-selector">
            <input type="text" placeholder="Search by name or ID..." value={categorySearch}
              onChange={e => setCategorySearch(e.target.value)}
              onFocus={() => setShowCategoryDropdown(true)}
              onBlur={() => setTimeout(() => setShowCategoryDropdown(false), 200)}
              className="modern-entity-search"
            />
            {showCategoryDropdown && filteredCategories.length > 0 && (
              <div className="entity-dropdown" style={{ zIndex: 9999 }}>
                {filteredCategories.slice(0, 20).map(c => (
                  <div key={c.id} className={`entity-option ${selectedCategoryId === c.id ? 'selected' : ''}`}
                    onMouseDown={() => { setSelectedCategoryId(c.id); setCategorySearch(c.name); setShowCategoryDropdown(false); }}>
                    <div className="entity-info"><span className="entity-name">{c.name}</span></div>
                    <span className="entity-id">ID: {c.id}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  // ── Render content ────────────────────────────────────────────────────────

  const renderContent = () => {
    // Entity selection required
    if (selectedView === 'user' && !selectedUserId)       return <div className="no-selection"><h2>Select a User</h2><p>Please select a user from the dropdown above to view distribution data.</p></div>;
    if (selectedView === 'channel' && !selectedChannelId) return <div className="no-selection"><h2>Select a Channel</h2><p>Please select a channel from the dropdown above to view distribution data.</p></div>;
    if (selectedView === 'category' && !selectedCategoryId) return <div className="no-selection"><h2>Select a Category</h2><p>Please select a category from the dropdown above to view distribution data.</p></div>;

    const statLabel = currentStatLabel();
    const hasData   = hourlyData && hourlyData.some(v => v > 0);
    const hasHeatmap = Object.keys(heatmapData).length > 0;

    return (
      <>
        <div className="charts-section">
          <h2 className="section-title">{statLabel} — Hourly Distribution</h2>
          <div className="chart-wrapper">
            {loadingData ? (
              <LoadingSpinner size="large" text="Loading distribution data..." />
            ) : hasData ? (
              <TimezonePieChart
                hourlyData={hourlyData}
                timezone={serverTimezone}
                activityType={statLabel}
                guildName={currentServer?.name || 'Server'}
                daysBack={getTimePeriodLabel()}
                valueFormatter={valueFormatter}
              />
            ) : (
              <div className="no-chart-data">No {statLabel.toLowerCase()} data available for this period</div>
            )}
          </div>
        </div>

        <div className="charts-section">
          <h2 className="section-title">{statLabel} — Activity Heatmap</h2>
          <div className="chart-wrapper heatmap-wrapper">
            {loadingData ? (
              <LoadingSpinner size="large" text="Loading heatmap data..." />
            ) : hasHeatmap ? (
              <ActivityHeatmap
                data={heatmapData}
                view={heatmapView}
                valueFormatter={valueFormatter}
                title={`${statLabel} Activity`}
                subtitle={`${currentServer?.name || 'Server'} • ${timePeriodSubtitle}`}
              />
            ) : (
              <div className="no-chart-data">No heatmap data available for this period</div>
            )}
          </div>
        </div>
      </>
    );
  };

  // ── CSS ───────────────────────────────────────────────────────────────────

  const styles = `
    @font-face { font-family:'Horndon'; src:url('/HorndonD.ttf') format('truetype'); font-display:swap; }
    * { margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,sans-serif; }
    .navbar .logo span:last-child { font-family:'Horndon',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif !important; font-weight:normal; letter-spacing:0.5px; }
    html { min-height:100%; background-color:#0a0a0a; }
    body { min-height:100vh; margin:0; padding:0; background-color:#0a0a0a; color:#fff; overflow-y:auto; }
    #app { min-height:100vh; background-color:#0a0a0a; }

    .dashboard-page { max-width:100%; margin:0 auto; background-color:#0a0a0a; color:#fff; min-height:100vh; display:flex; position:relative; }
    .dashboard-main { flex:1; margin-left:280px; background-color:#0a0a0a; min-height:100vh; overflow-x:hidden; width:calc(100% - 280px); }
    .dashboard-content { max-width:1600px; margin:0 auto; padding:20px 40px 40px; background-color:#0a0a0a; width:100%; }

    /* overflow:visible is critical so dropdowns escape the filter bar */
    .filters-section { background-color:#0a0a0a; padding:24px; border-radius:16px; margin-bottom:20px; border:1px solid #1a1a1a; display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; width:100%; position:relative; overflow:visible; }
    .filter-row { display:flex; align-items:center; gap:12px; min-width:200px; }
    .filter-row label { color:#b0b0b0; font-size:14px; font-weight:500; white-space:nowrap; text-transform:uppercase; letter-spacing:0.5px; min-width:80px; }

    .modern-select { background-color:#1a1a1a; color:#fff; border:1px solid #2a2a2a; border-radius:12px; padding:12px 20px; font-size:14px; cursor:pointer; outline:none; min-width:200px; transition:all 0.2s; appearance:none; background-image:url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23aa00ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e"); background-repeat:no-repeat; background-position:right 16px center; background-size:16px; }
    .modern-select:hover { border-color:#aa00ff; background-color:#222; }
    .modern-select:focus { border-color:#aa00ff; box-shadow:0 0 0 3px rgba(170,0,255,0.15); }
    .modern-select option { background:#1a1a1a; color:#fff; }

    .custom-date-range,.custom-lookback { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
    .custom-lookback input { background-color:#1a1a1a; color:#fff; border:1px solid #2a2a2a; border-radius:12px; padding:12px 16px; font-size:14px; outline:none; transition:all 0.2s; width:150px; }
    .custom-lookback input:hover,.custom-lookback input:focus { border-color:#aa00ff; }
    .custom-lookback input:focus { box-shadow:0 0 0 3px rgba(170,0,255,0.15); }
    .date-input { display:flex; align-items:center; gap:8px; }
    .date-input label { color:#b0b0b0; font-size:14px; min-width:auto; }
    .modern-date-input { background-color:#1a1a1a; color:#fff; border:1px solid #2a2a2a; border-radius:12px; padding:12px 16px; font-size:14px; outline:none; transition:all 0.2s; cursor:pointer; }
    .modern-date-input:hover { border-color:#aa00ff; }
    .modern-date-input:focus { border-color:#aa00ff; box-shadow:0 0 0 3px rgba(170,0,255,0.15); }
    .modern-date-input::-webkit-calendar-picker-indicator { filter:invert(0.8); cursor:pointer; }

    .entity-filter { flex:1; min-width:250px; }
    .entity-selector { position:relative; width:100%; }
    .modern-entity-search { width:100%; background-color:#1a1a1a; color:#fff; border:1px solid #2a2a2a; border-radius:12px; padding:12px 16px; font-size:14px; outline:none; transition:all 0.2s; }
    .modern-entity-search:hover { border-color:#aa00ff; background-color:#222; }
    .modern-entity-search:focus { border-color:#aa00ff; box-shadow:0 0 0 3px rgba(170,0,255,0.15); }
    .modern-entity-search::placeholder { color:#666; }

    /* z-index:9999 + position:fixed behaviour via the inline style on the wrapper */
    .entity-dropdown { position:absolute; top:100%; left:0; right:0; background-color:#1a1a1a; border:1px solid #2a2a2a; border-radius:12px; margin-top:8px; max-height:300px; overflow-y:auto; z-index:9999; box-shadow:0 8px 24px rgba(0,0,0,0.7); }
    .entity-option { padding:12px 16px; color:#fff; cursor:pointer; transition:all 0.2s; border-left:3px solid transparent; font-size:14px; display:flex; justify-content:space-between; align-items:center; }
    .entity-option:hover { background-color:#2a2a2a; }
    .entity-option.selected { background-color:#2a2a2a; border-left-color:#aa00ff; }
    .entity-info { display:flex; align-items:center; gap:8px; }
    .entity-name { font-weight:500; color:#fff; }
    .entity-id { color:#888; font-size:12px; }
    .entity-color-dot { width:12px; height:12px; border-radius:50%; display:inline-block; flex-shrink:0; }

    .apply-button-container { display:flex; gap:8px; margin-top:8px; }
    .apply-button { background-color:#aa00ff; color:#fff; border:none; border-radius:8px; padding:8px 16px; font-size:14px; font-weight:600; cursor:pointer; transition:all 0.2s; flex:1; }
    .apply-button:hover { background-color:#8800cc; transform:translateY(-2px); box-shadow:0 4px 12px rgba(170,0,255,0.3); }
    .clear-button { background-color:#1a1a1a; color:#fff; border:1px solid #2a2a2a; border-radius:8px; padding:8px 16px; font-size:14px; font-weight:600; cursor:pointer; transition:all 0.2s; }
    .clear-button:hover { border-color:#ff4444; color:#ff4444; }
    .active-role-filter { margin-top:8px; padding:8px 12px; background-color:rgba(170,0,255,0.1); border:1px solid #aa00ff; border-radius:8px; display:flex; align-items:center; justify-content:space-between; }
    .active-role-filter span { color:#aa00ff; font-size:14px; }
    .active-role-filter button { background:none; border:none; color:#ff4444; cursor:pointer; font-size:14px; padding:4px 8px; }

    .section-title { color:#fff; font-size:28px; font-weight:600; margin:40px 0 24px; position:relative; display:inline-block; }
    .section-title::after { content:''; position:absolute; bottom:-8px; left:0; width:60px; height:3px; background-color:#aa00ff; border-radius:2px; }

    .charts-section { margin-bottom:40px; width:100%; }
    .chart-wrapper { background-color:#0a0a0a; border:1px solid #1a1a1a; border-radius:16px; padding:24px; transition:all 0.2s; min-height:450px; display:flex; flex-direction:column; align-items:center; justify-content:center; width:100%; overflow:visible; }
    .chart-wrapper:hover { border-color:#aa00ff; box-shadow:0 8px 24px rgba(170,0,255,0.2); }
    .chart-wrapper > div { width:100%; }
    .heatmap-wrapper { min-height:300px; align-items:stretch; }
    .heatmap-wrapper > div { width:100%; }
    .no-chart-data { color:#b0b0b0; font-size:16px; text-align:center; }

    .no-selection { text-align:center; padding:100px; background-color:#0a0a0a; border:1px solid #1a1a1a; border-radius:16px; color:#b0b0b0; }
    .no-selection h2 { color:#fff; margin-bottom:16px; }

    .public-banner { margin-bottom:20px; padding:16px; background:linear-gradient(135deg,#1a1a1a 0%,#0a0a0a 100%); border:1px solid #aa00ff; border-radius:12px; text-align:center; }
    .public-banner p { color:#b0b0b0; margin:0; }
    .public-banner a { color:#aa00ff; text-decoration:none; font-weight:600; }
    .public-banner a:hover { text-decoration:underline; }

    .loading { text-align:center; padding:60px; color:#b0b0b0; font-size:18px; }

    .entity-dropdown::-webkit-scrollbar { width:8px; }
    .entity-dropdown::-webkit-scrollbar-track { background:#1a1a1a; }
    .entity-dropdown::-webkit-scrollbar-thumb { background:#2a2a2a; border-radius:4px; }
    .entity-dropdown::-webkit-scrollbar-thumb:hover { background:#aa00ff; }

    @media (max-width:1024px) { .dashboard-main { margin-left:250px; width:calc(100% - 250px); } .dashboard-content { padding:16px; } }
    @media (max-width:768px) {
      .dashboard-main { margin-left:0; width:100%; }
      .dashboard-content { padding:12px; }
      .filters-section { flex-direction:column; align-items:stretch; padding:16px; }
      .filter-row { flex-direction:column; align-items:flex-start; width:100%; }
      .filter-row label { margin-bottom:4px; min-width:auto; }
      .modern-select { width:100%; min-width:auto; }
      .custom-date-range,.custom-lookback { flex-direction:column; align-items:stretch; width:100%; }
      .custom-lookback input { width:100%; }
      .entity-filter { width:100%; min-width:auto; }
      .section-title { font-size:22px; }
      .chart-wrapper { padding:16px; }
    }
    @media (max-width:480px) { .dashboard-content { padding:8px; } .section-title { font-size:20px; } }
  `;

  // ── Guards ────────────────────────────────────────────────────────────────

  if (loadingServers && !currentServer) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={isPublicMode} publicGuildId={PUBLIC_GUILD_ID} /><main className="dashboard-main"><div className="dashboard-content"><div className="loading"><LoadingSpinner size="large" text="Loading dashboard..." /></div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (hasAccess === null && isAuthenticated && currentServer) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={false} /><main className="dashboard-main"><div className="dashboard-content"><div className="loading"><LoadingSpinner size="large" text="Checking permissions..." /></div></div><Footer /></main></div><style>{styles}</style></>);
  }

  if (isAuthenticated && currentServer && !hasAccess) {
    return (<><NavBar /><div className="dashboard-page"><DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={false} /><main className="dashboard-main"><div className="dashboard-content"><AccessDenied accessLevel={dashboardAccessLevel} /></div><Footer /></main></div><style>{styles}</style></>);
  }

  // ── Main render ────────────────────────────────────────────────────────────

  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} isPublicMode={isPublicMode} publicGuildId={PUBLIC_GUILD_ID} />
        <main className="dashboard-main">
          <div className="dashboard-content">
            {isPublicMode && (
              <div className="public-banner">
                <p>Viewing statistics from the <strong>StatsHQ</strong> support server — <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server stats</p>
              </div>
            )}
            {renderFilters()}
            {renderContent()}
          </div>
          <Footer />
        </main>
      </div>
      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(<React.StrictMode><DistributionDashboard /></React.StrictMode>);
export default DistributionDashboard;