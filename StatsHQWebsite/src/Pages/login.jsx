import React, { useState, useEffect, useRef } from 'react';

const Login = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Get the current hostname for API URL (now pointing to FastAPI on port 8000)
  const getApiUrl = () => {
    return window.location.origin;
  };

  const API_URL = getApiUrl();

  useEffect(() => {
    checkAuthStatus();
    
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const checkAuthStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/api/auth/status`, {
        credentials: 'include',
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      
      if (!response.ok) {
        throw new Error('Auth check failed');
      }
      
      const data = await response.json();
      
      
      if (data.authenticated) {
       
        
        setUser(data.user);
        localStorage.setItem('user', JSON.stringify(data.user));
      } else {
        setUser(null);
        localStorage.removeItem('user');
      }
    } catch (error) {
      console.error('Error checking auth status:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = (e) => {
    e.preventDefault();
    
    // CORRECTED: Use the proper OAuth2 user authorization link
    // This link ONLY has the scopes needed for user login (no bot scopes)
    const clientId = '1481328229909270568';
    const redirectUri = encodeURIComponent('https://statshq.xyz/api/auth/discord/callback');
    const currentOrigin = encodeURIComponent(window.location.origin);
    
    const discordAuthUrl = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&scope=identify%20guilds%20guilds.members.read&state=${currentOrigin}`;
    
    window.location.href = discordAuthUrl;
  };

  const handleLogout = async (e) => {
    e.preventDefault();
    try {
      await fetch(`${API_URL}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
    } catch (error) {
      console.error('Logout error:', error);
    }
    localStorage.removeItem('user');
    window.location.href = '/';
  };

  const handleManageServers = (e) => {
    e.preventDefault();
    window.location.href = '/Manage Servers';
  };

  const toggleDropdown = () => {
    setDropdownOpen(!dropdownOpen);
  };

  const getDisplayName = () => {
    if (!user) return '';
    // Try different possible name fields
    return user.global_name || user.username || 'User';
  };

  const getAvatarUrl = () => {
    if (!user) return '';
    
    // Check if user has avatar and id
    if (user.avatar && user.id) {
      return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=32`;
    }
    
    // Fallback to default avatar
    return 'https://cdn.discordapp.com/embed/avatars/0.png';
  };

  if (loading) {
    return (
      <a href="#" className="login-button" style={{ opacity: 0.7, pointerEvents: 'none' }}>
        Loading...
      </a>
    );
  }

  if (user) {
    return (
      <div className="user-menu-container" ref={dropdownRef}>
        <div className="user-info" onClick={toggleDropdown}>
          <img 
            src={getAvatarUrl()}
            alt={getDisplayName()}
            className="user-avatar"
            onError={(e) => {
              e.target.src = 'https://cdn.discordapp.com/embed/avatars/0.png';
            }}
          />
          <span className="display-name">{getDisplayName()}</span>
          <span className="dropdown-arrow">{dropdownOpen ? '▲' : '▼'}</span>
        </div>

        {dropdownOpen && (
          <div className="dropdown-menu">
            <a href="/Manage Servers" className="dropdown-item" onClick={handleManageServers}>
              Manage Servers
            </a>
            <button className="dropdown-item logout-item" onClick={handleLogout}>
              Log Out
            </button>
          </div>
        )}

        <style jsx>{`
          .user-menu-container {
            display: inline-block;
            position: relative;
          }

          .user-info {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(170, 0, 255, 0.1);
            padding: 6px 12px 6px 6px;
            border-radius: 30px;
            border: 1px solid rgba(170, 0, 255, 0.3);
            backdrop-filter: blur(5px);
            cursor: pointer;
            transition: all 0.2s ease;
          }

          .user-info:hover {
            background: rgba(170, 0, 255, 0.15);
            border-color: rgba(170, 0, 255, 0.5);
          }

          .user-avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            border: 2px solid #aa00ff;
            transition: transform 0.2s ease;
            object-fit: cover;
          }

          .user-info:hover .user-avatar {
            transform: scale(1.05);
          }

          .display-name {
            color: white;
            font-size: 14px;
            font-weight: 500;
            max-width: 120px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }

          .dropdown-arrow {
            color: #aa00ff;
            font-size: 12px;
            margin-left: 4px;
            transition: transform 0.2s ease;
          }

          .dropdown-menu {
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 8px;
            background: #1a1b1e;
            border: 1px solid #2c2f3a;
            border-radius: 8px;
            min-width: 180px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            z-index: 1000;
            overflow: hidden;
            animation: dropdownFade 0.2s ease;
          }

          @keyframes dropdownFade {
            from {
              opacity: 0;
              transform: translateY(-10px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }

          .dropdown-item {
            display: block;
            padding: 12px 16px;
            color: white;
            text-decoration: none;
            font-size: 14px;
            transition: all 0.2s ease;
            border: none;
            background: none;
            width: 100%;
            text-align: left;
            cursor: pointer;
            font-family: inherit;
          }

          .dropdown-item:hover {
            background: rgba(170, 0, 255, 0.1);
            padding-left: 20px;
          }

          .logout-item {
            color: #ff6b6b;
            border-top: 1px solid #2c2f3a;
          }

          .logout-item:hover {
            background: rgba(255, 107, 107, 0.1);
            color: #ff8a8a;
          }

          @media (max-width: 768px) {
            .user-info {
              padding: 4px 8px 4px 4px;
            }

            .display-name {
              display: none;
            }

            .dropdown-arrow {
              display: none;
            }

            .user-avatar {
              width: 28px;
              height: 28px;
            }

            .dropdown-menu {
              right: auto;
              left: -80px;
              min-width: 160px;
            }

            @media (max-width: 480px) {
              .dropdown-menu {
                left: -60px;
              }
            }

            @media (max-width: 360px) {
              .dropdown-menu {
                left: -40px;
              }
            }
          }

          @media (max-width: 480px) {
            .dropdown-menu {
              min-width: 150px;
            }
            
            .dropdown-item {
              padding: 10px 14px;
              font-size: 13px;
            }
          }
        `}</style>
      </div>
    );
  }

  return (
    <>
      <a href="#" onClick={handleLogin} className="login-button">
        Log In
      </a>

      <style jsx>{`
        .login-button {
          background-color: #aa00ff;
          color: white;
          text-decoration: none;
          padding: 12px 28px;
          border-radius: 8px;
          font-weight: 600;
          font-size: 16px;
          border: 3px solid #0a0b12;
          cursor: pointer;
          display: inline-block;
          transition: all 0.2s ease;
          font-family: inherit;
        }

        .login-button:hover {
          background-color: #9900e6;
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(170, 0, 255, 0.3);
        }

        .login-button:active {
          transform: translateY(0);
          box-shadow: 0 2px 6px rgba(170, 0, 255, 0.3);
        }

        @media (max-width: 768px) {
          .login-button {
            padding: 8px 16px;
            font-size: 14px;
            border-width: 2px;
          }
        }

        @media (max-width: 480px) {
          .login-button {
            padding: 6px 12px;
            font-size: 13px;
          }
        }
      `}</style>
    </>
  );
};

export default Login;