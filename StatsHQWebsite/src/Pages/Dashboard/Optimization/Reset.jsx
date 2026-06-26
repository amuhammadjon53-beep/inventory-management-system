import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../../../Components/NavBar.jsx";
import Footer from "../../../Components/Footer.jsx";
import DashboardSidebar from "../../../Components/sidebar.jsx";
import { Crown } from "lucide-react";

// API base URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const NAVBAR_HEIGHT = "80px";
const ACCENT = "#aa00ff";

// PRIVILEGED USERS - bypass all access levels
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

// Simple cache for user profiles with size limit (no avatars)
class ProfileCache {
  constructor(maxSize = 500) {
    this.cache = new Map();
    this.maxSize = maxSize;
  }

  get(key) {
    const value = this.cache.get(key);
    if (value && value.name && !value.name.startsWith('User ')) {
      this.cache.delete(key);
      this.cache.set(key, value);
      return value;
    }
    if (value) {
      this.cache.delete(key);
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
}

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

const profileCache = new ProfileCache(500);
const serverDataCache = new ServerDataCache(30, 5 * 60 * 1000);

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

// Batch fetch user basic info (usernames only, no avatars)
const batchFetchUserBasicInfo = async (userIds, guildId, isPublicMode) => {
  if (!userIds || userIds.length === 0) return {};
  
  const uniqueIds = [...new Set(userIds.map(id => String(id)))];
  const results = {};
  const uncachedIds = [];
  
  for (const id of uniqueIds) {
    const cached = profileCache.get(id);
    if (cached && cached.name && !cached.name.startsWith('User ')) {
      results[id] = cached;
    } else {
      uncachedIds.push(id);
    }
  }
  
  if (uncachedIds.length === 0) return results;
  
  try {
    const fetchPromises = uncachedIds.map(async (userId) => {
      const endpoint = isPublicMode
        ? `${API_BASE_URL}/api/public/username/any-table/${guildId}/${userId}`
        : `${API_BASE_URL}/api/username/any-table/${guildId}/${userId}`;
      
      const response = await fetch(endpoint, {
        credentials: isPublicMode ? 'omit' : 'include',
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
        const userData = {
          id: userId,
          username: username,
          global_name: username,
          name: username,
          avatar: null
        };
        results[userId] = userData;
        profileCache.set(userId, userData);
      }
    }
  } catch (error) {
    console.error('Error batch fetching usernames:', error);
  }
  
  for (const id of uncachedIds) {
    if (!results[id]) {
      const fallback = {
        id: id,
        username: `User ${id.slice(-4)}`,
        global_name: `User ${id.slice(-4)}`,
        name: `User ${id.slice(-4)}`,
        avatar: null
      };
      results[id] = fallback;
    }
  }
  
  return results;
};

// Access Denied Component
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
        <p className="error-message">You don't have permission to reset statistics for this server.</p>
        <p className="error-message">This server requires <strong>{requiredPermission}</strong> permission to reset statistics.</p>
      </div>
    </div>
  );
};

// Loading spinner component
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

const renderWithOptimizationLink = (text) => {
  if (!text || !text.includes('Optimization+')) {
    return (
      <>
        This needs the <a href="/Premium/" className="optimization-lock-link">Optimization+</a> Module
      </>
    );
  }
  const [before, after] = text.split('Optimization+');
  return (
    <>
      {before}
      <a href="/Premium/" className="optimization-lock-link">Optimization+</a>
      {after}
    </>
  );
};

const OptimizationLockNotice = ({ message }) => (
  <div className="optimization-lock">
    <div className="optimization-lock-icon">
      <Crown size={16} color={ACCENT} />
    </div>
    <div className="optimization-lock-text">
      {renderWithOptimizationLink(message)}
    </div>
  </div>
);

// Info Icon Component - without question mark cursor (cursor: pointer)
const InfoIcon = ({ descriptions }) => {
  const [showTooltip, setShowTooltip] = useState(false);
  let timeout;

  const handleMouseEnter = () => {
    timeout = setTimeout(() => setShowTooltip(true), 300);
  };

  const handleMouseLeave = () => {
    clearTimeout(timeout);
    setShowTooltip(false);
  };

  return (
    <span 
      className="info-icon" 
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{ position: 'relative', cursor: 'pointer', marginLeft: '8px' }}
    >
      ⓘ
      {showTooltip && (
        <div className="info-tooltip">
          {descriptions.map((desc, idx) => (
            <div key={idx} style={{ marginBottom: idx < descriptions.length - 1 ? '8px' : '0' }}>
              <strong style={{ color: '#aa00ff' }}>{desc.level}:</strong> {desc.description}
            </div>
          ))}
        </div>
      )}
    </span>
  );
};

// Enhanced Calendar Component with Year/Month selection
const SimpleCalendar = ({ value, onChange, onClose }) => {
  const [viewMode, setViewMode] = useState('day');
  const [currentYear, setCurrentYear] = useState(value ? value.getFullYear() : new Date().getFullYear());
  const [currentMonth, setCurrentMonth] = useState(value ? value.getMonth() : new Date().getMonth());
  const [selectedDate, setSelectedDate] = useState(value ? new Date(value) : null);

  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const dayNames = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

  const getDaysInMonth = (year, month) => {
    return new Date(year, month + 1, 0).getDate();
  };

  const getFirstDayOfMonth = (year, month) => {
    return new Date(year, month, 1).getDay();
  };

  const handleDateClick = (day) => {
    const newDate = new Date(currentYear, currentMonth, day);
    setSelectedDate(newDate);
    onChange(newDate);
    onClose();
  };

  const handleMonthSelect = (monthIndex) => {
    setCurrentMonth(monthIndex);
    setViewMode('day');
  };

  const handleYearSelect = (year) => {
    setCurrentYear(year);
    setViewMode('month');
  };

  const changeYear = (offset) => {
    setCurrentYear(currentYear + offset);
  };

  const getYears = () => {
    const currentYearNow = new Date().getFullYear();
    const years = [];
    for (let i = currentYearNow - 50; i <= currentYearNow + 10; i++) {
      years.push(i);
    }
    return years;
  };

  if (viewMode === 'year') {
    return (
      <div className="calendar-popup">
        <div className="calendar-header">
          <button className="calendar-nav" onClick={() => changeYear(-10)}>◀◀</button>
          <span className="calendar-title" onClick={() => setViewMode('year')}>{currentYear}</span>
          <button className="calendar-nav" onClick={() => changeYear(10)}>▶▶</button>
        </div>
        <div className="calendar-years">
          {getYears().map(year => (
            <div
              key={year}
              className={`calendar-year ${year === currentYear ? 'selected' : ''}`}
              onClick={() => handleYearSelect(year)}
            >
              {year}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (viewMode === 'month') {
    return (
      <div className="calendar-popup">
        <div className="calendar-header">
          <button className="calendar-nav" onClick={() => setViewMode('year')}>◀</button>
          <span className="calendar-title" onClick={() => setViewMode('month')}>{currentYear}</span>
          <button className="calendar-nav" onClick={() => setViewMode('year')}>▶</button>
        </div>
        <div className="calendar-months">
          {monthNames.map((month, index) => (
            <div
              key={month}
              className={`calendar-month ${index === currentMonth ? 'selected' : ''}`}
              onClick={() => handleMonthSelect(index)}
            >
              {month.substring(0, 3)}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const daysInMonth = getDaysInMonth(currentYear, currentMonth);
  const firstDay = getFirstDayOfMonth(currentYear, currentMonth);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const days = [];
  for (let i = 0; i < firstDay; i++) {
    days.push(null);
  }
  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }

  return (
    <div className="calendar-popup">
      <div className="calendar-header">
        <button className="calendar-nav" onClick={() => setViewMode('year')}>◀</button>
        <span className="calendar-title" onClick={() => setViewMode('month')}>
          {monthNames[currentMonth]} {currentYear}
        </span>
        <button className="calendar-nav" onClick={() => setViewMode('year')}>▶</button>
      </div>
      <div className="calendar-weekdays">
        {dayNames.map(day => <div key={day} className="calendar-weekday">{day}</div>)}
      </div>
      <div className="calendar-days">
        {days.map((day, index) => {
          if (day === null) {
            return <div key={`empty-${index}`} className="calendar-day empty"></div>;
          }
          const date = new Date(currentYear, currentMonth, day);
          const isToday = date.getTime() === today.getTime();
          const isSelected = selectedDate && date.getTime() === selectedDate.getTime();
          return (
            <div
              key={day}
              className={`calendar-day ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}`}
              onClick={() => handleDateClick(day)}
            >
              {day}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Compact Time Picker Component
const CompactTimePicker = ({ value, onChange, onClose }) => {
  const [timeFormat, setTimeFormat] = useState('24h');
  const [selectedHour, setSelectedHour] = useState(value ? parseInt(value.split(':')[0]) : 18);
  const [selectedMinute, setSelectedMinute] = useState(value ? parseInt(value.split(':')[1]) : 0);

  const handleConfirm = () => {
    const hour24 = timeFormat === '12h' 
      ? (selectedHour === 12 ? 0 : selectedHour)
      : selectedHour;
    const timeStr = `${String(hour24).padStart(2, '0')}:${String(selectedMinute).padStart(2, '0')}`;
    onChange(timeStr);
    onClose();
  };

  const formatDisplayHour = (hour) => {
    if (timeFormat === '12h') {
      if (hour === 0) return 12;
      if (hour > 12) return hour - 12;
      return hour;
    }
    return hour;
  };

  return (
    <div className="compact-time-picker">
      <div className="compact-time-header">
        <button 
          className={`compact-format-btn ${timeFormat === '12h' ? 'active' : ''}`}
          onClick={() => setTimeFormat('12h')}
        >
          12h
        </button>
        <button 
          className={`compact-format-btn ${timeFormat === '24h' ? 'active' : ''}`}
          onClick={() => setTimeFormat('24h')}
        >
          24h
        </button>
      </div>
      <div className="compact-time-body">
        <div className="compact-time-column">
          <button className="compact-time-arrow" onClick={() => setSelectedHour((selectedHour + 1) % (timeFormat === '24h' ? 24 : 12))}>▲</button>
          <div className="compact-time-value">{String(formatDisplayHour(selectedHour)).padStart(2, '0')}</div>
          <button className="compact-time-arrow" onClick={() => setSelectedHour((selectedHour - 1 + (timeFormat === '24h' ? 24 : 12)) % (timeFormat === '24h' ? 24 : 12))}>▼</button>
        </div>
        <div className="compact-time-separator">:</div>
        <div className="compact-time-column">
          <button className="compact-time-arrow" onClick={() => setSelectedMinute((selectedMinute + 15) % 60)}>▲</button>
          <div className="compact-time-value">{String(selectedMinute).padStart(2, '0')}</div>
          <button className="compact-time-arrow" onClick={() => setSelectedMinute((selectedMinute - 15 + 60) % 60)}>▼</button>
        </div>
      </div>
      <button className="compact-time-confirm" onClick={handleConfirm}>Confirm</button>
    </div>
  );
};

// ============================================
// STYLES
// ============================================

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

  .navbar {
    position: sticky !important;
    top: 0 !important;
    z-index: 1000 !important;
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

  /* Schedule Management Page Styles */
  .schedules-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .schedule-card {
    background: linear-gradient(135deg, #0f0f0f 0%, #0a0a0a 100%);
    border: 1px solid #1f1f1f;
    border-radius: 16px;
    padding: 20px;
    transition: all 0.3s ease;
  }

  .schedule-card:hover {
    border-color: #2a2a2a;
  }

  .schedule-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #1f1f1f;
  }

  .schedule-name {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
  }

  .schedule-status {
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 20px;
    background-color: rgba(0, 184, 148, 0.2);
    color: #00b894;
  }

  .schedule-card-content {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }

  .schedule-detail {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .detail-label {
    font-size: 11px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .detail-value {
    font-size: 14px;
    color: white;
    font-weight: 500;
  }

  .schedule-card-actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    padding-top: 12px;
    border-top: 1px solid #1f1f1f;
  }

  .schedule-action-btn {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s ease;
    color: #b0b0b0;
  }

  .schedule-action-btn:hover {
    border-color: #aa00ff;
    color: #aa00ff;
  }

  .schedule-action-btn.danger:hover {
    border-color: #ff4444;
    color: #ff4444;
  }

  .empty-schedules {
    text-align: center;
    padding: 60px;
    background-color: #1a1a1a;
    border-radius: 16px;
    color: #888;
  }

  .optimization-lock {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    background: linear-gradient(135deg, rgba(170, 0, 255, 0.08), rgba(170, 0, 255, 0.02));
    border: 1px solid rgba(170, 0, 255, 0.35);
    border-radius: 12px;
    padding: 14px 16px;
    margin-top: 4px;
  }

  .optimization-lock-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background-color: rgba(170, 0, 255, 0.15);
    flex-shrink: 0;
    margin-top: 1px;
  }

  .optimization-lock-text {
    color: #d8d8d8;
    font-size: 13px;
    line-height: 1.5;
  }

  .optimization-lock-link {
    color: #c266ff;
    font-weight: 600;
    text-decoration: none;
    border-bottom: 1px solid rgba(194, 102, 255, 0.4);
    transition: all 0.15s ease;
  }

  .optimization-lock-link:hover {
    color: #e0aaff;
    border-bottom-color: #e0aaff;
  }

  /* Section styles */
  .reset-section {
    background: linear-gradient(135deg, #0f0f0f 0%, #0a0a0a 100%);
    border: 1px solid #1f1f1f;
    border-radius: 20px;
    padding: 28px;
    margin-bottom: 24px;
    transition: all 0.3s ease;
  }

  .reset-section:hover {
    border-color: #2a2a2a;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid #1f1f1f;
  }

  .section-icon {
    font-size: 28px;
  }

  .section-title {
    font-size: 22px;
    font-weight: 600;
    color: #ffffff;
    display: flex;
    align-items: center;
  }

  .section-subtitle {
    font-size: 14px;
    color: #888;
    margin-left: auto;
  }

  /* Info icon tooltip */
  .info-icon {
    color: #888;
    font-size: 16px;
    transition: all 0.2s ease;
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background-color: #2a2a2a;
    font-style: normal;
    font-weight: bold;
  }

  .info-icon:hover {
    color: #aa00ff;
    background-color: #3a3a3a;
  }

  .info-tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    background-color: #1a1a1a;
    border: 1px solid #aa00ff;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
    width: 320px;
    z-index: 1000;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    pointer-events: none;
    white-space: normal;
    font-size: 12px;
    line-height: 1.5;
    color: #b0b0b0;
  }

  .info-tooltip::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border-width: 6px;
    border-style: solid;
    border-color: #aa00ff transparent transparent transparent;
  }

  /* Stat types grid */
  .stat-types-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .stat-card {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 14px 16px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .stat-card:hover {
    border-color: #aa00ff;
    background-color: #222;
    transform: translateY(-2px);
  }

  .stat-card.selected {
    border-color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.1);
  }

  .stat-card-content {
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .stat-checkbox {
    width: 20px;
    height: 20px;
    margin-top: 2px;
    cursor: pointer;
    accent-color: #aa00ff;
    flex-shrink: 0;
  }

  .stat-info {
    flex: 1;
  }

  .stat-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    flex-wrap: wrap;
  }

  .stat-label {
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
  }

  .stat-badge {
    font-size: 10px;
    background-color: rgba(255, 68, 68, 0.2);
    padding: 2px 8px;
    border-radius: 12px;
    color: #ff8888;
  }

  .stat-description {
    font-size: 12px;
    color: #888;
    line-height: 1.4;
  }

  .action-buttons-group {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
  }

  .action-button {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .action-button:hover {
    border-color: #aa00ff;
    color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
  }

  .selection-counter {
    background-color: #1a1a1a;
    border: 1px solid #aa00ff;
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    color: #aa00ff;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  /* Time period controls */
  .time-period-options {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 24px;
  }

  .time-option-btn {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 14px 24px;
    font-size: 14px;
    font-weight: 500;
    color: #b0b0b0;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .time-option-btn:hover {
    border-color: #aa00ff;
    color: #aa00ff;
  }

  .time-option-btn.active {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border-color: #aa00ff;
    color: white;
  }

  .time-option-description {
    font-size: 13px;
    color: #666;
    margin-left: 8px;
  }

  .days-input-group {
    display: flex;
    align-items: center;
    gap: 12px;
    background-color: #1a1a1a;
    padding: 12px 20px;
    border-radius: 12px;
    border: 1px solid #2a2a2a;
    margin-top: 16px;
  }

  .days-input {
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 12px;
    color: white;
    width: 80px;
    font-size: 14px;
    text-align: center;
  }

  .days-input:focus {
    outline: none;
    border-color: #aa00ff;
  }

  .apply-days-btn {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    color: white;
    cursor: pointer;
    font-weight: 500;
  }

  /* Date range inputs */
  .date-range-group {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-top: 16px;
    padding: 16px;
    background-color: #1a1a1a;
    border-radius: 12px;
    border: 1px solid #2a2a2a;
  }

  .date-input-wrapper {
    flex: 1;
    min-width: 200px;
    position: relative;
  }

  .date-label {
    display: block;
    font-size: 13px;
    color: #aa00ff;
    margin-bottom: 8px;
  }

  .date-input-container {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .date-input {
    flex: 1;
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 10px 14px;
    color: white;
    font-size: 14px;
  }

  .date-input:focus {
    outline: none;
    border-color: #aa00ff;
  }

  .calendar-btn {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    font-size: 16px;
    transition: all 0.2s ease;
  }

  .calendar-btn:hover {
    border-color: #aa00ff;
    background-color: #2a2a2a;
  }

  /* Calendar */
  .calendar-popup {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 8px;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 16px;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    min-width: 280px;
  }

  .calendar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .calendar-nav {
    background: none;
    border: none;
    color: white;
    cursor: pointer;
    font-size: 14px;
    padding: 4px 8px;
    border-radius: 4px;
  }

  .calendar-nav:hover {
    background-color: #2a2a2a;
  }

  .calendar-title {
    font-weight: 600;
    color: #aa00ff;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
  }

  .calendar-title:hover {
    background-color: #2a2a2a;
  }

  .calendar-weekdays {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    margin-bottom: 8px;
  }

  .calendar-weekday {
    text-align: center;
    font-size: 11px;
    color: #888;
    padding: 4px;
  }

  .calendar-days {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
  }

  .calendar-day {
    text-align: center;
    padding: 8px 4px;
    cursor: pointer;
    border-radius: 6px;
    font-size: 13px;
    transition: all 0.2s ease;
  }

  .calendar-day:hover {
    background-color: #2a2a2a;
  }

  .calendar-day.selected {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    color: white;
  }

  .calendar-day.today {
    border: 1px solid #aa00ff;
  }

  .calendar-day.empty {
    cursor: default;
  }

  .calendar-day.empty:hover {
    background: none;
  }

  .calendar-months {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }

  .calendar-month {
    text-align: center;
    padding: 10px;
    cursor: pointer;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .calendar-month:hover {
    background-color: #2a2a2a;
  }

  .calendar-month.selected {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    color: white;
  }

  .calendar-years {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    max-height: 200px;
    overflow-y: auto;
  }

  .calendar-year {
    text-align: center;
    padding: 10px;
    cursor: pointer;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .calendar-year:hover {
    background-color: #2a2a2a;
  }

  .calendar-year.selected {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    color: white;
  }

  .date-hint {
    font-size: 11px;
    color: #666;
    margin-top: 6px;
  }

  /* Schedule section */
  .schedule-section {
    margin-top: 8px;
  }

  .add-schedule-button {
    width: 100%;
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border: 2px dashed #2a2a2a;
    border-radius: 16px;
    padding: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    cursor: pointer;
    transition: all 0.3s ease;
    color: #888;
    font-size: 16px;
    font-weight: 500;
  }

  .add-schedule-button:hover {
    border-color: #aa00ff;
    color: #aa00ff;
    background: linear-gradient(135deg, #1f1f1f 0%, #151515 100%);
  }

  .schedule-preview {
    background-color: #1a1a1a;
    border-radius: 16px;
    padding: 20px;
    border: 1px solid #2a2a2a;
    position: relative;
  }

  .schedule-preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .schedule-preview-title {
    font-size: 14px;
    font-weight: 600;
    color: #aa00ff;
  }

  .remove-schedule {
    background: none;
    border: none;
    color: #ff4444;
    cursor: pointer;
    font-size: 18px;
    padding: 4px 8px;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .remove-schedule:hover {
    background-color: rgba(255, 68, 68, 0.1);
  }

  .schedule-preview-content {
    font-size: 15px;
    color: #ffffff;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }

  .schedule-preview-item {
    display: flex;
    align-items: center;
    gap: 8px;
    background-color: #0a0a0a;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 13px;
  }

  /* Reset button */
  .reset-button-container {
    display: flex;
    justify-content: flex-end;
    margin-top: 32px;
  }

  .reset-button {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 14px 32px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .reset-button:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.4);
  }

  .reset-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Results section */
  .results-section {
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
    padding: 24px;
    margin-top: 32px;
  }

  .results-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 16px;
  }

  .results-title {
    font-size: 18px;
    font-weight: 600;
    color: #aa00ff;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .results-table {
    width: 100%;
    border-collapse: collapse;
  }

  .results-table th,
  .results-table td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid #1a1a1a;
  }

  .results-table th {
    background-color: #0f0f0f;
    color: #aa00ff;
    font-weight: 600;
    font-size: 13px;
  }

  .success-badge {
    background-color: rgba(0, 184, 148, 0.2);
    color: #00b894;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
  }

  .error-badge {
    background-color: rgba(255, 118, 117, 0.2);
    color: #ff7675;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
  }

  /* Compact Time Picker */
  .compact-time-picker {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 8px;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    min-width: 180px;
  }

  .compact-time-header {
    display: flex;
    gap: 8px;
    justify-content: center;
    margin-bottom: 12px;
  }

  .compact-format-btn {
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 16px;
    padding: 4px 12px;
    cursor: pointer;
    font-size: 11px;
    transition: all 0.2s ease;
    color: #888;
  }

  .compact-format-btn.active {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    border-color: #aa00ff;
    color: white;
  }

  .compact-time-body {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .compact-time-column {
    text-align: center;
  }

  .compact-time-arrow {
    background: none;
    border: none;
    color: #aa00ff;
    font-size: 14px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
  }

  .compact-time-arrow:hover {
    background-color: #2a2a2a;
  }

  .compact-time-value {
    font-size: 24px;
    font-weight: 600;
    color: white;
    margin: 4px 0;
  }

  .compact-time-separator {
    font-size: 24px;
    font-weight: 600;
    color: white;
  }

  .compact-time-confirm {
    background: linear-gradient(135deg, #aa00ff, #8800cc);
    border: none;
    border-radius: 16px;
    padding: 6px 16px;
    color: white;
    cursor: pointer;
    font-weight: 500;
    font-size: 12px;
    width: 100%;
  }

  /* Modal overlay */
  .schedule-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 20px;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes slideUp {
    from {
      transform: translateY(30px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .schedule-modal {
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border-radius: 24px;
    width: 100%;
    max-width: 650px;
    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
    border: 1px solid #2a2a2a;
    animation: slideUp 0.3s ease;
    overflow: hidden;
  }

  .schedule-modal-header {
    padding: 24px 24px 16px 24px;
    border-bottom: 1px solid #2a2a2a;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .schedule-modal-title {
    font-size: 20px;
    font-weight: 600;
    background: linear-gradient(135deg, #aa00ff, #ff66cc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .schedule-modal-close {
    background: none;
    border: none;
    color: #888;
    font-size: 24px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .schedule-modal-close:hover {
    color: #ff4444;
    background-color: rgba(255, 68, 68, 0.1);
  }

  .schedule-modal-content {
    padding: 24px;
    min-height: 400px;
    max-height: 60vh;
    overflow-y: auto;
  }

  /* Schedule type options */
  .schedule-type-options {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .schedule-type-option {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 16px;
    padding: 18px 20px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .schedule-type-option:hover {
    border-color: #aa00ff;
    background-color: #222;
    transform: translateX(4px);
  }

  .schedule-type-option.selected {
    border-color: #aa00ff;
    background-color: rgba(170, 0, 255, 0.1);
  }

  .schedule-type-icon {
    font-size: 32px;
  }

  .schedule-type-info {
    flex: 1;
  }

  .schedule-type-name {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 4px;
  }

  .schedule-type-desc {
    font-size: 12px;
    color: #888;
  }

  .schedule-type-check {
    color: #aa00ff;
    font-size: 20px;
  }

  /* Multi-select chips */
  .multi-select-container {
    margin-bottom: 20px;
  }

  .multi-select-label {
    display: block;
    font-size: 14px;
    font-weight: 500;
    color: #aa00ff;
    margin-bottom: 10px;
  }

  .chips-container {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 12px;
  }

  .chip {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 20px;
    padding: 8px 16px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .chip:hover {
    border-color: #aa00ff;
  }

  .chip.selected {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border-color: #aa00ff;
    color: white;
  }

  .chip-remove {
    cursor: pointer;
    font-size: 14px;
    opacity: 0.7;
  }

  .chip-remove:hover {
    opacity: 1;
  }

  .add-input-group {
    display: flex;
    gap: 10px;
    margin-top: 12px;
  }

  .add-input {
    flex: 1;
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 10px 14px;
    color: white;
    font-size: 14px;
  }

  .add-input:focus {
    outline: none;
    border-color: #aa00ff;
  }

  .add-btn {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    color: white;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
  }

  .add-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 2px 8px rgba(170, 0, 255, 0.3);
  }

  /* Form inputs */
  .form-group {
    margin-bottom: 20px;
  }

  .form-label {
    display: block;
    font-size: 14px;
    font-weight: 500;
    color: #aa00ff;
    margin-bottom: 8px;
  }

  .form-input, .form-select {
    width: 100%;
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    color: #ffffff;
    font-size: 14px;
    transition: all 0.2s ease;
  }

  .form-input:focus, .form-select:focus {
    outline: none;
    border-color: #aa00ff;
    box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.1);
  }

  textarea.form-input {
    resize: vertical;
    min-height: 80px;
  }

  /* Time input group */
  .time-input-group {
    display: flex;
    gap: 10px;
    align-items: center;
    position: relative;
  }

  .time-input {
    flex: 1;
    background-color: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 10px 14px;
    color: white;
    font-size: 14px;
  }

  .time-input:focus {
    outline: none;
    border-color: #aa00ff;
  }

  .clock-btn {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    font-size: 16px;
    transition: all 0.2s ease;
  }

  .clock-btn:hover {
    border-color: #aa00ff;
    background-color: #2a2a2a;
  }

  /* Weekday selector */
  .weekday-selector {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 8px;
    margin-bottom: 16px;
  }

  .weekday-chip {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 8px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 13px;
    font-weight: 500;
  }

  .weekday-chip:hover {
    border-color: #aa00ff;
  }

  .weekday-chip.selected {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    border-color: #aa00ff;
    color: white;
  }

  /* Confirmation page */
  .confirmation-details {
    background-color: #1a1a1a;
    border-radius: 16px;
    padding: 20px;
    margin-top: 16px;
  }

  .confirmation-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #2a2a2a;
  }

  .confirmation-row:last-child {
    border-bottom: none;
  }

  .confirmation-label {
    font-size: 14px;
    color: #888;
  }

  .confirmation-value {
    font-size: 14px;
    font-weight: 500;
    color: #aa00ff;
  }

  .modal-footer {
    padding: 16px 24px 24px 24px;
    border-top: 1px solid #2a2a2a;
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .modal-btn {
    padding: 10px 20px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
  }

  .modal-btn-back {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #ffffff;
  }

  .modal-btn-back:hover {
    border-color: #aa00ff;
    color: #aa00ff;
  }

  .modal-btn-next {
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white;
  }

  .modal-btn-next:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
  }

  .modal-btn-next:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .modal-btn-cancel {
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #888;
  }

  .modal-btn-cancel:hover {
    border-color: #ff4444;
    color: #ff4444;
  }

  /* Delete confirmation modal */
  .delete-confirm-modal {
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border-radius: 24px;
    width: 100%;
    max-width: 450px;
    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
    border: 1px solid #ff4444;
    animation: slideUp 0.3s ease;
    overflow: hidden;
  }

  .delete-confirm-header {
    padding: 24px 24px 16px 24px;
    border-bottom: 1px solid #ff4444;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .delete-confirm-title {
    font-size: 20px;
    font-weight: 600;
    color: #ff4444;
  }

  .delete-confirm-content {
    padding: 24px;
  }

  .delete-confirm-footer {
    padding: 16px 24px 24px 24px;
    border-top: 1px solid #2a2a2a;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }

  .modal-btn-delete {
    background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
    color: white;
  }

  .modal-btn-delete:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
  }

  /* Step indicator */
  .step-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin: 16px 0 24px 0;
  }

  .step-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #2a2a2a;
    transition: all 0.3s ease;
  }

  .step-dot.active {
    width: 24px;
    border-radius: 4px;
    background: linear-gradient(135deg, #aa00ff, #8800cc);
  }

  .step-dot.completed {
    background-color: #00b894;
  }

  /* View selector */
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

  /* Scope selector */
  .scope-selector-section {
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

  .scope-controls {
    display: flex;
    gap: 20px;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .scope-selector {
    flex: 1;
    min-width: 250px;
  }

  .scope-dropdown {
    width: 100%;
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    cursor: pointer;
    outline: none;
    appearance: none;
    background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23aa00ff'%3e%3cpath d='M7 10l5 5 5-5z'/%3e%3c/svg%3e");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 20px;
  }

  .entity-selector-wrapper {
    flex: 2;
    min-width: 250px;
    max-width: 100%;
    width: 100%;
  }

  .entity-selector-input-wrapper {
    position: relative;
    width: 100%;
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
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #2a2a2a;
  }

  .entity-option:hover {
    background-color: #2a2a2a;
  }

  .selected-entity-info {
    margin-top: 12px;
    padding: 12px;
    background-color: #1a1a1a;
    border-radius: 8px;
    border-left: 3px solid #aa00ff;
    font-size: 14px;
  }

  .selected-entity-label {
    color: #aa00ff;
    font-weight: 600;
    margin-right: 8px;
  }

  .loading-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid white;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    display: inline-block;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
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

  .error-message-container {
    text-align: center;
    padding: 80px 40px;
    background-color: #1a1a1a;
    border: 1px solid #ff4444;
    border-radius: 16px;
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

  .no-server {
    text-align: center;
    padding: 80px 60px;
    background-color: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 16px;
  }

  .invite-button, .login-button {
    display: inline-block;
    background: linear-gradient(135deg, #aa00ff 0%, #8800cc 100%);
    color: white;
    padding: 12px 28px;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 600;
    margin-top: 20px;
  }

  @media (max-width: 768px) {
    .dashboard-main {
      margin-left: 0;
    }
    .dashboard-content {
      padding: 16px;
    }
    .reset-section {
      padding: 20px;
    }
    .stat-types-grid {
      grid-template-columns: 1fr;
    }
    .schedule-modal {
      margin: 16px;
      width: calc(100% - 32px);
    }
    .section-header {
      flex-wrap: wrap;
    }
    .weekday-selector {
      grid-template-columns: repeat(4, 1fr);
    }
    .time-period-options {
      flex-direction: column;
    }
    .date-range-group {
      flex-direction: column;
    }
    .schedule-card-content {
      grid-template-columns: 1fr;
    }
  }
`;

// ============================================
// STAT TYPES CONFIGURATION
// ============================================

const STAT_TYPES = {
  server: {
    all: { label: "All Statistics", description: "Reset ALL statistics (irreversible!)", serverWideOnly: false },
    messages: { label: "Messages", description: "Reset message tracking", serverWideOnly: false },
    "voice activity": { label: "Voice Activity", description: "Reset voice session history", serverWideOnly: false },
    "invite tracking": { label: "Invite Tracking", description: "Reset invite tracking", serverWideOnly: true },
    "emoji stats": { label: "Emoji Stats", description: "Reset emoji usage", serverWideOnly: false },
    activity: { label: "Activity", description: "Reset activity tracking (sessions, streaks, logs)", serverWideOnly: true },
    mentions: { label: "Mentions", description: "Reset user mentions", serverWideOnly: false },
    "role growth": { label: "Role Growth", description: "Reset role growth tracking", serverWideOnly: true },
    "member growth": { label: "Member Growth", description: "Reset member join/leave tracking", serverWideOnly: true }
  },
  user: {
    all: { label: "All Statistics", description: "Reset ALL statistics", serverWideOnly: false },
    messages: { label: "Messages", description: "Reset message tracking", serverWideOnly: false },
    "voice activity": { label: "Voice Activity", description: "Reset voice activity", serverWideOnly: false },
    activity: { label: "Activity", description: "Reset activity tracking", serverWideOnly: true },
    "invite tracking": { label: "Invite Tracking", description: "Reset invite tracking", serverWideOnly: true },
    "emoji stats": { label: "Emoji Stats", description: "Reset emoji usage", serverWideOnly: false },
    mentions: { label: "Mentions", description: "Reset mentions", serverWideOnly: false },
    "role growth": { label: "Role Growth", description: "Reset role growth tracking", serverWideOnly: true }
  }
};

const weekdays = [
  { value: 0, label: "Monday", short: "Mon" },
  { value: 1, label: "Tuesday", short: "Tue" },
  { value: 2, label: "Wednesday", short: "Wed" },
  { value: 3, label: "Thursday", short: "Thu" },
  { value: 4, label: "Friday", short: "Fri" },
  { value: 5, label: "Saturday", short: "Sat" },
  { value: 6, label: "Sunday", short: "Sun" }
];

const getFilteredStatTypes = (commandType, scope) => {
  const types = STAT_TYPES[commandType];
  if (!types) return [];
  
  return Object.entries(types)
    .filter(([key, config]) => {
      if (scope === "server") return true;
      return !config.serverWideOnly;
    })
    .map(([key, config]) => ({
      value: key,
      label: config.label,
      description: config.description
    }));
};

// ============================================
// DELETE SCHEDULE CONFIRM MODAL (No CONFIRM typing)
// ============================================

const DeleteScheduleConfirmModal = ({ isOpen, onClose, onConfirm, scheduleId }) => {
  if (!isOpen) return null;

  return (
    <div className="schedule-modal-overlay" onClick={onClose}>
      <div className="delete-confirm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="delete-confirm-header">
          <h3 className="delete-confirm-title">Delete Schedule</h3>
          <button className="schedule-modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="delete-confirm-content">
          <p style={{ marginBottom: '16px', color: '#fff' }}>
            Are you sure you want to delete schedule #{scheduleId}? This action cannot be undone.
          </p>
        </div>
        <div className="delete-confirm-footer">
          <button className="modal-btn modal-btn-cancel" onClick={onClose}>Cancel</button>
          <button className="modal-btn modal-btn-delete" onClick={() => onConfirm(scheduleId)}>Delete</button>
        </div>
      </div>
    </div>
  );
};

// ============================================
// ENHANCED EDIT SCHEDULE MODAL
// ============================================

const EditScheduleModal = ({ isOpen, onClose, onConfirm, schedule, currentServer }) => {
  const [step, setStep] = useState(1);
  const [scheduleName, setScheduleName] = useState("");
  const [reason, setReason] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [scheduleType, setScheduleType] = useState(null);
  const [selectedWeekdays, setSelectedWeekdays] = useState([]);
  const [selectedMonthDays, setSelectedMonthDays] = useState([]);
  const [selectedTimes, setSelectedTimes] = useState(["18:00"]);
  const [intervalDays, setIntervalDays] = useState(7);
  const [selectedStatTypes, setSelectedStatTypes] = useState([]);
  const [newTime, setNewTime] = useState("");
  const [newMonthDay, setNewMonthDay] = useState("");
  const [availableStatTypes, setAvailableStatTypes] = useState([]);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (schedule && isOpen) {
      setScheduleName(schedule.schedule_name || "");
      setEnabled(schedule.enabled !== false && !schedule.completed);
      setReason(schedule.reason || "");
      setSelectedStatTypes(schedule.reset_types || []);
      
      if (schedule.recurring_pattern) {
        let pattern = schedule.recurring_pattern;
        if (pattern === "custom_days") {
          pattern = "custom";
        }
        setScheduleType(pattern);
        
        if (schedule.recurring_pattern === 'weekly' && schedule.recurring_weekdays) {
          setSelectedWeekdays(schedule.recurring_weekdays);
        }
        
        if (schedule.recurring_pattern === 'monthly' && schedule.recurring_days_of_month) {
          setSelectedMonthDays(schedule.recurring_days_of_month);
        }
        
        if (schedule.recurring_pattern === 'custom_days' && schedule.recurring_interval_days) {
          setIntervalDays(schedule.recurring_interval_days);
        }
        
        if (schedule.recurring_times) {
          const timeStrings = schedule.recurring_times.map(t => {
            if (typeof t === 'string') return t;
            return `${String(t.hour).padStart(2, '0')}:${String(t.minute).padStart(2, '0')}`;
          });
          setSelectedTimes(timeStrings);
        }
      }
      
      loadStatTypes();
    }
  }, [schedule, isOpen]);

  const loadStatTypes = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/reset/ui/stat-types`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guild_id: currentServer?.id,
          command_type: schedule?.scope_type === 'user' ? 'user' : 'server',
          scope: schedule?.scope_type || 'server'
        })
      });
      const data = await response.json();
      setAvailableStatTypes(data.stat_types || []);
    } catch (error) {
      console.error('Error loading stat types:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStatTypeToggle = (statType) => {
    setSelectedStatTypes(prev => {
      if (prev.includes(statType)) {
        return prev.filter(t => t !== statType);
      } else {
        return [...prev, statType];
      }
    });
  };

  const toggleWeekday = (value) => {
    setSelectedWeekdays(prev =>
      prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value].sort()
    );
  };

  const addMonthDay = () => {
    if (newMonthDay) {
      const day = parseInt(newMonthDay);
      if (day >= 1 && day <= 31 && !selectedMonthDays.includes(day)) {
        setSelectedMonthDays([...selectedMonthDays, day].sort((a, b) => a - b));
        setNewMonthDay("");
      }
    }
  };

  const removeMonthDay = (day) => {
    setSelectedMonthDays(prev => prev.filter(d => d !== day));
  };

  const addTime = () => {
    if (newTime && /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/.test(newTime)) {
      if (!selectedTimes.includes(newTime)) {
        setSelectedTimes([...selectedTimes, newTime].sort());
        setNewTime("");
      }
    }
  };

  const removeTime = (time) => {
    setSelectedTimes(prev => prev.filter(t => t !== time));
  };

  const getSchedulePreview = () => {
    if (!scheduleType) return null;
    
    const timesStr = selectedTimes.join(", ");
    
    if (scheduleType === "daily") {
      return `Every day at ${timesStr}`;
    }
    if (scheduleType === "weekly") {
      const weekdayNames = selectedWeekdays.map(w => weekdays.find(d => d.value === w)?.short);
      return `Every ${weekdayNames.join(", ")} at ${timesStr}`;
    }
    if (scheduleType === "monthly") {
      const daysStr = selectedMonthDays.join(", ");
      return `Every ${daysStr} of the month at ${timesStr}`;
    }
    if (scheduleType === "custom") {
      return `Every ${intervalDays} days at ${timesStr}`;
    }
    return "";
  };

  const getOrdinal = (n) => {
    if (n > 3 && n < 21) return 'th';
    switch (n % 10) {
      case 1: return 'st';
      case 2: return 'nd';
      case 3: return 'rd';
      default: return 'th';
    }
  };

  const handleConfirm = () => {
    const updateData = {
      schedule_id: schedule.id,
      guild_id: currentServer?.id,
      enabled: enabled,
      schedule_name: scheduleName,
      reason: reason,
      reset_types: selectedStatTypes
    };
    
    if (scheduleType) {
      let patternForApi = scheduleType;
      if (scheduleType === "custom") {
        patternForApi = "custom_days";
      }
      updateData.recurring_pattern = patternForApi;
      updateData.recurring_times = selectedTimes;
      
      if (scheduleType === "weekly") {
        updateData.recurring_weekdays = selectedWeekdays;
      }
      if (scheduleType === "monthly") {
        updateData.recurring_days_of_month = selectedMonthDays;
      }
      if (scheduleType === "custom") {
        updateData.recurring_interval_days = intervalDays;
      }
    }
    
    onConfirm(schedule.id, updateData);
  };

  const isStepValid = () => {
    if (step === 1) return true;
    if (step === 2) return selectedStatTypes.length > 0;
    if (step === 3) {
      if (!scheduleType) return false;
      if (scheduleType === "weekly") return selectedWeekdays.length > 0 && selectedTimes.length > 0;
      if (scheduleType === "monthly") return selectedMonthDays.length > 0 && selectedTimes.length > 0;
      if (scheduleType === "custom") return intervalDays >= 1 && selectedTimes.length > 0;
      if (scheduleType === "daily") return selectedTimes.length > 0;
      return false;
    }
    return false;
  };

  if (!isOpen || !schedule) return null;

  return (
    <div className="schedule-modal-overlay" onClick={onClose}>
      <div className="schedule-modal" onClick={(e) => e.stopPropagation()}>
        <div className="schedule-modal-header">
          <h3 className="schedule-modal-title">Edit Schedule #{schedule.id}</h3>
          <button className="schedule-modal-close" onClick={onClose}>✕</button>
        </div>
        
        <div className="step-indicator">
          <div className={`step-dot ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 3 ? 'active' : ''} ${step > 3 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 4 ? 'active' : ''}`}></div>
        </div>
        
        <div className="schedule-modal-content">
          {step === 1 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Schedule Details</h4>
              <div className="form-group">
                <label className="form-label">Schedule Name (Optional)</label>
                <input
                  type="text"
                  className="form-input"
                  value={scheduleName}
                  onChange={(e) => setScheduleName(e.target.value)}
                  placeholder="e.g., Weekly Cleanup, Monthly Reset, etc."
                  maxLength="100"
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Reason (Optional)</label>
                <textarea
                  className="form-input"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Add a reason for this schedule..."
                  rows="3"
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Status</label>
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      checked={enabled}
                      onChange={() => setEnabled(true)}
                      style={{ accentColor: '#aa00ff' }}
                    />
                    <span style={{ color: '#00b894' }}>Enabled</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      checked={!enabled}
                      onChange={() => setEnabled(false)}
                      style={{ accentColor: '#aa00ff' }}
                    />
                    <span style={{ color: '#ff4444' }}>Disabled</span>
                  </label>
                </div>
              </div>
            </div>
          )}
          
          {step === 2 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Reset Types</h4>
              {loading ? (
                <LoadingSpinner size="small" text="Loading..." />
              ) : (
                <div className="stat-types-grid" style={{ maxHeight: '400px', overflowY: 'auto' }}>
                  {availableStatTypes.map(stat => (
                    <div 
                      key={stat.value}
                      className={`stat-card ${selectedStatTypes.includes(stat.value) ? "selected" : ""}`}
                      onClick={() => handleStatTypeToggle(stat.value)}
                    >
                      <div className="stat-card-content">
                        <input 
                          type="checkbox" 
                          checked={selectedStatTypes.includes(stat.value)}
                          onChange={() => {}}
                          onClick={(e) => e.stopPropagation()}
                          className="stat-checkbox"
                        />
                        <div className="stat-info">
                          <div className="stat-header">
                            <span className="stat-label">{stat.label}</span>
                          </div>
                          <div className="stat-description">{stat.description}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {selectedStatTypes.length === 0 && (
                <div style={{ color: '#ff4444', fontSize: '12px', marginTop: '8px' }}>
                  Please select at least one statistic type
                </div>
              )}
            </div>
          )}
          
          {step === 3 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Schedule Configuration</h4>
              
              <div className="schedule-type-options">
                <div 
                  className={`schedule-type-option ${scheduleType === 'daily' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('daily')}
                >
                  <div className="schedule-type-icon">📅</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Every Day</div>
                    <div className="schedule-type-desc">Runs at the same time(s) every day</div>
                  </div>
                  {scheduleType === 'daily' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'weekly' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('weekly')}
                >
                  <div className="schedule-type-icon">📆</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Weekly</div>
                    <div className="schedule-type-desc">Runs on selected day(s) of the week</div>
                  </div>
                  {scheduleType === 'weekly' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'monthly' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('monthly')}
                >
                  <div className="schedule-type-icon">📅</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Monthly</div>
                    <div className="schedule-type-desc">Runs on selected day(s) of the month</div>
                  </div>
                  {scheduleType === 'monthly' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'custom' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('custom')}
                >
                  <div className="schedule-type-icon">⚙️</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Custom Interval</div>
                    <div className="schedule-type-desc">Runs every X days at specified time(s)</div>
                  </div>
                  {scheduleType === 'custom' && <div className="schedule-type-check">✓</div>}
                </div>
              </div>
              
              {scheduleType === 'weekly' && (
                <div className="form-group" style={{ marginTop: '20px' }}>
                  <label className="form-label">Select Weekdays</label>
                  <div className="weekday-selector">
                    {weekdays.map(day => (
                      <div
                        key={day.value}
                        className={`weekday-chip ${selectedWeekdays.includes(day.value) ? 'selected' : ''}`}
                        onClick={() => toggleWeekday(day.value)}
                      >
                        {day.short}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {scheduleType === 'monthly' && (
                <div className="multi-select-container" style={{ marginTop: '20px' }}>
                  <label className="multi-select-label">Month Days</label>
                  <div className="chips-container">
                    {selectedMonthDays.map(day => (
                      <div key={day} className="chip selected">
                        {day}{getOrdinal(day)}
                        <span className="chip-remove" onClick={() => removeMonthDay(day)}>✕</span>
                      </div>
                    ))}
                  </div>
                  <div className="add-input-group">
                    <input
                      type="number"
                      className="add-input"
                      placeholder="Enter day (1-31)"
                      min="1"
                      max="31"
                      value={newMonthDay}
                      onChange={(e) => setNewMonthDay(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && addMonthDay()}
                    />
                    <button className="add-btn" onClick={addMonthDay}>Add</button>
                  </div>
                </div>
              )}

              {scheduleType === 'custom' && (
                <div className="form-group" style={{ marginTop: '20px' }}>
                  <label className="form-label">Interval (Days)</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="365"
                    value={intervalDays}
                    onChange={(e) => setIntervalDays(Math.min(365, Math.max(1, parseInt(e.target.value) || 1)))}
                  />
                </div>
              )}

              {(scheduleType === 'daily' || scheduleType === 'weekly' || scheduleType === 'monthly' || scheduleType === 'custom') && (
                <div className="multi-select-container" style={{ marginTop: '20px' }}>
                  <label className="multi-select-label">Times of Day</label>
                  <div className="chips-container">
                    {selectedTimes.map(time => (
                      <div key={time} className="chip selected">
                        🕐 {time}
                        <span className="chip-remove" onClick={() => removeTime(time)}>✕</span>
                      </div>
                    ))}
                  </div>
                  <div className="add-input-group">
                    <TimePickerInput
                      value={newTime}
                      onChange={setNewTime}
                      placeholder="HH:MM"
                    />
                    <button className="add-btn" onClick={addTime}>Add Time</button>
                  </div>
                </div>
              )}

              <div className="confirmation-details" style={{ marginTop: '20px' }}>
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule Preview:</span>
                  <span className="confirmation-value">{getSchedulePreview() || 'Select a schedule type'}</span>
                </div>
              </div>
            </div>
          )}
          
          {step === 4 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Confirm Changes</h4>
              <div className="confirmation-details">
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule Name:</span>
                  <span className="confirmation-value">{scheduleName || '(No name)'}</span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Status:</span>
                  <span className="confirmation-value" style={{ color: enabled ? '#00b894' : '#ff4444' }}>
                    {enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Reset Types:</span>
                  <span className="confirmation-value">{selectedStatTypes.length} type(s)</span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule:</span>
                  <span className="confirmation-value">{getSchedulePreview()}</span>
                </div>
                {reason && (
                  <div className="confirmation-row">
                    <span className="confirmation-label">Reason:</span>
                    <span className="confirmation-value">{reason}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="modal-btn modal-btn-cancel" onClick={onClose}>Cancel</button>
          {step > 1 && (
            <button className="modal-btn modal-btn-back" onClick={() => setStep(step - 1)}>Back</button>
          )}
          {step < 4 && (
            <button 
              className="modal-btn modal-btn-next" 
              onClick={() => setStep(step + 1)}
              disabled={!isStepValid()}
            >
              Next
            </button>
          )}
          {step === 4 && (
            <button className="modal-btn modal-btn-next" onClick={handleConfirm}>
              Save Changes
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================
// DATE RANGE MODAL
// ============================================

const DateRangeModal = ({ isOpen, onClose, onConfirm }) => {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [showFromCalendar, setShowFromCalendar] = useState(false);
  const [showToCalendar, setShowToCalendar] = useState(false);

  const parseDate = (dateStr) => {
    if (!dateStr) return null;
    let cleaned = dateStr.trim().replace(/\s+/g, '-');
    let parts;
    if (cleaned.includes('-')) {
      parts = cleaned.split('-');
    } else if (cleaned.includes('/')) {
      parts = cleaned.split('/');
    } else if (cleaned.includes('.')) {
      parts = cleaned.split('.');
    } else {
      return null;
    }
    if (parts.length !== 3) return null;
    const day = parseInt(parts[0]);
    const month = parseInt(parts[1]) - 1;
    const year = parseInt(parts[2]);
    if (isNaN(day) || isNaN(month) || isNaN(year)) return null;
    const date = new Date(year, month, day);
    if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null;
    return date;
  };

  const formatDateForDisplay = (date) => {
    if (!date) return "";
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    return `${day}-${month}-${year}`;
  };

  const formatDateForAPI = (date) => {
    if (!date) return null;
    return date.toISOString();
  };

  const handleFromDateChange = (date) => {
    setFromDate(formatDateForDisplay(date));
    setShowFromCalendar(false);
  };

  const handleToDateChange = (date) => {
    setToDate(formatDateForDisplay(date));
    setShowToCalendar(false);
  };

  const handleConfirm = () => {
    const fromDateObj = parseDate(fromDate);
    const toDateObj = parseDate(toDate);
    
    if ((fromDate && !fromDateObj) || (toDate && !toDateObj)) {
      alert("Invalid date format. Use DD-MM-YYYY (e.g., 25-12-2024)");
      return;
    }
    
    onConfirm(fromDateObj ? formatDateForAPI(fromDateObj) : null, toDateObj ? formatDateForAPI(toDateObj) : null);
    setFromDate("");
    setToDate("");
    onClose();
  };

  const handleClose = () => {
    setFromDate("");
    setToDate("");
    setShowFromCalendar(false);
    setShowToCalendar(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="schedule-modal-overlay" onClick={handleClose}>
      <div className="schedule-modal" onClick={(e) => e.stopPropagation()}>
        <div className="schedule-modal-header">
          <h3 className="schedule-modal-title">Date Range Selection</h3>
          <button className="schedule-modal-close" onClick={handleClose}>✕</button>
        </div>
        <div className="schedule-modal-content">
          <div className="date-range-group" style={{ flexDirection: 'column', marginTop: 0 }}>
            <div className="date-input-wrapper" style={{ width: '100%' }}>
              <label className="date-label">From Date (Optional)</label>
              <div className="date-input-container">
                <input
                  type="text"
                  className="date-input"
                  placeholder="DD-MM-YYYY (e.g., 01-01-2024)"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                />
                <button className="calendar-btn" onClick={() => setShowFromCalendar(!showFromCalendar)}>📅</button>
              </div>
              {showFromCalendar && (
                <SimpleCalendar value={parseDate(fromDate)} onChange={handleFromDateChange} onClose={() => setShowFromCalendar(false)} />
              )}
              <div className="date-hint">Leave empty to delete from the oldest data available</div>
            </div>
            <div className="date-input-wrapper" style={{ width: '100%' }}>
              <label className="date-label">To Date (Optional)</label>
              <div className="date-input-container">
                <input
                  type="text"
                  className="date-input"
                  placeholder="DD-MM-YYYY (e.g., 31-12-2024)"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                />
                <button className="calendar-btn" onClick={() => setShowToCalendar(!showToCalendar)}>📅</button>
              </div>
              {showToCalendar && (
                <SimpleCalendar value={parseDate(toDate)} onChange={handleToDateChange} onClose={() => setShowToCalendar(false)} />
              )}
              <div className="date-hint">Leave empty to delete until the most recent data</div>
            </div>
          </div>
          <div className="confirmation-details" style={{ marginTop: '20px' }}>
            <div className="confirmation-row">
              <span className="confirmation-label">Range Preview:</span>
              <span className="confirmation-value">
                {fromDate || "Start"} → {toDate || "End"}
              </span>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="modal-btn modal-btn-cancel" onClick={handleClose}>Cancel</button>
          <button className="modal-btn modal-btn-next" onClick={handleConfirm}>Apply Range</button>
        </div>
      </div>
    </div>
  );
};

// ============================================
// TIME PICKER INPUT
// ============================================

const TimePickerInput = ({ value, onChange, placeholder }) => {
  const [showPicker, setShowPicker] = useState(false);
  const [localValue, setLocalValue] = useState(value || "18:00");

  const handleTimeChange = (newTime) => {
    setLocalValue(newTime);
    onChange(newTime);
  };

  return (
    <div style={{ position: 'relative', flex: 1 }}>
      <div className="time-input-group">
        <input
          type="text"
          className="time-input"
          placeholder={placeholder || "HH:MM"}
          value={localValue}
          onChange={(e) => {
            setLocalValue(e.target.value);
            onChange(e.target.value);
          }}
        />
        <button className="clock-btn" onClick={() => setShowPicker(!showPicker)}>🕐</button>
      </div>
      {showPicker && (
        <CompactTimePicker value={localValue} onChange={handleTimeChange} onClose={() => setShowPicker(false)} />
      )}
    </div>
  );
};

// ============================================
// ENHANCED SCHEDULE MODAL (CREATE) - No description, has reason
// ============================================

const ScheduleModal = ({ isOpen, onClose, onConfirm, existingSchedule }) => {
  const [step, setStep] = useState(1);
  const [scheduleName, setScheduleName] = useState("");
  const [reason, setReason] = useState("");
  const [scheduleType, setScheduleType] = useState(null);
  const [selectedWeekdays, setSelectedWeekdays] = useState([]);
  const [selectedMonthDays, setSelectedMonthDays] = useState([]);
  const [selectedTimes, setSelectedTimes] = useState(["18:00"]);
  const [intervalDays, setIntervalDays] = useState(7);
  const [newTime, setNewTime] = useState("");
  const [newMonthDay, setNewMonthDay] = useState("");

  const resetState = () => {
    setStep(1);
    setScheduleName("");
    setReason("");
    setScheduleType(null);
    setSelectedWeekdays([]);
    setSelectedMonthDays([]);
    setSelectedTimes(["18:00"]);
    setIntervalDays(7);
    setNewTime("");
    setNewMonthDay("");
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleNext = () => {
    if (step === 1) {
      setStep(2);
    } else if (step === 2 && scheduleType) {
      setStep(3);
    } else if (step === 3) {
      setStep(4);
    }
  };

  const handleBack = () => {
    if (step > 1) {
      setStep(step - 1);
    }
  };

  const toggleWeekday = (value) => {
    setSelectedWeekdays(prev =>
      prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value].sort()
    );
  };

  const addMonthDay = () => {
    if (newMonthDay) {
      const day = parseInt(newMonthDay);
      if (day >= 1 && day <= 31 && !selectedMonthDays.includes(day)) {
        setSelectedMonthDays([...selectedMonthDays, day].sort((a, b) => a - b));
        setNewMonthDay("");
      }
    }
  };

  const removeMonthDay = (day) => {
    setSelectedMonthDays(prev => prev.filter(d => d !== day));
  };

  const addTime = () => {
    if (newTime && /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/.test(newTime)) {
      if (!selectedTimes.includes(newTime)) {
        setSelectedTimes([...selectedTimes, newTime].sort());
        setNewTime("");
      }
    }
  };

  const removeTime = (time) => {
    setSelectedTimes(prev => prev.filter(t => t !== time));
  };

  const getSchedulePreview = () => {
    if (!scheduleType) return null;
    
    const timesStr = selectedTimes.join(", ");
    
    if (scheduleType === "daily") {
      return `Every day at ${timesStr}`;
    }
    if (scheduleType === "weekly") {
      const weekdayNames = selectedWeekdays.map(w => weekdays.find(d => d.value === w)?.short);
      return `Every ${weekdayNames.join(", ")} at ${timesStr}`;
    }
    if (scheduleType === "monthly") {
      const daysStr = selectedMonthDays.join(", ");
      return `Every ${daysStr} of the month at ${timesStr}`;
    }
    if (scheduleType === "custom") {
      return `Every ${intervalDays} days at ${timesStr}`;
    }
    return "";
  };

  const getOrdinal = (n) => {
    if (n > 3 && n < 21) return 'th';
    switch (n % 10) {
      case 1: return 'st';
      case 2: return 'nd';
      case 3: return 'rd';
      default: return 'th';
    }
  };

  const handleConfirm = () => {
    let scheduleDescriptionStr = "";
    let scheduleData = { name: scheduleName, reason: reason };

    if (scheduleType === "weekly") {
      const weekdayNames = selectedWeekdays.map(w => weekdays.find(d => d.value === w)?.label);
      scheduleDescriptionStr = `Every ${weekdayNames.join(", ")} at ${selectedTimes.join(", ")}`;
      scheduleData = { name: scheduleName, reason: reason, pattern: "weekly", weekdays: selectedWeekdays, times: selectedTimes };
    } else if (scheduleType === "daily") {
      scheduleDescriptionStr = `Every day at ${selectedTimes.join(", ")}`;
      scheduleData = { name: scheduleName, reason: reason, pattern: "daily", times: selectedTimes };
    } else if (scheduleType === "monthly") {
      scheduleDescriptionStr = `Every ${selectedMonthDays.join(", ")} of the month at ${selectedTimes.join(", ")}`;
      scheduleData = { name: scheduleName, reason: reason, pattern: "monthly", monthDays: selectedMonthDays, times: selectedTimes };
    } else if (scheduleType === "custom") {
      scheduleDescriptionStr = `Every ${intervalDays} days at ${selectedTimes.join(", ")}`;
      scheduleData = { name: scheduleName, reason: reason, pattern: "custom_days", intervalDays: intervalDays, times: selectedTimes };
    }

    onConfirm(scheduleDescriptionStr, scheduleData);
    resetState();
    onClose();
  };

  const isStepValid = () => {
    if (step === 1) return true;
    if (step === 2) return scheduleType !== null;
    if (step === 3) {
      if (scheduleType === "weekly") return selectedWeekdays.length > 0 && selectedTimes.length > 0;
      if (scheduleType === "monthly") return selectedMonthDays.length > 0 && selectedTimes.length > 0;
      if (scheduleType === "custom") return intervalDays >= 1 && selectedTimes.length > 0;
      if (scheduleType === "daily") return selectedTimes.length > 0;
      return false;
    }
    return true;
  };

  if (!isOpen) return null;

  return (
    <div className="schedule-modal-overlay" onClick={handleClose}>
      <div className="schedule-modal" onClick={(e) => e.stopPropagation()}>
        <div className="schedule-modal-header">
          <h3 className="schedule-modal-title">Create Reset Schedule</h3>
          <button className="schedule-modal-close" onClick={handleClose}>✕</button>
        </div>

        <div className="step-indicator">
          <div className={`step-dot ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 3 ? 'active' : ''} ${step > 3 ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step >= 4 ? 'active' : ''}`}></div>
        </div>

        <div className="schedule-modal-content">
          {step === 1 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Schedule Details</h4>
              <div className="form-group">
                <label className="form-label">Schedule Name (Optional)</label>
                <input
                  type="text"
                  className="form-input"
                  value={scheduleName}
                  onChange={(e) => setScheduleName(e.target.value)}
                  placeholder="e.g., Weekly Cleanup, Monthly Reset, etc."
                  maxLength="100"
                />
                <div style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>
                  Give your schedule a descriptive name to easily identify it later.
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Reason (Optional)</label>
                <textarea
                  className="form-input"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Add a reason for this schedule..."
                  rows="3"
                />
                <div style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>
                  Describe why this schedule was created or what it's for.
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Choose schedule type</h4>
              <div className="schedule-type-options">
                <div 
                  className={`schedule-type-option ${scheduleType === 'daily' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('daily')}
                >
                  <div className="schedule-type-icon">📅</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Every Day</div>
                    <div className="schedule-type-desc">Runs at the same time(s) every day</div>
                  </div>
                  {scheduleType === 'daily' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'weekly' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('weekly')}
                >
                  <div className="schedule-type-icon">📆</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Weekly</div>
                    <div className="schedule-type-desc">Runs on selected day(s) of the week</div>
                  </div>
                  {scheduleType === 'weekly' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'monthly' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('monthly')}
                >
                  <div className="schedule-type-icon">📅</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Monthly</div>
                    <div className="schedule-type-desc">Runs on selected day(s) of the month</div>
                  </div>
                  {scheduleType === 'monthly' && <div className="schedule-type-check">✓</div>}
                </div>

                <div 
                  className={`schedule-type-option ${scheduleType === 'custom' ? 'selected' : ''}`}
                  onClick={() => setScheduleType('custom')}
                >
                  <div className="schedule-type-icon">⚙️</div>
                  <div className="schedule-type-info">
                    <div className="schedule-type-name">Custom Interval</div>
                    <div className="schedule-type-desc">Runs every X days at specified time(s)</div>
                  </div>
                  {scheduleType === 'custom' && <div className="schedule-type-check">✓</div>}
                </div>
              </div>
            </div>
          )}

          {step === 3 && scheduleType && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Configure schedule</h4>
              
              {scheduleType === 'weekly' && (
                <div className="form-group">
                  <label className="form-label">Select Weekdays</label>
                  <div className="weekday-selector">
                    {weekdays.map(day => (
                      <div
                        key={day.value}
                        className={`weekday-chip ${selectedWeekdays.includes(day.value) ? 'selected' : ''}`}
                        onClick={() => toggleWeekday(day.value)}
                      >
                        {day.short}
                      </div>
                    ))}
                  </div>
                  {selectedWeekdays.length === 0 && (
                    <div style={{ color: '#ff4444', fontSize: '12px', marginTop: '8px' }}>
                      Please select at least one weekday
                    </div>
                  )}
                </div>
              )}

              {scheduleType === 'monthly' && (
                <div className="multi-select-container">
                  <label className="multi-select-label">Month Days</label>
                  <div className="chips-container">
                    {selectedMonthDays.map(day => (
                      <div key={day} className="chip selected">
                        {day}{getOrdinal(day)}
                        <span className="chip-remove" onClick={() => removeMonthDay(day)}>✕</span>
                      </div>
                    ))}
                  </div>
                  <div className="add-input-group">
                    <input
                      type="number"
                      className="add-input"
                      placeholder="Enter day (1-31)"
                      min="1"
                      max="31"
                      value={newMonthDay}
                      onChange={(e) => setNewMonthDay(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && addMonthDay()}
                    />
                    <button className="add-btn" onClick={addMonthDay}>Add</button>
                  </div>
                  {selectedMonthDays.length === 0 && (
                    <div style={{ color: '#ff4444', fontSize: '12px', marginTop: '8px' }}>
                      Please add at least one month day
                    </div>
                  )}
                </div>
              )}

              {scheduleType === 'custom' && (
                <div className="form-group">
                  <label className="form-label">Interval (Days)</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="365"
                    value={intervalDays}
                    onChange={(e) => setIntervalDays(Math.min(365, Math.max(1, parseInt(e.target.value) || 1)))}
                  />
                  {intervalDays < 1 && (
                    <div style={{ color: '#ff4444', fontSize: '12px', marginTop: '8px' }}>
                      Interval must be at least 1 day
                    </div>
                  )}
                </div>
              )}

              <div className="multi-select-container">
                <label className="multi-select-label">Times of Day</label>
                <div className="chips-container">
                  {selectedTimes.map(time => (
                    <div key={time} className="chip selected">
                      🕐 {time}
                      <span className="chip-remove" onClick={() => removeTime(time)}>✕</span>
                    </div>
                  ))}
                </div>
                <div className="add-input-group">
                  <TimePickerInput
                    value={newTime}
                    onChange={setNewTime}
                    placeholder="HH:MM"
                  />
                  <button className="add-btn" onClick={addTime}>Add Time</button>
                </div>
                {selectedTimes.length === 0 && (
                  <div style={{ color: '#ff4444', fontSize: '12px', marginTop: '8px' }}>
                    Please add at least one time
                  </div>
                )}
              </div>

              <div className="confirmation-details" style={{ marginTop: '20px' }}>
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule Preview:</span>
                  <span className="confirmation-value">{getSchedulePreview()}</span>
                </div>
              </div>
            </div>
          )}

          {step === 4 && (
            <div>
              <h4 style={{ marginBottom: '16px', fontSize: '16px', color: '#fff' }}>Confirm Schedule</h4>
              <div className="confirmation-details">
                {scheduleName && (
                  <div className="confirmation-row">
                    <span className="confirmation-label">Name:</span>
                    <span className="confirmation-value">{scheduleName}</span>
                  </div>
                )}
                {reason && (
                  <div className="confirmation-row">
                    <span className="confirmation-label">Reason:</span>
                    <span className="confirmation-value">{reason}</span>
                  </div>
                )}
                <div className="confirmation-row">
                  <span className="confirmation-label">Type:</span>
                  <span className="confirmation-value">
                    {scheduleType === 'daily' && 'Daily'}
                    {scheduleType === 'weekly' && 'Weekly'}
                    {scheduleType === 'monthly' && 'Monthly'}
                    {scheduleType === 'custom' && 'Custom Interval'}
                  </span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Schedule:</span>
                  <span className="confirmation-value">{getSchedulePreview()}</span>
                </div>
                <div className="confirmation-row">
                  <span className="confirmation-label">Times:</span>
                  <span className="confirmation-value">{selectedTimes.join(", ")}</span>
                </div>
                {scheduleType === 'weekly' && (
                  <div className="confirmation-row">
                    <span className="confirmation-label">Weekdays:</span>
                    <span className="confirmation-value">
                      {selectedWeekdays.map(w => weekdays.find(d => d.value === w)?.label).join(", ")}
                    </span>
                  </div>
                )}
                {scheduleType === 'monthly' && (
                  <div className="confirmation-row">
                    <span className="confirmation-label">Month Days:</span>
                    <span className="confirmation-value">
                      {selectedMonthDays.map(d => `${d}${getOrdinal(d)}`).join(", ")}
                    </span>
                  </div>
                )}
                {scheduleType === 'custom' && (
                  <div className="confirmation-row">
                    <span className="confirmation-label">Interval:</span>
                    <span className="confirmation-value">Every {intervalDays} days</span>
                  </div>
                )}
                <div className="confirmation-row">
                  <span className="confirmation-label">Next Run:</span>
                  <span className="confirmation-value">Will be calculated automatically</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="modal-btn modal-btn-cancel" onClick={handleClose}>Cancel</button>
          {step > 1 && (
            <button className="modal-btn modal-btn-back" onClick={handleBack}>Back</button>
          )}
          {step < 4 && (
            <button 
              className="modal-btn modal-btn-next" 
              onClick={handleNext}
              disabled={!isStepValid()}
            >
              Next
            </button>
          )}
          {step === 4 && (
            <button className="modal-btn modal-btn-next" onClick={handleConfirm}>
              Create Schedule
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================
// SCHEDULE MANAGEMENT COMPONENT
// ============================================

const ScheduleManagement = ({ currentServer }) => {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [showToast, setShowToast] = useState(null);
  const [lockMessage, setLockMessage] = useState(null); 

  const showToastMessage = (message, type = 'info') => {
    setShowToast({ message, type });
    setTimeout(() => setShowToast(null), 3000);
  };

  const fetchSchedules = async () => {
    if (!currentServer) return;
    
    setLoading(true);
    setLockMessage(null); // ADD THIS
    try {
      const response = await fetch(`${API_BASE_URL}/api/reset/schedules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ guild_id: currentServer.id })
      });
      
      const data = await response.json();

      if (response.status === 403) {           // ADD THIS BLOCK
        setLockMessage(data.detail || data.message);
        setSchedules([]);
        return;
      }

      if (data.success) {
        setSchedules(data.schedules);
      } else if (data.message && data.message.includes('Optimization+')) {  // ADD THIS (covers the 200-with-swallowed-403 case from your logs)
        setLockMessage(data.message);
      }
    } catch (error) {
      console.error('Error fetching schedules:', error);
      showToastMessage('Failed to load schedules', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedules();
  }, [currentServer]);

  const handleDeleteSchedule = async (scheduleId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/reset/schedule/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ schedule_id: scheduleId, guild_id: currentServer.id })
      });
      
      const data = await response.json();

      if (response.status === 403) {
        setLockMessage(data.detail || data.message);
        showToastMessage(data.detail || data.message || 'Scheduled resets require Optimization+', 'error');
      } else if (data.success) {
        showToastMessage(`Schedule #${scheduleId} deleted successfully`, 'success');
        fetchSchedules();
      } else {
        showToastMessage(data.message || 'Failed to delete schedule', 'error');
      }
    } catch (error) {
      console.error('Error deleting schedule:', error);
      showToastMessage('Failed to delete schedule', 'error');
    }
    setDeleteModalOpen(false);
    setSelectedSchedule(null);
  };

  const handleEditSchedule = async (scheduleId, updateData) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/reset/schedule/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(updateData)
      });
      
      const data = await response.json();

      if (response.status === 403) {
        setLockMessage(data.detail || data.message);
        showToastMessage(data.detail || data.message || 'Scheduled resets require Optimization+', 'error');
      } else if (data.success) {
        showToastMessage(`Schedule #${scheduleId} updated successfully`, 'success');
        fetchSchedules();
      } else {
        showToastMessage(data.message || 'Failed to update schedule', 'error');
      }
    } catch (error) {
      console.error('Error updating schedule:', error);
      showToastMessage('Failed to update schedule', 'error');
    }
    setEditModalOpen(false);
    setSelectedSchedule(null);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const ToastMessageComponent = () => {
    if (!showToast) return null;
    const colors = {
      success: { bg: '#00b894', icon: '✅' },
      error: { bg: '#ff7675', icon: '❌' },
      info: { bg: '#0984e3', icon: 'ℹ️' }
    };
    const color = colors[showToast.type] || colors.info;
    
    return (
      <div className="toast-message" style={{ backgroundColor: color.bg }}>
        <span>{color.icon}</span>
        <span>{showToast.message}</span>
        <button onClick={() => setShowToast(null)} style={{
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

  if (loading) {
    return (
      <div className="reset-section">
        <div className="section-header">
          <div className="section-icon">📋</div>
          <div className="section-title">Manage Schedules</div>
        </div>
        <div style={{ padding: '40px' }}>
          <LoadingSpinner text="Loading schedules..." />
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="reset-section">
        <div className="section-header">
          <div className="section-icon">📋</div>
          <div className="section-title">Manage Schedules</div>
          <div className="section-subtitle">{schedules.length} schedules</div>
        </div>

        {lockMessage && (
          <div style={{ marginBottom: '16px' }}>
            <OptimizationLockNotice message={lockMessage} />
          </div>
        )}
        
        <div className="schedules-container">
          {schedules.length === 0 ? (
            <div className="empty-schedules">
              <p>No schedules found.</p>
              <p style={{ fontSize: '12px', marginTop: '8px' }}>Go to the Server or User tab to create a schedule.</p>
            </div>
          ) : (
            schedules.map(schedule => (
              <div key={schedule.id} className="schedule-card">
                <div className="schedule-card-header">
                  <div>
                    <span className="schedule-name">{schedule.schedule_name || `Schedule #${schedule.id}`}</span>
                  </div>
                  <span className="schedule-status" style={{ 
                    backgroundColor: schedule.completed ? 'rgba(136, 136, 136, 0.2)' : (schedule.enabled === false ? 'rgba(255, 68, 68, 0.2)' : 'rgba(0, 184, 148, 0.2)'),
                    color: schedule.completed ? '#888' : (schedule.enabled === false ? '#ff4444' : '#00b894')
                  }}>
                    {schedule.completed ? 'Completed' : (schedule.enabled === false ? 'Disabled' : 'Active')}
                  </span>
                </div>
                <div className="schedule-card-content">
                  <div className="schedule-detail">
                    <span className="detail-label">Schedule ID</span>
                    <span className="detail-value">#{schedule.id}</span>
                  </div>
                  <div className="schedule-detail">
                    <span className="detail-label">Scope</span>
                    <span className="detail-value">{schedule.scope_type || 'N/A'}</span>
                  </div>
                  <div className="schedule-detail">
                    <span className="detail-label">Reset Types</span>
                    <span className="detail-value">{schedule.reset_types?.join(', ') || 'N/A'}</span>
                  </div>
                  <div className="schedule-detail">
                    <span className="detail-label">Schedule Type</span>
                    <span className="detail-value">
                      {schedule.schedule_type === 'recurring' ? 'Recurring' : 
                       schedule.schedule_type === 'one_time' ? 'One Time' : 
                       schedule.schedule_type === 'date_range' ? 'Date Range' : schedule.schedule_type || 'N/A'}
                    </span>
                  </div>
                  {schedule.recurring_pattern && (
                    <div className="schedule-detail">
                      <span className="detail-label">Pattern</span>
                      <span className="detail-value">
                        {schedule.recurring_pattern === 'custom_days' ? 'custom_days' : schedule.recurring_pattern}
                      </span>
                    </div>
                  )}
                  {schedule.recurring_times && schedule.recurring_times.length > 0 && (
                    <div className="schedule-detail">
                      <span className="detail-label">Times</span>
                      <span className="detail-value">{schedule.recurring_times.join(', ')}</span>
                    </div>
                  )}
                  {schedule.recurring_weekdays && schedule.recurring_weekdays.length > 0 && (
                    <div className="schedule-detail">
                      <span className="detail-label">Weekdays</span>
                      <span className="detail-value">{schedule.recurring_weekdays.map(w => weekdays.find(d => d.value === w)?.short).join(', ')}</span>
                    </div>
                  )}
                  {schedule.recurring_days_of_month && schedule.recurring_days_of_month.length > 0 && (
                    <div className="schedule-detail">
                      <span className="detail-label">Month Days</span>
                      <span className="detail-value">{schedule.recurring_days_of_month.join(', ')}</span>
                    </div>
                  )}
                  {schedule.recurring_interval_days && (
                    <div className="schedule-detail">
                      <span className="detail-label">Interval</span>
                      <span className="detail-value">Every {schedule.recurring_interval_days} days</span>
                    </div>
                  )}
                  {schedule.next_execution_at && (
                    <div className="schedule-detail">
                      <span className="detail-label">Next Execution</span>
                      <span className="detail-value">{formatDate(schedule.next_execution_at)}</span>
                    </div>
                  )}
                  {schedule.created_at && (
                    <div className="schedule-detail">
                      <span className="detail-label">Created</span>
                      <span className="detail-value">{formatDate(schedule.created_at)}</span>
                    </div>
                  )}
                  {schedule.time_period_days && (
                    <div className="schedule-detail">
                      <span className="detail-label">Time Period</span>
                      <span className="detail-value">Last {schedule.time_period_days} days</span>
                    </div>
                  )}
                  {schedule.reason && (
                    <div className="schedule-detail">
                      <span className="detail-label">Reason</span>
                      <span className="detail-value">{schedule.reason}</span>
                    </div>
                  )}
                </div>
                {!schedule.completed && (
                  <div className="schedule-card-actions">
                    <button 
                      className="schedule-action-btn"
                      onClick={() => {
                        setSelectedSchedule(schedule);
                        setEditModalOpen(true);
                      }}
                    >
                      Edit
                    </button>
                    <button 
                      className="schedule-action-btn danger"
                      onClick={() => {
                        setSelectedSchedule(schedule);
                        setDeleteModalOpen(true);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      <DeleteScheduleConfirmModal 
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setSelectedSchedule(null);
        }}
        onConfirm={handleDeleteSchedule}
        scheduleId={selectedSchedule?.id}
      />

      <EditScheduleModal 
        isOpen={editModalOpen}
        onClose={() => {
          setEditModalOpen(false);
          setSelectedSchedule(null);
        }}
        onConfirm={handleEditSchedule}
        schedule={selectedSchedule}
        currentServer={currentServer}
      />

      <ToastMessageComponent />
    </>
  );
};

// ============================================
// MAIN RESET DASHBOARD COMPONENT
// ============================================

const ResetDashboard = () => {
  const [selectedView, setSelectedView] = useState("server");
  const [currentServer, setCurrentServer] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingServers, setLoadingServers] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasAccess, setHasAccess] = useState(null);
  const [dashboardAccessLevel, setDashboardAccessLevel] = useState('Member');
  const [actionLoading, setActionLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [toast, setToast] = useState(null);
  const [resetResults, setResetResults] = useState(null);
  
  const [scope, setScope] = useState("server");
  const [selectedStatTypes, setSelectedStatTypes] = useState([]);
  const [timeOption, setTimeOption] = useState("all");
  const [timePeriodDays, setTimePeriodDays] = useState(7);
  const [dateRangeFrom, setDateRangeFrom] = useState(null);
  const [dateRangeTo, setDateRangeTo] = useState(null);
  const [showDateRangeModal, setShowDateRangeModal] = useState(false);
  const [schedule, setSchedule] = useState(null);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  
  const [channelSearch, setChannelSearch] = useState("");
  const [categorySearch, setCategorySearch] = useState("");
  const [channels, setChannels] = useState([]);
  const [filteredChannels, setFilteredChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [filteredCategories, setFilteredCategories] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false);
  
  const [userSearch, setUserSearch] = useState("");
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [channelsLoaded, setChannelsLoaded] = useState(false);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);
  
  const [isPublicMode, setIsPublicMode] = useState(false);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const ToastMessageComponent = () => {
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

  const isPrivilegedUser = (userId) => PRIVILEGED_USERS.includes(userId);

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
          hasAccessFlag = hasAdmin;
        } else if (accessLevel === 'Moderator') {
          hasAccessFlag = hasAdmin || hasManageServer;
        } else if (accessLevel === 'Admin') {
          hasAccessFlag = hasAdmin;
        }
        
        setHasAccess(hasAccessFlag);
      } else {
        setHasAccess(false);
      }
    } catch (error) {
      console.error('Error checking server access:', error);
      setHasAccess(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (currentServer && hasAccess && initialLoadComplete) {
      loadData();
    }
  }, [currentServer, hasAccess]);

  useEffect(() => {
    if (scope !== "channel" && scope !== "category") {
      setSelectedChannel(null);
      setSelectedCategory(null);
      setChannelSearch("");
      setCategorySearch("");
    }
  }, [scope]);

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

  // Load users with names (no avatars) using batch fetching
  useEffect(() => {
    if (showUserDropdown && filteredUsers.length > 0 && usersLoaded) {
      const usersWithoutNames = filteredUsers.filter(u => !u.name);
      if (usersWithoutNames.length > 0 && currentServer) {
        const userIds = usersWithoutNames.map(u => u.id);
        batchFetchUserBasicInfo(userIds, currentServer.id, isPublicMode).then(results => {
          setUsers(prev => prev.map(u => {
            if (results[u.id]) {
              return { ...u, name: results[u.id].name, username: results[u.id].username };
            }
            return u;
          }));
          setFilteredUsers(prev => prev.map(u => {
            if (results[u.id]) {
              return { ...u, name: results[u.id].name, username: results[u.id].username };
            }
            return u;
          }));
        });
      }
    }
  }, [showUserDropdown, filteredUsers, usersLoaded, currentServer, isPublicMode]);

  useEffect(() => {
    if (userSearch.trim() === "") {
      setFilteredUsers(users);
    } else {
      const searchLower = userSearch.toLowerCase();
      setFilteredUsers(users.filter(user => 
        (user.name?.toLowerCase().includes(searchLower)) ||
        (user.username?.toLowerCase().includes(searchLower)) ||
        (user.global_name?.toLowerCase().includes(searchLower)) ||
        user.id?.includes(searchLower)
      ));
    }
  }, [userSearch, users]);

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
        setIsAuthenticated(false);
        setIsPublicMode(true);
        setHasAccess(true);
        setCurrentServer({ id: '1424021358680998022', name: 'StatsHQ' });
        setInitialLoadComplete(true);
        setLoadingServers(false);
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
    
    await Promise.all([
      fetchAllUsers(),
      fetchAllChannels(),
      fetchAllCategories()
    ]);
    
    setLoading(false);
  };

  const fetchAllUsers = async () => {
    try {
      const isPublic = isPublicMode;
      const cacheKey = getCacheKey('reset-users', currentServer.id, { public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setUsers(cached);
        setFilteredUsers(cached);
        setUsersLoaded(true);
        return;
      }
      
      const endpoint = isPublic 
        ? `${API_BASE_URL}/api/public/messages/users?guild_id=${currentServer.id}`
        : `${API_BASE_URL}/api/messages/users?guild_id=${currentServer.id}`;
      
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include'
      });
      if (response.ok) {
        const data = await response.json();
        const userList = (data.user_ids || []).map(userId => ({
          id: String(userId),
          username: null,
          global_name: null,
          name: null
        }));
        setUsers(userList);
        setFilteredUsers(userList);
        serverDataCache.set(cacheKey, userList);
      }
    } catch (error) {
      console.error('Error fetching users:', error);
    } finally {
      setUsersLoaded(true);
    }
  };

  const fetchAllChannels = async () => {
    try {
      const isPublic = isPublicMode;
      const cacheKey = getCacheKey('reset-channels', currentServer.id, { public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setChannels(cached);
        setFilteredChannels(cached);
        setChannelsLoaded(true);
        return;
      }
      
      const endpoint = `${API_BASE_URL}/api/server/real-channels?guild_id=${currentServer.id}`;
      
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include'
      });
      if (response.ok) {
        const data = await response.json();
        const channelList = (data || []).map(channel => ({
          id: String(channel.id),
          name: channel.name
        }));
        setChannels(channelList);
        setFilteredChannels(channelList);
        serverDataCache.set(cacheKey, channelList);
      }
    } catch (error) {
      console.error('Error fetching channels:', error);
    } finally {
      setChannelsLoaded(true);
    }
  };

  const fetchAllCategories = async () => {
    try {
      const isPublic = isPublicMode;
      const cacheKey = getCacheKey('reset-categories', currentServer.id, { public: isPublic });
      const cached = serverDataCache.get(cacheKey);
      
      if (cached) {
        setCategories(cached);
        setFilteredCategories(cached);
        setCategoriesLoaded(true);
        return;
      }
      
      const endpoint = `${API_BASE_URL}/api/server/real-categories?guild_id=${currentServer.id}`;
      
      const response = await fetch(endpoint, {
        credentials: isPublic ? 'omit' : 'include'
      });
      if (response.ok) {
        const data = await response.json();
        const categoryList = (data || []).map(category => ({
          id: String(category.id),
          name: category.name
        }));
        setCategories(categoryList);
        setFilteredCategories(categoryList);
        serverDataCache.set(cacheKey, categoryList);
      }
    } catch (error) {
      console.error('Error fetching categories:', error);
    } finally {
      setCategoriesLoaded(true);
    }
  };

  const handleStatTypeToggle = (statType) => {
    setSelectedStatTypes(prev => {
      if (prev.includes(statType)) {
        return prev.filter(t => t !== statType);
      } else {
        return [...prev, statType];
      }
    });
  };

  const handleSelectAll = () => {
    const availableTypes = getFilteredStatTypes(selectedView, scope);
    setSelectedStatTypes(availableTypes.map(t => t.value));
    showToast(`Selected all ${availableTypes.length} stat types`, 'info');
  };

  const handleClearAll = () => {
    setSelectedStatTypes([]);
    showToast('Cleared all selections', 'info');
  };

  const handleDateRangeConfirm = (fromDate, toDate) => {
    setDateRangeFrom(fromDate);
    setDateRangeTo(toDate);
    setTimeOption('range');
    showToast(`Date range set: ${fromDate || 'Start'} to ${toDate || 'End'}`, 'success');
  };

  const handleAddSchedule = (scheduleDescription, scheduleData) => {
    setSchedule({ description: scheduleDescription, data: scheduleData, name: scheduleData.name, reason: scheduleData.reason });
    showToast(`Schedule added: ${scheduleDescription}`, 'success');
  };

  const handleRemoveSchedule = () => {
    setSchedule(null);
    showToast('Schedule removed', 'info');
  };

  const handleApplyDays = () => {
    setTimeOption('days');
    showToast(`Days period set to ${timePeriodDays} days`, 'success');
  };

  const handleReset = async () => {
    if (selectedStatTypes.length === 0) {
      showToast("Please select at least one statistic type to reset", "error");
      return;
    }

    if (!timeOption) {
      showToast("Please select a time period option", "error");
      return;
    }

    setActionLoading(true);
    
    try {
      if (schedule) {
        await createSchedule();
      } else {
        await executeReset();
      }
    } catch (error) {
      console.error('Error:', error);
      showToast("Failed to process request", "error");
    } finally {
      setActionLoading(false);
    }
  };

  const createSchedule = async () => {
    let scopeValue = scope;
    let scopeDetails = "";
    let channelId = null;
    let categoryId = null;
    
    if (scope === "channel" && selectedChannel) {
      scopeDetails = `Channel: #${selectedChannel.name} (ID: ${selectedChannel.id})`;
      channelId = selectedChannel.id;
    } else if (scope === "category" && selectedCategory) {
      scopeDetails = `Category: ${selectedCategory.name} (ID: ${selectedCategory.id})`;
      categoryId = selectedCategory.id;
    } else {
      scopeDetails = "Entire Server";
    }
    
    const resetTypes = selectedStatTypes;
    
    let recurringPattern = null;
    let recurringWeekdays = null;
    let recurringMonthDays = null;
    let recurringTimes = null;
    let recurringIntervalDays = null;
    
    if (schedule.data.pattern === 'daily') {
      recurringPattern = 'daily';
      recurringTimes = schedule.data.times;
    } else if (schedule.data.pattern === 'weekly') {
      recurringPattern = 'weekly';
      recurringWeekdays = schedule.data.weekdays;
      recurringTimes = schedule.data.times;
    } else if (schedule.data.pattern === 'monthly') {
      recurringPattern = 'monthly';
      recurringMonthDays = schedule.data.monthDays;
      recurringTimes = schedule.data.times;
    } else if (schedule.data.pattern === 'custom_days') {
      recurringPattern = 'custom_days';
      recurringIntervalDays = schedule.data.intervalDays;
      recurringTimes = schedule.data.times;
    }
    
    let timePeriodDaysParam = null;
    let deleteFromDateParam = null;
    let deleteToDateParam = null;
    
    if (timeOption === 'days') {
      timePeriodDaysParam = timePeriodDays;
    } else if (timeOption === 'range') {
      deleteFromDateParam = dateRangeFrom;
      deleteToDateParam = dateRangeTo;
    }
    
    const body = {
      guild_id: currentServer.id,
      requested_by_id: currentUserId,
      reset_types: resetTypes,
      schedule_name: schedule.data.name || null,
      reason: schedule.data.reason || null,
      schedule_type: "recurring",
      recurring_pattern: recurringPattern,
      recurring_weekdays: recurringWeekdays,
      recurring_days_of_month: recurringMonthDays,
      recurring_times: recurringTimes,
      recurring_interval_days: recurringIntervalDays,
      time_period_days: timePeriodDaysParam,
      delete_from_date: deleteFromDateParam,
      delete_to_date: deleteToDateParam,
      scope_type: scopeValue,
      scope_details: scopeDetails,
      channel_id: channelId,
      category_id: categoryId
    };
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/reset/schedule/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body)
      });
      
      const result = await response.json();
      
      if (result.success) {
        const scheduleNameText = schedule.data.name ? ` "${schedule.data.name}"` : '';
        showToast(`Schedule${scheduleNameText} created! Schedule #${result.schedule_id}`, "success");
        setResetResults([{
          type: "schedule",
          label: `Schedule Created${scheduleNameText} (${resetTypes.length} types)`,
          success: true,
          message: schedule.description,
          schedule_id: result.schedule_id
        }]);
      } else {
        showToast(`Failed to create schedule: ${result.message}`, "error");
        setResetResults([{
          type: "schedule",
          label: "Schedule Creation",
          success: false,
          message: result.message || "Unknown error"
        }]);
      }
    } catch (error) {
      console.error('Error creating schedule:', error);
      showToast("Failed to create schedule", "error");
      setResetResults([{
        type: "schedule",
        label: "Schedule Creation",
        success: false,
        message: error.message || "Network error"
      }]);
    }
  };

  const executeReset = async () => {
    const results = [];
    
    try {
      for (const statType of selectedStatTypes) {
        let endpoint = "";
        let body = {};
        
        if (selectedView === "server") {
          endpoint = `${API_BASE_URL}/api/reset/server`;
          body = {
            guild_id: currentServer.id,
            stat_type: statType
          };
          
          if (scope === "channel" && selectedChannel) {
            body.channel_id = selectedChannel.id;
          } else if (scope === "category" && selectedCategory) {
            body.category_id = selectedCategory.id;
          }
        } else {
          if (!selectedUser) {
            showToast("Please select a user", "error");
            setActionLoading(false);
            return;
          }
          
          endpoint = `${API_BASE_URL}/api/reset/user`;
          body = {
            guild_id: currentServer.id,
            user_id: selectedUser.id,
            stat_type: statType
          };
          
          if (scope === "channel" && selectedChannel) {
            body.channel_id = selectedChannel.id;
          } else if (scope === "category" && selectedCategory) {
            body.category_id = selectedCategory.id;
          }
        }
        
        if (timeOption === 'days') {
          body.time_period_days = timePeriodDays;
        } else if (timeOption === 'range') {
          if (dateRangeFrom) body.delete_from_date = dateRangeFrom;
          if (dateRangeTo) body.delete_to_date = dateRangeTo;
        }
        
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body)
        });
        
        const result = await response.json();
        
        results.push({
          statType,
          label: STAT_TYPES[selectedView][statType]?.label || statType,
          success: result.success,
          message: result.message,
          deleted_counts: result.deleted_counts
        });
      }
      
      setResetResults(results);
      
      serverDataCache.clearPattern('reset-users');
      serverDataCache.clearPattern('reset-channels');
      serverDataCache.clearPattern('reset-categories');
      
      const successCount = results.filter(r => r.success).length;
      if (successCount === results.length) {
        showToast(`Successfully reset ${successCount} statistic types`, "success");
      } else if (successCount > 0) {
        showToast(`Reset ${successCount}/${results.length} statistic types`, "info");
      } else {
        showToast("Failed to reset statistics", "error");
      }
    } catch (error) {
      console.error('Error resetting stats:', error);
      showToast("Failed to reset statistics", "error");
    }
  };

  const getScopeLabel = () => {
    if (scope === "server") return "the entire server";
    if (scope === "channel" && selectedChannel) return `channel #${selectedChannel.name}`;
    if (scope === "category" && selectedCategory) return `category ${selectedCategory.name}`;
    return "the selected scope";
  };

  const getTimePeriodDescription = () => {
    if (timeOption === 'days') {
      return `Deleting stats from the last ${timePeriodDays} days`;
    } else if (timeOption === 'range') {
      const fromStr = dateRangeFrom ? new Date(dateRangeFrom).toLocaleDateString() : 'Start';
      const toStr = dateRangeTo ? new Date(dateRangeTo).toLocaleDateString() : 'End';
      return `Deleting stats from ${fromStr} to ${toStr}`;
    } else if (timeOption === 'all') {
      return `Deleting ALL stats (no time limit)`;
    }
    return "No time period selected";
  };

  const availableStatTypes = getFilteredStatTypes(selectedView, scope);
  const selectedCount = selectedStatTypes.length;
  const hasSelection = selectedCount > 0;

  const handleTimeOptionSelect = (option) => {
    if (timeOption === option) {
      setTimeOption(null);
    } else {
      setTimeOption(option);
    }
  };

  // Schedule type info for the info icon
  const scheduleTypeInfo = [
    { level: "Daily", description: "Runs every day at selected time(s)" },
    { level: "Weekly", description: "Runs on selected day(s) at selected time(s)" },
    { level: "Monthly", description: "Runs on selected day(s) of month at selected time(s)" },
    { level: "Custom", description: "Runs every X days at selected time(s)" }
  ];

  // Loading states
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

  if (!isAuthenticated && currentServer) {
    // Public mode
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar topOffset={NAVBAR_HEIGHT} isPublicMode={true} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="public-banner" style={{ marginBottom: '20px', padding: '12px', background: 'linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%)', border: '1px solid #aa00ff', borderRadius: '12px', textAlign: 'center' }}>
                <p>Viewing statistics from the <strong>StatsHQ</strong> support server - <a href={`${API_BASE_URL}/api/auth/discord`} style={{ color: '#aa00ff' }}>Login</a> to reset your own server stats</p>
              </div>
              
              <div className="view-selector">
                <button 
                  className={`view-button ${selectedView === "server" ? "active" : ""}`}
                  onClick={() => {
                    setSelectedView("server");
                    setSelectedStatTypes([]);
                    setScope("server");
                    setSelectedUser(null);
                    setUserSearch("");
                    setTimeOption("all");
                    setSchedule(null);
                  }}
                >
                  Server
                </button>
                <button 
                  className={`view-button ${selectedView === "user" ? "active" : ""}`}
                  onClick={() => {
                    setSelectedView("user");
                    setSelectedStatTypes([]);
                    setScope("server");
                    setSelectedUser(null);
                    setUserSearch("");
                    setTimeOption("all");
                    setSchedule(null);
                  }}
                >
                  User
                </button>
                <button 
                  className={`view-button ${selectedView === "schedules" ? "active" : ""}`}
                  onClick={() => setSelectedView("schedules")}
                >
                  Schedules
                </button>
              </div>

              {selectedView === "schedules" ? (
                <ScheduleManagement currentServer={currentServer} />
              ) : (
                <>
                  <div className="scope-selector-section">
                    <h2 className="section-title">Select Scope</h2>
                    <div className="scope-controls">
                      <div className="scope-selector">
                        <div className="scope-dropdown-wrapper">
                          <select 
                            className="scope-dropdown"
                            value={scope}
                            onChange={(e) => {
                              setScope(e.target.value);
                              setSelectedStatTypes([]);
                              setTimeOption("all");
                              setSchedule(null);
                            }}
                          >
                            <option value="server">Server</option>
                            <option value="channel">Channel</option>
                            <option value="category">Category</option>
                          </select>
                        </div>
                      </div>
                      
                      {scope === "channel" && (
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
                                      setSelectedChannel(channel);
                                      setChannelSearch(channel.name);
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
                          {selectedChannel && (
                            <div className="selected-entity-info">
                              <span className="selected-entity-label">Selected Channel:</span>
                              #{selectedChannel.name} (ID: {selectedChannel.id})
                            </div>
                          )}
                        </div>
                      )}
                      
                      {scope === "category" && (
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
                                      setSelectedCategory(category);
                                      setCategorySearch(category.name);
                                      setShowCategoryDropdown(false);
                                    }}
                                  >
                                    <div className="entity-option-info">
                                      <span className="entity-name">📁 {category.name}</span>
                                    </div>
                                    <span className="entity-subtext">ID: {category.id}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                          {selectedCategory && (
                            <div className="selected-entity-info">
                              <span className="selected-entity-label">Selected Category:</span>
                              {selectedCategory.name} (ID: {selectedCategory.id})
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    
                    {selectedView === "user" && (
                      <div className="entity-selector-wrapper" style={{ marginTop: "20px", width: "100%" }}>
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
                                    setSelectedUser(user);
                                    setUserSearch(user.name || user.username || user.global_name || `User ${user.id}`);
                                    setShowUserDropdown(false);
                                  }}
                                >
                                  <div className="entity-option-info">
                                    <span className="entity-name">
                                      {user.name || user.username || user.global_name || `User ${user.id}`}
                                    </span>
                                  </div>
                                  <span className="entity-subtext">ID: {user.id}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        {selectedUser && (
                          <div className="selected-entity-info">
                            <span className="selected-entity-label">Selected User:</span>
                            {selectedUser.name || selectedUser.username || selectedUser.global_name || selectedUser.id}
                            <span style={{ color: "#888", marginLeft: "8px" }}>(ID: {selectedUser.id})</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="reset-section">
                    <div className="section-header">
                      <div className="section-icon">📊</div>
                      <div className="section-title">Select Stat Types to Reset</div>
                      <div className="section-subtitle">
                        {selectedCount > 0 && `${selectedCount} selected`}
                      </div>
                    </div>
                    
                    <div className="action-buttons-group">
                      <button className="action-button" onClick={handleSelectAll}>
                        <span>✅</span> Select All
                      </button>
                      <button className="action-button" onClick={handleClearAll}>
                        <span>🗑️</span> Clear All
                      </button>
                    </div>
                    
                    <div className="stat-types-grid">
                      {availableStatTypes.map(stat => (
                        <div 
                          key={stat.value}
                          className={`stat-card ${selectedStatTypes.includes(stat.value) ? "selected" : ""}`}
                          onClick={() => handleStatTypeToggle(stat.value)}
                        >
                          <div className="stat-card-content">
                            <input 
                              type="checkbox" 
                              checked={selectedStatTypes.includes(stat.value)}
                              onChange={() => {}}
                              onClick={(e) => e.stopPropagation()}
                              className="stat-checkbox"
                            />
                            <div className="stat-info">
                              <div className="stat-header">
                                <span className="stat-label">{stat.label}</span>
                                {stat.value === "all" && <span className="stat-badge">DANGER</span>}
                              </div>
                              <div className="stat-description">{stat.description}</div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="reset-section">
                    <div className="section-header">
                      <div className="section-icon">⏰</div>
                      <div className="section-title">Time Period</div>
                      <div className="section-subtitle">Choose which data to delete</div>
                    </div>
                    
                    <div className="time-period-options">
                      <button 
                        className={`time-option-btn ${timeOption === 'all' ? 'active' : ''}`}
                        onClick={() => handleTimeOptionSelect('all')}
                      >
                        <span>All Time</span>
                        <span className="time-option-description">Delete ALL stats with no time limit</span>
                      </button>
                      <button 
                        className={`time-option-btn ${timeOption === 'days' ? 'active' : ''}`}
                        onClick={() => handleTimeOptionSelect('days')}
                      >
                        <span>Days Back</span>
                        <span className="time-option-description">Delete stats from the last X days</span>
                      </button>
                      <button 
                        className={`time-option-btn ${timeOption === 'range' ? 'active' : ''}`}
                        onClick={() => setShowDateRangeModal(true)}
                      >
                        <span>Date Range</span>
                        <span className="time-option-description">Delete stats within a specific date range</span>
                      </button>
                    </div>

                    {timeOption === 'days' && (
                      <div className="days-input-group">
                        <input 
                          type="number"
                          className="days-input"
                          min="1"
                          max="365"
                          value={timePeriodDays}
                          onChange={(e) => setTimePeriodDays(Math.min(365, Math.max(1, parseInt(e.target.value) || 1)))}
                        />
                        <span>days</span>
                        <button className="apply-days-btn" onClick={handleApplyDays}>Apply</button>
                      </div>
                    )}

                    {timeOption && (
                      <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#1a1a1a', borderRadius: '8px', fontSize: '13px', color: '#aa00ff' }}>
                        {getTimePeriodDescription()}
                      </div>
                    )}
                  </div>

                  <div className="reset-section">
                    <div className="section-header">
                      <div className="section-icon">⏱️</div>
                      <div className="section-title">
                        Schedule (Optional)
                        <InfoIcon descriptions={scheduleTypeInfo} />
                      </div>
                      <div className="section-subtitle">Set up automatic recurring resets</div>
                    </div>
                    
                    <div className="schedule-section">
                      {!schedule ? (
                        <button 
                          className="add-schedule-button"
                          onClick={() => setShowScheduleModal(true)}
                        >
                          <span>➕</span> Add Schedule
                        </button>
                      ) : (
                        <div className="schedule-preview">
                          <div className="schedule-preview-header">
                            <span className="schedule-preview-title">
                              {schedule.name || 'Active Schedule'}
                            </span>
                            <button className="remove-schedule" onClick={handleRemoveSchedule}>✕</button>
                          </div>
                          {schedule.reason && (
                            <div style={{ marginBottom: '8px', fontSize: '13px', color: '#aaa' }}>
                              📝 Reason: {schedule.reason}
                            </div>
                          )}
                          <div className="schedule-preview-content">
                            <div className="schedule-preview-item">
                              <span>🕐</span> {schedule.description}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="reset-button-container">
                    <button 
                      className="reset-button"
                      onClick={handleReset}
                      disabled={actionLoading || !hasSelection || !timeOption}
                    >
                      {actionLoading ? (
                        <>
                          <div className="loading-spinner"></div>
                          Processing...
                        </>
                      ) : (
                        <>
                          {schedule ? "CREATE SCHEDULE" : "RESET NOW"}
                        </>
                      )}
                    </button>
                  </div>

                  {resetResults && resetResults.length > 0 && (
                    <div className="results-section">
                      <div className="results-header">
                        <div className="results-title">
                          <span>📋</span> {resetResults[0].type === "schedule" ? "Schedule Results" : "Reset Results"}
                        </div>
                        <div className="results-stats">
                          {resetResults.filter(r => r.success).length} of {resetResults.length} successful
                        </div>
                      </div>
                      <table className="results-table">
                        <thead>
                          <tr>
                            <th>Type</th>
                            <th>Status</th>
                            <th>Message</th>
                          </tr>
                        </thead>
                        <tbody>
                          {resetResults.map((result, idx) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: 500 }}>{result.label}</td>
                              <td>
                                {result.success ? (
                                  <span className="success-badge">Success</span>
                                ) : (
                                  <span className="error-badge">Failed</span>
                                )}
                              </td>
                              <td style={{ fontSize: "12px", color: "#888" }}>{result.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
            <Footer />
          </main>
        </div>

        <DateRangeModal 
          isOpen={showDateRangeModal}
          onClose={() => setShowDateRangeModal(false)}
          onConfirm={handleDateRangeConfirm}
        />

        <ScheduleModal 
          isOpen={showScheduleModal}
          onClose={() => setShowScheduleModal(false)}
          onConfirm={handleAddSchedule}
          existingSchedule={schedule}
        />

        <ToastMessageComponent />
        <style>{styles}</style>
      </>
    );
  }

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

  // Render Schedule Management page
  if (selectedView === "schedules") {
    return (
      <>
        <NavBar />
        <div className="dashboard-page">
          <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
          <main className="dashboard-main">
            <div className="dashboard-content">
              <div className="view-selector">
                <button 
                  className={`view-button ${selectedView === "server" ? "active" : ""}`}
                  onClick={() => {
                    setSelectedView("server");
                    setSelectedStatTypes([]);
                    setScope("server");
                    setSelectedUser(null);
                    setUserSearch("");
                    setTimeOption("all");
                    setSchedule(null);
                  }}
                >
                  Server
                </button>
                <button 
                  className={`view-button ${selectedView === "user" ? "active" : ""}`}
                  onClick={() => {
                    setSelectedView("user");
                    setSelectedStatTypes([]);
                    setScope("server");
                    setSelectedUser(null);
                    setUserSearch("");
                    setTimeOption("all");
                    setSchedule(null);
                  }}
                >
                  User
                </button>
                <button 
                  className={`view-button ${selectedView === "schedules" ? "active" : ""}`}
                  onClick={() => setSelectedView("schedules")}
                >
                  Schedules
                </button>
              </div>

              <ScheduleManagement currentServer={currentServer} />
            </div>
            <Footer />
          </main>
        </div>
        <ToastMessageComponent />
        <style>{styles}</style>
      </>
    );
  }

  // Authenticated and has access - normal rendering
  return (
    <>
      <NavBar />
      <div className="dashboard-page">
        <DashboardSidebar currentServerId={currentServer?.id} topOffset={NAVBAR_HEIGHT} />
        
        <main className="dashboard-main">
          <div className="dashboard-content">
            <div className="view-selector">
              <button 
                className={`view-button ${selectedView === "server" ? "active" : ""}`}
                onClick={() => {
                  setSelectedView("server");
                  setSelectedStatTypes([]);
                  setScope("server");
                  setSelectedUser(null);
                  setUserSearch("");
                  setTimeOption("all");
                  setSchedule(null);
                }}
              >
                Server
              </button>
              <button 
                className={`view-button ${selectedView === "user" ? "active" : ""}`}
                onClick={() => {
                  setSelectedView("user");
                  setSelectedStatTypes([]);
                  setScope("server");
                  setSelectedUser(null);
                  setUserSearch("");
                  setTimeOption("all");
                  setSchedule(null);
                }}
              >
                User
              </button>
              <button 
                className={`view-button ${selectedView === "schedules" ? "active" : ""}`}
                onClick={() => setSelectedView("schedules")}
              >
                Schedules
              </button>
            </div>

            <div className="scope-selector-section">
              <h2 className="section-title">Select Scope</h2>
              <div className="scope-controls">
                <div className="scope-selector">
                  <div className="scope-dropdown-wrapper">
                    <select 
                      className="scope-dropdown"
                      value={scope}
                      onChange={(e) => {
                        setScope(e.target.value);
                        setSelectedStatTypes([]);
                        setTimeOption("all");
                        setSchedule(null);
                      }}
                    >
                      <option value="server">Server</option>
                      <option value="channel">Channel</option>
                      <option value="category">Category</option>
                    </select>
                  </div>
                </div>
                
                {scope === "channel" && (
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
                                setSelectedChannel(channel);
                                setChannelSearch(channel.name);
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
                    {selectedChannel && (
                      <div className="selected-entity-info">
                        <span className="selected-entity-label">Selected Channel:</span>
                        #{selectedChannel.name} (ID: {selectedChannel.id})
                      </div>
                    )}
                  </div>
                )}
                
                {scope === "category" && (
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
                                setSelectedCategory(category);
                                setCategorySearch(category.name);
                                setShowCategoryDropdown(false);
                              }}
                            >
                              <div className="entity-option-info">
                                <span className="entity-name">📁 {category.name}</span>
                              </div>
                              <span className="entity-subtext">ID: {category.id}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {selectedCategory && (
                      <div className="selected-entity-info">
                        <span className="selected-entity-label">Selected Category:</span>
                        {selectedCategory.name} (ID: {selectedCategory.id})
                      </div>
                    )}
                  </div>
                )}
              </div>
              
              {selectedView === "user" && (
                <div className="entity-selector-wrapper" style={{ marginTop: "20px", width: "100%" }}>
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
                              setSelectedUser(user);
                              setUserSearch(user.name || user.username || user.global_name || `User ${user.id}`);
                              setShowUserDropdown(false);
                            }}
                          >
                            <div className="entity-option-info">
                              <span className="entity-name">
                                {user.name || user.username || user.global_name || `User ${user.id}`}
                              </span>
                            </div>
                            <span className="entity-subtext">ID: {user.id}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {selectedUser && (
                    <div className="selected-entity-info">
                      <span className="selected-entity-label">Selected User:</span>
                      {selectedUser.name || selectedUser.username || selectedUser.global_name || selectedUser.id}
                      <span style={{ color: "#888", marginLeft: "8px" }}>(ID: {selectedUser.id})</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="reset-section">
              <div className="section-header">
                <div className="section-icon">📊</div>
                <div className="section-title">Select Stat Types to Reset</div>
                <div className="section-subtitle">
                  {selectedCount > 0 && `${selectedCount} selected`}
                </div>
              </div>
              
              <div className="action-buttons-group">
                <button className="action-button" onClick={handleSelectAll}>
                  <span>✅</span> Select All
                </button>
                <button className="action-button" onClick={handleClearAll}>
                  <span>🗑️</span> Clear All
                </button>
              </div>
              
              <div className="stat-types-grid">
                {availableStatTypes.map(stat => (
                  <div 
                    key={stat.value}
                    className={`stat-card ${selectedStatTypes.includes(stat.value) ? "selected" : ""}`}
                    onClick={() => handleStatTypeToggle(stat.value)}
                  >
                    <div className="stat-card-content">
                      <input 
                        type="checkbox" 
                        checked={selectedStatTypes.includes(stat.value)}
                        onChange={() => {}}
                        onClick={(e) => e.stopPropagation()}
                        className="stat-checkbox"
                      />
                      <div className="stat-info">
                        <div className="stat-header">
                          <span className="stat-label">{stat.label}</span>
                          {stat.value === "all" && <span className="stat-badge">DANGER</span>}
                        </div>
                        <div className="stat-description">{stat.description}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="reset-section">
              <div className="section-header">
                <div className="section-icon">⏰</div>
                <div className="section-title">Time Period</div>
                <div className="section-subtitle">Choose which data to delete</div>
              </div>
              
              <div className="time-period-options">
                <button 
                  className={`time-option-btn ${timeOption === 'all' ? 'active' : ''}`}
                  onClick={() => handleTimeOptionSelect('all')}
                >
                  <span>All Time</span>
                  <span className="time-option-description">Delete ALL stats with no time limit</span>
                </button>
                <button 
                  className={`time-option-btn ${timeOption === 'days' ? 'active' : ''}`}
                  onClick={() => handleTimeOptionSelect('days')}
                >
                  <span>Days Back</span>
                  <span className="time-option-description">Delete stats from the last X days</span>
                </button>
                <button 
                  className={`time-option-btn ${timeOption === 'range' ? 'active' : ''}`}
                  onClick={() => setShowDateRangeModal(true)}
                >
                  <span>Date Range</span>
                  <span className="time-option-description">Delete stats within a specific date range</span>
                </button>
              </div>

              {timeOption === 'days' && (
                <div className="days-input-group">
                  <input 
                    type="number"
                    className="days-input"
                    min="1"
                    max="365"
                    value={timePeriodDays}
                    onChange={(e) => setTimePeriodDays(Math.min(365, Math.max(1, parseInt(e.target.value) || 1)))}
                  />
                  <span>days</span>
                  <button className="apply-days-btn" onClick={handleApplyDays}>Apply</button>
                </div>
              )}

              {timeOption && (
                <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#1a1a1a', borderRadius: '8px', fontSize: '13px', color: '#aa00ff' }}>
                  {getTimePeriodDescription()}
                </div>
              )}
            </div>

            <div className="reset-section">
              <div className="section-header">
                <div className="section-icon">⏱️</div>
                <div className="section-title">
                  Schedule (Optional)
                  <InfoIcon descriptions={scheduleTypeInfo} />
                </div>
                <div className="section-subtitle">Set up automatic recurring resets</div>
              </div>
              
              <div className="schedule-section">
                {!schedule ? (
                  <button 
                    className="add-schedule-button"
                    onClick={() => setShowScheduleModal(true)}
                  >
                    <span>➕</span> Add Schedule
                  </button>
                ) : (
                  <div className="schedule-preview">
                    <div className="schedule-preview-header">
                      <span className="schedule-preview-title">
                        {schedule.name || 'Active Schedule'}
                      </span>
                      <button className="remove-schedule" onClick={handleRemoveSchedule}>✕</button>
                    </div>
                    {schedule.reason && (
                      <div style={{ marginBottom: '8px', fontSize: '13px', color: '#aaa' }}>
                        📝 Reason: {schedule.reason}
                      </div>
                    )}
                    <div className="schedule-preview-content">
                      <div className="schedule-preview-item">
                        <span>🕐</span> {schedule.description}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="reset-button-container">
              <button 
                className="reset-button"
                onClick={handleReset}
                disabled={actionLoading || !hasSelection || !timeOption}
              >
                {actionLoading ? (
                  <>
                    <div className="loading-spinner"></div>
                    Processing...
                  </>
                ) : (
                  <>
                    {schedule ? "CREATE SCHEDULE" : "RESET NOW"}
                  </>
                )}
              </button>
            </div>

            {resetResults && resetResults.length > 0 && (
              <div className="results-section">
                <div className="results-header">
                  <div className="results-title">
                    <span>📋</span> {resetResults[0].type === "schedule" ? "Schedule Results" : "Reset Results"}
                  </div>
                  <div className="results-stats">
                    {resetResults.filter(r => r.success).length} of {resetResults.length} successful
                  </div>
                </div>
                <table className="results-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resetResults.map((result, idx) => (
                      <tr key={idx}>
                        <td style={{ fontWeight: 500 }}>{result.label}</td>
                        <td>
                          {result.success ? (
                            <span className="success-badge">Success</span>
                          ) : (
                            <span className="error-badge">Failed</span>
                          )}
                        </td>
                        <td style={{ fontSize: "12px", color: "#888" }}>{result.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <Footer />
        </main>
      </div>

      <DateRangeModal 
        isOpen={showDateRangeModal}
        onClose={() => setShowDateRangeModal(false)}
        onConfirm={handleDateRangeConfirm}
      />

      <ScheduleModal 
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        onConfirm={handleAddSchedule}
        existingSchedule={schedule}
      />

      <ToastMessageComponent />
      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <ResetDashboard />
  </React.StrictMode>
);

export default ResetDashboard;