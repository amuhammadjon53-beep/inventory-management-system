import React, { useMemo } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const TimezonePieChart = ({ 
  hourlyData = [], 
  timezone = 'UTC',
  activityType = 'Messages',
  guildName = 'Server Name',
  daysBack = null,
  valueFormatter = (value) => value.toLocaleString()
}) => {
  const [hoveredIndex, setHoveredIndex] = React.useState(null);

  // Timezone offsets mapping
  const timezoneOffsets = {
    "UTC": 0, "GMT": 0,
    "EST": -5, "PST": -8, "CST": -6, "MST": -7,
    "CET": 1, "EET": 2, "IST": 5.5, "JST": 9,
    "AEST": 10, "NZST": 12
  };

  // ACTIVITY COLORS
  const activityColors = {
    "Peak Activity": "#FFD700",
    "High Activity": "#FF6B6B",
    "Medium Activity": "#51CF66",
    "Low Activity": "#868E96"
  };

  // Apply timezone offset to hourly data
  const applyTimezoneOffset = (data, tz) => {
    const offset = timezoneOffsets[tz] || 0;
    const offsetHours = Math.floor(offset);
    const shiftedData = new Array(24).fill(0);
    
    for (let i = 0; i < 24; i++) {
      const newIndex = (i - offsetHours + 24) % 24;
      shiftedData[newIndex] = data[i] || 0;
    }
    
    return shiftedData;
  };

  // Categorize activity levels
  const categorizeActivityLevels = (data) => {
    const totalActivity = data.reduce((sum, val) => sum + val, 0);
    if (totalActivity === 0) {
      return data.map(() => ({ category: "Low Activity", value: 0 }));
    }

    const avgActivity = totalActivity / 24;
    const peakThreshold = avgActivity * 2.0;
    const highThreshold = avgActivity * 1.5;
    const mediumThreshold = avgActivity * 0.8;

    return data.map(value => {
      let category = "Low Activity";
      if (value >= peakThreshold) category = "Peak Activity";
      else if (value >= highThreshold) category = "High Activity";
      else if (value >= mediumThreshold) category = "Medium Activity";
      
      return { category, value };
    });
  };

  // Process data with timezone
  const processedData = useMemo(() => {
    const timezoneData = applyTimezoneOffset(hourlyData, timezone);
    return categorizeActivityLevels(timezoneData);
  }, [hourlyData, timezone]);

  // Prepare data for pie chart with EQUAL slices
  const pieData = useMemo(() => {
    return processedData.map((item, index) => {
      const hour24 = index;
      const displayHour = `${hour24.toString().padStart(2, '0')}:00`;
      
      return {
        name: displayHour,
        displayHour: displayHour,
        value: 1,
        actualValue: item.value,
        category: item.category,
        hour: hour24
      };
    });
  }, [processedData]);

  // Calculate statistics
  const statistics = useMemo(() => {
    const total = processedData.reduce((sum, item) => sum + item.value, 0);
    const peakHours = processedData.filter(item => item.category === "Peak Activity").length;
    const highHours = processedData.filter(item => item.category === "High Activity").length;
    const mediumHours = processedData.filter(item => item.category === "Medium Activity").length;
    const lowHours = processedData.filter(item => item.category === "Low Activity").length;
    
    return {
      total,
      peakHours,
      highHours,
      mediumHours,
      lowHours
    };
  }, [processedData]);

  // Custom tooltip - DARK THEME, NO WHITE RECTANGLE
  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      
      return (
        <div style={{
          backgroundColor: '#1a1a1a',
          padding: '10px 15px',
          border: `2px solid ${activityColors[data.category]}`,
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          color: '#fff',
          minWidth: '120px',
          textAlign: 'center'
        }}>
          <p style={{ margin: '0 0 5px 0', fontWeight: 'bold', fontSize: '14px', color: activityColors[data.category] }}>
            {data.name}
          </p>
          <p style={{ margin: '0', fontSize: '12px', color: '#ccc' }}>
            {data.category}
          </p>
          <p style={{ margin: '5px 0 0 0', fontSize: '16px', fontWeight: 'bold', color: '#fff' }}>
            {valueFormatter(data.actualValue)}
          </p>
        </div>
      );
    }
    return null;
  };

  // Format the time period text
  const timePeriodText = daysBack === null ? 'ALL TIME' : `Last ${daysBack} days`;

  return (
    <div style={{ 
      background: 'linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 100%)',
      borderRadius: '24px', 
      padding: '20px',
      color: 'white',
      minHeight: '500px',
      width: '100%',
      boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
      border: '1px solid rgba(255,255,255,0.05)'
    }}>
      {/* TOP BAR */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '20px',
        padding: '0 10px',
        flexWrap: 'wrap',
        gap: '10px'
      }}>
        <div style={{ 
          fontSize: '16px', 
          fontWeight: '600',
          color: '#fff',
          background: 'rgba(255,255,255,0.1)',
          padding: '6px 12px',
          borderRadius: '30px',
          border: '1px solid rgba(255,255,255,0.2)'
        }}>
          {timezone}
        </div>
        <div style={{ 
          fontSize: '14px', 
          color: '#888',
          background: 'rgba(255,255,255,0.05)',
          padding: '6px 12px',
          borderRadius: '30px',
          border: '1px solid rgba(255,255,255,0.1)'
        }}>
          {new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
        </div>
      </div>

      {/* Main chart area - RESPONSIVE LAYOUT */}
      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'center' }}>
        {/* Pie chart - responsive width */}
        <div style={{ width: '100%', maxWidth: '500px', minWidth: '280px', height: 'auto', position: 'relative' }}>
          <div style={{ position: 'relative', width: '100%', paddingBottom: '100%' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={0}
                    outerRadius="80%"
                    paddingAngle={1}
                    dataKey="value"
                    startAngle={90}
                    endAngle={-270}
                    labelLine={false}
                    label={false}
                    onMouseEnter={(_, index) => setHoveredIndex(index)}
                    onMouseLeave={() => setHoveredIndex(null)}
                  >
                    {pieData.map((entry, index) => (
                      <Cell 
                        key={`cell-${index}`} 
                        fill={activityColors[entry.category]}
                        stroke="#0a0a0a"
                        strokeWidth={hoveredIndex === index ? 3 : 2}
                        style={{
                          filter: hoveredIndex === index ? 'brightness(1.2)' : 'none',
                          transition: 'all 0.1s ease',
                          cursor: 'pointer',
                          opacity: hoveredIndex !== null && hoveredIndex !== index ? 0.8 : 1
                        }}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          {/* Small dot in the middle */}
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: 'white',
            boxShadow: '0 0 10px white',
            zIndex: 30,
            pointerEvents: 'none'
          }} />
        </div>

        {/* Statistics panel - responsive */}
        <div style={{ 
          flex: 1, 
          minWidth: '200px',
          padding: '20px',
          background: 'rgba(10,10,10,0.7)',
          borderRadius: '20px',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255,255,255,0.1)',
          boxShadow: '0 10px 30px rgba(0,0,0,0.2)'
        }}>
          <h3 style={{ 
            margin: '0 0 20px 0', 
            color: '#fff',
            fontSize: '18px',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '1px',
            borderBottom: '2px solid #AA00FF',
            paddingBottom: '8px',
            display: 'inline-block'
          }}>
            Activity Summary
          </h3>
          
          <div style={{ 
            marginBottom: '20px',
            textAlign: 'center',
            background: 'rgba(255,255,255,0.05)',
            padding: '15px',
            borderRadius: '12px',
            border: '1px solid rgba(255,255,255,0.1)'
          }}>
            <div style={{ fontSize: '12px', color: '#aaa', marginBottom: '5px' }}>
              TOTAL {activityType.toUpperCase()} • {timePeriodText}
            </div>
            <div style={{ fontSize: '36px', fontWeight: 'bold', color: '#fff' }}>
              {valueFormatter(statistics.total)}
            </div>
          </div>

          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '1fr 1fr', 
            gap: '15px'
          }}>
            <div style={{ 
              padding: '12px',
              background: 'rgba(255,215,0,0.1)',
              borderRadius: '10px',
              borderLeft: '3px solid #FFD700'
            }}>
              <div style={{ fontSize: '11px', color: '#aaa', marginBottom: '3px' }}>PEAK</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#FFD700' }}>{statistics.peakHours}</div>
              <div style={{ fontSize: '10px', color: '#666' }}>hours</div>
            </div>

            <div style={{ 
              padding: '12px',
              background: 'rgba(255,107,107,0.1)',
              borderRadius: '10px',
              borderLeft: '3px solid #FF6B6B'
            }}>
              <div style={{ fontSize: '11px', color: '#aaa', marginBottom: '3px' }}>HIGH</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#FF6B6B' }}>{statistics.highHours}</div>
              <div style={{ fontSize: '10px', color: '#666' }}>hours</div>
            </div>

            <div style={{ 
              padding: '12px',
              background: 'rgba(81,207,102,0.1)',
              borderRadius: '10px',
              borderLeft: '3px solid #51CF66'
            }}>
              <div style={{ fontSize: '11px', color: '#aaa', marginBottom: '3px' }}>MEDIUM</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#51CF66' }}>{statistics.mediumHours}</div>
              <div style={{ fontSize: '10px', color: '#666' }}>hours</div>
            </div>

            <div style={{ 
              padding: '12px',
              background: 'rgba(134,142,150,0.1)',
              borderRadius: '10px',
              borderLeft: '3px solid #868E96'
            }}>
              <div style={{ fontSize: '11px', color: '#aaa', marginBottom: '3px' }}>LOW</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#868E96' }}>{statistics.lowHours}</div>
              <div style={{ fontSize: '10px', color: '#666' }}>hours</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TimezonePieChart;