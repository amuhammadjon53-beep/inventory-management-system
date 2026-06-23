import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import Leaderboard from "../../../Components/Leaderboard.jsx";

// API base URL - your FastAPI backend
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

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
    this.cache.set(key, { data: value, timestamp: Date.now() });
  }

  get(key) {
    const entry = this.cache.get(key);
    if (entry && (Date.now() - entry.timestamp < this.TTL)) {
      return entry.data;
    }
    if (entry) this.cache.delete(key);
    return null;
  }

  clear() {
    this.cache.clear();
  }
}

const profileCache = new ProfileCache(500);
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);

const getCacheKey = (type, id, params) => `${type}:${id}:${JSON.stringify(params)}`;

const buildUrl = (baseUrl, params) => {
  const url = new URL(baseUrl, window.location.origin);
  Object.keys(params).forEach(key => {
    if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
      if (key === 'role_filter_ids' && Array.isArray(params[key]) && params[key].length > 0) {
        url.searchParams.append(key, params[key].join(','));
      } else if (Array.isArray(params[key])) {
        if (params[key].length > 0) url.searchParams.append(key, params[key].join(','));
      } else {
        url.searchParams.append(key, params[key]);
      }
    }
  });
  return url.toString();
};

// Loading Spinner Component
const LoadingSpinner = ({ size = "medium", text = "Loading..." }) => {
  const spinnerSize = size === "small" ? "24px" : size === "medium" ? "40px" : "60px";
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: '30px', gap: '12px',
      width: '100%', height: '100%', minHeight: '150px'
    }}>
      <div style={{
        width: spinnerSize, height: spinnerSize,
        border: '3px solid #2a2a2a', borderTop: '3px solid #aa00ff',
        borderRadius: '50%', animation: 'spin 1s linear infinite'
      }} />
      {text && <span style={{ color: '#b0b0b0', fontSize: '14px' }}>{text}</span>}
      <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
};

const LoadingCard = () => (
  <div className="leaderboard-wrapper">
    <LoadingSpinner size="medium" text="Loading data..." />
  </div>
);

const AccessDenied = ({ accessLevel }) => {
  let requiredPermission = "Manage Server or Administrator";
  if (accessLevel === 'Admin') requiredPermission = "Administrator";
  return (
    <div className="no-selection">
      <h2>🔒 Access Denied</h2>
      <p>You don't have permission to view this server's statistics.</p>
      <p>This server requires <strong>{requiredPermission}</strong> permissions.</p>
      <p className="setting-note" style={{ marginTop: '12px', fontSize: '12px', color: '#666' }}>
        Note: Server owners automatically have Administrator permission.
      </p>
    </div>
  );
};

// ---- Components defined OUTSIDE MentionsDashboard to prevent focus loss on re-render ----

