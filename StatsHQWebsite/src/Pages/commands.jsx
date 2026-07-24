import React from "react";
import { createRoot } from "react-dom/client";
import { useState, useEffect, useRef } from "react";
import NavBar from "../Components/NavBar.jsx";
import Footer from "../Components/Footer.jsx";

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

const CommandsPage = () => {
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [commandType, setCommandType] = useState("slash");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCommand, setSelectedCommand] = useState(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(true);
  const searchRef = useRef(null);

  const categories = [
    "Starter",
    "Basic Stats",
    "Leaderboards",
    "Charts",
    "Emoji Statistics",
    "Status Activity Tracking",
    "Mentions Tracking",
    "Invite Tracking",
    "Fun Statistics",
    "Averages",
    "Distribution",
    "Growth Monitoring",
    "Optimization"
  ];

  const commands = [
    // Starter
    { name: "help", prefixShortcut: "", description: "Display the help menu", category: "Starter" },
    { name: "links", prefixShortcut: "bot invite, support", description: "Get the most important links regarding the bot.", category: "Starter" },
    { name: "get id", prefixShortcut: "", description: "Get the id of your account, server, channel, category, or role", category: "Starter" },
    { name: "vote", prefixShortcut: "voting, topgg", description: "Get the link to vote for the bot on top.gg", category: "Starter" },
    { name: "feedback", prefixShortcut: "fb, suggest, bugreport", description: "Submit a suggestion or a bug report directly to the developers", category: "Starter" },

    // Basic Stats
    { name: "user stats", prefixShortcut: "u", description: "Get a user's message and voice activity stats", category: "Basic Stats" },
    { name: "server stats", prefixShortcut: "s", description: "Get a server's message and voice activity stats", category: "Basic Stats" },
    { name: "category stats", prefixShortcut: "ca", description: "Get a category's message and voice activity stats", category: "Basic Stats" },
    { name: "channel stats", prefixShortcut: "ch", description: "Get a channel's message and voice activity stats", category: "Basic Stats" },

    // Leaderboards
    { name: "leaderboard server", prefixShortcut: "ls", description: "Display a leaderboard showcasing the top users, channels and categories based on either message or voice activity stats", category: "Leaderboards" },
    { name: "leaderboard channel", prefixShortcut: "lch", description: "Display a leaderboard showcasing the top users in a specific channel based on either message or voice activity stats", category: "Leaderboards" },
    { name: "leaderboard category", prefixShortcut: "lca", description: "Display a leaderboard showcasing the top users and top channels in a specific category based on either message or voice activity stats", category: "Leaderboards" },
    { name: "leaderboard role", prefixShortcut: "lr", description: "Display the top roles in the server, channel or category based on messages, voice activity or invites", category: "Leaderboards" },

    // Charts
    { name: "chart user", prefixShortcut: "cu", description: "Display a chart representing a user's messages, voice activity or invite stats in the server", category: "Charts" },
    { name: "chart channel", prefixShortcut: "cch", description: "Display a chart representing a channel's message or voice activity stats", category: "Charts" },
    { name: "chart category", prefixShortcut: "cca", description: "Display a chart representing a category's message or voice activity stats", category: "Charts" },
    { name: "chart server", prefixShortcut: "cs", description: "Display a chart representing a server's message, voice activity or invite stats", category: "Charts" },

    // Emoji Statistics
    { name: "emoji server leaderboard", prefixShortcut: "els", description: "Display the top emojis in the server in terms of usage", category: "Emoji Statistics" },
    { name: "emoji user leaderboard", prefixShortcut: "eul", description: "Display the top users in the server based on the amount of emoji usage", category: "Emoji Statistics" },
    { name: "emoji channel leaderboard", prefixShortcut: "elch", description: "Display the top emojis in a channel in terms of usage", category: "Emoji Statistics" },
    { name: "emoji category leaderboard", prefixShortcut: "elca", description: "Display the top emojis in a category in terms of usage", category: "Emoji Statistics" },
    { name: "emoji user stats", prefixShortcut: "eu", description: "Display a user's most used emojis across the server, channel or category", category: "Emoji Statistics" },

    // Activity Tracking
    { name: "status activity user", prefixShortcut: "au", description: "Display a user's top activities based on time spent and sessions", category: "Status Activity Tracking" },
    { name: "status activity server", prefixShortcut: "as", description: "Display a server's top activities based on time spent, sessions or users", category: "Status Activity Tracking" },
    { name: "status activity whos", prefixShortcut: "aw", description: "Find the top users that are currently doing a specific activity", category: "Status Activity Tracking" },
    { name: "status activity leaderboard", prefixShortcut: "al", description: "Display a leaderboard showcasing the top activities in a server based on time spent, sessions or users, or view a specific user's top activities", category: "Status Activity Tracking" },
    { name: "status activity streak", prefixShortcut: "sas", description: "Display the top activity streaks per category for the server, or view a specific user's activity streaks", category: "Status Activity Tracking" },

    // Mentions Tracking
    { name: "mentions leaderboard", prefixShortcut: "ml", description: "Display a leaderboard showcasing the top users based on mentions sent or received, in the server, a channel, a category, or of a specific user", category: "Mentions Tracking" },
    { name: "mentions ratios leaderboard", prefixShortcut: "mrl", description: "Display a leaderboard showcasing the top users by mentions ratio (received vs sent), optionally filtered by channel or category", category: "Mentions Tracking" },
    { name: "mentions ratio", prefixShortcut: "mr", description: "Display a user's mentions ratio, comparing mentions received to mentions sent", category: "Mentions Tracking" },

    // Invite Tracking
    { name: "invite stats", prefixShortcut: "is", description: "Display a user's invite stats", category: "Invite Tracking" },
    { name: "inviter", prefixShortcut: "ir", description: "Find the inviter of a specific user", category: "Invite Tracking" },
    { name: "invite leaderboard", prefixShortcut: "il", description: "Display a leaderboard showcasing the top users in terms of valid invites", category: "Invite Tracking" },

    // Fun Statistics
    { name: "ship compatability", prefixShortcut: "sh", description: "Get a compatability score based on the mentions, activity overlap, shared channels, vc time spent, and the recent activity between two users", category: "Fun Statistics" },
    { name: "ship leaderboard", prefixShortcut: "sl", description: "Display a leaderboard showcasing the top ship scores in a server", category: "Fun Statistics" },

    // Averages
    { name: "average server", prefixShortcut: "avs", description: "Displays averages for statistics in a server", category: "Averages" },
    { name: "average user", prefixShortcut: "avu", description: "Displays averages for a user's statistics", category: "Averages" },

    // Distribution
    { name: "distribution server", prefixShortcut: "ds", description: "Displays a server-wide hourly activity distribution clock chart for messages, voice activity, activities, emoji usage, mentions, invites, joins or leaves", category: "Distribution" },
    { name: "distribution channel", prefixShortcut: "dc", description: "Displays an hourly activity distribution clock chart for a specific channel, defaults to the current channel", category: "Distribution" },
    { name: "distribution category", prefixShortcut: "dca", description: "Displays an hourly activity distribution clock chart for a specific category", category: "Distribution" },
    { name: "distribution user", prefixShortcut: "du", description: "Displays an hourly activity distribution clock chart for a specific user, defaults to yourself", category: "Distribution" },

    // Growth Monitoring
    { name: "growth role", prefixShortcut: "gr", description: "Displays a chart representing the growth of a role based on additions or removals", category: "Growth Monitoring" },
    { name: "growth member", prefixShortcut: "gm", description: "Displays a chart representing the growth of members in a server based on joins and leaves", category: "Growth Monitoring" },

    // Optimization
    { name: "reset server", prefixShortcut: "rs", description: "Reset statistics in a server", category: "Optimization" },
    { name: "reset user", prefixShortcut: "ru", description: "Reset a user's statistics in a server", category: "Optimization" },
    { name: "reset schedules", prefixShortcut: "", description: "View and delete scheduled resets for the server (Admin only)", category: "Optimization" }, // NEW COMMAND
    { name: "settings server", prefixShortcut: "set", description: "Displays the server settings menu", category: "Optimization" }, // RENAMED
    { name: "settings user", prefixShortcut: "setu", description: "Displays the user settings menu for personal preferences and configurations", category: "Optimization" }, // NEW COMMAND
    { name: "blacklist menu", prefixShortcut: "bm", description: "Displays the blacklist menu for excluding users, channels, categories and roles from statistics", category: "Optimization" },
    { name: "blacklist view", prefixShortcut: "bv", description: "Displays the blacklisted users, channels, categories or roles", category: "Optimization" }
  ];

  // Simulate loading
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(false);
    }, 1000);
    
    return () => clearTimeout(timer);
  }, []);

  const filteredCommands = commands.filter(cmd => {
    const matchesCategory = selectedCategory === "All" || cmd.category === selectedCategory;
    const matchesSearch = cmd.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         cmd.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const searchSuggestions = commands
    .filter(cmd => cmd.name.toLowerCase().includes(searchQuery.toLowerCase()) && searchQuery.length > 0)
    .slice(0, 5);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setShowSuggestions(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleCommandClick = (command) => {
    setSelectedCommand(command);
  };

  const closeModal = () => {
    setSelectedCommand(null);
  };

  const getDisplayName = (command) => {
    if (commandType === "slash") {
      return `/${command.name}`;
    }
    return `s!${command.name}`;
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

    .commands-page {
      max-width: 1400px;
      margin: 0 auto;
      background-color: #0a0a0a;
      color: #ffffff;
      min-height: calc(100vh - 200px);
    }

    /* Hero Section */
    .hero {
      text-align: center;
      margin-bottom: 100px;
      padding: 80px 20px 60px;
      background-color: #0a0a0a;
      border-bottom: 1px solid #1a1a1a;
    }

    .hero-title {
      font-size: 48px;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 40px;
      line-height: 1.2;
      letter-spacing: -0.02em;
      max-width: 900px;
      margin-left: auto;
      margin-right: auto;
      position: relative;
      display: inline-block;
    }

    .hero-title::after {
      content: '';
      position: absolute;
      bottom: -10px;
      left: 50%;
      transform: translateX(-50%);
      width: 100px;
      height: 4px;
      background-color: #aa00ff;
      border-radius: 2px;
    }

    /* Controls */
    .controls-container {
      display: flex;
      gap: 30px;
      justify-content: space-between;
      align-items: center;
      max-width: 1200px;
      margin: 0 auto;
      flex-wrap: wrap;
    }

    /* Toggle Switch */
    .toggle-container {
      display: flex;
      align-items: center;
      gap: 12px;
      background-color: #1a1a1a;
      padding: 8px 16px;
      border-radius: 40px;
      border: 1px solid #2a2a2a;
      order: 1;
      backdrop-filter: blur(10px);
    }

    .toggle-option {
      font-size: 16px;
      font-weight: 500;
      color: #b0b0b0;
      transition: color 0.2s ease;
    }

    .toggle-option.active {
      color: #aa00ff;
    }

    .switch {
      position: relative;
      display: inline-block;
      width: 50px;
      height: 24px;
    }

    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .slider {
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: #2D2D2D;
      transition: 0.3s;
      border-radius: 24px;
    }

    .slider:before {
      position: absolute;
      content: "";
      height: 18px;
      width: 18px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: 0.3s;
      border-radius: 50%;
    }

    input:checked + .slider {
      background-color: #aa00ff;
    }

    input:checked + .slider:before {
      transform: translateX(26px);
    }

    /* Search Bar */
    .search-container {
      flex: 1;
      max-width: 400px;
      position: relative;
      order: 2;
    }

    .search-input {
      width: 100%;
      padding: 14px 20px;
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      color: #ffffff;
      font-size: 16px;
      transition: all 0.2s ease;
    }

    .search-input:focus {
      outline: none;
      border-color: #aa00ff;
      box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
    }

    .search-input::placeholder {
      color: #666;
    }

    .search-input:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .search-suggestions {
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      margin-top: 8px;
      z-index: 10;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
      backdrop-filter: blur(10px);
    }

    .suggestion-item {
      padding: 12px 20px;
      color: #b0b0b0;
      cursor: pointer;
      transition: all 0.2s ease;
      font-size: 16px;
      border-left: 3px solid transparent;
    }

    .suggestion-item:hover {
      background-color: #2a2a2a;
      color: #ffffff;
      border-left-color: #aa00ff;
    }

    /* Dropdown */
    .dropdown-container {
      min-width: 200px;
      order: 3;
    }

    .category-dropdown {
      width: 100%;
      padding: 14px 20px;
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      color: #ffffff;
      font-size: 16px;
      cursor: pointer;
      appearance: none;
      background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23aa00ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
      background-repeat: no-repeat;
      background-position: right 16px center;
      background-size: 16px;
      transition: all 0.2s ease;
    }

    .category-dropdown:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .category-dropdown:focus {
      outline: none;
      border-color: #aa00ff;
      box-shadow: 0 0 0 3px rgba(170, 0, 255, 0.15);
    }

    .category-dropdown option {
      background-color: #1a1a1a;
      color: #ffffff;
    }

    /* Commands Section */
    .commands-section {
      padding: 0 20px 80px;
    }

    .commands-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 25px;
      max-width: 1200px;
      margin: 0 auto;
    }

    /* Command Cards */
    .command-card {
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 16px;
      padding: 25px 20px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
      min-height: 80px;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      backdrop-filter: blur(10px);
    }

    .command-card:hover {
      transform: translateY(-4px);
      border-color: #aa00ff;
      box-shadow: 0 8px 24px rgba(170, 0, 255, 0.2);
    }

    .command-card:hover::after {
      content: '';
      position: absolute;
      bottom: -10px;
      right: -10px;
      width: 100%;
      height: 100%;
      border: 2px solid #aa00ff;
      border-radius: 16px;
      opacity: 0.3;
      pointer-events: none;
    }

    .command-name {
      font-size: 18px;
      font-weight: 600;
      color: #ffffff;
      margin: 0;
      word-break: break-word;
      line-height: 1.4;
      position: relative;
      z-index: 2;
    }

    /* Modal */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(0, 0, 0, 0.8);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 1000;
      backdrop-filter: blur(5px);
    }

    .modal-content {
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 16px;
      max-width: 600px;
      width: 90%;
      max-height: 80vh;
      overflow-y: auto;
      position: relative;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
      backdrop-filter: blur(10px);
    }

    .modal-content::after {
      content: '';
      position: absolute;
      bottom: -10px;
      right: -10px;
      width: 100%;
      height: 100%;
      border: 2px solid #aa00ff;
      border-radius: 16px;
      z-index: -1;
      opacity: 0.3;
    }

    .modal-close {
      position: absolute;
      top: 15px;
      right: 15px;
      background: none;
      border: none;
      color: #b0b0b0;
      font-size: 28px;
      cursor: pointer;
      transition: color 0.2s ease;
      z-index: 10;
      width: 40px;
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
    }

    .modal-close:hover {
      color: #aa00ff;
      background-color: #2a2a2a;
    }

    .modal-body {
      padding: 40px;
    }

    .modal-command-name {
      font-size: 32px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 20px;
      padding-right: 30px;
      letter-spacing: -0.01em;
    }

    .modal-prefix-shortcut {
      background-color: #2a2a2a;
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 8px;
      border: 1px solid #3a3a3a;
    }

    .prefix-label {
      font-size: 12px;
      color: #b0b0b0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-weight: 500;
    }

    .prefix-value {
      font-size: 16px;
      color: #aa00ff;
      font-weight: 500;
    }

    .modal-description {
      font-size: 18px;
      line-height: 1.7;
      color: #b0b0b0;
      margin: 0;
    }

    /* Loading States */
    .loading-container {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 400px;
      background-color: #0a0a0a;
    }

    .loading-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 25px;
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 20px;
    }

    .loading-card {
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 16px;
      padding: 25px 20px;
      min-height: 80px;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
    }

    .loading-card::after {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(
        90deg,
        transparent,
        rgba(170, 0, 255, 0.1),
        transparent
      );
      animation: loading 1.5s infinite;
    }

    @keyframes loading {
      0% {
        transform: translateX(-100%);
      }
      100% {
        transform: translateX(100%);
      }
    }

    /* Responsive */
    @media (max-width: 968px) {
      .hero {
        margin-bottom: 0;
      }

      .controls-container {
        flex-direction: column;
        align-items: stretch;
        gap: 20px;
      }

      .toggle-container {
        justify-content: center;
        order: 1;
        padding: 6px 12px;
        gap: 8px;
        width: auto;
        max-width: 200px;
        margin: 0 auto;
      }

      .toggle-option {
        font-size: 14px;
      }

      .switch {
        width: 42px;
        height: 20px;
      }

      .slider:before {
        height: 14px;
        width: 14px;
        left: 3px;
        bottom: 3px;
      }

      input:checked + .slider:before {
        transform: translateX(22px);
      }

      .search-container {
        max-width: 100%;
        width: 100%;
        order: 2;
      }

      .search-input {
        padding: 12px 16px;
        font-size: 15px;
      }

      .dropdown-container {
        width: 100%;
        order: 3;
      }

      .commands-grid {
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      }
    }

    @media (max-width: 768px) {
      .hero {
        margin-bottom: 0;
        padding: 60px 20px 40px;
      }

      .hero-title {
        font-size: 36px;
      }

      .commands-section {
        padding: 0 20px 60px;
        margin-top: 20px;
      }

      .commands-grid {
        grid-template-columns: 1fr;
        gap: 20px;
      }

      .command-card {
        padding: 20px;
        min-height: 70px;
      }

      .command-name {
        font-size: 18px;
      }

      .modal-body {
        padding: 30px 20px;
      }

      .modal-command-name {
        font-size: 24px;
      }

      .modal-description {
        font-size: 16px;
      }
    }

    @media (max-width: 480px) {
      .hero {
        padding: 50px 16px 30px;
      }

      .hero-title {
        font-size: 28px;
        margin-bottom: 30px;
      }

      .controls-container {
        gap: 16px;
      }

      .toggle-container {
        max-width: 180px;
        padding: 5px 10px;
      }

      .toggle-option {
        font-size: 13px;
      }

      .switch {
        width: 38px;
        height: 18px;
      }

      .slider:before {
        height: 12px;
        width: 12px;
        left: 3px;
        bottom: 3px;
      }

      input:checked + .slider:before {
        transform: translateX(20px);
      }

      .search-input {
        padding: 10px 14px;
        font-size: 14px;
      }

      .commands-section {
        padding: 0 16px 50px;
        margin-top: 24px;
      }

      .command-card {
        padding: 15px;
        min-height: 60px;
      }

      .command-name {
        font-size: 16px;
      }

      .modal-content {
        width: 95%;
      }
    }

    @media (max-width: 360px) {
      .toggle-container {
        max-width: 160px;
        padding: 4px 8px;
      }

      .toggle-option {
        font-size: 12px;
      }

      .switch {
        width: 34px;
        height: 16px;
      }

      .slider:before {
        height: 10px;
        width: 10px;
        left: 3px;
        bottom: 3px;
      }

      input:checked + .slider:before {
        transform: translateX(18px);
      }

      .commands-section {
        margin-top: 28px;
      }
    }
  `;

  return (
    <>
      <NavBar />
      <div className="commands-page">
        {/* Hero Section */}
        <section className="hero">
          <h1 className="hero-title">
            Command List
          </h1>
          
          <div className="controls-container">
            {/* Toggle Switch */}
            <div className="toggle-container">
              <span className={`toggle-option ${commandType === 'slash' ? 'active' : ''}`}>Slash</span>
              <label className="switch">
                <input 
                  type="checkbox" 
                  checked={commandType === 'prefix'}
                  onChange={(e) => setCommandType(e.target.checked ? 'prefix' : 'slash')}
                />
                <span className="slider round"></span>
              </label>
              <span className={`toggle-option ${commandType === 'prefix' ? 'active' : ''}`}>Prefix</span>
            </div>

            {/* Search Bar */}
            <div className="search-container" ref={searchRef}>
              <input
                type="text"
                className="search-input"
                placeholder="Search commands..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setShowSuggestions(true);
                }}
                onFocus={() => setShowSuggestions(true)}
              />
              {showSuggestions && searchSuggestions.length > 0 && (
                <div className="search-suggestions">
                  {searchSuggestions.map((cmd, index) => (
                    <div 
                      key={index} 
                      className="suggestion-item"
                      onClick={() => {
                        setSearchQuery(cmd.name);
                        setShowSuggestions(false);
                      }}
                    >
                      {cmd.name}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Category Dropdown */}
            <div className="dropdown-container">
              <select 
                className="category-dropdown"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                <option value="All">All Categories</option>
                {categories.map((category, index) => (
                  <option key={index} value={category}>{category}</option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Commands Grid Section with Loading Animation */}
        <section className="commands-section">
          {loading ? (
            <div className="loading-grid">
              {[...Array(12)].map((_, index) => (
                <div key={index} className="loading-card">
                  <LoadingSpinner size="small" text="" />
                </div>
              ))}
            </div>
          ) : (
            <div className="commands-grid">
              {filteredCommands.map((command, index) => (
                <div 
                  key={index} 
                  className="command-card"
                  onClick={() => handleCommandClick(command)}
                >
                  <h3 className="command-name">{getDisplayName(command)}</h3>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Footer */}
      <Footer />

      {/* Command Detail Modal */}
      {selectedCommand && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={closeModal}>×</button>
            <div className="modal-body">
              <h2 className="modal-command-name">
                {commandType === "slash" ? `/${selectedCommand.name}` : `s!${selectedCommand.name}`}
              </h2>
              {commandType === "prefix" && selectedCommand.prefixShortcut && (
                <div className="modal-prefix-shortcut">
                  <span className="prefix-label">Prefix Shortcut:</span>
                  <span className="prefix-value">s!{selectedCommand.prefixShortcut}</span>
                </div>
              )}
              <p className="modal-description">{selectedCommand.description}</p>
            </div>
          </div>
        </div>
      )}

      <style>{styles}</style>
    </>
  );
};

// Create root and render
const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <CommandsPage />
  </React.StrictMode>
);

export default CommandsPage;