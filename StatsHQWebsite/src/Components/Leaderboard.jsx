import React, { useState, useEffect, useRef } from 'react';

const Leaderboard = ({
  data = [],
  title = "Leaderboard",
  valueLabel = "Value",
  valueFormatter = (value) => value.toLocaleString(),
  showProfilePictures = false,
  getProfilePicture = null,
  itemsPerPage = 20,
  className = "",
  backgroundColor = "#0a0a0a",
  cardBackground = "#1a1a1a",
  accentColor = "#5865F2",
  textColor = "#ffffff",
  secondaryTextColor = "#888888",
  borderColor = "#333333",
  nameKey = "name",
  valueKey = "value",
  idKey = "id",
  showPodium = true,
  customRenderItem = null,
  itemType = "generic",
  maxHeight = "500px",
  // Optional: pass a function (item) => ReactNode to override name rendering.
  // When omitted the component behaves exactly as before.
  renderName = null,
}) => {
  const [profilePictures, setProfilePictures] = useState({});
  const scrollContainerRef = useRef(null);
  const [displayedCount, setDisplayedCount] = useState(itemsPerPage);
  const loadedIdsRef = useRef(new Set());
  const loadingIdsRef = useRef(new Set());

  // Podium items - only top 3
  const podiumItemsRaw = showPodium ? data.slice(0, 3) : [];
  
  const getOrderedPodiumItems = () => {
    const count = podiumItemsRaw.length;
    if (count === 0) return [];
    if (count === 1) return [{ item: podiumItemsRaw[0], position: 'middle', rank: 1 }];
    if (count === 2) return [
      { item: podiumItemsRaw[1], position: 'left', rank: 2 },
      { item: podiumItemsRaw[0], position: 'middle', rank: 1 }
    ];
    if (count === 3) return [
      { item: podiumItemsRaw[1], position: 'left', rank: 2 },
      { item: podiumItemsRaw[0], position: 'middle', rank: 1 },
      { item: podiumItemsRaw[2], position: 'right', rank: 3 }
    ];
    return [];
  };

  const orderedPodiumItems = getOrderedPodiumItems();
  const scrollableItems = data.slice(showPodium ? 3 : 0);
  const displayedItems = scrollableItems.slice(0, displayedCount);
  const hasMoreItems = displayedCount < scrollableItems.length;
  const hasScrollableItems = scrollableItems.length > 0;

  // Load a single profile picture
  const loadProfilePicture = async (userId) => {
    if (!userId) return null;
    if (!showProfilePictures || itemType !== 'user' || !getProfilePicture) return null;
    
    const stringId = String(userId);
    
    if (loadedIdsRef.current.has(stringId)) return profilePictures[stringId];
    if (loadingIdsRef.current.has(stringId)) return null;
    
    loadingIdsRef.current.add(stringId);
    
    try {
      const avatarUrl = await getProfilePicture(stringId);
      if (avatarUrl) {
        setProfilePictures(prev => ({ ...prev, [stringId]: avatarUrl }));
        loadedIdsRef.current.add(stringId);
        return avatarUrl;
      }
    } catch (error) {
      console.error(`[Leaderboard] Failed to load profile picture for ${stringId}:`, error);
    } finally {
      loadingIdsRef.current.delete(stringId);
    }
    return null;
  };

  // Load profile pictures for podium items (top 3 only)
  useEffect(() => {
    if (!showProfilePictures || itemType !== 'user' || !getProfilePicture) {
      return;
    }
    
    const loadPodiumPictures = async () => {
      for (const podiumItem of orderedPodiumItems) {
        const item = podiumItem.item;
        const itemId = item[idKey];
        
        if (item.avatar) continue;
        if (!itemId) continue;
        if (loadedIdsRef.current.has(String(itemId))) continue;
        
        await loadProfilePicture(itemId);
      }
    };
    
    loadPodiumPictures();
  }, [orderedPodiumItems, showProfilePictures, idKey, itemType]);

  const loadMoreItems = () => {
    if (hasMoreItems) {
      const newCount = Math.min(displayedCount + itemsPerPage, scrollableItems.length);
      setDisplayedCount(newCount);
    }
  };

  const handleScroll = (e) => {
    if (!e.target || !hasMoreItems) return;
    const { scrollTop, scrollHeight, clientHeight } = e.target;
    if (scrollHeight - scrollTop - clientHeight < 100) {
      loadMoreItems();
    }
  };

  // Reset when data changes
  useEffect(() => {
    setDisplayedCount(itemsPerPage);
    setProfilePictures({});
    loadedIdsRef.current.clear();
    loadingIdsRef.current.clear();
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
  }, [data, itemsPerPage]);

  // ─── name helpers ────────────────────────────────────────────────────────────
  // renderName(item) is used when the caller supplies it (e.g. emoji dashboard).
  // Everything else falls back to the original logic so no other dashboard breaks.

  const getDisplayName = (item) => {
    if (customRenderItem) return customRenderItem(item, 'name');
    return item[nameKey] || 'Unknown';
  };

  // Returns a React node for the name cell.
  // If renderName prop is provided it takes priority; otherwise plain text.
  const renderNameNode = (item) => {
    if (renderName) return renderName(item);
    return getDisplayName(item);
  };

  const getDisplayValue = (item) => {
    if (customRenderItem) return customRenderItem(item, 'value');
    return item[valueKey] || 0;
  };
  // ─────────────────────────────────────────────────────────────────────────────

  const getPodiumIcon = (item) => {
    const itemId = item[idKey];
    const iconSize = '80px';
    const fontSize = '32px';
    
    if (itemType === 'user') {
      if (item.avatar) {
        return (
          <img
            src={item.avatar}
            alt={getDisplayName(item)}
            style={{ width: iconSize, height: iconSize, borderRadius: '50%', objectFit: 'cover' }}
            onError={(e) => {
              e.target.style.display = 'none';
              const parent = e.target.parentNode;
              if (parent) {
                const initialChar = (getDisplayName(item).charAt(0).toUpperCase() || '?');
                parent.innerHTML = `<div style="width:${iconSize};height:${iconSize};border-radius:50%;background-color:${accentColor};display:flex;align-items:center;justify-content:center;font-size:${fontSize};font-weight:bold;color:${textColor}">${initialChar}</div>`;
              }
            }}
          />
        );
      }
      
      if (showProfilePictures && itemId && profilePictures[itemId]) {
        return (
          <img
            src={profilePictures[itemId]}
            alt={getDisplayName(item)}
            style={{ width: iconSize, height: iconSize, borderRadius: '50%', objectFit: 'cover' }}
            onError={(e) => {
              e.target.style.display = 'none';
              const parent = e.target.parentNode;
              if (parent) {
                const initialChar = (getDisplayName(item).charAt(0).toUpperCase() || '?');
                parent.innerHTML = `<div style="width:${iconSize};height:${iconSize};border-radius:50%;background-color:${accentColor};display:flex;align-items:center;justify-content:center;font-size:${fontSize};font-weight:bold;color:${textColor}">${initialChar}</div>`;
              }
            }}
          />
        );
      }
    }

    const getDefaultIcon = () => {
      switch(itemType) {
        case 'user':     return '👤';
        case 'channel':  return '📺';
        case 'category': return '📁';
        case 'role':     return '🎭';
        default:         return '📊';
      }
    };

    return (
      <div style={{
        width: iconSize, height: iconSize, borderRadius: '50%', margin: '0 auto',
        backgroundColor: accentColor, display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: fontSize, fontWeight: 'bold', color: textColor
      }}>
        {getDefaultIcon()}
      </div>
    );
  };

  const getRankBadgeIcon = (rank) => {
    switch(rank) {
      case 1: return '🥇';
      case 2: return '🥈';
      case 3: return '🥉';
      default: return `#${rank}`;
    }
  };

  const getPodiumStyle = (position, rank) => {
    if (position === 'middle') {
      return {
        container: { transform: 'translateY(-30px)', zIndex: 3 },
        rank: { background: 'linear-gradient(135deg, #FFD700 0%, #FFA500 100%)', boxShadow: '0 0 30px rgba(255, 215, 0, 0.4)' },
        width: '280px',
        valueFontSize: '28px'
      };
    } else {
      return {
        container: { transform: 'translateY(-15px)', zIndex: 2 },
        rank: {
          background: rank === 2
            ? 'linear-gradient(135deg, #C0C0C0 0%, #A0A0A0 100%)'
            : 'linear-gradient(135deg, #CD7F32 0%, #AD5F12 100%)',
          boxShadow: rank === 2
            ? '0 0 20px rgba(192, 192, 192, 0.3)'
            : '0 0 20px rgba(205, 127, 50, 0.3)'
        },
        width: '240px',
        valueFontSize: '24px'
      };
    }
  };

  const getPodiumContainerStyle = () => {
    const count = orderedPodiumItems.length;
    if (count === 1) return { justifyContent: 'center' };
    if (count === 2) return { justifyContent: 'center', gap: '30px' };
    return { justifyContent: 'center', gap: '20px' };
  };

  const getPodiumContainerHeight = () => {
    const count = orderedPodiumItems.length;
    if (count === 1) return '300px';
    return '320px';
  };

  const needsScroll = scrollableItems.length > itemsPerPage;

  return (
    <div className={`leaderboard-container ${className}`} style={{
      backgroundColor, borderRadius: '16px', padding: '24px', color: textColor,
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      display: 'flex', flexDirection: 'column', height: '100%'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '24px', paddingBottom: '16px', borderBottom: `1px solid ${borderColor}`,
        flexShrink: 0
      }}>
        <h2 style={{
          margin: 0, fontSize: '28px', fontWeight: '600',
          background: `linear-gradient(135deg, ${textColor} 0%, ${accentColor} 100%)`,
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'
        }}>
          {title}
        </h2>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{
            backgroundColor: cardBackground, padding: '4px 12px',
            borderRadius: '20px', fontSize: '14px', color: secondaryTextColor
          }}>
            {data.length} total entries
          </span>
        </div>
      </div>

      {/* Podium Section */}
      {orderedPodiumItems.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'flex-end', marginBottom: '40px',
          minHeight: getPodiumContainerHeight(), flexWrap: 'wrap', flexShrink: 0,
          ...getPodiumContainerStyle(), position: 'relative', overflow: 'visible'
        }}>
          {orderedPodiumItems.map((podiumItem, idx) => {
            const style = getPodiumStyle(podiumItem.position, podiumItem.rank);
            const rank = podiumItem.rank;
            const item = podiumItem.item;
            
            return (
              <div key={`podium-${idx}`} style={{
                flex: '0 0 auto', width: style.width, ...style.container,
                position: 'relative', marginBottom: rank === 1 ? '0' : '15px'
              }}>
                <div style={{
                  backgroundColor: cardBackground, borderRadius: '16px', padding: '20px',
                  textAlign: 'center', boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
                  border: `1px solid ${borderColor}`, transition: 'transform 0.2s',
                  width: '100%', boxSizing: 'border-box'
                }}>
                  <div style={{
                    width: '60px', height: '60px', borderRadius: '50%', margin: '0 auto 15px',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '24px', fontWeight: 'bold', ...style.rank
                  }}>
                    {getRankBadgeIcon(rank)}
                  </div>
                  <div style={{ marginBottom: '12px' }}>
                    {getPodiumIcon(item)}
                  </div>

                  {/* ── Podium name: uses renderName when provided ── */}
                  <h3 style={{
                    margin: '0 0 8px 0', fontSize: '18px', fontWeight: '600', color: textColor,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    maxWidth: '100%',
                    // Only apply ellipsis truncation when renderName is NOT active
                    // (emoji images shouldn't be clipped by text-overflow)
                    ...(renderName ? { overflow: 'visible', whiteSpace: 'normal' } : {})
                  }} title={renderName ? undefined : getDisplayName(item)}>
                    {renderNameNode(item)}
                  </h3>

                  <div style={{
                    fontSize: style.valueFontSize, fontWeight: 'bold',
                    color: rank === 1 ? '#FFD700' : rank === 2 ? '#C0C0C0' : '#CD7F32',
                    marginBottom: '4px'
                  }}>
                    {valueFormatter(getDisplayValue(item))}
                  </div>
                  <div style={{
                    fontSize: '12px', color: secondaryTextColor,
                    textTransform: 'uppercase', letterSpacing: '1px'
                  }}>
                    {valueLabel}
                  </div>
                  <div style={{ marginTop: '10px', fontSize: '12px', color: secondaryTextColor }}>
                    #{rank}{rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th'} place
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Scrollable Table Section */}
      {hasScrollableItems ? (
        <div
          ref={scrollContainerRef}
          onScroll={needsScroll ? handleScroll : undefined}
          style={{
            flex: 1, overflowY: needsScroll ? 'auto' : 'visible',
            maxHeight: needsScroll ? maxHeight : 'none', borderRadius: '12px'
          }}
        >
          <div style={{
            backgroundColor: cardBackground, borderRadius: '12px',
            overflow: 'hidden', border: `1px solid ${borderColor}`
          }}>
            {/* Table header */}
            <div style={{
              display: 'grid', gridTemplateColumns: '80px 1fr 150px',
              padding: '16px 20px', borderBottom: `1px solid ${borderColor}`,
              fontWeight: '600', color: secondaryTextColor, fontSize: '14px',
              textTransform: 'uppercase', letterSpacing: '1px',
              position: 'sticky', top: 0, zIndex: 10, backgroundColor: cardBackground
            }}>
              <div>Rank</div>
              <div>Name</div>
              <div style={{ textAlign: 'right' }}>{valueLabel}</div>
            </div>

            {displayedItems.map((item, index) => {
              const globalRank = index + 4;
              
              return (
                <div
                  key={`scrollable-${index}`}
                  style={{
                    display: 'grid', gridTemplateColumns: '80px 1fr 150px',
                    padding: '12px 20px',
                    borderBottom: index < displayedItems.length - 1 ? `1px solid ${borderColor}` : 'none',
                    alignItems: 'center', transition: 'background-color 0.2s'
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.02)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: '600', color: secondaryTextColor }}>
                      #{globalRank}
                    </span>
                  </div>

                  {/* ── Row name: uses renderName when provided ── */}
                  <div style={{
                    display: 'flex', alignItems: 'center', minWidth: 0,
                    overflow: renderName ? 'visible' : 'hidden'
                  }}>
                    <span style={{
                      fontWeight: '500', color: textColor,
                      overflow: renderName ? 'visible' : 'hidden',
                      textOverflow: renderName ? 'unset' : 'ellipsis',
                      whiteSpace: renderName ? 'normal' : 'nowrap',
                      flex: 1
                    }} title={renderName ? undefined : getDisplayName(item)}>
                      {renderNameNode(item)}
                    </span>
                  </div>

                  <div style={{ textAlign: 'right', fontWeight: '600', color: accentColor }}>
                    {valueFormatter(getDisplayValue(item))}
                  </div>
                </div>
              );
            })}

            {hasMoreItems && (
              <div style={{
                textAlign: 'center', padding: '20px', color: secondaryTextColor,
                fontSize: '14px', borderTop: `1px solid ${borderColor}`
              }}>
                {needsScroll ? "Scroll to load more..." : (
                  <button
                    onClick={loadMoreItems}
                    style={{
                      background: 'none', border: `1px solid ${accentColor}`,
                      borderRadius: '8px', padding: '8px 16px', color: accentColor,
                      cursor: 'pointer', fontSize: '14px', fontWeight: '500'
                    }}
                  >
                    Load More ({displayedCount} / {scrollableItems.length})
                  </button>
                )}
              </div>
            )}

            {!hasMoreItems && scrollableItems.length > 0 && (
              <div style={{
                textAlign: 'center', padding: '20px', color: secondaryTextColor,
                fontSize: '14px', borderTop: `1px solid ${borderColor}`
              }}>
                ✓ You've reached the end ({scrollableItems.length} items)
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{
          textAlign: 'center', padding: '60px', color: secondaryTextColor,
          fontSize: '16px', backgroundColor: cardBackground,
          borderRadius: '12px', border: `1px solid ${borderColor}`
        }}>
          No data available
        </div>
      )}

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default Leaderboard;