const FiltersSection = ({
  selectedView, setSelectedView,
  timePeriod, setTimePeriod,
  customDaysBack, setCustomDaysBack,
  customStartDate, setCustomStartDate,
  customEndDate, setCustomEndDate,
  timePeriodOptions,
  // Role filter
  showRoleFilter,
  tempRoleSearch, setTempRoleSearch,
  showRoleDropdown, setShowRoleDropdown,
  filteredRoles,
  tempRoleId,
  handleTempRoleSelect,
  clearRoleFilter,
  showApplyButton,
  applyRoleFilter,
  selectedRoleId,
  getRoleName,
  // User filter
  userSearch, setUserSearch,
  showUserDropdown, setShowUserDropdown,
  filteredUsers,
  selectedUserId,
  handleUserSelect,
  // Channel filter
  channelSearch, setChannelSearch,
  showChannelDropdown, setShowChannelDropdown,
  filteredChannels,
  selectedChannelId,
  handleChannelSelect,
  // Category filter
  categorySearch, setCategorySearch,
  showCategoryDropdown, setShowCategoryDropdown,
  filteredCategories,
  selectedCategoryId,
  handleCategorySelect,
}) => (
  <div className="filters-section">
    <div className="filter-row">
      <label>View:</label>
      <select value={selectedView} onChange={(e) => setSelectedView(e.target.value)} className="modern-select">
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
        <input type="number" placeholder="Days to look back" value={customDaysBack} onChange={(e) => setCustomDaysBack(e.target.value)} min="1" />
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

    {showRoleFilter && (
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
              <div className="entity-option" onMouseDown={() => { clearRoleFilter(); setShowRoleDropdown(false); }}>
                <div className="entity-info"><span className="entity-name">Clear Role Filter</span></div>
                <span className="entity-id">✕</span>
              </div>
              {filteredRoles.slice(0, 20).map(role => (
                <div key={role.id} className={`entity-option ${tempRoleId === role.id ? 'selected' : ''}`} onMouseDown={() => handleTempRoleSelect(role)}>
                  <div className="entity-info">
                    <span className="entity-color-dot" style={{ backgroundColor: role.color || '#99aab5' }}></span>
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
                  <div className="entity-info"><span className="entity-name">{user.global_name || user.username || user.name || `User ${user.id}`}</span></div>
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
            placeholder="Search by name or ID..."
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
                  <div className="entity-info">
                    <span className="entity-name">{channel.name}</span>
                    {channel.type && <span className="entity-id">{channel.type}</span>}
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
                <div key={category.id} className={`entity-option ${selectedCategoryId === category.id ? 'selected' : ''}`} onMouseDown={() => handleCategorySelect(category)}>
                  <div className="entity-info"><span className="entity-name">{category.name}</span></div>
                  <span className="entity-id">ID: {category.id}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )}
  </div>
);

const ScopeLeaderboards = ({
  loadingSummaryStats,
  loadingSent, topSentData,
  loadingReceived, topReceivedData,
  loadingRatioHigh, topRatioHighData,
  loadingRatioLow, topRatioLowData,
  summaryData, scopeName,
  formatValue,
}) => (
  <>
    <div className="summary-stats">
      {loadingSummaryStats ? (
        <>
          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
          <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
        </>
      ) : summaryData && (
        <>
          <div className="stat-card">
            <h3>Total Mentions Sent</h3>
            <p className="stat-value">{(summaryData.totalSent || 0).toLocaleString()}</p>
          </div>
          <div className="stat-card">
            <h3>Total Mentions Received</h3>
            <p className="stat-value">{(summaryData.totalReceived || 0).toLocaleString()}</p>
          </div>
          <div className="stat-card">
            <h3>Avg Mentions Ratio</h3>
            <p className="stat-value">{summaryData.avgRatio || 'N/A'}</p>
          </div>
          <div className="stat-card">
            <h3>Active Users</h3>
            <p className="stat-value">{(summaryData.activeUsers || 0).toLocaleString()}</p>
          </div>
        </>
      )}
    </div>

    <div className="leaderboards-section">
      <h2 className="section-title">Leaderboards {scopeName ? `— ${scopeName}` : ''}</h2>
      <div className="leaderboards-stack">
        {loadingSent ? <LoadingCard /> : topSentData.length > 0 ? (
          <div className="leaderboard-wrapper">
            <Leaderboard data={topSentData} title="Top Mention Senders" valueLabel="Mentions Sent" valueFormatter={formatValue} showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
              getProfilePicture={async (userId) => { const u = topSentData.find(x => x.userId === userId); return u?.avatar || null; }} />
          </div>
        ) : <div className="no-data-message">No mention sent data available</div>}

        {loadingReceived ? <LoadingCard /> : topReceivedData.length > 0 ? (
          <div className="leaderboard-wrapper">
            <Leaderboard data={topReceivedData} title="Top Mention Receivers" valueLabel="Mentions Received" valueFormatter={formatValue} showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
              getProfilePicture={async (userId) => { const u = topReceivedData.find(x => x.userId === userId); return u?.avatar || null; }} />
          </div>
        ) : <div className="no-data-message">No mention received data available</div>}

        {loadingRatioHigh ? <LoadingCard /> : topRatioHighData.length > 0 ? (
          <div className="leaderboard-wrapper">
            <Leaderboard data={topRatioHighData} title="Most Popular (High Ratio)" valueLabel="Ratio" valueFormatter={(v, item) => item?.ratioDisplay ? `${item.ratioDisplay}x` : `${v}`} showProfilePictures={true} itemType="user" nameKey="name" valueKey="ratioDisplay" idKey="userId" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
              getProfilePicture={async (userId) => { const u = topRatioHighData.find(x => x.userId === userId); return u?.avatar || null; }} />
          </div>
        ) : <div className="no-data-message">No ratio data available</div>}

        {loadingRatioLow ? <LoadingCard /> : topRatioLowData.length > 0 ? (
          <div className="leaderboard-wrapper">
            <Leaderboard data={topRatioLowData} title="Most Ignored (Low Ratio)" valueLabel="Ratio" valueFormatter={(v, item) => item?.ratioDisplay ? `${item.ratioDisplay}x` : `${v}`} showProfilePictures={true} itemType="user" nameKey="name" valueKey="ratioDisplay" idKey="userId" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
              getProfilePicture={async (userId) => { const u = topRatioLowData.find(x => x.userId === userId); return u?.avatar || null; }} />
          </div>
        ) : <div className="no-data-message">No ratio data available</div>}
      </div>
    </div>
  </>
);

const MainContent = ({
  // Filters
  selectedView, setSelectedView,
  timePeriod, setTimePeriod,
  customDaysBack, setCustomDaysBack,
  customStartDate, setCustomStartDate,
  customEndDate, setCustomEndDate,
  timePeriodOptions,
  tempRoleSearch, setTempRoleSearch,
  showRoleDropdown, setShowRoleDropdown,
  filteredRoles, tempRoleId,
  handleTempRoleSelect, clearRoleFilter,
  showApplyButton, applyRoleFilter,
  selectedRoleId, getRoleName,
  userSearch, setUserSearch,
  showUserDropdown, setShowUserDropdown,
  filteredUsers, selectedUserId, handleUserSelect,
  channelSearch, setChannelSearch,
  showChannelDropdown, setShowChannelDropdown,
  filteredChannels, selectedChannelId, handleChannelSelect,
  categorySearch, setCategorySearch,
  showCategoryDropdown, setShowCategoryDropdown,
  filteredCategories, selectedCategoryId, handleCategorySelect,
  // User sub-scope
  userSubScope, setUserSubScope,
  userScopeChannelId, setUserScopeChannelId,
  userScopeCategoryId, setUserScopeCategoryId,
  userScopeChannelSearch, setUserScopeChannelSearch,
  userScopeCategorySearch, setUserScopeCategorySearch,
  showUserScopeChannelDropdown, setShowUserScopeChannelDropdown,
  showUserScopeCategoryDropdown, setShowUserScopeCategoryDropdown,
  // Loading states
  loadingSummaryStats,
  loadingTopSent, loadingTopReceived, loadingTopRatioHigh, loadingTopRatioLow,
  loadingUserMentionsTo, loadingUserMentionsFrom,
  loadingChannelTopSent, loadingChannelTopReceived, loadingChannelTopRatioHigh, loadingChannelTopRatioLow,
  loadingCategoryTopSent, loadingCategoryTopReceived, loadingCategoryTopRatioHigh, loadingCategoryTopRatioLow,
  // Data
  serverSummary, userSummary, channelSummary, categorySummary,
  topSent, topReceived, topRatioHigh, topRatioLow,
  userMentionsTo, userMentionsFrom,
  channelTopSent, channelTopReceived, channelTopRatioHigh, channelTopRatioLow,
  categoryTopSent, categoryTopReceived, categoryTopRatioHigh, categoryTopRatioLow,
  // Helpers
  formatValue, getChannelName, getCategoryName,
}) => (
  <div className="dashboard-content">
    <FiltersSection
      selectedView={selectedView} setSelectedView={setSelectedView}
      timePeriod={timePeriod} setTimePeriod={setTimePeriod}
      customDaysBack={customDaysBack} setCustomDaysBack={setCustomDaysBack}
      customStartDate={customStartDate} setCustomStartDate={setCustomStartDate}
      customEndDate={customEndDate} setCustomEndDate={setCustomEndDate}
      timePeriodOptions={timePeriodOptions}
      showRoleFilter={selectedView !== 'user'}
      tempRoleSearch={tempRoleSearch} setTempRoleSearch={setTempRoleSearch}
      showRoleDropdown={showRoleDropdown} setShowRoleDropdown={setShowRoleDropdown}
      filteredRoles={filteredRoles} tempRoleId={tempRoleId}
      handleTempRoleSelect={handleTempRoleSelect} clearRoleFilter={clearRoleFilter}
      showApplyButton={showApplyButton} applyRoleFilter={applyRoleFilter}
      selectedRoleId={selectedRoleId} getRoleName={getRoleName}
      userSearch={userSearch} setUserSearch={setUserSearch}
      showUserDropdown={showUserDropdown} setShowUserDropdown={setShowUserDropdown}
      filteredUsers={filteredUsers} selectedUserId={selectedUserId} handleUserSelect={handleUserSelect}
      channelSearch={channelSearch} setChannelSearch={setChannelSearch}
      showChannelDropdown={showChannelDropdown} setShowChannelDropdown={setShowChannelDropdown}
      filteredChannels={filteredChannels} selectedChannelId={selectedChannelId} handleChannelSelect={handleChannelSelect}
      categorySearch={categorySearch} setCategorySearch={setCategorySearch}
      showCategoryDropdown={showCategoryDropdown} setShowCategoryDropdown={setShowCategoryDropdown}
      filteredCategories={filteredCategories} selectedCategoryId={selectedCategoryId} handleCategorySelect={handleCategorySelect}
    />

    {selectedView === 'server' && (
      <ScopeLeaderboards
        loadingSummaryStats={loadingSummaryStats}
        loadingSent={loadingTopSent} topSentData={topSent}
        loadingReceived={loadingTopReceived} topReceivedData={topReceived}
        loadingRatioHigh={loadingTopRatioHigh} topRatioHighData={topRatioHigh}
        loadingRatioLow={loadingTopRatioLow} topRatioLowData={topRatioLow}
        summaryData={serverSummary}
        scopeName=""
        formatValue={formatValue}
      />
    )}

    {selectedView === 'user' && (
      <>
        {!selectedUserId ? (
          <div className="no-selection">
            <h2>Select a User</h2>
            <p>Please select a user from the dropdown above to view their mention statistics.</p>
          </div>
        ) : (
          <>
            {/* Sub-scope selector for user view */}
            <div className="sub-scope-section">
              <label>Scope:</label>
              <select
                value={userSubScope}
                onChange={(e) => {
                  setUserSubScope(e.target.value);
                  setUserScopeChannelId("");
                  setUserScopeCategoryId("");
                  setUserScopeChannelSearch("");
                  setUserScopeCategorySearch("");
                }}
                className="modern-select"
                style={{ minWidth: '160px' }}
              >
                <option value="server">Server</option>
                <option value="channel">Channel</option>
                <option value="category">Category</option>
              </select>

              {userSubScope === 'channel' && (
                <div style={{ position: 'relative', minWidth: '250px' }}>
                  <input
                    type="text"
                    placeholder="Search channel..."
                    value={userScopeChannelSearch}
                    onChange={(e) => setUserScopeChannelSearch(e.target.value)}
                    onFocus={() => setShowUserScopeChannelDropdown(true)}
                    onBlur={() => setTimeout(() => setShowUserScopeChannelDropdown(false), 200)}
                    className="modern-entity-search"
                  />
                  {showUserScopeChannelDropdown && filteredChannels.length > 0 && (
                    <div className="entity-dropdown">
                      {filteredChannels.slice(0, 20).map(ch => (
                        <div
                          key={ch.id}
                          className={`entity-option ${userScopeChannelId === ch.id ? 'selected' : ''}`}
                          onMouseDown={() => {
                            setUserScopeChannelId(ch.id);
                            setUserScopeChannelSearch(ch.name);
                            setShowUserScopeChannelDropdown(false);
                          }}
                        >
                          <span className="entity-name">{ch.name}</span>
                          <span className="entity-id">ID: {ch.id}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {userSubScope === 'category' && (
                <div style={{ position: 'relative', minWidth: '250px' }}>
                  <input
                    type="text"
                    placeholder="Search category..."
                    value={userScopeCategorySearch}
                    onChange={(e) => setUserScopeCategorySearch(e.target.value)}
                    onFocus={() => setShowUserScopeCategoryDropdown(true)}
                    onBlur={() => setTimeout(() => setShowUserScopeCategoryDropdown(false), 200)}
                    className="modern-entity-search"
                  />
                  {showUserScopeCategoryDropdown && filteredCategories.length > 0 && (
                    <div className="entity-dropdown">
                      {filteredCategories.slice(0, 20).map(cat => (
                        <div
                          key={cat.id}
                          className={`entity-option ${userScopeCategoryId === cat.id ? 'selected' : ''}`}
                          onMouseDown={() => {
                            setUserScopeCategoryId(cat.id);
                            setUserScopeCategorySearch(cat.name);
                            setShowUserScopeCategoryDropdown(false);
                          }}
                        >
                          <span className="entity-name">{cat.name}</span>
                          <span className="entity-id">ID: {cat.id}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="summary-stats">
              {loadingSummaryStats ? (
                <>
                  <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                  <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                  <div className="stat-card"><LoadingSpinner size="small" text="" /></div>
                </>
              ) : userSummary && (
                <>
                  <div className="stat-card">
                    <h3>Total Mentions Sent</h3>
                    <p className="stat-value">{(userSummary.mentionsSent || 0).toLocaleString()}</p>
                  </div>
                  <div className="stat-card">
                    <h3>Total Mentions Received</h3>
                    <p className="stat-value">{(userSummary.mentionsReceived || 0).toLocaleString()}</p>
                  </div>
                  <div className="stat-card">
                    <h3>Mentions Ratio</h3>
                    <p className="stat-value">{userSummary.ratio || 'N/A'}</p>
                  </div>
                </>
              )}
            </div>

            <div className="leaderboards-section">
              <h2 className="section-title">Mention Interactions</h2>
              <div className="leaderboards-stack">
                {loadingUserMentionsTo ? <LoadingCard /> : userMentionsTo.length > 0 ? (
                  <div className="leaderboard-wrapper">
                    <Leaderboard data={userMentionsTo} title="Users They Mentioned Most" valueLabel="Times Mentioned" valueFormatter={formatValue} showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                      getProfilePicture={async (userId) => { const u = userMentionsTo.find(x => x.userId === userId); return u?.avatar || null; }} />
                  </div>
                ) : <div className="no-data-message">No outgoing mention data available for this user</div>}

                {loadingUserMentionsFrom ? <LoadingCard /> : userMentionsFrom.length > 0 ? (
                  <div className="leaderboard-wrapper">
                    <Leaderboard data={userMentionsFrom} title="Users Who Mentioned Them Most" valueLabel="Times Mentioned" valueFormatter={formatValue} showProfilePictures={true} itemType="user" nameKey="name" valueKey="value" idKey="userId" backgroundColor="transparent" cardBackground="#1a1a1a" accentColor="#aa00ff"
                      getProfilePicture={async (userId) => { const u = userMentionsFrom.find(x => x.userId === userId); return u?.avatar || null; }} />
                  </div>
                ) : <div className="no-data-message">No incoming mention data available for this user</div>}
              </div>
            </div>
          </>
        )}
      </>
    )}

    {selectedView === 'channel' && (
      <>
        {!selectedChannelId ? (
          <div className="no-selection">
            <h2>Select a Channel</h2>
            <p>Please select a channel from the dropdown above to view its mention statistics.</p>
          </div>
        ) : (
          <ScopeLeaderboards
            loadingSummaryStats={loadingSummaryStats}
            loadingSent={loadingChannelTopSent} topSentData={channelTopSent}
            loadingReceived={loadingChannelTopReceived} topReceivedData={channelTopReceived}
            loadingRatioHigh={loadingChannelTopRatioHigh} topRatioHighData={channelTopRatioHigh}
            loadingRatioLow={loadingChannelTopRatioLow} topRatioLowData={channelTopRatioLow}
            summaryData={channelSummary}
            scopeName={getChannelName(selectedChannelId)}
            formatValue={formatValue}
          />
        )}
      </>
    )}

    {selectedView === 'category' && (
      <>
        {!selectedCategoryId ? (
          <div className="no-selection">
            <h2>Select a Category</h2>
            <p>Please select a category from the dropdown above to view its mention statistics.</p>
          </div>
        ) : (
          <ScopeLeaderboards
            loadingSummaryStats={loadingSummaryStats}
            loadingSent={loadingCategoryTopSent} topSentData={categoryTopSent}
            loadingReceived={loadingCategoryTopReceived} topReceivedData={categoryTopReceived}
            loadingRatioHigh={loadingCategoryTopRatioHigh} topRatioHighData={categoryTopRatioHigh}
            loadingRatioLow={loadingCategoryTopRatioLow} topRatioLowData={categoryTopRatioLow}
            summaryData={categorySummary}
            scopeName={getCategoryName(selectedCategoryId)}
            formatValue={formatValue}
          />
        )}
      </>
    )}
  </div>
);

// ---- Main dashboard component ----

const MentionsDashboard = () => {
  const [selectedView, setSelectedView] = useState("server");
  const [timePeriod, setTimePeriod] = useState("30");
  const [customDaysBack, setCustomDaysBack] = useState("");
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [selectedRoleId, setSelectedRoleId] = useState("");

  // User view: sub-scope (server/channel/category)
  const [userSubScope, setUserSubScope] = useState("server");
  const [userScopeChannelId, setUserScopeChannelId] = useState("");
  const [userScopeCategoryId, setUserScopeCategoryId] = useState("");
  const [userScopeChannelSearch, setUserScopeChannelSearch] = useState("");
  const [userScopeCategorySearch, setUserScopeCategorySearch] = useState("");
  const [showUserScopeChannelDropdown, setShowUserScopeChannelDropdown] = useState(false);
  const [showUserScopeCategoryDropdown, setShowUserScopeCategoryDropdown] = useState(false);

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
  const [currentServer, setCurrentServer] = useState(null);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(true);
  const [isPublicMode, setIsPublicMode] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [currentUserId, setCurrentUserId] = useState(null);
  const [retentionAlert, setRetentionAlert] = useState(null);
  const [retentionDismissed, setRetentionDismissed] = useState(false);

  // Individual loading states
  const [loadingSummaryStats, setLoadingSummaryStats] = useState(true);
  const [loadingTopSent, setLoadingTopSent] = useState(true);
  const [loadingTopReceived, setLoadingTopReceived] = useState(true);
  const [loadingTopRatioHigh, setLoadingTopRatioHigh] = useState(true);
  const [loadingTopRatioLow, setLoadingTopRatioLow] = useState(true);
  const [loadingUserMentionsTo, setLoadingUserMentionsTo] = useState(true);
  const [loadingUserMentionsFrom, setLoadingUserMentionsFrom] = useState(true);
  const [loadingChannelTopSent, setLoadingChannelTopSent] = useState(true);
  const [loadingChannelTopReceived, setLoadingChannelTopReceived] = useState(true);
  const [loadingChannelTopRatioHigh, setLoadingChannelTopRatioHigh] = useState(true);
  const [loadingChannelTopRatioLow, setLoadingChannelTopRatioLow] = useState(true);
  const [loadingCategoryTopSent, setLoadingCategoryTopSent] = useState(true);
  const [loadingCategoryTopReceived, setLoadingCategoryTopReceived] = useState(true);
  const [loadingCategoryTopRatioHigh, setLoadingCategoryTopRatioHigh] = useState(true);
  const [loadingCategoryTopRatioLow, setLoadingCategoryTopRatioLow] = useState(true);

  // Summary data
  const [serverSummary, setServerSummary] = useState(null);
  const [userSummary, setUserSummary] = useState(null);
  const [channelSummary, setChannelSummary] = useState(null);
  const [categorySummary, setCategorySummary] = useState(null);

  // Leaderboard data
  const [topSent, setTopSent] = useState([]);
  const [topReceived, setTopReceived] = useState([]);
  const [topRatioHigh, setTopRatioHigh] = useState([]);
  const [topRatioLow, setTopRatioLow] = useState([]);

  // User-specific
  const [userMentionsTo, setUserMentionsTo] = useState([]);
  const [userMentionsFrom, setUserMentionsFrom] = useState([]);

  // Channel-specific
  const [channelTopSent, setChannelTopSent] = useState([]);
  const [channelTopReceived, setChannelTopReceived] = useState([]);
  const [channelTopRatioHigh, setChannelTopRatioHigh] = useState([]);
  const [channelTopRatioLow, setChannelTopRatioLow] = useState([]);

  // Category-specific
  const [categoryTopSent, setCategoryTopSent] = useState([]);
  const [categoryTopReceived, setCategoryTopReceived] = useState([]);
  const [categoryTopRatioHigh, setCategoryTopRatioHigh] = useState([]);
  const [categoryTopRatioLow, setCategoryTopRatioLow] = useState([]);

  const [channelNames, setChannelNames] = useState({});
  const [categoryNames, setCategoryNames] = useState({});
  const [roleColors, setRoleColors] = useState({});

  const [usersLoaded, setUsersLoaded] = useState(false);
  const [channelsLoaded, setChannelsLoaded] = useState(false);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [rolesLoaded, setRolesLoaded] = useState(false);

  const fetchedRef = useRef(false);
  const prevFiltersRef = useRef(JSON.stringify({
    selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
    selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId,
    userSubScope, userScopeChannelId, userScopeCategoryId
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

  const NAVBAR_HEIGHT = "80px";

  const getApiEndpoint = (endpoint, isPublic) => {
    if (isPublic) return endpoint.replace('/api/', '/api/public/');
    return endpoint;
  };

  const isPrivilegedUser = (userId) => PRIVILEGED_USERS.includes(userId);

  useEffect(() => { loadInitialData(); }, []);

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
        credentials: 'include', headers: { 'Accept': 'application/json' }
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
              credentials: 'include', headers: { 'Accept': 'application/json' }
            });

            if (serversResponse.ok) {
              const servers = await serversResponse.json();
              if (Array.isArray(servers) && servers.length > 0) {
                let selectedServer = null;
                if (authData.user.selected_server) {
                  selectedServer = servers.find(s => s.id === authData.user.selected_server);
                }
                if (!selectedServer) selectedServer = servers[0];
                if (selectedServer) setCurrentServer(selectedServer);
                else { setIsPublicMode(true); setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' }); }
              } else { setIsPublicMode(true); setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' }); }
            } else { setIsPublicMode(true); setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' }); }

            setLoadingServers(false);
            return;
          }

          const serversResponse = await fetch(`${API_BASE_URL}/api/user/servers`, {
            credentials: 'include', headers: { 'Accept': 'application/json' }
          });

          if (serversResponse.ok) {
            const servers = await serversResponse.json();
            if (Array.isArray(servers) && servers.length > 0) {
              let selectedServer = null;
              if (authData.user.selected_server) {
                selectedServer = servers.find(s => s.id === authData.user.selected_server);
              }
              if (!selectedServer) selectedServer = servers[0];
              if (selectedServer) {
                setCurrentServer(selectedServer);
                await checkServerAccess(selectedServer.id, selectedServer.permissions, selectedServer.has_admin, selectedServer.has_manage_server);
              } else setLoadingServers(false);
            } else setLoadingServers(false);
          } else setLoadingServers(false);
        } else {
          setIsAuthenticated(false);
          setIsPublicMode(true);
          setHasAccess(true);
          setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
          setLoadingServers(false);
        }
      } else {
        setIsAuthenticated(false);
        setIsPublicMode(true);
        setHasAccess(true);
        setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
        setLoadingServers(false);
      }
    } catch (error) {
      console.error('Error loading initial data:', error);
      setApiError('Failed to load data. Please check your connection.');
      setIsPublicMode(true);
      setHasAccess(true);
      setCurrentServer({ id: PUBLIC_GUILD_ID, name: 'StatsHQ' });
      setLoadingServers(false);
    }
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

        let hasAccessFlag = false;
        if (accessLevel === 'Public' || accessLevel === 'Member') hasAccessFlag = true;
        else if (accessLevel === 'Moderator') hasAccessFlag = hasAdmin || hasManageServer;
        else if (accessLevel === 'Admin') hasAccessFlag = hasAdmin;
        else hasAccessFlag = true;

        setHasAccess(hasAccessFlag);
        const timeParams = applyServerTimePeriod(settingsData);
        setLoading(false);
        
        // Fetch data immediately with the computed params
        await fetchDataWithParams(timeParams);
      } else {
        setHasAccess(false);
        setLoading(false);
      }
    } catch (error) {
      console.error('Error checking server access:', error);
      setHasAccess(false);
      setLoading(false);
    }
  };

  // NEW: fetchDataWithParams - uses overrides instead of state
  const fetchDataWithParams = async (overrides = {}) => {
    if (!currentServer || !hasAccess) return;
    setLoading(true);
    setApiError(null);

    const effectiveTimePeriod = overrides.timePeriod ?? timePeriod;
    const effectiveCustomDaysBack = overrides.customDaysBack ?? customDaysBack;
    const effectiveCustomStartDate = overrides.customStartDate ?? customStartDate;
    const effectiveCustomEndDate = overrides.customEndDate ?? customEndDate;

    let startDate = null;
    let endDate = null;

    if (effectiveTimePeriod === "all") {
      startDate = null;
      endDate = null;
    } else if (effectiveTimePeriod === "custom-lookback") {
      if (!effectiveCustomDaysBack || parseInt(effectiveCustomDaysBack) <= 0) {
        startDate = null;
        endDate = null;
      } else {
        endDate = new Date();
        startDate = new Date();
        startDate.setDate(startDate.getDate() - parseInt(effectiveCustomDaysBack));
      }
    } else if (effectiveTimePeriod === "custom-range") {
      if (!effectiveCustomStartDate || !effectiveCustomEndDate) {
        startDate = null;
        endDate = null;
      } else {
        startDate = new Date(effectiveCustomStartDate);
        endDate = new Date(effectiveCustomEndDate);
      }
    } else {
      endDate = new Date();
      startDate = new Date();
      startDate.setDate(startDate.getDate() - parseInt(effectiveTimePeriod));
    }

    try {
      if (selectedView === 'server') await fetchServerDataWithDates(startDate, endDate);
      else if (selectedView === 'user' && selectedUserId) await fetchUserDataWithDates(startDate, endDate);
      else if (selectedView === 'channel' && selectedChannelId) await fetchChannelDataWithDates(startDate, endDate);
      else if (selectedView === 'category' && selectedCategoryId) await fetchCategoryDataWithDates(startDate, endDate);
    } catch (error) {
      console.error('Error fetching data:', error);
      setApiError(error.message);
    } finally {
      setLoading(false);
      fetchedRef.current = true;
    }
  };

  // Helper functions for fetchDataWithParams
  const fetchServerDataWithDates = async (startDate, endDate) => {
    const isPublic = isPublicMode;
    const guildId = currentServer.id;
    const roleFilterIds = selectedRoleId ? selectedRoleId : undefined;
    const startTime = startDate?.toISOString();
    const endTime = endDate?.toISOString();

    const baseParams = { guild_id: guildId, role_filter_ids: roleFilterIds, start_time: startTime, end_time: endTime, limit: 100 };
    const prefix = isPublic ? `${API_BASE_URL}/api/public` : `${API_BASE_URL}/api`;
    const creds = isPublic ? 'omit' : 'include';

    setLoadingSummaryStats(true);
    setLoadingTopSent(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/sent/server`, baseParams);
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setTopSent(formatted);
        const totalSent = data.reduce((acc, item) => acc + (item.mention_count || 0), 0);
        setServerSummary(prev => ({ ...(prev || {}), totalSent, activeUsers: data.length }));
      }
    } catch (e) { console.error('Error fetching top sent:', e); } finally { setLoadingTopSent(false); }

    setLoadingTopReceived(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/received/server`, baseParams);
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setTopReceived(formatted);
        const totalReceived = data.reduce((acc, item) => acc + (item.mention_count || 0), 0);
        setServerSummary(prev => ({ ...(prev || {}), totalReceived }));
      }
    } catch (e) { console.error('Error fetching top received:', e); } finally { setLoadingTopReceived(false); }

    setLoadingTopRatioHigh(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/ratio/server`, { ...baseParams, min_mentions_sent: 1 });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatRatioLeaderboard(data);
        setTopRatioHigh(formatted);
        const validRatios = data.filter(d => d.ratio !== null && d.ratio !== undefined && !isNaN(d.ratio));
        const avgRatio = validRatios.length > 0 ? (validRatios.reduce((acc, d) => acc + parseFloat(d.ratio), 0) / validRatios.length).toFixed(2) : 'N/A';
        setServerSummary(prev => ({ ...(prev || {}), avgRatio }));
      }
    } catch (e) { console.error('Error fetching ratio high:', e); } finally { setLoadingTopRatioHigh(false); }

    setLoadingTopRatioLow(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/ratio/server`, { ...baseParams, min_mentions_sent: 1 });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const reversed = [...data].reverse();
        const formatted = await formatRatioLeaderboard(reversed);
        setTopRatioLow(formatted);
      }
    } catch (e) { console.error('Error fetching ratio low:', e); } finally { setLoadingTopRatioLow(false); }

    setLoadingSummaryStats(false);
  };

  const fetchUserDataWithDates = async (startDate, endDate) => {
    if (!selectedUserId) return;
    const isPublic = isPublicMode;
    const guildId = currentServer.id;
    const startTime = startDate?.toISOString();
    const endTime = endDate?.toISOString();
    const prefix = isPublic ? `${API_BASE_URL}/api/public` : `${API_BASE_URL}/api`;
    const creds = isPublic ? 'omit' : 'include';

    let scopeSuffix = 'server';
    let extraParam = {};
    if (userSubScope === 'channel' && userScopeChannelId) {
      scopeSuffix = 'channel';
      extraParam = { channel_id: userScopeChannelId };
    } else if (userSubScope === 'category' && userScopeCategoryId) {
      scopeSuffix = 'category';
      extraParam = { category_id: userScopeCategoryId };
    }

    const baseParams = { guild_id: guildId, start_time: startTime, end_time: endTime, limit: 100, ...extraParam };

    setLoadingSummaryStats(true);

    try {
      const url = buildUrl(`${prefix}/mentions/ratio/${scopeSuffix}`, { ...baseParams, user_id: selectedUserId });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        setUserSummary({
          mentionsSent: data.mentions_sent || 0,
          mentionsReceived: data.mentions_received || 0,
          ratio: data.ratio !== null && data.ratio !== undefined ? parseFloat(data.ratio).toFixed(2) : 'N/A'
        });
      }
    } catch (e) { console.error('Error fetching user ratio:', e); }

    setLoadingSummaryStats(false);

    setLoadingUserMentionsTo(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/to-user/${scopeSuffix}`, { ...baseParams, source_user_id: selectedUserId });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setUserMentionsTo(formatted);
      }
    } catch (e) { console.error('Error fetching user mentions to:', e); } finally { setLoadingUserMentionsTo(false); }

    setLoadingUserMentionsFrom(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/target-user/${scopeSuffix}`, { ...baseParams, target_user_id: selectedUserId });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setUserMentionsFrom(formatted);
      }
    } catch (e) { console.error('Error fetching user mentions from:', e); } finally { setLoadingUserMentionsFrom(false); }
  };

  const fetchChannelDataWithDates = async (startDate, endDate) => {
    if (!selectedChannelId) return;
    const isPublic = isPublicMode;
    const guildId = currentServer.id;
    const roleFilterIds = selectedRoleId ? selectedRoleId : undefined;
    const startTime = startDate?.toISOString();
    const endTime = endDate?.toISOString();
    const prefix = isPublic ? `${API_BASE_URL}/api/public` : `${API_BASE_URL}/api`;
    const creds = isPublic ? 'omit' : 'include';
    const baseParams = { guild_id: guildId, channel_id: selectedChannelId, role_filter_ids: roleFilterIds, start_time: startTime, end_time: endTime, limit: 100 };

    setLoadingSummaryStats(true);

    setLoadingChannelTopSent(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/sent/channel`, baseParams);
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setChannelTopSent(formatted);
        const totalSent = data.reduce((acc, item) => acc + (item.mention_count || 0), 0);
        setChannelSummary(prev => ({ ...(prev || {}), totalSent, activeUsers: data.length }));
      }
    } catch (e) { console.error('Error fetching channel top sent:', e); } finally { setLoadingChannelTopSent(false); }

    setLoadingChannelTopReceived(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/received/channel`, baseParams);
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setChannelTopReceived(formatted);
        const totalReceived = data.reduce((acc, item) => acc + (item.mention_count || 0), 0);
        setChannelSummary(prev => ({ ...(prev || {}), totalReceived }));
      }
    } catch (e) { console.error('Error fetching channel top received:', e); } finally { setLoadingChannelTopReceived(false); }

    setLoadingChannelTopRatioHigh(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/ratio/channel`, { ...baseParams, min_mentions_sent: 1 });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatRatioLeaderboard(data);
        setChannelTopRatioHigh(formatted);
        const validRatios = data.filter(d => d.ratio !== null && !isNaN(d.ratio));
        const avgRatio = validRatios.length > 0 ? (validRatios.reduce((acc, d) => acc + parseFloat(d.ratio), 0) / validRatios.length).toFixed(2) : 'N/A';
        setChannelSummary(prev => ({ ...(prev || {}), avgRatio }));
      }
    } catch (e) { console.error('Error fetching channel ratio high:', e); } finally { setLoadingChannelTopRatioHigh(false); }

    setLoadingChannelTopRatioLow(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/ratio/channel`, { ...baseParams, min_mentions_sent: 1 });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const reversed = [...data].reverse();
        const formatted = await formatRatioLeaderboard(reversed);
        setChannelTopRatioLow(formatted);
      }
    } catch (e) { console.error('Error fetching channel ratio low:', e); } finally { setLoadingChannelTopRatioLow(false); }

    setLoadingSummaryStats(false);
  };

  const fetchCategoryDataWithDates = async (startDate, endDate) => {
    if (!selectedCategoryId) return;
    const isPublic = isPublicMode;
    const guildId = currentServer.id;
    const roleFilterIds = selectedRoleId ? selectedRoleId : undefined;
    const startTime = startDate?.toISOString();
    const endTime = endDate?.toISOString();
    const prefix = isPublic ? `${API_BASE_URL}/api/public` : `${API_BASE_URL}/api`;
    const creds = isPublic ? 'omit' : 'include';
    const baseParams = { guild_id: guildId, category_id: selectedCategoryId, role_filter_ids: roleFilterIds, start_time: startTime, end_time: endTime, limit: 100 };

    setLoadingSummaryStats(true);

    setLoadingCategoryTopSent(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/sent/category`, baseParams);
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setCategoryTopSent(formatted);
        const totalSent = data.reduce((acc, item) => acc + (item.mention_count || 0), 0);
        setCategorySummary(prev => ({ ...(prev || {}), totalSent, activeUsers: data.length }));
      }
    } catch (e) { console.error('Error fetching category top sent:', e); } finally { setLoadingCategoryTopSent(false); }

    setLoadingCategoryTopReceived(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/received/category`, baseParams);
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatLeaderboardUsers(data, 'mention_count');
        setCategoryTopReceived(formatted);
        const totalReceived = data.reduce((acc, item) => acc + (item.mention_count || 0), 0);
        setCategorySummary(prev => ({ ...(prev || {}), totalReceived }));
      }
    } catch (e) { console.error('Error fetching category top received:', e); } finally { setLoadingCategoryTopReceived(false); }

    setLoadingCategoryTopRatioHigh(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/ratio/category`, { ...baseParams, min_mentions_sent: 1 });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const formatted = await formatRatioLeaderboard(data);
        setCategoryTopRatioHigh(formatted);
        const validRatios = data.filter(d => d.ratio !== null && !isNaN(d.ratio));
        const avgRatio = validRatios.length > 0 ? (validRatios.reduce((acc, d) => acc + parseFloat(d.ratio), 0) / validRatios.length).toFixed(2) : 'N/A';
        setCategorySummary(prev => ({ ...(prev || {}), avgRatio }));
      }
    } catch (e) { console.error('Error fetching category ratio high:', e); } finally { setLoadingCategoryTopRatioHigh(false); }

    setLoadingCategoryTopRatioLow(true);
    try {
      const url = buildUrl(`${prefix}/mentions/leaderboard/ratio/category`, { ...baseParams, min_mentions_sent: 1 });
      const res = await fetch(url, { credentials: creds, headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        const reversed = [...data].reverse();
        const formatted = await formatRatioLeaderboard(reversed);
        setCategoryTopRatioLow(formatted);
      }
    } catch (e) { console.error('Error fetching category ratio low:', e); } finally { setLoadingCategoryTopRatioLow(false); }

    setLoadingSummaryStats(false);
  };

  // UPDATED: Fetch settings and apply time period, then fetch data immediately
  useEffect(() => {
    if (!currentServer) return;
    
    const fetchAndApplyTimePeriod = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/settings/get`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: isPublicMode ? 'omit' : 'include',
          body: JSON.stringify({ guild_id: currentServer.id })
        });
        if (response.ok) {
          const data = await response.json();
          const timeParams = applyServerTimePeriod(data);
          await fetchDataWithParams(timeParams);
        } else {
          await fetchData();
        }
      } catch (e) {
        console.error('Error fetching time period settings:', e);
        await fetchData();
      }
    };
    
    fetchAndApplyTimePeriod();
  }, [currentServer]);

  const fetchUserBasicInfo = async (userId) => {
    if (!userId) return null;
    const stringId = String(userId);
    const cached = profileCache.get(stringId);
    if (cached) return cached;

    try {
      const isPublic = isPublicMode;
      const endpoint = isPublic
        ? `${API_BASE_URL}/api/public/username/any-table/${currentServer?.id}/${stringId}`
        : `${API_BASE_URL}/api/username/any-table/${currentServer?.id}/${stringId}`;

      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success && data.username && !data.username.startsWith('User ')) {
          const userData = { id: stringId, username: data.username, global_name: data.username, name: data.username, avatar: null };
          profileCache.set(stringId, userData);
          return userData;
        }
      }
    } catch (error) {
      console.error(`Error fetching user ${stringId}:`, error);
    }

    return { id: stringId, username: `User ${stringId.slice(-4)}`, global_name: null, name: `User ${stringId.slice(-4)}`, avatar: null };
  };

  const batchFetchUserBasicInfo = async (userIds) => {
    if (!userIds || userIds.length === 0) return {};
    const uniqueIds = [...new Set(userIds.map(id => String(id)))];
    const results = {};
    const uncachedIds = [];

    for (const id of uniqueIds) {
      const cached = profileCache.get(id);
      if (cached && cached.name && !cached.name.startsWith('User ')) results[id] = cached;
      else uncachedIds.push(id);
    }

    if (uncachedIds.length === 0) return results;

    try {
      const isPublic = isPublicMode;
      const fetchPromises = uncachedIds.map(async (userId) => {
        const endpoint = isPublic
          ? `${API_BASE_URL}/api/public/username/any-table/${currentServer?.id}/${userId}`
          : `${API_BASE_URL}/api/username/any-table/${currentServer?.id}/${userId}`;

        const response = await fetch(endpoint, {
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
          const userData = { id: userId, username, global_name: username, name: username, avatar: null };
          results[userId] = userData;
          profileCache.set(userId, userData);
        }
      }
    } catch (error) {
      console.error('Error batch fetching usernames:', error);
    }

    for (const id of uncachedIds) {
      if (!results[id]) {
        results[id] = { id, username: `User ${id.slice(-4)}`, global_name: `User ${id.slice(-4)}`, name: `User ${id.slice(-4)}`, avatar: null };
      }
    }

    return results;
  };

  const fetchUserAvatar = async (userId) => {
    if (!userId) return null;
    const stringId = String(userId);
    try {
      const response = await fetch(`${API_BASE_URL}/api/user/profile-picture/${stringId}`, {
        credentials: isPublicMode ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        if (data.success) return data.avatar_url;
      }
    } catch (error) {
      console.error(`Error fetching user avatar ${stringId}:`, error);
    }
    return null;
  };

  const getChannelName = (channelId) => {
    if (!channelId) return 'Unknown Channel';
    const stringId = String(channelId).trim();
    const channel = channelsRef.current.find(c => String(c.id) === stringId);
    if (channel) return channel.name;
    if (channelNamesRef.current[stringId]) return channelNamesRef.current[stringId];
    return `Channel ${stringId}`;
  };

  const getCategoryName = (categoryId) => {
    if (!categoryId) return 'Unknown Category';
    const stringId = String(categoryId).trim();
    const category = categoriesRef.current.find(c => String(c.id) === stringId);
    if (category) return category.name;
    if (categoryNamesRef.current[stringId]) return categoryNamesRef.current[stringId];
    return `Category ${stringId}`;
  };

  const getRoleName = (roleId) => {
    if (!roleId) return 'Unknown Role';
    const stringId = String(roleId).trim();
    const role = rolesRef.current.find(r => String(r.id) === stringId);
    if (role) return role.name;
    return `Role ${stringId}`;
  };

  const fetchAllUsers = async () => {
    if (!currentServer) return;
    const isPublic = isPublicMode;
    setUsersLoaded(false);

    const cacheKey = getCacheKey('users', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setUsers(cached.users);
      setFilteredUsers(cached.users);
      setUsersLoaded(true);
      return;
    }

    try {
      const endpoint = getApiEndpoint(`${API_BASE_URL}/api/messages/users?guild_id=${currentServer.id}`, isPublic);
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });

      if (!response.ok) { setUsersLoaded(true); return; }

      const data = await response.json();
      if (!data.user_ids || data.user_ids.length === 0) { setUsersLoaded(true); return; }

      const userList = data.user_ids.map(userId => ({
        id: String(userId), username: null, global_name: null, name: null, avatar: null
      }));

      serverDataCache.set(cacheKey, { users: userList });
      setUsers(userList);
      setFilteredUsers(userList);
    } catch (error) {
      console.error('Error fetching users:', error);
    } finally {
      setUsersLoaded(true);
    }
  };

  useEffect(() => {
    if (showUserDropdown && filteredUsers.length > 0) {
      const usersWithoutNames = filteredUsers.filter(u => !u.name);
      if (usersWithoutNames.length > 0) {
        const userIds = usersWithoutNames.map(u => u.id);
        batchFetchUserBasicInfo(userIds).then(results => {
          setUsers(prev => prev.map(u => results[u.id] ? { ...u, name: results[u.id].name, username: results[u.id].username } : u));
          setFilteredUsers(prev => prev.map(u => results[u.id] ? { ...u, name: results[u.id].name, username: results[u.id].username } : u));
        });
      }
    }
  }, [showUserDropdown, filteredUsers]);

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
      const response = await fetch(`${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });

      if (response.ok) {
        const channelsData = await response.json();
        if (Array.isArray(channelsData) && channelsData.length > 0) {
          const channelList = [];
          const nameMap = {};
          channelsData.forEach(channel => {
            const channelId = String(channel.id);
            channelList.push({ id: channelId, name: channel.name, type: channel.type, category_id: channel.category_id ? String(channel.category_id) : null, searchString: `${channel.name} ${channelId}`.toLowerCase() });
            nameMap[channelId] = channel.name;
          });
          channelList.sort((a, b) => a.name.localeCompare(b.name));
          serverDataCache.set(cacheKey, { channelList, nameMap });
          setChannels(channelList);
          setFilteredChannels(channelList);
          setChannelNames(nameMap);
        } else { setChannels([]); setFilteredChannels([]); setChannelNames({}); }
      } else { setChannels([]); setFilteredChannels([]); setChannelNames({}); }
    } catch (error) {
      console.error('Error fetching channels:', error);
      setChannels([]); setFilteredChannels([]); setChannelNames({});
    } finally {
      setChannelsLoaded(true);
    }
  };

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
      const response = await fetch(`${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`, {
        credentials: isPublic ? 'omit' : 'include',
        headers: { 'Accept': 'application/json' }
      });

      if (response.ok) {
        const categoriesData = await response.json();
        if (Array.isArray(categoriesData) && categoriesData.length > 0) {
          const categoryList = [];
          const nameMap = {};
          categoriesData.forEach(category => {
            const categoryId = String(category.id);
            categoryList.push({ id: categoryId, name: category.name, searchString: `${category.name} ${categoryId}`.toLowerCase() });
            nameMap[categoryId] = category.name;
          });
          categoryList.sort((a, b) => a.name.localeCompare(b.name));
          serverDataCache.set(cacheKey, { categoryList, nameMap });
          setCategories(categoryList);
          setFilteredCategories(categoryList);
          setCategoryNames(nameMap);
        } else { setCategories([]); setFilteredCategories([]); setCategoryNames({}); }
      } else { setCategories([]); setFilteredCategories([]); setCategoryNames({}); }
    } catch (error) {
      console.error('Error fetching categories:', error);
      setCategories([]); setFilteredCategories([]); setCategoryNames({});
    } finally {
      setCategoriesLoaded(true);
    }
  };

  const fetchAllRoles = async () => {
    if (!currentServer) return;
    const isPublic = isPublicMode;
    setRolesLoaded(false);

    const cacheKey = getCacheKey('roles', currentServer.id, { public: isPublic });
    const cached = serverDataCache.get(cacheKey);
    if (cached) {
      setRoles(cached.roleList);
      setFilteredRoles(cached.roleList);
      setRoleColors(cached.colorMap);
      setRolesLoaded(true);
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/server/real-roles?guild_id=${currentServer.id}`, {
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
            roleList.push({ id: roleId, name: role.name, color: role.color, position: role.position || 0, searchString: `${role.name} ${roleId}`.toLowerCase() });
            nameMap[roleId] = role.name;
            colorMap[roleId] = role.color || '#99aab5';
          });
          roleList.sort((a, b) => b.position - a.position);
          serverDataCache.set(cacheKey, { roleList, nameMap, colorMap });
          setRoles(roleList);
          setFilteredRoles(roleList);
          setRoleColors(colorMap);
        } else { setRoles([]); setFilteredRoles([]); setRoleColors({}); }
      } else { setRoles([]); setFilteredRoles([]); setRoleColors({}); }
    } catch (error) {
      console.error('Error fetching roles:', error);
      setRoles([]); setFilteredRoles([]); setRoleColors({});
    } finally {
      setRolesLoaded(true);
    }
  };

  const resetLoadingStates = () => {
    setLoadingSummaryStats(true);
    setLoadingTopSent(true);
    setLoadingTopReceived(true);
    setLoadingTopRatioHigh(true);
    setLoadingTopRatioLow(true);
    setLoadingUserMentionsTo(true);
    setLoadingUserMentionsFrom(true);
    setLoadingChannelTopSent(true);
    setLoadingChannelTopReceived(true);
    setLoadingChannelTopRatioHigh(true);
    setLoadingChannelTopRatioLow(true);
    setLoadingCategoryTopSent(true);
    setLoadingCategoryTopReceived(true);
    setLoadingCategoryTopRatioHigh(true);
    setLoadingCategoryTopRatioLow(true);
  };

  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    fetchedRef.current = false;
    resetLoadingStates();
    setLoading(true);
    setUsersLoaded(false);
    setChannelsLoaded(false);
    setCategoriesLoaded(false);
    setRolesLoaded(false);
    setTopSent([]); setTopReceived([]); setTopRatioHigh([]); setTopRatioLow([]);
    setUserMentionsTo([]); setUserMentionsFrom([]);
    setChannelTopSent([]); setChannelTopReceived([]); setChannelTopRatioHigh([]); setChannelTopRatioLow([]);
    setCategoryTopSent([]); setCategoryTopReceived([]); setCategoryTopRatioHigh([]); setCategoryTopRatioLow([]);
    setServerSummary(null); setUserSummary(null); setChannelSummary(null); setCategorySummary(null);
    profileCache.clear();

    Promise.all([fetchAllUsers(), fetchAllChannels(), fetchAllCategories(), fetchAllRoles()]).then(() => {
      fetchData();
    });
  }, [currentServer, hasAccess]);

  useEffect(() => {
    if (!currentServer || !hasAccess) return;
    const currentFilters = JSON.stringify({
      selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId,
      userSubScope, userScopeChannelId, userScopeCategoryId
    });
    if (prevFiltersRef.current !== currentFilters) {
      prevFiltersRef.current = currentFilters;
      fetchData();
    }
  }, [selectedView, timePeriod, customDaysBack, customStartDate, customEndDate,
      selectedUserId, selectedChannelId, selectedCategoryId, selectedRoleId,
      userSubScope, userScopeChannelId, userScopeCategoryId]);

  useEffect(() => {
    if (userSearch.trim() === "") setFilteredUsers(users);
    else {
      const searchLower = userSearch.toLowerCase();
      setFilteredUsers(users.filter(u =>
        (u.name?.toLowerCase().includes(searchLower)) ||
        (u.username?.toLowerCase().includes(searchLower)) ||
        u.id?.includes(searchLower)
      ));
    }
  }, [userSearch, users]);

  useEffect(() => {
    if (channelSearch.trim() === "") setFilteredChannels(channels);
    else {
      const searchLower = channelSearch.toLowerCase();
      setFilteredChannels(channels.filter(c => c.searchString?.includes(searchLower) || c.id?.includes(searchLower)));
    }
  }, [channelSearch, channels]);

  useEffect(() => {
    if (categorySearch.trim() === "") setFilteredCategories(categories);
    else {
      const searchLower = categorySearch.toLowerCase();
      setFilteredCategories(categories.filter(c => c.searchString?.includes(searchLower) || c.id?.includes(searchLower)));
    }
  }, [categorySearch, categories]);

  useEffect(() => {
    if (userScopeChannelSearch.trim() === "") setFilteredChannels(channels);
    else {
      const searchLower = userScopeChannelSearch.toLowerCase();
      setFilteredChannels(channels.filter(c => c.searchString?.includes(searchLower) || c.id?.includes(searchLower)));
    }
  }, [userScopeChannelSearch, channels]);

  useEffect(() => {
    if (userScopeCategorySearch.trim() === "") setFilteredCategories(categories);
    else {
      const searchLower = userScopeCategorySearch.toLowerCase();
      setFilteredCategories(categories.filter(c => c.searchString?.includes(searchLower) || c.id?.includes(searchLower)));
    }
  }, [userScopeCategorySearch, categories]);

  useEffect(() => {
    if (tempRoleSearch.trim() === "") setFilteredRoles(roles);
    else {
      const searchLower = tempRoleSearch.toLowerCase();
      setFilteredRoles(roles.filter(r => r.searchString?.includes(searchLower) || r.id?.includes(searchLower)));
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

  const formatLeaderboardUsers = async (data, valueKey) => {
    if (!Array.isArray(data) || data.length === 0) return [];
    const allUserIds = data.map(item => String(item.user_id));
    const infoMap = await batchFetchUserBasicInfo(allUserIds);
    const top3 = allUserIds.slice(0, 3);
    const avatars = await Promise.all(top3.map(id => fetchUserAvatar(id)));
    return data.map((item, index) => {
      const userId = String(item.user_id);
      const info = infoMap[userId];
      const isTop3 = index < 3;
      return {
        userId,
        name: info?.name || `User ${userId.slice(-4)}`,
        value: item[valueKey] || 0,
        avatar: isTop3 ? (avatars[index] || null) : null
      };
    });
  };

  const formatRatioLeaderboard = async (data) => {
    if (!Array.isArray(data) || data.length === 0) return [];
    const allUserIds = data.map(item => String(item.user_id));
    const infoMap = await batchFetchUserBasicInfo(allUserIds);
    const top3 = allUserIds.slice(0, 3);
    const avatars = await Promise.all(top3.map(id => fetchUserAvatar(id)));
    return data.map((item, index) => {
      const userId = String(item.user_id);
      const info = infoMap[userId];
      const isTop3 = index < 3;
      const ratio = item.ratio !== null && item.ratio !== undefined ? parseFloat(item.ratio).toFixed(2) : 'N/A';
      return {
        userId,
        name: info?.name || `User ${userId.slice(-4)}`,
        value: item.mentions_received || 0,
        secondaryValue: item.mentions_sent || 0,
        ratioDisplay: ratio,
        avatar: isTop3 ? (avatars[index] || null) : null
      };
    });
  };

  const fetchData = async () => {
    if (!currentServer || !hasAccess) return;
    setLoading(true);
    setApiError(null);

    try {
      if (selectedView === 'server') await fetchServerData();
      else if (selectedView === 'user' && selectedUserId) await fetchUserData();
      else if (selectedView === 'channel' && selectedChannelId) await fetchChannelData();
      else if (selectedView === 'category' && selectedCategoryId) await fetchCategoryData();
    } catch (error) {
      console.error('Error fetching data:', error);
      setApiError(error.message);
    } finally {
      setLoading(false);
      fetchedRef.current = true;
    }
  };

  const fetchServerData = async () => {
    const { startDate, endDate } = getDateRange();
    await fetchServerDataWithDates(startDate, endDate);
  };

  const fetchUserData = async () => {
    const { startDate, endDate } = getDateRange();
    await fetchUserDataWithDates(startDate, endDate);
  };

  const fetchChannelData = async () => {
    const { startDate, endDate } = getDateRange();
    await fetchChannelDataWithDates(startDate, endDate);
  };

  const fetchCategoryData = async () => {
    const { startDate, endDate } = getDateRange();
    await fetchCategoryDataWithDates(startDate, endDate);
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

  const formatValue = (value) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
    return value.toString();
  };

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

    * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }

    .navbar .logo span:last-child {
      font-family: 'Horndon', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
      font-weight: normal; letter-spacing: 0.5px;
    }

    html { min-height: 100%; background-color: #0a0a0a; }
    body { min-height: 100vh; margin: 0; padding: 0; background-color: #0a0a0a; color: #ffffff; overflow-y: auto; }
    #app { min-height: 100vh; background-color: #0a0a0a; }

    .dashboard-page { max-width: 100%; margin: 0 auto; background-color: #0a0a0a; color: #ffffff; min-height: 100vh; display: flex; position: relative; }
    .dashboard-main { flex: 1; margin-left: 280px; background-color: #0a0a0a; min-height: 100vh; overflow-x: hidden; width: calc(100% - 280px); }
    .dashboard-content { max-width: 1600px; margin: 0 auto; padding: 20px 40px 40px 40px; background-color: #0a0a0a; width: 100%; overflow-x: visible; }

    .leaderboards-stack { display: flex; flex-direction: column; gap: 30px; width: 100%; }

    .leaderboard-wrapper { background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; overflow: visible; transition: all 0.2s ease; width: 100%; min-height: 300px; }
    .leaderboard-wrapper:hover { border-color: #aa00ff; box-shadow: 0 4px 20px rgba(170, 0, 255, 0.2); }
    .leaderboard-wrapper > div { transform: scale(0.95); transform-origin: top left; width: 105.26%; }

    .filters-section { background-color: #0a0a0a; padding: 24px; border-radius: 16px; margin-bottom: 20px; border: 1px solid #1a1a1a; display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; backdrop-filter: blur(10px); width: 100%; }
    .filter-row { display: flex; align-items: center; gap: 12px; min-width: 200px; }
    .filter-row label { color: #b0b0b0; font-size: 14px; font-weight: 500; white-space: nowrap; text-transform: uppercase; letter-spacing: 0.5px; min-width: 80px; }

    .modern-select { background-color: #1a1a1a; color: #ffffff; border: 1px solid #2a2a2a; border-radius: 12px; padding: 12px 20px; font-size: 14px; cursor: pointer; outline: none; min-width: 200px; transition: all 0.2s ease; appearance: none; background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23aa00ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e"); background-repeat: no-repeat; background-position: right 16px center; background-size: 16px; }
    .modern-select:hover { border-color: #aa00ff; background-color: #222; }
    .modern-select:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }

    .custom-date-range, .custom-lookback { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .custom-lookback input { background-color: #1a1a1a; color: #ffffff; border: 1px solid #2a2a2a; border-radius: 12px; padding: 12px 16px; font-size: 14px; outline: none; transition: all 0.2s ease; width: 150px; }
    .custom-lookback input:hover { border-color: #aa00ff; background-color: #222; }
    .custom-lookback input:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }

    .date-input { display: flex; align-items: center; gap: 8px; }
    .date-input label { color: #b0b0b0; font-size: 14px; }
    .modern-date-input { background-color: #1a1a1a; color: #ffffff; border: 1px solid #2a2a2a; border-radius: 12px; padding: 12px 16px; font-size: 14px; outline: none; transition: all 0.2s ease; cursor: pointer; }
    .modern-date-input:hover { border-color: #aa00ff; background-color: #222; }
    .modern-date-input:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }
    .modern-date-input::-webkit-calendar-picker-indicator { filter: invert(0.8); cursor: pointer; }

    .entity-filter { flex: 1; min-width: 250px; position: relative; }
    .entity-selector { position: relative; width: 100%; }
    .modern-entity-search { width: 100%; background-color: #1a1a1a; color: #ffffff; border: 1px solid #2a2a2a; border-radius: 12px; padding: 12px 16px; font-size: 14px; outline: none; transition: all 0.2s ease; }
    .modern-entity-search:hover { border-color: #aa00ff; background-color: #222; }
    .modern-entity-search:focus { border-color: #aa00ff; box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15); }
    .modern-entity-search::placeholder { color: #666; }

    .entity-dropdown { position: absolute; top: 100%; left: 0; right: 0; background-color: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; margin-top: 8px; max-height: 300px; overflow-y: auto; z-index: 1000; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5); backdrop-filter: blur(10px); }
    .entity-option { padding: 12px 16px; color: #ffffff; cursor: pointer; transition: all 0.2s ease; border-left: 3px solid transparent; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
    .entity-option:hover { background-color: #2a2a2a; }
    .entity-option.selected { background-color: #2a2a2a; border-left-color: #aa00ff; }

    .entity-info { display: flex; align-items: center; gap: 8px; }
    .entity-name { font-weight: 500; }
    .entity-id { color: #888; font-size: 12px; }
    .entity-color-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }

    .apply-button-container { display: flex; gap: 8px; margin-top: 8px; }
    .apply-button { background-color: #aa00ff; color: white; border: none; border-radius: 8px; padding: 8px 16px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; flex: 1; }
    .apply-button:hover { background-color: #8800cc; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3); }
    .clear-button { background-color: #1a1a1a; color: #ffffff; border: 1px solid #2a2a2a; border-radius: 8px; padding: 8px 16px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
    .clear-button:hover { border-color: #ff4444; color: #ff4444; background-color: #2a2a2a; }
    .active-role-filter { margin-top: 8px; padding: 8px 12px; background-color: rgba(170, 0, 255, 0.1); border: 1px solid #aa00ff; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; }
    .active-role-filter span { color: #aa00ff; font-size: 14px; }
    .active-role-filter button { background: none; border: none; color: #ff4444; cursor: pointer; font-size: 14px; padding: 4px 8px; }
    .active-role-filter button:hover { text-decoration: underline; }

    .loading { text-align: center; padding: 60px; color: #b0b0b0; font-size: 18px; }
    .error-message { text-align: center; padding: 60px; background-color: #0a0a0a; border: 1px solid #ff3333; border-radius: 16px; color: #ff3333; }
    .no-selection { text-align: center; padding: 100px; background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; color: #b0b0b0; }
    .no-selection h2 { color: #ffffff; margin-bottom: 16px; }
    .setting-note { color: #666; font-size: 12px; margin-top: 8px; }

    .summary-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 24px; margin-bottom: 40px; }
    .stat-card { background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; padding: 28px; transition: all 0.2s ease; min-height: 130px; display: flex; flex-direction: column; justify-content: center; }
    .stat-card:hover { border-color: #aa00ff; box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2); transform: translateY(-2px); }
    .stat-card h3 { color: #b0b0b0; font-size: 16px; font-weight: 500; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-value { color: #ffffff !important; font-size: 42px; font-weight: 700; margin: 0; background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; line-height: 1.2; }

    .section-title { color: #ffffff; font-size: 28px; font-weight: 600; margin: 40px 0 24px 0; position: relative; display: inline-block; }
    .section-title::after { content: ''; position: absolute; bottom: -8px; left: 0; width: 60px; height: 3px; background-color: #aa00ff; border-radius: 2px; }

    .leaderboards-section { margin-bottom: 40px; }
    .no-data-message { text-align: center; padding: 60px; background-color: #0a0a0a; border: 1px solid #1a1a1a; border-radius: 16px; color: #b0b0b0; font-size: 16px; }

    .public-banner { margin-bottom: 20px; padding: 16px; background: linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%); border: 1px solid #aa00ff; border-radius: 12px; text-align: center; }
    .public-banner p { color: #b0b0b0; margin: 0; }
    .public-banner a { color: #aa00ff; text-decoration: none; font-weight: 600; }
    .public-banner a:hover { text-decoration: underline; }

    .sub-scope-section { background-color: #0f0f0f; border: 1px solid #1a1a1a; border-radius: 12px; padding: 16px 20px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
    .sub-scope-section label { color: #b0b0b0; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }

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
      .custom-date-range, .custom-lookback { flex-direction: column; align-items: stretch; width: 100%; }
      .custom-lookback input { width: 100%; }
      .date-input { flex-direction: column; align-items: flex-start; width: 100%; }
      .date-input input[type="date"] { width: 100%; }
      .entity-filter { width: 100%; min-width: auto; }
      .summary-stats { grid-template-columns: 1fr; }
      .section-title { font-size: 22px; }
      .leaderboard-wrapper > div { transform: scale(0.85); transform-origin: top left; width: 117.6%; margin-bottom: -30px; }
      .stat-value { font-size: 28px; }
      .stat-card { padding: 16px; }
    }

    @media (max-width: 480px) {
      .dashboard-content { padding: 8px; }
      .leaderboard-wrapper > div { transform: scale(0.78); width: 128.2%; margin-bottom: -50px; }
      .stat-value { font-size: 24px; }
      .section-title { font-size: 20px; }
    }

    .retention-banner { width:100%; box-sizing:border-box; background:linear-gradient(135deg,#3a2f00 0%,#4a3a00 100%); border-bottom:1px solid #ffcc00; padding:12px 24px; display:flex; align-items:center; justify-content:center; gap:16px; position:relative; }
    .retention-banner-text { color:#ffe066; font-size:14px; font-weight:500; text-align:center; max-width:900px; }
    .retention-banner-close { background:none; border:none; color:#ffe066; font-size:14px; cursor:pointer; padding:4px 8px; border-radius:6px; line-height:1; flex-shrink:0; transition:background-color 0.15s,color 0.15s; }
    .retention-banner-close:hover { background-color:rgba(255,224,102,0.15); color:#fff; }

    .stat-value, .stat-number, .entity-name, .entity-option, .modern-select, .modern-entity-search, .modern-date-input, .custom-lookback input { color: #ffffff !important; }
    @supports (-webkit-touch-callout: none) { .stat-value { background: none !important; -webkit-text-fill-color: #ffffff !important; color: #ffffff !important; } }

    .entity-dropdown::-webkit-scrollbar { width: 8px; }
    .entity-dropdown::-webkit-scrollbar-track { background: #1a1a1a; }
    .entity-dropdown::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 4px; }
    .entity-dropdown::-webkit-scrollbar-thumb:hover { background: #aa00ff; }
  `;

  // Assemble all props for MainContent
  const mainContentProps = {
    selectedView, setSelectedView,
    timePeriod, setTimePeriod,
    customDaysBack, setCustomDaysBack,
    customStartDate, setCustomStartDate,
    customEndDate, setCustomEndDate,
    timePeriodOptions,
    tempRoleSearch, setTempRoleSearch,
    showRoleDropdown, setShowRoleDropdown,
    filteredRoles, tempRoleId,
    handleTempRoleSelect, clearRoleFilter,
    showApplyButton, applyRoleFilter,
    selectedRoleId, getRoleName,
    userSearch, setUserSearch,
    showUserDropdown, setShowUserDropdown,
    filteredUsers, selectedUserId, handleUserSelect,
    channelSearch, setChannelSearch,
    showChannelDropdown, setShowChannelDropdown,
    filteredChannels, selectedChannelId, handleChannelSelect,
    categorySearch, setCategorySearch,
    showCategoryDropdown, setShowCategoryDropdown,
    filteredCategories, selectedCategoryId, handleCategorySelect,
    userSubScope, setUserSubScope,
    userScopeChannelId, setUserScopeChannelId,
    userScopeCategoryId, setUserScopeCategoryId,
    userScopeChannelSearch, setUserScopeChannelSearch,
    userScopeCategorySearch, setUserScopeCategorySearch,
    showUserScopeChannelDropdown, setShowUserScopeChannelDropdown,
    showUserScopeCategoryDropdown, setShowUserScopeCategoryDropdown,
    loadingSummaryStats,
    loadingTopSent, loadingTopReceived, loadingTopRatioHigh, loadingTopRatioLow,
    loadingUserMentionsTo, loadingUserMentionsFrom,
    loadingChannelTopSent, loadingChannelTopReceived, loadingChannelTopRatioHigh, loadingChannelTopRatioLow,
    loadingCategoryTopSent, loadingCategoryTopReceived, loadingCategoryTopRatioHigh, loadingCategoryTopRatioLow,
    serverSummary, userSummary, channelSummary, categorySummary,
    topSent, topReceived, topRatioHigh, topRatioLow,
    userMentionsTo, userMentionsFrom,
    channelTopSent, channelTopReceived, channelTopRatioHigh, channelTopRatioLow,
    categoryTopSent, categoryTopReceived, categoryTopRatioHigh, categoryTopRatioLow,
    formatValue, getChannelName, getCategoryName,
  };

  // ---- Render states ----

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

  if (!isAuthenticated && isPublicMode) {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={true} publicGuildId={PUBLIC_GUILD_ID} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="public-banner">
                <p>Viewing statistics from the <strong>StatsHQ</strong> support server — <a href={`${API_BASE_URL}/api/auth/discord`}>Login</a> to see your own server stats</p>
              </div>
              <MainContent {...mainContentProps} />
            </div>
            <Footer />
          </main>
        </div>
        <style>{styles}</style>
      </>
    );
  }

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
          <MainContent {...mainContentProps} />
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
    <MentionsDashboard />
  </React.StrictMode>
);

export default MentionsDashboard;