import React from "react";
import { createRoot } from "react-dom/client";
import { useEffect, useRef, useState } from "react";
import NavBar from "../Components/NavBar.jsx";
import Footer from "../Components/Footer.jsx";

// Loading Spinner Component (same as Commands and Docs)
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

const HomePage = () => {
  const [loading, setLoading] = useState(true);
  const featuresRef = useRef(null);

  const scrollToFeatures = () => {
    featuresRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Simulate loading like in Commands and Docs
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(false);
    }, 800);
    
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      {
        threshold: 0.1,
        rootMargin: "0px 0px -50px 0px",
      }
    );

    const featureSections = document.querySelectorAll(".feature-section");
    featureSections.forEach((section) => observer.observe(section));

    return () => {
      featureSections.forEach((section) => observer.unobserve(section));
    };
  }, [loading]);

  const features = [
    {
      title: "Messages and Voice Activity",
      description: "Understand how your community communicates. Track messages and voice activity across users, channels, categories, roles, and your entire server. Identify your most active members. Discover which channels drive engagement. Monitor activity trends over time, filtered however you need.",
      image: "/user stats.png",
      alt: "User statistics visualization"
    },
    {
      title: "Leaderboards",
      description: "Turn activity into friendly competition that drives engagement. Leaderboards rank users, channels, categories, and roles using real server data. They help communities recognize active members and encourage participation.",
      image: "/role leaderboard.png",
      alt: "Role leaderboard display"
    },
    {
      title: "Invite Tracking",
      description: "Track all server invites, including valid, suspicious, and left invites. See who invited specific users. Generate leaderboards showcasing your top inviters or invite codes.",
      image: "/invite stats.png",
      alt: "Invite statistics dashboard"
    },
    {
      title: "Growth Monitoring",
      description: "Monitor community growth with detailed member and role analytics. Track joins, leaves, net growth, and role expansion over time. Use growth projections to estimate future server size and spot long-term trends before they become obvious.",
      image: "/growth.png",
      alt: "Server growth monitoring chart"
    },
    {
      title: "Status Activity Tracking",
      description: "Track application activity shown on users' Discord profiles, including games, streaming apps, music, movies, and more. Stats records total sessions per activity, total time spent, and daily-updating activity streaks to reveal each user's most-used applications over any time period. Get a clear view of habits and favoured activities across your server.",
      image: "/activity user.png",
      alt: "User activity tracking display"
    },
    {
      title: "Emoji Statistics",
      description: "View leaderboards for the most popular emojis across your server, channels, or categories. See each user's most-used emojis. Track the top emoji users with dedicated leaderboards.",
      image: "/emoji user stats.png",
      alt: "Emoji usage statistics"
    },
    {
      title: "Hourly Stat Distribution",
      description: "Discover when your community is most active. Hourly activity distributions reveal peak engagement hours. Use them to schedule events, announcements, giveaways, and content when they're most likely to be seen.",
      image: "/distribution.png",
      alt: "Hourly activity distribution chart"
    },
    {
      title: "Charts",
      description: "Access a wide range of charts that track messages, voice activity, and invites across your server. Clear, easy-to-read line charts make it simple to follow trends over time. Instantly spot which days, weeks, or months drive the most activity.",
      image: "/chart.png",
      alt: "Statistical chart example"
    },
    {
      title: "Ship",
      description: "The most accurate ship system on Discord. Stats calculates compatibility based on real engagement data: shared VC time, mentions, common channels, activity overlap, and recent activity. Get ship percentages that actually mean something.",
      image: "/ship.png",
      alt: "Ship compatibility meter"
    }
  ];

  return (
    <>
      <NavBar />
      <div className="homepage">
        {/* Hero Section */}
        <section className="hero">
          <h1 className="hero-title">
            The Best Discord Analytics Bot
          </h1>
          <p className="hero-description">
            Stats is the ultimate Discord analytics bot. It tracks the most important statistics in your server then transforms that data into leaderboards, charts, averages, and heatmaps all filterable by user, channel, category, and role giving you the most in-depth data out of any Discord bot.
          </p>
          
          {/* Button Container */}
          <div className="button-container">
            <a 
              href="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863601&integration_type=0&scope=bot+applications.commands" 
              className="btn btn-primary"
              target="_blank"
              rel="noopener noreferrer"
            >
              Add to Discord Server
            </a>
            <button onClick={scrollToFeatures} className="btn btn-secondary">
              See Features
            </button>
          </div>
        </section>

        {/* Social Proof Bar */}
        <div className="social-proof-bar">
          <div className="social-proof-inner">
            <span className="social-proof-live">
              <span className="live-dot" />
              <span className="live-dot-ring" />
            </span>
            <span className="social-proof-text">Tracking Statistics For More Than 100,000 Users</span>
          </div>
        </div>

        {/* Features Anchor */}
        <div ref={featuresRef} className="features-anchor" />

        {/* Show loading spinner or feature sections */}
        {loading ? (
          <div className="loading-container">
            <LoadingSpinner size="large" text="Loading..." />
          </div>
        ) : (
          <>
            {/* Feature Sections - Alternating Layout with Dark Gray Variants */}
            {features.map((feature, index) => (
              <section 
                key={index} 
                className={`feature-section ${index % 2 === 0 ? 'bg-base' : 'bg-darker'}`}
              >
                <div className={`feature-content ${index % 2 === 0 ? 'image-left' : 'image-right'}`}>
                  <div className="image-container">
                    <img src={feature.image} alt={feature.alt} />
                  </div>
                  <div className="text-container">
                    <h2 className="feature-title">{feature.title}</h2>
                    <p className="feature-description">{feature.description}</p>
                    <div className="feature-button-wrapper">
                      <a 
                        href="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863601&integration_type=0&scope=bot+applications.commands" 
                        className="btn btn-primary btn-small"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Add to Discord Server
                      </a>
                    </div>
                  </div>
                </div>
              </section>
            ))}

            {/* Call to Action Section - Using Darker Variant */}
            <section className="feature-section bg-darker cta-feature-section">
              <div className="feature-content cta-content">
                <div className="cta-text-container">
                  <h2 className="cta-title">Take your server to the next level with Stats</h2>
                  <div className="cta-button-wrapper">
                    <a 
                      href="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863601&integration_type=0&scope=bot+applications.commands" 
                      className="btn btn-primary btn-large"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Add to Discord Server
                    </a>
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        {/* Footer */}
        <Footer />

        <style jsx>{`
          @font-face {
            font-family: 'Horndon';
            src: url('/HorndonD.ttf') format('truetype');
            font-display: swap;
            font-weight: normal;
            font-style: normal;
          }

          /* Global Styles */
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
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
            margin: 0;
            padding: 0;
            background-color: #0a0a0a;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            color: #ffffff;
            overflow-y: auto;
          }

          #app {
            min-height: 100vh;
            background-color: #0a0a0a;
          }

          .homepage {
            max-width: 100%;
            margin: 0 auto;
            background-color: #0a0a0a;
            color: #ffffff;
          }

          /* Hero Section */
          .hero {
            text-align: center;
            margin-bottom: 0;
            padding: 80px 20px 60px;
            background: #0a0a0a;
            border-bottom: 1px solid #1a1a1a;
          }

          .hero-title {
            font-size: 48px;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 24px;
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
            bottom: -12px;
            left: 50%;
            transform: translateX(-50%);
            width: 100px;
            height: 4px;
            background-color: #aa00ff;
            border-radius: 2px;
          }

          .hero-description {
            font-size: 20px;
            line-height: 1.6;
            color: #b0b0b0;
            max-width: 800px;
            margin: 40px auto 40px;
          }

          /* Button Container */
          .button-container {
            display: flex;
            gap: 20px;
            justify-content: center;
            align-items: center;
            margin-top: 20px;
          }

          /* Social Proof Bar */
          .social-proof-bar {
            background-color: #0f0f0f;
            border-bottom: 1px solid #222222;
            border-top: 1px solid #222222;
            padding: 20px 20px;
            text-align: center;
          }

          .social-proof-inner {
            display: inline-flex;
            align-items: center;
            gap: 12px;
          }

          .social-proof-live {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            flex-shrink: 0;
          }

          .live-dot {
            position: absolute;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #aa00ff;
            z-index: 1;
          }

          .live-dot-ring {
            position: absolute;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background-color: #aa00ff;
            opacity: 0.4;
            animation: ping 1.5s ease-out infinite;
          }

          @keyframes ping {
            0% { transform: scale(0.5); opacity: 0.5; }
            100% { transform: scale(1.8); opacity: 0; }
          }

          .social-proof-text {
            font-size: 15px;
            font-weight: 600;
            letter-spacing: 0.04em;
            color: #cccccc;
          }

          .btn {
            padding: 16px 32px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            display: inline-block;
            border: 2px solid transparent;
            outline: none;
          }

          .btn:focus {
            outline: none;
          }

          .btn-primary {
            background-color: #aa00ff;
            color: white;
            box-shadow: 0 8px 16px rgba(170, 0, 255, 0.2);
          }

          .btn-primary:hover {
            background-color: #8800cc;
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(170, 0, 255, 0.3);
          }

          .btn-primary:active {
            transform: translateY(-2px);
          }

          .btn-secondary {
            background-color: #1a1a1a;
            color: white;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
            border: 1px solid #2a2a2a;
          }

          .btn-secondary:hover {
            background-color: #2a2a2a;
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.3);
            border-color: #aa00ff;
          }

          .btn-secondary:active {
            transform: translateY(-2px);
          }

          .btn-small {
            padding: 12px 24px;
            font-size: 16px;
            margin-top: 24px;
          }

          .btn-large {
            padding: 20px 40px;
            font-size: 20px;
          }

          /* Features Anchor */
          .features-anchor {
            scroll-margin-top: 40px;
          }

          /* Loading Container */
          .loading-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 400px;
            background-color: #0a0a0a;
            margin-bottom: 40px;
          }

          /* Feature Sections */
          .feature-section {
            padding: 80px 0;
            opacity: 0;
            transform: translateY(40px);
            transition: opacity 0.8s ease, transform 0.8s ease;
            border-bottom: 1px solid #1a1a1a;
            width: 100%;
          }

          .feature-section.visible {
            opacity: 1;
            transform: translateY(0);
          }

          .bg-base {
            background-color: #0a0a0a;
          }

          .bg-darker {
            background-color: #050505;
          }

          .feature-content {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 60px;
            padding: 0 20px;
          }

          .image-left .image-container {
            order: 1;
          }

          .image-left .text-container {
            order: 2;
          }

          .image-right .image-container {
            order: 2;
          }

          .image-right .text-container {
            order: 1;
          }

          .image-container {
            flex: 1;
            position: relative;
            transition: transform 0.3s ease;
          }

          .image-container:hover {
            transform: translateY(-4px);
          }

          .image-container::after {
            content: '';
            position: absolute;
            bottom: -10px;
            right: -10px;
            width: 100%;
            height: 100%;
            border: 2px solid #aa00ff;
            border-radius: 12px;
            z-index: -1;
            opacity: 0.3;
            transition: opacity 0.3s ease;
          }

          .image-container:hover::after {
            opacity: 0.5;
          }

          .image-container img {
            width: 100%;
            height: auto;
            border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
            border: 1px solid #2a2a2a;
            position: relative;
            z-index: 1;
            transition: border-color 0.3s ease;
          }

          .image-container:hover img {
            border-color: #aa00ff;
          }

          .text-container {
            flex: 1;
          }

          .feature-title {
            font-size: 36px;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 24px;
            letter-spacing: -0.01em;
            position: relative;
            display: inline-block;
          }

          .feature-title::after {
            content: '';
            position: absolute;
            bottom: -8px;
            left: 0;
            width: 60px;
            height: 3px;
            background-color: #aa00ff;
            border-radius: 2px;
            transition: width 0.3s ease;
          }

          .feature-title:hover::after {
            width: 100%;
          }

          .feature-description {
            font-size: 18px;
            line-height: 1.7;
            color: #b0b0b0;
          }

          .feature-button-wrapper {
            display: flex;
            justify-content: flex-start;
          }

          /* CTA Feature Section */
          .cta-feature-section {
            border-bottom: none;
          }

          .cta-content {
            justify-content: center;
            text-align: center;
          }

          .cta-text-container {
            flex: 1;
            max-width: 800px;
            margin: 0 auto;
          }

          .cta-title {
            font-size: 48px;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 40px;
            line-height: 1.2;
            letter-spacing: -0.02em;
            position: relative;
            display: inline-block;
          }

          .cta-title::after {
            content: '';
            position: absolute;
            bottom: -12px;
            left: 50%;
            transform: translateX(-50%);
            width: 80px;
            height: 4px;
            background-color: #aa00ff;
            border-radius: 2px;
            transition: width 0.3s ease;
          }

          .cta-title:hover::after {
            width: 120px;
          }

          .cta-button-wrapper {
            display: flex;
            justify-content: center;
            margin-top: 20px;
          }

          /* Responsive Design */
          @media (max-width: 968px) {
            .feature-content {
              flex-direction: column;
              gap: 40px;
            }

            .image-left .image-container,
            .image-left .text-container,
            .image-right .image-container,
            .image-right .text-container {
              order: 0;
            }

            .image-container,
            .text-container {
              width: 100%;
            }

            .feature-title {
              text-align: center;
            }

            .feature-title::after {
              left: 50%;
              transform: translateX(-50%);
            }

            .feature-description {
              text-align: center;
            }

            .feature-button-wrapper {
              justify-content: center;
            }

            .cta-title {
              font-size: 42px;
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

            .hero-description {
              font-size: 18px;
              margin-bottom: 30px;
            }

            .button-container {
              flex-direction: column;
              gap: 16px;
            }

            .btn {
              padding: 14px 28px;
              font-size: 16px;
              width: 100%;
              max-width: 300px;
            }

            .btn-large {
              max-width: 400px;
            }

            .feature-section {
              padding: 60px 0;
            }

            .feature-title {
              font-size: 28px;
            }

            .feature-description {
              font-size: 16px;
            }

            .cta-title {
              font-size: 32px;
            }

            .social-proof-text {
              font-size: 13px;
              letter-spacing: 0.03em;
            }
          }

          @media (max-width: 480px) {
            .hero-title {
              font-size: 28px;
            }

            .hero-description {
              font-size: 16px;
            }

            .feature-title {
              font-size: 24px;
            }

            .cta-title {
              font-size: 28px;
            }

            .btn-small {
              padding: 10px 20px;
              font-size: 14px;
            }

            .cta-title::after {
              width: 60px;
              height: 3px;
            }

            .cta-title:hover::after {
              width: 100px;
            }
          }
        `}</style>
      </div>
    </>
  );
};

// Create root and render
const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <HomePage />
  </React.StrictMode>
);

export default HomePage;