import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import NavBar from "../Components/NavBar.jsx";
import Footer from "../Components/Footer.jsx";

// PRIVILEGED USERS - can use ID lookup
const PRIVILEGED_USERS = ['1428927519515611141', '591655972414685229'];

const ServersPage = () => {
  const [servers, setServers] = useState([]);
  const [filteredServers, setFilteredServers] = useState([]);
  const [selectedServer, setSelectedServer] = useState(null);
  const [savedServer, setSavedServer] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingStage, setLoadingStage] = useState("Checking authentication...");
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [hasChanges, setHasChanges] = useState(false);
  const [showAlert, setShowAlert] = useState(false);
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const [showActionBar, setShowActionBar] = useState(false);
  const [showLoginOverlay, setShowLoginOverlay] = useState(false);
  
  // Privileged ID lookup state
  const [isPrivileged, setIsPrivileged] = useState(false);
  const [showIdLookup, setShowIdLookup] = useState(false);
  const [serverIdInput, setServerIdInput] = useState("");
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState(null);
  const [lookedUpServer, setLookedUpServer] = useState(null);

  // Get the current hostname for API URL
  const getApiUrl = () => {
    return window.location.origin;
  };

  const API_URL = getApiUrl();

  // Check if current user is privileged
  const checkPrivilegedStatus = (userId) => {
    return PRIVILEGED_USERS.includes(userId);
  };

  // Fetch user data and servers on component mount
  useEffect(() => {
    checkAuthAndFetchServers();
  }, []);

  // Auto-hide success message after 3 seconds
  useEffect(() => {
    if (showSuccessMessage) {
      const timer = setTimeout(() => {
        setShowSuccessMessage(false);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [showSuccessMessage]);

  const checkAuthAndFetchServers = async () => {
    try {
      setLoadingStage("Checking authentication...");
      setLoadingProgress(10);
      
      const authResponse = await fetch(`${API_URL}/api/auth/status`, {
        credentials: 'include',
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      
      setLoadingProgress(20);
      
      if (!authResponse.ok) {
        if (authResponse.status === 401) {
          setShowLoginOverlay(true);
          setLoading(false);
          return;
        }
        throw new Error(`Auth check failed: ${authResponse.status}`);
      }
      
      const authData = await authResponse.json();
   
      
      if (authData.authenticated) {
        setUser(authData.user);
        
        // Check if user is privileged
        const privileged = checkPrivilegedStatus(authData.user.id);
        setIsPrivileged(privileged);
     
        
        setLoadingStage("Fetching saved server preference...");
        setLoadingProgress(30);
        
        await fetchSavedServer();
        await fetchUserServers();
      } else {
        setShowLoginOverlay(true);
        setLoading(false);
      }
    } catch (error) {
      console.error('Error checking auth:', error);
      if (error.message.includes('401')) {
        setShowLoginOverlay(true);
      } else {
        setError(error.message);
      }
      setLoading(false);
    }
  };

  const fetchSavedServer = async () => {
    try {
      const savedServerResponse = await fetch(`${API_URL}/api/user/saved-server`, {
        credentials: 'include',
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      
      if (savedServerResponse.ok) {
        const savedData = await savedServerResponse.json();
     
        setSavedServer(savedData.selected_server);
      }
    } catch (error) {
      console.error('Error fetching saved server:', error);
    }
  };

  const fetchUserServers = async () => {
    setLoading(true);
    setError(null);
    
    try {
      setLoadingStage("Fetching your Discord servers...");
      setLoadingProgress(40);
      
      const startTime = Date.now();
      
      const response = await fetch(`${API_URL}/api/user/servers`, {
        credentials: 'include',
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      
      const elapsedTime = (Date.now() - startTime) / 1000;
   
      
      setLoadingProgress(80);
      setLoadingStage("Processing server data...");
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Error response:', errorText);
        throw new Error(`Failed to fetch servers: ${response.status}`);
      }
      
      const data = await response.json();
   
      
      setLoadingProgress(90);
      setLoadingStage("Almost done...");
      
      const processedServers = data.map(server => ({
        ...server,
        formattedMembers: formatNumber(server.member_count || 0),
        iconUrl: server.icon 
          ? `https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png?size=128`
          : 'https://cdn.discordapp.com/embed/avatars/0.png'
      }));
      
      setServers(processedServers);
      setFilteredServers(processedServers);
      
      if (savedServer) {
        const saved = processedServers.find(s => s.id === savedServer);
        if (saved) {
          setSelectedServer(saved);
        } else if (processedServers.length > 0) {
          setSelectedServer(processedServers[0]);
        }
      } else if (processedServers.length > 0) {
        setSelectedServer(processedServers[0]);
      }
      
      setLoadingProgress(100);
      
      setTimeout(() => {
        setLoading(false);
      }, 500);
      
    } catch (error) {
      console.error('Error fetching servers:', error);
      setError(error.message);
      setLoading(false);
    }
  };

  // Privileged: Look up a server by ID
  const handleLookupServer = async () => {
    if (!serverIdInput.trim()) {
      setLookupError("Please enter a server ID");
      return;
    }
    
    setLookupLoading(true);
    setLookupError(null);
    setLookedUpServer(null);
    
    try {
      const response = await fetch(`${API_URL}/api/admin/lookup-server/${serverIdInput.trim()}`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      const result = await response.json();
      
      if (result.success && result.found) {
        const lookedUp = result.server;
        
        // Format the looked up server to match our server format
        const formattedServer = {
          ...lookedUp,
          formattedMembers: formatNumber(lookedUp.member_count || 0),
          iconUrl: lookedUp.icon_url || 'https://cdn.discordapp.com/embed/avatars/0.png',
          has_bot: true
        };
        
        setLookedUpServer(formattedServer);
        
        // Check if this server is already in the user's list
        const alreadyInList = servers.some(s => s.id === formattedServer.id);
        if (alreadyInList) {
          setLookupError("This server is already in your list above");
        }
      } else {
        setLookupError(result.message || "Server not found or bot is not in this server");
      }
    } catch (error) {
      console.error('Error looking up server:', error);
      setLookupError("Failed to lookup server. Please try again.");
    } finally {
      setLookupLoading(false);
    }
  };
  
  // Privileged: Add looked up server to the list and set as active
  const handleAddLookedUpServer = async () => {
    if (!lookedUpServer) return;
    
    // Check if already exists
    if (servers.some(s => s.id === lookedUpServer.id)) {
      setLookupError("This server is already in your list");
      setLookedUpServer(null);
      setServerIdInput("");
      return;
    }
    
    setLookupLoading(true);
    
    try {
      // Call the endpoint to add server to user's list AND set as active
      const response = await fetch(`${API_URL}/api/admin/add-server-to-user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({ guild_id: lookedUpServer.id })
      });
      
      const result = await response.json();
      
      if (result.success) {
        // Format the server to match our server format
        const formattedServer = {
          id: lookedUpServer.id,
          name: lookedUpServer.name,
          icon: lookedUpServer.icon,
          member_count: lookedUpServer.member_count,
          formattedMembers: formatNumber(lookedUpServer.member_count || 0),
          iconUrl: lookedUpServer.icon_url || 'https://cdn.discordapp.com/embed/avatars/0.png',
          has_bot: true
        };
        
        // Add to servers list
        setServers(prev => [formattedServer, ...prev]);
        setFilteredServers(prev => [formattedServer, ...prev]);
        
        // Set as selected server
        setSelectedServer(formattedServer);
        setSavedServer(formattedServer.id);
        setHasChanges(false);
        
        // Show success message
        setSuccessMessage(`Added and set as active dashboard: ${lookedUpServer.name}`);
        setShowSuccessMessage(true);
        
        // Clear lookup
        setLookedUpServer(null);
        setServerIdInput("");
        setShowIdLookup(false);
      } else {
        setLookupError(result.message || "Failed to add server");
      }
    } catch (error) {
      console.error('Error adding server:', error);
      setLookupError("Failed to add server. Please try again.");
    } finally {
      setLookupLoading(false);
    }
  };

  const formatNumber = (num) => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  };

  const handleServerSelect = (server) => {
    setSelectedServer(server);
    setHasChanges(server.id !== savedServer);
    setShowActionBar(true);
  };

  const handleSearch = (e) => {
    const query = e.target.value.toLowerCase();
    setSearchQuery(query);
    
    const filtered = servers.filter(server => 
      server.name.toLowerCase().includes(query)
    );
    setFilteredServers(filtered);
  };

  const handleSave = async () => {
    if (!selectedServer) return;
    
    setActionLoading(true);
    
    try {
      const response = await fetch(`${API_URL}/api/user/save-server`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({ guild_id: selectedServer.id })
      });
      
      
      if (response.ok) {
        const result = await response.json();
        
        setSavedServer(selectedServer.id);
        setHasChanges(false);
        setShowAlert(false);
        
        setSuccessMessage(`Dashboard server set to: ${selectedServer.name}`);
        setShowSuccessMessage(true);
        setShowActionBar(true);
      } else {
        const error = await response.json();
        console.error('Save error:', error);
        setSuccessMessage(error.detail || 'Failed to save server preference');
        setShowSuccessMessage(true);
      }
    } catch (error) {
      console.error('Error saving server:', error);
      setSuccessMessage('Failed to save server preference');
      setShowSuccessMessage(true);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = () => {
    if (savedServer) {
      const original = servers.find(s => s.id === savedServer);
      setSelectedServer(original);
    } else {
      setSelectedServer(null);
    }
    setHasChanges(false);
    setShowAlert(false);
    setShowActionBar(false);
  };

  const handleLogin = () => {
    window.location.href = `${API_URL}/api/auth/discord?returnTo=${encodeURIComponent(window.location.href)}`;
  };

  const [actionLoading, setActionLoading] = useState(false);

  // If login overlay is shown - FIXED VERSION
  if (showLoginOverlay) {
    return (
      <>
        <NavBar />
        <div className="servers-page">
          <div className="login-overlay">
            <div className="login-modal">
              <div className="login-icon">🔒</div>
              <h2>Authentication Required</h2>
              <p>Please log in to access the server management dashboard</p>
              <button 
                className="login-button"
                onClick={handleLogin}
              >
                Log In with Discord
              </button>
            </div>
          </div>
        </div>
        <Footer />
        <style jsx>{`
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }

          body {
            margin: 0;
            padding: 0;
            background-color: #0a0a0a;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
          }

          .servers-page {
            min-height: calc(100vh - 200px);
            width: 100%;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 100%);
            color: #ffffff;
            position: relative;
            overflow: hidden;
          }
          
          .servers-page::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" opacity="0.05"><path d="M20 20 L80 20 L80 80 L20 80 Z" fill="none" stroke="%23aa00ff" stroke-width="2"/><circle cx="50" cy="50" r="15" fill="none" stroke="%23aa00ff" stroke-width="2"/></svg>') repeat;
            background-size: 100px 100px;
            animation: backgroundMove 20s linear infinite;
            pointer-events: none;
          }
          
          @keyframes backgroundMove {
            0% { background-position: 0 0; }
            100% { background-position: 100px 100px; }
          }
          
          .login-overlay {
            position: relative;
            min-height: calc(100vh - 200px);
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            z-index: 10;
          }
          
          .login-modal {
            background: rgba(10, 10, 10, 0.95);
            backdrop-filter: blur(20px);
            border: 2px solid #aa00ff;
            border-radius: 40px;
            padding: 60px 40px;
            max-width: 500px;
            width: 100%;
            text-align: center;
            box-shadow: 0 30px 60px rgba(170, 0, 255, 0.3);
            animation: modalAppear 0.5s ease;
            position: relative;
            z-index: 10;
          }
          
          @keyframes modalAppear {
            from {
              opacity: 0;
              transform: translateY(30px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
          
          .login-icon {
            font-size: 80px;
            margin-bottom: 30px;
            animation: pulse 2s infinite;
          }
          
          @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
          }
          
          .login-modal h2 {
            font-size: 36px;
            font-weight: 800;
            margin-bottom: 20px;
            background: linear-gradient(135deg, #ffffff, #aa00ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
          }
          
          .login-modal p {
            color: #b0b0b0;
            font-size: 18px;
            margin-bottom: 40px;
            line-height: 1.6;
          }
          
          .login-button {
            background: #aa00ff;
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 50px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
            min-height: 36px;
            max-height: 36px;
            line-height: 1;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background-image: linear-gradient(135deg, #aa00ff, #ff00aa);
            background-size: 100% 100%;
            background-repeat: no-repeat;
          }
          
          .login-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(170, 0, 255, 0.4);
            background-image: linear-gradient(135deg, #bb00ff, #ff00bb);
          }
          
          .login-button:active {
            transform: translateY(0);
            box-shadow: 0 2px 8px rgba(170, 0, 255, 0.3);
          }
          
          @media (max-width: 768px) {
            .login-modal {
              padding: 40px 20px;
            }
            
            .login-icon {
              font-size: 60px;
            }
            
            .login-modal h2 {
              font-size: 28px;
            }
            
            .login-modal p {
              font-size: 16px;
            }
            
            .login-button {
              padding: 8px 20px;
              font-size: 13px;
              min-height: 32px;
              max-height: 32px;
            }
          }
        `}</style>
      </>
    );
  }

  if (loading) {
    return (
      <>
        <NavBar />
        <div className="servers-page">
          <div className="loading-container">
            <div className="loading-spinner"></div>
            <div className="loading-progress">
              <div 
                className="loading-progress-bar" 
                style={{ width: `${loadingProgress}%` }}
              ></div>
            </div>
            <p className="loading-text">{loadingStage}</p>
            <p className="loading-subtext">
              {loadingProgress < 40 ? "This should be quick..." :
               loadingProgress < 80 ? "Checking bot presence in your servers..." :
               "Processing server data..."}
            </p>
            {loadingProgress >= 80 && loadingProgress < 100 && (
              <p className="loading-warning">
                This is taking longer than expected. Large servers may take more time.
              </p>
            )}
          </div>
        </div>
        <style jsx>{`
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }

          body {
            margin: 0;
            padding: 0;
            background-color: #0a0a0a;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
          }

          .servers-page {
            min-height: calc(100vh - 200px);
            width: 100%;
            background-color: #0a0a0a;
            position: relative;
          }
          
          .loading-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: calc(100vh - 200px);
            width: 100%;
            gap: 20px;
            padding: 20px;
            background-color: #0a0a0a;
          }
          
          .loading-spinner {
            width: 60px;
            height: 60px;
            border: 4px solid #232323;
            border-top-color: #aa00ff;
            border-right-color: #aa00ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
          }
          
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
          
          .loading-progress {
            width: 300px;
            height: 6px;
            background-color: #232323;
            border-radius: 3px;
            overflow: hidden;
            margin: 10px 0;
          }
          
          .loading-progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #aa00ff, #ff00aa);
            transition: width 0.3s ease;
            border-radius: 3px;
          }
          
          .loading-text {
            color: #ffffff;
            font-size: 18px;
            font-weight: 500;
            margin: 10px 0 5px;
          }
          
          .loading-subtext {
            color: #b0b0b0;
            font-size: 14px;
          }
          
          .loading-warning {
            color: #ffaa00;
            font-size: 14px;
            margin-top: 20px;
            padding: 10px 20px;
            background: rgba(255, 170, 0, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(255, 170, 0, 0.3);
            max-width: 400px;
            text-align: center;
          }
        `}</style>
      </>
    );
  }

  if (error) {
    return (
      <>
        <NavBar />
        <div className="servers-page">
          <div className="error-container">
            <div className="error-icon">⚠️</div>
            <h2>Error Loading Servers</h2>
            <p>{error}</p>
            <div className="error-details">
              <p>This could be because:</p>
              <ul>
                <li>The bot is not in any of your servers</li>
                <li>Discord API is taking too long to respond</li>
                <li>Your session might have expired</li>
              </ul>
            </div>
            <button className="retry-button" onClick={() => window.location.reload()}>
              Try Again
            </button>
          </div>
        </div>
        <style jsx>{`
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }

          body {
            margin: 0;
            padding: 0;
            background-color: #0a0a0a;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
          }

          .servers-page {
            min-height: calc(100vh - 200px);
            width: 100%;
            background-color: #0a0a0a;
            position: relative;
          }
          
          .error-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: calc(100vh - 200px);
            width: 100%;
            text-align: center;
            padding: 40px 20px;
            background-color: #0a0a0a;
          }
          
          .error-icon {
            font-size: 64px;
            margin-bottom: 20px;
          }
          
          .error-container h2 {
            color: #ff6b6b;
            font-size: 28px;
            margin-bottom: 16px;
          }
          
          .error-container p {
            color: #b0b0b0;
            font-size: 16px;
            margin-bottom: 20px;
            max-width: 500px;
          }
          
          .error-details {
            background: #1a1a1a;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #232323;
            margin: 20px 0;
            max-width: 400px;
            text-align: left;
          }
          
          .error-details p {
            color: #ffaa00;
            margin-bottom: 10px;
            font-weight: 500;
          }
          
          .error-details ul {
            color: #b0b0b0;
            padding-left: 20px;
          }
          
          .error-details li {
            margin: 8px 0;
          }
          
          .retry-button {
            background-color: #aa00ff;
            color: white;
            border: none;
            padding: 14px 32px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 2px solid #aa00ff;
          }
          
          .retry-button:hover {
            background-color: transparent;
            color: #aa00ff;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
          }
        `}</style>
      </>
    );
  }

  return (
    <>
      <NavBar />
      <div className="servers-page">
        {/* Success Message Toast */}
        {showSuccessMessage && (
          <div className="success-toast">
            {successMessage}
          </div>
        )}

        {/* Hero Section */}
        <section className="hero">
          <h1 className="hero-title">
            Select a Server
          </h1>
          <p className="hero-subtitle">
            Choose which server you want to set as your active dashboard
          </p>
          
          {/* Stats Summary */}
          <div className="stats-summary">
            <div className="stat-item">
              <span className="stat-value">{servers.length}</span>
              <span className="stat-label">Available Servers</span>
            </div>
            {isPrivileged && (
              <div className="stat-item privileged-badge">
                <span className="stat-value">👑</span>
                <span className="stat-label">Privileged Access</span>
              </div>
            )}
          </div>
          
          {/* Search Bar */}
          <div className="search-container">
            <input
              type="text"
              className="search-input"
              placeholder="Search servers..."
              value={searchQuery}
              onChange={handleSearch}
            />
          </div>
          
          {/* Privileged: ID Lookup Toggle Button */}
          {isPrivileged && (
            <div className="lookup-toggle">
              <button 
                className="lookup-toggle-button"
                onClick={() => setShowIdLookup(!showIdLookup)}
              >
                {showIdLookup ? '🔒 Hide Server Lookup' : '🔑 Server ID Lookup (Privileged)'}
              </button>
            </div>
          )}
          
          {/* Privileged: ID Lookup Panel */}
          {isPrivileged && showIdLookup && (
            <div className="lookup-panel">
              <h3>Lookup Server by ID</h3>
              <p>Enter a Discord server ID to add it to your server list (bot must be in the server)</p>
              <div className="lookup-input-group">
                <input
                  type="text"
                  className="lookup-input"
                  placeholder="Enter server ID (e.g., 123456789012345678)"
                  value={serverIdInput}
                  onChange={(e) => setServerIdInput(e.target.value)}
                />
                <button 
                  className="lookup-button"
                  onClick={handleLookupServer}
                  disabled={lookupLoading}
                >
                  {lookupLoading ? 'Looking up...' : 'Lookup'}
                </button>
              </div>
              
              {lookupError && (
                <div className="lookup-error">
                  ❌ {lookupError}
                </div>
              )}
              
              {lookedUpServer && (
                <div className="lookup-result">
                  <div className="lookup-result-header">
                    <span>✅ Server Found!</span>
                    <button 
                      className="add-server-button"
                      onClick={handleAddLookedUpServer}
                      disabled={lookupLoading}
                    >
                      {lookupLoading ? 'Adding...' : 'Add to List & Set as Active'}
                    </button>
                  </div>
                  <div className="lookup-result-server">
                    <img 
                      src={lookedUpServer.iconUrl} 
                      alt={lookedUpServer.name}
                      className="lookup-server-icon"
                      onError={(e) => {
                        e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png';
                      }}
                    />
                    <div className="lookup-server-info">
                      <div className="lookup-server-name">{lookedUpServer.name}</div>
                      <div className="lookup-server-details">
                        ID: {lookedUpServer.id} • {lookedUpServer.formattedMembers} members
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Servers Grid Section */}
        <section className="servers-section">
          {filteredServers.length === 0 ? (
            <div className="no-results">
              <div className="no-results-icon">🔍</div>
              <p>No servers found matching "{searchQuery}"</p>
              {servers.length === 0 && (
                <>
                  <p className="no-servers-help">
                    Make sure the bot is in at least one of your Discord servers.
                  </p>
                  <button 
                    className="refresh-button"
                    onClick={fetchUserServers}
                  >
                    Refresh Servers
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="servers-grid">
              {filteredServers.map((server) => (
                <div
                  key={server.id}
                  className={`server-card ${selectedServer?.id === server.id ? 'selected' : ''}`}
                  onClick={() => handleServerSelect(server)}
                >
                  <div className="server-members">
                    {server.formattedMembers} members
                  </div>
                  <div className="server-icon-container">
                    <img
                      src={server.iconUrl}
                      alt={server.name}
                      className="server-icon"
                      loading="lazy"
                      onError={(e) => {
                        e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png';
                      }}
                    />
                    {savedServer === server.id && (
                      <div className="saved-badge">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M20 6L9 17L4 12" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </div>
                    )}
                  </div>
                  <div className="server-name">
                    {server.name}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Action Bar */}
        {selectedServer && showActionBar && (
          <div className="action-bar">
            <div className="action-bar-content">
              <div className="selected-info">
                <span className="selected-label">Selected:</span>
                <img
                  src={selectedServer.iconUrl}
                  alt={selectedServer.name}
                  className="selected-icon"
                  onError={(e) => {
                    e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png';
                  }}
                />
                <span className="selected-name">{selectedServer.name}</span>
                {savedServer === selectedServer.id && (
                  <span className="current-badge">Current</span>
                )}
              </div>
              <div className="action-buttons">
                <button
                  className="cancel-button"
                  onClick={handleCancel}
                  disabled={!hasChanges}
                >
                  Cancel
                </button>
                <button
                  className="save-button"
                  onClick={handleSave}
                  disabled={!hasChanges || selectedServer.id === savedServer || actionLoading}
                >
                  {actionLoading ? 'Saving...' : 'Apply Changes'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Unsaved Changes Alert */}
        {showAlert && hasChanges && (
          <div className="alert-overlay">
            <div className="alert-modal">
              <h3>Unsaved Changes</h3>
              <p>You have unsaved changes. Do you want to save them before leaving?</p>
              <div className="alert-buttons">
                <button className="alert-save" onClick={handleSave}>Save Changes</button>
                <button className="alert-discard" onClick={() => {
                  handleCancel();
                  setShowAlert(false);
                }}>Discard</button>
                <button className="alert-cancel" onClick={() => setShowAlert(false)}>Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <Footer />

      <style jsx>{`
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }

        body {
          margin: 0;
          padding: 0;
          background-color: #0a0a0a;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }

        .servers-page {
          min-height: calc(100vh - 200px);
          width: 100%;
          background-color: #0a0a0a;
          color: #ffffff;
          padding-bottom: 100px;
          position: relative;
        }

        .success-toast {
          position: fixed;
          top: 80px;
          left: 50%;
          transform: translateX(-50%);
          background: linear-gradient(135deg, #00c851, #007e33);
          color: white;
          padding: 12px 24px;
          border-radius: 40px;
          font-size: 14px;
          font-weight: 500;
          z-index: 1000;
          box-shadow: 0 4px 15px rgba(0, 200, 81, 0.3);
          animation: slideDown 0.3s ease;
          border: 1px solid rgba(255, 255, 255, 0.2);
          backdrop-filter: blur(10px);
        }

        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translate(-50%, -20px);
          }
          to {
            opacity: 1;
            transform: translate(-50%, 0);
          }
        }

        .hero {
          text-align: center;
          margin-bottom: 40px;
          padding: 60px 20px 30px;
          background: linear-gradient(180deg, #0a0a0a 0%, #050505 100%);
          border-bottom: 1px solid #232323;
        }

        .hero-title {
          font-size: 48px;
          font-weight: 800;
          color: #ffffff;
          margin-bottom: 16px;
          line-height: 1.2;
          letter-spacing: -0.02em;
          background: linear-gradient(135deg, #ffffff 0%, #aa00ff 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .hero-subtitle {
          font-size: 18px;
          color: #b0b0b0;
          margin-bottom: 30px;
        }

        .stats-summary {
          display: flex;
          justify-content: center;
          gap: 20px;
          margin-bottom: 30px;
          flex-wrap: wrap;
        }

        .stat-item {
          display: flex;
          align-items: baseline;
          gap: 8px;
          background: rgba(170, 0, 255, 0.1);
          padding: 12px 24px;
          border-radius: 40px;
          border: 1px solid rgba(170, 0, 255, 0.3);
        }

        .privileged-badge {
          background: linear-gradient(135deg, rgba(255, 215, 0, 0.2), rgba(255, 215, 0, 0.1));
          border-color: #ffd700;
        }

        .privileged-badge .stat-value {
          color: #ffd700;
        }

        .stat-value {
          font-size: 24px;
          font-weight: 700;
          color: #aa00ff;
        }

        .stat-label {
          font-size: 16px;
          color: #b0b0b0;
        }

        .search-container {
          max-width: 500px;
          margin: 0 auto;
        }

        .search-input {
          width: 100%;
          padding: 16px 24px;
          background-color: #050505;
          border: 2px solid #232323;
          border-radius: 40px;
          color: #ffffff;
          font-size: 16px;
          transition: all 0.2s ease;
        }

        .search-input:focus {
          outline: none;
          border-color: #aa00ff;
          box-shadow: 0 0 0 4px rgba(170, 0, 255, 0.1);
        }

        .search-input::placeholder {
          color: #666;
        }

        .lookup-toggle {
          margin-top: 20px;
        }

        .lookup-toggle-button {
          background: transparent;
          border: 2px solid #aa00ff;
          color: #aa00ff;
          padding: 10px 24px;
          border-radius: 40px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .lookup-toggle-button:hover {
          background: rgba(170, 0, 255, 0.1);
          transform: translateY(-2px);
        }

        .lookup-panel {
          max-width: 600px;
          margin: 20px auto 0;
          background: rgba(10, 10, 10, 0.95);
          border: 2px solid #ffd700;
          border-radius: 20px;
          padding: 20px;
          text-align: left;
        }

        .lookup-panel h3 {
          color: #ffd700;
          font-size: 18px;
          margin-bottom: 8px;
        }

        .lookup-panel p {
          color: #b0b0b0;
          font-size: 13px;
          margin-bottom: 15px;
        }

        .lookup-input-group {
          display: flex;
          gap: 12px;
        }

        .lookup-input {
          flex: 1;
          padding: 12px 16px;
          background-color: #050505;
          border: 2px solid #232323;
          border-radius: 12px;
          color: #ffffff;
          font-size: 14px;
          font-family: monospace;
        }

        .lookup-input:focus {
          outline: none;
          border-color: #ffd700;
        }

        .lookup-button {
          background: linear-gradient(135deg, #ffd700, #ffaa00);
          color: #1a1a1a;
          border: none;
          padding: 12px 24px;
          border-radius: 12px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .lookup-button:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 4px 15px rgba(255, 215, 0, 0.3);
        }

        .lookup-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .lookup-error {
          margin-top: 15px;
          padding: 12px;
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid #ff4444;
          border-radius: 10px;
          color: #ff8888;
          font-size: 13px;
        }

        .lookup-result {
          margin-top: 20px;
          padding: 15px;
          background: rgba(255, 215, 0, 0.1);
          border: 1px solid #ffd700;
          border-radius: 12px;
        }

        .lookup-result-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .lookup-result-header span {
          color: #ffd700;
          font-weight: 600;
        }

        .add-server-button {
          background: linear-gradient(135deg, #00c851, #007e33);
          color: white;
          border: none;
          padding: 6px 16px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .add-server-button:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 2px 10px rgba(0, 200, 81, 0.3);
        }

        .add-server-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .lookup-result-server {
          display: flex;
          align-items: center;
          gap: 15px;
        }

        .lookup-server-icon {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          border: 2px solid #ffd700;
        }

        .lookup-server-info {
          flex: 1;
        }

        .lookup-server-name {
          font-size: 16px;
          font-weight: 600;
          color: #ffffff;
          margin-bottom: 4px;
        }

        .lookup-server-details {
          font-size: 12px;
          color: #b0b0b0;
        }

        .servers-section {
          padding: 0 20px 40px;
          max-width: 1400px;
          margin: 0 auto;
          min-height: 50vh;
        }

        .servers-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 24px;
          margin: 0 auto;
        }

        .server-card {
          background-color: #0a0a0a;
          border: 2px solid #232323;
          border-radius: 20px;
          padding: 30px 20px 20px;
          cursor: pointer;
          transition: all 0.2s ease;
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 15px;
          min-height: 240px;
          width: 100%;
        }

        .server-card:hover {
          transform: translateY(-4px);
          border-color: #aa00ff;
          box-shadow: 0 20px 30px rgba(170, 0, 255, 0.2);
        }

        .server-card.selected {
          border-color: #aa00ff;
          background: linear-gradient(145deg, #0a0a0a, #150022);
          box-shadow: 0 0 30px rgba(170, 0, 255, 0.3);
        }

        .server-members {
          position: absolute;
          top: 16px;
          right: 16px;
          font-size: 14px;
          color: #b0b0b0;
          background-color: rgba(0, 0, 0, 0.8);
          padding: 6px 12px;
          border-radius: 30px;
          border: 1px solid #333;
          backdrop-filter: blur(5px);
          font-weight: 500;
        }

        .server-icon-container {
          position: relative;
          width: 100px;
          height: 100px;
          margin: 10px 0;
        }

        .server-icon {
          width: 100%;
          height: 100%;
          border-radius: 50%;
          border: 3px solid #aa00ff;
          transition: transform 0.3s ease;
          object-fit: cover;
        }

        .server-card:hover .server-icon {
          transform: scale(1.1) rotate(5deg);
        }

        .saved-badge {
          position: absolute;
          bottom: 0;
          right: 0;
          width: 32px;
          height: 32px;
          background-color: #aa00ff;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          border: 3px solid #000000;
          box-shadow: 0 4px 10px rgba(170, 0, 255, 0.5);
        }

        .saved-badge svg {
          width: 18px;
          height: 18px;
        }

        .server-name {
          font-size: 18px;
          font-weight: 600;
          color: #ffffff;
          text-align: center;
          word-break: break-word;
          max-width: 100%;
          padding: 0 10px;
          line-height: 1.4;
        }

        .no-results {
          text-align: center;
          padding: 80px 20px;
          color: #b0b0b0;
          font-size: 18px;
          background: #0a0a0a;
          border-radius: 30px;
          border: 2px dashed #232323;
          margin: 40px 0;
          min-height: 300px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        }

        .no-results-icon {
          font-size: 64px;
          margin-bottom: 20px;
          opacity: 0.5;
        }

        .no-servers-help {
          margin-top: 20px;
          color: #aa00ff;
          font-size: 16px;
        }

        .refresh-button {
          margin-top: 30px;
          background-color: transparent;
          color: #aa00ff;
          border: 2px solid #aa00ff;
          padding: 12px 30px;
          border-radius: 40px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .refresh-button:hover {
          background-color: #aa00ff;
          color: white;
          transform: translateY(-2px);
          box-shadow: 0 4px 15px rgba(170, 0, 255, 0.4);
        }

        .action-bar {
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          background-color: rgba(10, 10, 10, 0.95);
          border-top: 2px solid #232323;
          padding: 20px;
          z-index: 100;
          backdrop-filter: blur(20px);
          animation: slideUp 0.3s ease;
        }

        @keyframes slideUp {
          from {
            transform: translateY(100%);
          }
          to {
            transform: translateY(0);
          }
        }

        .action-bar-content {
          max-width: 1200px;
          margin: 0 auto;
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 20px;
        }

        .selected-info {
          display: flex;
          align-items: center;
          gap: 15px;
          flex-wrap: wrap;
        }

        .selected-label {
          color: #b0b0b0;
          font-size: 14px;
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .selected-icon {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          border: 2px solid #aa00ff;
          object-fit: cover;
        }

        .selected-name {
          font-size: 18px;
          font-weight: 600;
          color: #ffffff;
        }

        .current-badge {
          background: linear-gradient(135deg, #aa00ff, #ff00aa);
          color: white;
          padding: 6px 12px;
          border-radius: 30px;
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .action-buttons {
          display: flex;
          gap: 12px;
        }

        .cancel-button,
        .save-button {
          padding: 14px 28px;
          border-radius: 40px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          border: none;
        }

        .cancel-button {
          background-color: transparent;
          color: #b0b0b0;
          border: 2px solid #232323;
        }

        .cancel-button:hover:not(:disabled) {
          border-color: #ff6b6b;
          color: #ff6b6b;
          transform: translateY(-2px);
        }

        .save-button {
          background: linear-gradient(135deg, #aa00ff, #ff00aa);
          color: white;
          border: 2px solid transparent;
        }

        .save-button:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 10px 20px rgba(170, 0, 255, 0.4);
        }

        .cancel-button:disabled,
        .save-button:disabled {
          opacity: 0.3;
          cursor: not-allowed;
          transform: none;
        }

        .alert-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: rgba(0, 0, 0, 0.9);
          display: flex;
          justify-content: center;
          align-items: center;
          z-index: 1000;
          backdrop-filter: blur(10px);
        }

        .alert-modal {
          background: linear-gradient(145deg, #0a0a0a, #150022);
          border: 2px solid #aa00ff;
          border-radius: 30px;
          padding: 40px;
          max-width: 450px;
          width: 90%;
          box-shadow: 0 30px 60px rgba(170, 0, 255, 0.3);
        }

        .alert-modal h3 {
          font-size: 24px;
          font-weight: 700;
          color: #ffffff;
          margin-bottom: 15px;
          background: linear-gradient(135deg, #ffffff, #aa00ff);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .alert-modal p {
          color: #b0b0b0;
          font-size: 16px;
          margin-bottom: 30px;
          line-height: 1.6;
        }

        .alert-buttons {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
        }

        .alert-save,
        .alert-discard,
        .alert-cancel {
          padding: 12px 20px;
          border-radius: 30px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          border: none;
        }

        .alert-save {
          background: linear-gradient(135deg, #aa00ff, #ff00aa);
          color: white;
        }

        .alert-save:hover {
          transform: translateY(-2px);
          box-shadow: 0 5px 15px rgba(170, 0, 255, 0.4);
        }

        .alert-discard {
          background-color: #ff6b6b;
          color: white;
        }

        .alert-discard:hover {
          background-color: #ff5252;
          transform: translateY(-2px);
        }

        .alert-cancel {
          background-color: transparent;
          color: #b0b0b0;
          border: 2px solid #232323;
        }

        .alert-cancel:hover {
          border-color: #ffffff;
          color: #ffffff;
        }

        @media (max-width: 768px) {
          .hero-title {
            font-size: 36px;
          }

          .hero-subtitle {
            font-size: 16px;
          }

          .servers-grid {
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 16px;
          }

          .server-card {
            padding: 25px 15px 15px;
            min-height: 220px;
          }

          .server-icon-container {
            width: 80px;
            height: 80px;
          }

          .action-bar-content {
            flex-direction: column;
            align-items: stretch;
          }

          .selected-info {
            justify-content: center;
          }

          .action-buttons {
            justify-content: center;
          }

          .cancel-button,
          .save-button {
            padding: 12px 24px;
            font-size: 14px;
          }

          .success-toast {
            width: 90%;
            text-align: center;
            font-size: 13px;
            padding: 10px 16px;
          }

          .lookup-panel {
            margin: 20px;
          }

          .lookup-input-group {
            flex-direction: column;
          }
        }

        @media (max-width: 480px) {
          .hero-title {
            font-size: 28px;
          }

          .hero {
            padding: 40px 15px 20px;
          }

          .servers-grid {
            grid-template-columns: 1fr;
          }

          .server-card {
            min-height: 200px;
          }

          .server-members {
            font-size: 12px;
            padding: 4px 8px;
          }

          .server-name {
            font-size: 16px;
          }

          .action-buttons {
            flex-direction: column;
          }

          .cancel-button,
          .save-button {
            width: 100%;
          }

          .alert-modal {
            padding: 30px 20px;
          }

          .alert-buttons {
            flex-direction: column;
          }

          .alert-save,
          .alert-discard,
          .alert-cancel {
            width: 100%;
          }

          .success-toast {
            top: 70px;
            font-size: 12px;
            padding: 8px 14px;
          }

          .stats-summary {
            flex-direction: column;
            align-items: center;
          }
        }
      `}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <ServersPage />
  </React.StrictMode>
);

export default ServersPage;