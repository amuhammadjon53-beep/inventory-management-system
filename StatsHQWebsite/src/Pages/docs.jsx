import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
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

const DocsPage = () => {
  const [currentPage, setCurrentPage] = useState("Introduction");
  const [activeSection, setActiveSection] = useState("");
  const [isManuallyScrolling, setIsManuallyScrolling] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [loading, setLoading] = useState(true);
  const scrollTimeoutRef = useRef(null);
  const contentRef = useRef(null);
  const navbarRef = useRef(null);
  const leftMenuRef = useRef(null);
  const rightTocRef = useRef(null);

  const pages = ["Introduction", "Set Up", "FAQ", "Invite Tracking", "Distribution", "Ships", "Privacy Policy", "Terms Of Service", "Cookie Policy"];
  
  const categories = {
    "The Basics": ["Introduction", "Set Up", "FAQ"],
    "Features": ["Invite Tracking", "Distribution", "Ships"],
    "Legal": ["Privacy Policy", "Terms Of Service", "Cookie Policy"]
  };

  // Map URL params to page names
  const paramToPage = {
    'intro': 'Introduction',
    'setup': 'Set Up',
    'faq': 'FAQ',
    'invite-tracking': 'Invite Tracking',
    'distribution': 'Distribution',
    'ships': 'Ships',
    'privacy': 'Privacy Policy',
    'terms': 'Terms Of Service',
    'cookies': 'Cookie Policy'
  };

  // Map page names to URL params
  const pageToParam = {
    'Introduction': 'intro',
    'Set Up': 'setup',
    'FAQ': 'faq',
    'Invite Tracking': 'invite-tracking',
    'Distribution': 'distribution',
    'Ships': 'ships',
    'Privacy Policy': 'privacy',
    'Terms Of Service': 'terms',
    'Cookie Policy': 'cookies'
  };

  // Simulate loading
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(false);
    }, 800);
    
    return () => clearTimeout(timer);
  }, [currentPage]);

  useEffect(() => {
    // Check URL for page parameter on initial load
    const searchParams = new URLSearchParams(window.location.search);
    const pageParam = searchParams.get('page');
    
    if (pageParam && paramToPage[pageParam]) {
      setCurrentPage(paramToPage[pageParam]);
    }
  }, []);

  // Handle scroll for navbar and sticky elements
  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY;
      
      // Set scrolled state for navbar background change
      if (scrollPosition > 50) {
        setIsScrolled(true);
      } else {
        setIsScrolled(false);
      }

      // Update sticky positions for left menu and right TOC
      if (window.innerWidth > 968) { // Desktop only
        const navbar = navbarRef.current;
        const leftMenu = leftMenuRef.current;
        const rightToc = rightTocRef.current;
        
        if (navbar && leftMenu && rightToc) {
          const navbarHeight = navbar.offsetHeight;
          const scrollY = window.scrollY;
          
          // Calculate top position (navbar height + some padding)
          const topPosition = navbarHeight + 20;
          
          // Apply to left menu
          leftMenu.style.top = `${topPosition}px`;
          
          // Apply to right TOC
          rightToc.style.top = `${topPosition}px`;
        }
      }
    };

    window.addEventListener("scroll", handleScroll);
    // Initial call to set positions
    setTimeout(handleScroll, 100); // Delay to ensure navbar height is calculated
    
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const totalPages = pages.length;
  const currentIndex = pages.indexOf(currentPage);

  // Get page intro
  const getPageIntro = () => {
    switch (currentPage) {
      case "Introduction":
        return {
          title: "Welcome to the Stats Docs!",
          description: "In here you will find explanation about what Stats is, what it does, how to set it up, FAQ and so much more!"
        };
      case "Set Up":
        return {
          title: "Set Up",
          description: "Find out the most important info regarding the bot's set up."
        };
      case "Invite Tracking":
        return {
          title: "Invite Tracking",
          description: "Learn how Stats monitors invites and categorizes new members."
        };
      case "Distribution":
        return {
          title: "Distribution",
          description: "Understand the 24-hour activity breakdown and how activity levels are calculated."
        };
      case "Ships":
        return {
          title: "Ships",
          description: "Discover how compatibility between users is calculated based on interaction patterns."
        };
      case "FAQ":
        return {
          title: "FAQ",
          description: "Frequently asked questions"
        };
      case "Privacy Policy":
        return {
          title: "Privacy Policy",
          description: "Learn exactly how data is being processed, stored and so much more regarding user and server privacy"
        };
      case "Terms Of Service":
        return {
          title: "Terms Of Service",
          description: "Learn the rules that govern your use of the bot."
        };
      case "Cookie Policy":
        return {
          title: "Cookie Policy",
          description: "Understand how we use cookies and similar technologies on our website to enhance your experience."
        };
      default:
        return {
          title: "",
          description: ""
        };
    }
  };

  const pageIntro = getPageIntro();

  // Get sections for current page for the table of contents
  const getPageSections = () => {
    switch (currentPage) {
      case "Introduction":
        return [
          { id: "what-is-stats", title: "What is Stats?" },
          { id: "is-bot-free", title: "Is the Bot free?" },
          { id: "what-makes-different", title: "What makes Stats different?" },
          { id: "is-stats-for-me", title: "Is Stats for me?" }
        ];
      case "Set Up":
        return [
          { id: "setup", title: "Set Up" },
          { id: "permissions", title: "Permissions" },
          { id: "prefix-slash", title: "Prefix and Slash commands" },
          { id: "other-info", title: "Other Info" }
        ];
      case "Invite Tracking":
        return [
          { id: "what-is-invite-tracking", title: "What is Invite Tracking?" },
          { id: "activate-invite-tracking", title: "How do I activate invite tracking?" },
          { id: "invite-types", title: "What are invite types?" },
          { id: "suspicious-invites", title: "How are suspicious invites determined?" }
        ];
      case "Distribution":
        return [
          { id: "what-is-distribution", title: "What is distribution?" },
          { id: "timezone-distribution", title: "What timezone is the distribution command based on?" },
          { id: "activity-levels", title: "How are the activity levels made?" }
        ];
      case "Ships":
        return [
          { id: "what-are-ships", title: "What are ships?" },
          { id: "how-ships-calculated", title: "How are ships calculated?" },
          { id: "no-ships-leaderboard", title: "Why are there no ships in the leaderboard?" }
        ];
      case "FAQ":
        return [
          { id: "timezone", title: "Change timezone" },
          { id: "filter-role", title: "Filter by role" },
          { id: "streaks-update", title: "Activity streaks update" }
        ];
      case "Privacy Policy":
        return [
          { id: "scope", title: "1. Scope of This Policy" },
          { id: "categories", title: "2. Categories of Data Collected" },
          { id: "user-tracking", title: "2A. User Tracking Data" },
          { id: "member-tracking", title: "2B. Member Activity Tracking" },
          { id: "voice-tracking", title: "2C. Voice Activity Tracking" },
          { id: "message-tracking", title: "2D. Message Tracking" },
          { id: "invite-tracking", title: "2E. Invite Tracking" },
          { id: "emoji-tracking", title: "2F. Emoji Tracking" },
          { id: "activity-tracking", title: "2G. Activity & Presence Tracking" },
          { id: "guild-tracking", title: "2H. Server & Role Tracking" },
          { id: "command-tracking", title: "2I. Command Usage Tracking" },
          { id: "lawful-basis", title: "3. Lawful Basis for Processing" },
          { id: "security", title: "4. Data Security and Encryption" },
          { id: "retention", title: "5. Data Retention and Deletion" },
          { id: "transfers", title: "6. International Data Transfers" },
          { id: "rights", title: "7. Data Subject Rights" },
          { id: "sharing", title: "8. Data Sharing and Disclosure" },
          { id: "children", title: "9. Children's Privacy" },
          { id: "compliance", title: "10. Compliance with Discord Requirements" },
          { id: "changes", title: "11. Changes to This Policy" },
          { id: "contact", title: "12. Contact Information" }
        ];
      case "Terms Of Service":
        return [
          { id: "acceptance", title: "1. Acceptance of Terms" },
          { id: "description", title: "2. Description of the Service" },
          { id: "responsibilities", title: "3. User Responsibilities" },
          { id: "management", title: "4. Account and Server Management" },
          { id: "prohibited", title: "5. Prohibited Conduct" },
          { id: "intellectual", title: "6. Intellectual Property" },
          { id: "liability", title: "7. Liability Limitation" },
          { id: "indemnification", title: "8. Indemnification" },
          { id: "changes-tos", title: "9. Changes to the Service" },
          { id: "termination", title: "10. Termination" },
          { id: "governing", title: "11. Governing Law and Contact" }
        ];
      case "Cookie Policy":
        return [
          { id: "cookie-introduction", title: "1. Introduction" },
          { id: "what-are-cookies", title: "2. What Are Cookies?" },
          { id: "types-of-cookies", title: "3. Types of Cookies We Use" },
          { id: "third-party-cookies", title: "4. Third-Party Cookies" },
          { id: "how-we-use-cookies", title: "5. How We Use Cookies" },
          { id: "your-cookie-choices", title: "6. Your Cookie Choices" },
          { id: "data-stored", title: "7. Data Stored in Our Cookies" },
          { id: "cookie-duration", title: "8. Cookie Duration" },
          { id: "security-measures", title: "9. Security Measures" },
          { id: "cookie-policy-changes", title: "10. Changes to This Policy" },
          { id: "your-rights-cookies", title: "11. Your Rights" },
          { id: "cookie-contact", title: "12. Contact Us" },
          { id: "cookie-consent", title: "13. Consent" }
        ];
      default:
        return [];
    }
  };

  const pageSections = getPageSections();

  const handlePageChange = (page) => {
    setCurrentPage(page);
    setActiveSection("");
    setIsMobileMenuOpen(false);
    setLoading(true);
    
    const param = pageToParam[page];
    const url = new URL(window.location);
    url.searchParams.set('page', param);
    window.history.pushState({}, '', url);
    
    // Dispatch a custom event to notify NavBar of URL change
    window.dispatchEvent(new Event('urlchange'));
    
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handlePrevious = () => {
    if (currentIndex > 0) {
      handlePageChange(pages[currentIndex - 1]);
    }
  };

  const handleNext = () => {
    if (currentIndex < totalPages - 1) {
      handlePageChange(pages[currentIndex + 1]);
    }
  };

  const scrollToSection = (sectionId) => {
    setIsManuallyScrolling(true);
    setIsMobileMenuOpen(false);
    
    const element = document.getElementById(sectionId);
    if (element) {
      const navbar = navbarRef.current;
      const navbarHeight = navbar ? navbar.offsetHeight : 80;
      const offset = navbarHeight + 20;
      
      const elementPosition = element.getBoundingClientRect().top;
      const offsetPosition = elementPosition + window.pageYOffset - offset;
      
      window.scrollTo({
        top: offsetPosition,
        behavior: "smooth"
      });
      
      setActiveSection(sectionId);
      
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      
      scrollTimeoutRef.current = setTimeout(() => {
        setIsManuallyScrolling(false);
        scrollTimeoutRef.current = null;
      }, 500);
    }
  };

  useEffect(() => {
    const handleScroll = () => {
      if (isManuallyScrolling) return;
      
      const navbar = navbarRef.current;
      const navbarHeight = navbar ? navbar.offsetHeight : 80;
      const scrollPosition = window.scrollY + navbarHeight + 20;

      for (const section of pageSections) {
        const element = document.getElementById(section.id);
        if (element) {
          const { offsetTop, offsetHeight } = element;
          if (scrollPosition >= offsetTop && scrollPosition < offsetTop + offsetHeight) {
            setActiveSection(section.id);
            break;
          }
        }
      }
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, [pageSections, isManuallyScrolling]);

  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  const renderContent = () => {
    if (loading) {
      return (
        <div className="loading-container">
          <LoadingSpinner size="large" text="Loading content..." />
        </div>
      );
    }

    switch (currentPage) {
    case "Introduction":
        return (
          <div className="docs-content" ref={contentRef}>
            <h2 id="what-is-stats" className="docs-heading">What is Stats?</h2>
            <p className="docs-text">
              Stats is the ultimate statistics Discord bot for communities that want full monitoring, engagement insights, or need to boost engagement within their server. It tracks <strong>8 different types of statistics</strong> and displays them in many different forms like leaderboards, averages, charts, and more.
            </p>
            
            <p className="docs-text">
              Stats currently tracks a total of <strong>8 types of statistics</strong>:
            </p>
            
            <ul className="docs-list">
              <li>Messages</li>
              <li>Voice Activity</li>
              <li>Invites</li>
              <li>Activity (games, streaming, music that appear in the status of a user)</li>
              <li>Emojis</li>
              <li>Member Growth</li>
              <li>Role Growth</li>
              <li>Mentions</li>
            </ul>
            
            <p className="docs-text">
              Stats also tracks statistics per channel, category, role, and member, giving you the flexibility to break down activity exactly how you need. You can monitor the member/role growth of your server over time, identify top users, channels, categories or roles with leaderboards, track trends through charts, and much more.
            </p>

            <h2 id="is-bot-free" className="docs-heading">Is the Bot free?</h2>
            <p className="docs-text">
              Yes! Stats is currently <strong>completely free</strong> with premium planned for the future. <a href="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863601&integration_type=0&scope=applications.commands+bot" className="docs-link" target="_blank" rel="noopener noreferrer">Invite Stats now</a> and enjoy all its features completely free before premium is released!
            </p>

            <h2 id="what-makes-different" className="docs-heading">What makes Stats different from other bots that track statistics?</h2>
            <p className="docs-text">
              Stats is capable of many things that are simply not available on other bots.
            </p>
            
            <p className="docs-text">Here are some of the features exclusively on Stats:</p>
            
            <ul className="docs-list">
              <li><strong>8 different types of statistics</strong> all tracked by one bot (messages, voice activity, emojis, activity, invites, member growth, role growth, mentions)</li>
              <li><strong>Filter stats</strong> by channel, category, role, or member</li>
              <li><strong>Advanced emoji tracking</strong> (separates reactions vs messages)</li>
              <li><strong>In-depth activity tracking</strong> (sessions, streaks, behavior patterns)</li>
              <li><strong>Projected member growth</strong> (predicts future server trends)</li>
              <li><strong>Hourly activity distribution</strong> (identify peak activity times)</li>
              <li><strong>Full data dashboard</strong> (access and visualize all stats in one place)</li>
              <li><strong>Role-specific analytics</strong> (track role additions/removals)</li>
              <li><strong>Role leaderboards</strong> (rank roles by activity/stat type)</li>
            </ul>
            
            <p className="docs-text">
              With Stats, you get insights and precision that no other statistics bot can match.
            </p>

            <h2 id="is-stats-for-me" className="docs-heading">Is Stats for me?</h2>
            <p className="docs-text">
              Stats is meant for <strong>two types of people</strong>: server managers who want deep analytical insight into their server, and those who want to actively boost and promote engagement within their server.
            </p>

            <p className="docs-text">
              <strong>For server owners and administrators who care about data</strong>: Stats delivers detailed tracking across messages, voice activity, invites, emojis, application activity, member growth, and role growth, giving you the clarity needed to monitor trends, analyze behavior, and make informed decisions.
            </p>

            <p className="docs-text">
              <strong>For those focused on boosting engagement</strong>: Stats transforms activity into motivation through competitive leaderboards, visible rankings, and clear progress tracking that naturally encourages interaction.
            </p>
          </div>
        );

      case "Set Up":
        return (
          <div className="docs-content">
            <h2 id="setup" className="docs-heading">Set Up</h2>
            <p className="docs-text">
              Stats requires <strong>ZERO setup</strong>. You simply have to invite the bot with <a href="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863601&integration_type=0&scope=applications.commands+bot" className="docs-link" target="_blank" rel="noopener noreferrer">this invite link</a>, select the server you wish to add the bot to, and click authorize. Tracking for any type of statistic will automatically start upon the bot's join. Keep in mind that only statistics from after the bot's join are tracked, the bot doesn't have access to any data before its join date.
            </p>

            <h2 id="permissions" className="docs-heading">Permissions</h2>
            <p className="docs-text">
              In order to track statistics, Stats needs the following permissions in a server:
            </p>
            
            <ul className="docs-list">
              <li><strong>View Channels</strong> - Required for the bot to view channels and track their statistics.</li>
              <li><strong>Send Messages, Embed Links, Attach files & Read Message History</strong> - All required for the bot to respond to commands on Discord.</li>
              <li><strong>Use application commands</strong> - Slash commands won't work if the bot doesn't have this permission.</li>
              <li><strong>Manage Server, Create Invite & View Audit Log</strong> - Needed to track invites in the server.</li>
              <li><strong>Manage Roles</strong> - Needed for the upcoming autoroles feature</li>
              <li><strong>Manage Channels & Connect</strong> - Needed for the upcoming counters feature</li>
            </ul>

            <h2 id="prefix-slash" className="docs-heading">Prefix and Slash commands</h2>
            <p className="docs-text">
              The default prefix is <strong>s!</strong>, you can change this prefix anytime using the settings command. The bot also supports <strong>slash commands</strong> on all commands.
            </p>

            <h2 id="other-info" className="docs-heading">Other Info</h2>
            <p className="docs-text">
              After adding the bot and allowing the correct permissions the bot should instantly start working perfectly. Make sure it has access to all the channels or categories you need it to track statistics for. If you need help with the commands, you can visit the <a href="/Commands/index.html" className="docs-link">Commands page</a> and look at our full list of commands with a short explanation to each. If you generally need help with anything else please don't hesitate to join our <a href="https://discord.gg/hreJvck8cK" className="docs-link" target="_blank" rel="noopener noreferrer">support discord server</a> and ask our dev team directly.
            </p>
          </div>
        );

      case "Invite Tracking":
        return (
          <div className="docs-content">
            <h2 id="what-is-invite-tracking" className="docs-heading">What is Invite Tracking?</h2>
            <p className="docs-text">
              Invite tracking is a system that monitors who invites new members into a Discord server and records the outcome of those joins. It categorizes each invite based on what happens after a user joins, so you can see which invites brought in active members, suspicious users, or users who left.
            </p>

            <h2 id="activate-invite-tracking" className="docs-heading">How do I activate invite tracking?</h2>
            <p className="docs-text">
              Invite tracking activates automatically once the bot has the required permissions in your server. No manual setup is needed. As soon as the bot can access invite data, it begins tracking and logging invites in the background.
            </p>

            <h2 id="invite-types" className="docs-heading">What are invite types?</h2>
            <p className="docs-text">
              There are three invite types:
            </p>
            <ul className="docs-list">
              <li><strong>Valid:</strong> Users who joined through an invite and stayed in the server.</li>
              <li><strong>Suspicious:</strong> Users flagged based on account age conditions (explained below).</li>
              <li><strong>Left:</strong> Users who joined but later left the server.</li>
            </ul>

            <h2 id="suspicious-invites" className="docs-heading">How are suspicious invites determined to be suspicious?</h2>
            <p className="docs-text">
              An invite is marked suspicious if either:
            </p>
            <ul className="docs-list">
              <li>The inviter's account is newer than the configured threshold (default: 3 days), or</li>
              <li>The invited user's account is newer than that same threshold.</li>
            </ul>
            <p className="docs-text">
              This threshold can be changed using the server settings command.
            </p>
          </div>
        );

      case "Distribution":
        return (
          <div className="docs-content">
            <h2 id="what-is-distribution" className="docs-heading">What is distribution?</h2>
            <p className="docs-text">
              Distribution is a 24-hour activity breakdown shown as a pie chart. Each hour represents how much activity happened during that specific time, helping identify when the server is most active throughout the day.
            </p>

            <h2 id="timezone-distribution" className="docs-heading">What timezone is the distribution command based on?</h2>
            <p className="docs-text">
              By default, distribution is based on UTC timezone. However, this can be changed in the server settings using the settings command, where multiple timezone options are available.
            </p>

            <h2 id="activity-levels" className="docs-heading">How are the activity levels in the distribution command made?</h2>
            <p className="docs-text">
              Activity levels are calculated using statistical thresholds based on the server's average activity:
            </p>
            <ul className="docs-list">
              <li><strong>Peak activity:</strong> ≥ 200% of average activity</li>
              <li><strong>High activity:</strong> ≥ 150% of average activity</li>
              <li><strong>Medium activity:</strong> ≥ 80% of average activity</li>
              <li><strong>Low activity:</strong> {'<'} 80% of average activity</li>
            </ul>
          </div>
        );

      case "Ships":
        return (
          <div className="docs-content">
            <h2 id="what-are-ships" className="docs-heading">What are ships?</h2>
            <p className="docs-text">
              Ships calculate the compatibility between two users in a server. They represent how well two members “match” based on their interaction patterns and activity inside the community.
            </p>

            <h2 id="how-ships-calculated" className="docs-heading">How are ships calculated?</h2>
            <p className="docs-text">
              Ships are not random. They are based on multiple real activity signals, including:
            </p>
            <ul className="docs-list">
              <li>Mentions between the two users</li>
              <li>Overlapping activity in the same channels</li>
              <li>Time spent together in voice channels</li>
              <li>Overall activity frequency</li>
              <li>How recent their interactions are</li>
            </ul>
            <p className="docs-text">
              All these factors are combined to produce a compatibility score.
            </p>

            <h2 id="no-ships-leaderboard" className="docs-heading">Why are there no ships in the ship leaderboard?</h2>
            <p className="docs-text">
              This usually happens when no ship calculations have been created yet in the server. The leaderboard only populates after at least one ship has been generated.
              To fix this, create a ship using the ship compatibility command. Once ships exist, they will appear in the leaderboard automatically.
            </p>
          </div>
        );

      case "FAQ":
        return (
          <div className="docs-content">
            <h2 id="faq" className="docs-heading">Frequently Asked Questions</h2>
            
            <h3 id="timezone" className="docs-subheading">How do I change the timezone of the distribution command?</h3>
            <p className="docs-text">Simply head over to settings, choose <strong>timezone settings</strong>, then choose from our range of timezones.</p>

            <h3 id="filter-role" className="docs-subheading">How do I filter stats by role?</h3>
            <p className="docs-text">
              <strong>If you're using the discord bot:</strong> use the <strong>"Input role id"</strong> button available in most commands to input the id of the specific role you wish to filter to, you can get the id of a role by using the <strong>"get id"</strong> command on that role.
            </p>
            <p className="docs-text">
              <strong>If you're using the dashboard:</strong> you can use the role filter dropdown menu that should have all the roles in your server listed.
            </p>

            <h3 id="streaks-update" className="docs-subheading">When do the activity streaks update?</h3>
            <p className="docs-text">The activity streaks update everyday at <strong>00:00 UTC</strong>. This is a heavy global event that needs time to be distributed among all servers, please wait a few minutes after the stated time to contact support.</p>
          </div>
        );

      case "Privacy Policy":
        return (
          <div className="docs-content">
            <h1 id="privacy-policy" className="docs-main-title">Privacy Policy</h1>
            
            <p className="docs-text">
              <strong>Effective Date:</strong> 25 February 2026<br />
              <strong>Last Updated:</strong> 25 February 2026
            </p>

            <p className="docs-text">
              This Privacy Policy explains how Stats ("we," "us," or "our") collects, processes, stores, protects, and manages information when you use the Stats Discord bot (the "Service"). By adding or interacting with Stats in a Discord server, you acknowledge and agree to this Privacy Policy.
            </p>

            <p className="docs-text">
              Stats is committed to complying with applicable data protection laws and regulatory frameworks, including but not limited to:
            </p>

            <ul className="docs-list">
              <li>General Data Protection Regulation (GDPR) (EU)</li>
              <li>UK GDPR and Data Protection Act 2018</li>
              <li>Applicable U.S. and international data protection laws</li>
            </ul>

            <p className="docs-text">
              Stats also operates in accordance with:
            </p>

            <ul className="docs-list">
              <li>Discord Developer Policy: <a href="https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy" target="_blank" rel="noopener noreferrer" className="docs-link">https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy</a></li>
              <li>Discord Developer Terms of Service: <a href="https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service" target="_blank" rel="noopener noreferrer" className="docs-link">https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service</a></li>
            </ul>

            <h2 id="scope" className="docs-heading">1. Scope of This Policy</h2>
            <p className="docs-text">This Privacy Policy applies to all users interacting with Stats via Discord and governs all statistical, engagement, and operational data processed through the Service.</p>
            <p className="docs-text">Stats acts as an independent data controller for the limited data it processes to provide analytics, engagement tracking, and operational functionality.</p>

            <h2 id="categories" className="docs-heading">2. Categories of Data Collected</h2>
            <p className="docs-text">Stats collects only data necessary to provide its features. Below is a comprehensive breakdown of all data categories we collect and process:</p>
            
            <h3 className="docs-subheading">A. Discord Identifiers</h3>
            <ul className="docs-list">
              <li>Discord User IDs</li>
              <li>Discord Usernames and display names (updated periodically)</li>
              <li>Discord Server (Guild) IDs</li>
              <li>Channel IDs and Category IDs</li>
              <li>Role IDs</li>
              <li>Message IDs (for tracking purposes only, content not stored)</li>
              <li>Invite codes and related metadata</li>
            </ul>
            <p className="docs-text">These identifiers allow Stats to associate statistics accurately across our database tables without storing personal message content.</p>

            <h3 id="user-tracking" className="docs-heading">2A. User Tracking Data</h3>
            <p className="docs-text">For each user in a server, Stats maintains comprehensive tracking records including:</p>
            <ul className="docs-list">
              <li><strong>User Profile Information:</strong> User ID, username, display name, avatar hash, and account creation date</li>
              <li><strong>Join/Leave Records:</strong> Timestamps of when users join or leave servers, including multiple join/leave events</li>
              <li><strong>First Interaction:</strong> Date when a user was first seen by the bot in each server</li>
              <li><strong>Role History:</strong> Current roles and role assignment changes over time</li>
              <li><strong>User Activity Flags:</strong> Whether users are bots, have left the server, or have disabled tracking</li>
            </ul>

            <h3 id="member-tracking" className="docs-heading">2B. Member Activity Tracking</h3>
            <p className="docs-text">Stats maintains per-member daily statistics including:</p>
            <ul className="docs-list">
              <li><strong>Message Counts:</strong> Number of messages sent per hour, per channel (message content is never stored)</li>
              <li><strong>Voice Activity:</strong> Daily voice minutes, join/leave events, and session durations</li>
              <li><strong>Invite Tracking:</strong> Number of invites used, invites created, and inviter-invitee relationships</li>
              <li><strong>Emoji Usage:</strong> Daily emoji usage counts, split by reactions and message emojis</li>
              <li><strong>Activity Tracking:</strong> Daily activity sessions (gaming, streaming, listening), total activity minutes, and streak data</li>
              <li><strong>Hourly Distribution:</strong> Per-hour activity breakdowns for messages and voice activity</li>
              <li><strong>Channel Activity:</strong> Activity statistics broken down by individual channels</li>
              <li><strong>Category Activity:</strong> Aggregated statistics by channel categories</li>
              <li><strong>Role-based Statistics:</strong> Activity filtered and aggregated by role assignments</li>
            </ul>

            <h3 id="voice-tracking" className="docs-heading">2C. Voice Activity Tracking</h3>
            <p className="docs-text">Voice activity is tracked at multiple levels of granularity:</p>
            <ul className="docs-list">
              <li><strong>Per-Session Tracking:</strong> For each voice session, we track start time, end time, channel ID, and duration</li>
              <li><strong>Hourly Aggregates:</strong> Total voice minutes per user, per channel, per day</li>
              <li><strong>Voice State Changes:</strong> Records of when users join, leave, move between voice channels, or go deaf/mute</li>
              <li><strong>Session Boundaries:</strong> Detection of session starts and ends, including overnight sessions that span multiple days</li>
              <li><strong>Server-wide Voice Activity:</strong> Aggregated voice minutes for entire servers, broken down by hour and day</li>
            </ul>

            <h3 id="message-tracking" className="docs-heading">2D. Message Tracking</h3>
            <p className="docs-text">Message statistics are tracked with careful privacy considerations:</p>
            <ul className="docs-list">
              <li><strong>Message Counts:</strong> Number of messages sent per user, per channel, per day (message content is NEVER stored or logged)</li>
              <li><strong>Message Deletions:</strong> Detection of message deletions to adjust statistics if configured</li>
              <li><strong>Message Edits:</strong> Detection of emoji additions through edits to track emoji usage</li>
              <li><strong>Channel Activity:</strong> Daily message counts broken down by channel and category</li>
              <li><strong>Hourly Distribution:</strong> Per-hour message activity patterns</li>
              <li><strong>Role-based Message Activity:</strong> Message statistics aggregated by user roles</li>
            </ul>

            <h3 id="invite-tracking" className="docs-heading">2E. Invite Tracking</h3>
            <p className="docs-text">Invite tracking includes comprehensive invite analytics:</p>
            <ul className="docs-list">
              <li><strong>Invite Creation:</strong> Tracking who created invites, when, and their expiration settings</li>
              <li><strong>Invite Usage:</strong> Recording which users joined using which invites</li>
              <li><strong>Inviter Statistics:</strong> Number of successful invites per user, including fake/invalid joins filtered out</li>
              <li><strong>Vanity URLs:</strong> Tracking usage of server vanity URLs if applicable</li>
              <li><strong>Invite Metadata:</strong> Channel where invite was created, max uses, and expiration timestamps</li>
              <li><strong>Join Sources:</strong> Distinguishing between new joins, re-joins, and tracking inviter relationships</li>
            </ul>

            <h3 id="emoji-tracking" className="docs-heading">2F. Emoji Tracking</h3>
            <p className="docs-text">Advanced emoji tracking distinguishes between different types of emoji usage:</p>
            <ul className="docs-list">
              <li><strong>Reaction Emojis:</strong> Tracking when users add reactions to messages, including which emoji was used</li>
              <li><strong>Message Emojis:</strong> Tracking emojis used directly in message content</li>
              <li><strong>Emoji Types:</strong> Distinguishing between standard Unicode emojis and custom server emojis</li>
              <li><strong>Reaction Additions/Removals:</strong> Tracking when reactions are added or removed to maintain accurate counts</li>
              <li><strong>Per-User Emoji Statistics:</strong> Total emoji usage broken down by user and emoji</li>
              <li><strong>Emoji Popularity:</strong> Most used emojis across the server, with separate tracking for reactions vs. message content</li>
              <li><strong>Reaction Detection:</strong> Special handling for emojis added through message edits to ensure complete tracking</li>
            </ul>

            <h3 id="activity-tracking" className="docs-heading">2G. Activity & Presence Tracking</h3>
            <p className="docs-text">User presence and activity tracking includes:</p>
            <ul className="docs-list">
              <li><strong>Activity Types:</strong> Gaming, streaming, listening to music, watching content, competing, and custom statuses</li>
              <li><strong>Activity Names:</strong> Names of games, applications, or content being used (e.g., "Spotify," "YouTube," specific game titles)</li>
              <li><strong>Activity Sessions:</strong> Start and end times for continuous activity sessions</li>
              <li><strong>Streak Tracking:</strong> Daily activity streaks and session streaks with configurable reset times</li>
              <li><strong>Activity Duration:</strong> Total minutes spent in each activity type per day</li>
              <li><strong>Session Boundaries:</strong> Intelligent session detection that accounts for short interruptions</li>
              <li><strong>Multiple Activities:</strong> Tracking when users have multiple simultaneous activities</li>
              <li><strong>Activity Timestamps:</strong> When activities started and when they were last updated</li>
              <li><strong>Application Details:</strong> Application IDs for Discord-integrated activities (without storing personal content)</li>
            </ul>

            <h3 id="guild-tracking" className="docs-heading">2H. Server & Role Tracking</h3>
            <p className="docs-text">Server-wide tracking includes:</p>
            <ul className="docs-list">
              <li><strong>Member Growth:</strong> Daily snapshots of total member counts, including bot vs. human counts</li>
              <li><strong>Join/Leave Analytics:</strong> Daily join and leave counts with trend analysis</li>
              <li><strong>Role Growth:</strong> Tracking role popularity and member counts per role over time</li>
              <li><strong>Channel Activity:</strong> Daily activity metrics for each channel and category</li>
              <li><strong>Server Settings:</strong> Configurable tracking preferences, timezone settings, and filtering options</li>
              <li><strong>Role Filtering:</strong> Ability to include/exclude specific roles from statistics</li>
              <li><strong>Channel Filtering:</strong> Configurable channel exclusions for tracking</li>
              <li><strong>Bot Filtering:</strong> Optional inclusion/exclusion of bot accounts from statistics</li>
              <li><strong>Projected Growth:</strong> Trend-based member growth projections</li>
            </ul>

            <h3 id="command-tracking" className="docs-heading">2I. Command Usage Tracking</h3>
            <p className="docs-text">To improve our service and debug issues, we track:</p>
            <ul className="docs-list">
              <li><strong>Command Names:</strong> Which commands are being used</li>
              <li><strong>Usage Frequency:</strong> How often commands are invoked</li>
              <li><strong>Error Logs:</strong> Technical errors that occur during command execution</li>
              <li><strong>Performance Metrics:</strong> Response times and system performance data</li>
              <li><strong>Command Parameters:</strong> Aggregated parameter usage (without storing user inputs)</li>
            </ul>

            <h3 className="docs-subheading">J. Technical and Operational Data</h3>
            <ul className="docs-list">
              <li>Command usage logs (command names and frequency only)</li>
              <li>Error reports (for debugging and service improvement)</li>
              <li>System performance metrics</li>
              <li>Database query performance data</li>
              <li>API response times and reliability metrics</li>
            </ul>
            <p className="docs-text">This data supports reliability, security, and service improvement only and is not used for user profiling.</p>

            <h2 id="lawful-basis" className="docs-heading">3. Lawful Basis for Processing (GDPR Compliance)</h2>
            <p className="docs-text">Stats processes data under the following lawful bases:</p>
            <p className="docs-text"><strong>Legitimate Interest (Article 6(1)(f))</strong> — to provide analytics, engagement tracking, and server insights requested by server administrators. Our processing is necessary for the purposes of providing statistical analysis and engagement tools that server administrators have intentionally added to their servers.</p>
            <p className="docs-text"><strong>Performance of a Service (Article 6(1)(b))</strong> — to fulfill Stats functionality when added to a server, including all tracking features described in this policy.</p>
            <p className="docs-text"><strong>Consent (Article 6(1)(a))</strong> — for any optional features that may be introduced in the future that require additional data processing.</p>
            <p className="docs-text">Consent banners are unnecessary for core functionality, as Stats functions only after intentional server authorization by users with appropriate permissions.</p>

            <h2 id="security" className="docs-heading">4. Data Security and Encryption</h2>
            <p className="docs-text">Stats implements strong safeguards to protect data against unauthorized access, alteration, disclosure, or destruction.</p>
            <p className="docs-text">Measures include:</p>
            <ul className="docs-list">
              <li>Encryption of stored usernames and sensitive identifiers at rest</li>
              <li>Encrypted database connections and secure API communications</li>
              <li>Secure database architecture with regular backups</li>
              <li>Least privilege principles for internal access - only authorized personnel can access production data</li>
              <li>Restricted access for authorized personnel only with multi-factor authentication</li>
              <li>Infrastructure-level protections appropriate to the Service including DDoS protection</li>
              <li>Regular security audits and dependency updates</li>
              <li>Input validation and sanitization to prevent injection attacks</li>
              <li>Rate limiting on commands and API endpoints</li>
            </ul>
            <p className="docs-text">While no system can guarantee absolute security, we continuously review and improve protections and follow industry best practices.</p>

            <h2 id="retention" className="docs-heading">5. Data Retention and Deletion</h2>
            <p className="docs-text">Data is retained indefinitely to preserve historical trends and long-term analytics, unless explicitly deleted by authorized users.</p>
            <p className="docs-text"><strong>Data Deletion Options:</strong></p>
            <ul className="docs-list">
              <li><strong>Server Administrators</strong> may permanently delete all stored statistics for their server using the <code>"reset server"</code> command or through the web dashboard. This removes all member statistics, channel data, and server settings associated with that guild.</li>
              <li><strong>Individual User Deletion:</strong> Authorized administrators can delete statistics for specific users using the <code>"reset user"</code> command. This removes all tracking data for that user from the server while preserving other users' data.</li>
              <li><strong>Privacy Mode:</strong> Individual users can turn on a privacy mode that can be found by running the settings user command. This mode will delete all of their personal data from our systems on the server the mode was tunred on in, it will also block any tracking the bot tries to do on that user in that specific server.</li>
              <li><strong>Bot Removal:</strong> If the bot is removed from a server, data will remain stored but inaccessible through normal commands. Server administrators must initialize a reset before bot removal to ensure data deletion.</li>
            </ul>
            <p className="docs-text">Once data is deleted through any of these methods, it is permanently and irreversibly removed from our databases. Backups containing deleted data are rotated and purged according to our backup retention policy (maximum 30 days).</p>
            <p className="docs-text">Data will remain stored even after bot removal unless a reset is initialized beforehand.</p>

            <h2 id="transfers" className="docs-heading">6. International Data Transfers</h2>
            <p className="docs-text">Stats may store or process data outside a user's country of residence. Our infrastructure may be located in various regions including the European Union, United States, or other jurisdictions. Appropriate safeguards are implemented consistent with GDPR and recognized international standards, including Standard Contractual Clauses where required.</p>
            <p className="docs-text">By using our Service, you acknowledge that your data may be transferred to and processed in countries outside your residence, which may have different data protection laws. We ensure appropriate safeguards are in place for all international transfers.</p>

            <h2 id="rights" className="docs-heading">7. Data Subject Rights</h2>
            <p className="docs-text">Users in jurisdictions with privacy laws (e.g., EU, UK, California, Brazil) may exercise the following rights:</p>
            <ul className="docs-list">
              <li><strong>Right of access:</strong> Request a copy of your personal data we hold</li>
              <li><strong>Right to rectification:</strong> Correct inaccurate or incomplete data</li>
              <li><strong>Right to erasure ("right to be forgotten"):</strong> Request deletion of your data</li>
              <li><strong>Right to restrict processing:</strong> Limit how we use your data</li>
              <li><strong>Right to object:</strong> Object to processing based on legitimate interests</li>
              <li><strong>Right to data portability:</strong> Receive your data in a structured, commonly used format</li>
              <li><strong>Right to withdraw consent:</strong> For any processing based on consent</li>
            </ul>
            <p className="docs-text">Requests are processed via official Stats support channels within applicable legal timeframes (typically 30 days). We may need to verify your identity before processing requests.</p>

            <h2 id="sharing" className="docs-heading">8. Data Sharing and Disclosure</h2>
            <p className="docs-text">Stats does not sell, rent, or trade user data to third parties for marketing or any other purposes.</p>
            <p className="docs-text">Data may be disclosed only in the following limited circumstances:</p>
            <ul className="docs-list">
              <li><strong>Legal Compliance:</strong> To comply with valid legal processes, law enforcement requests, or government requirements where required by law</li>
              <li><strong>Service Protection:</strong> To protect the rights, property, or personal safety of Stats, our users, or the public (e.g., investigating security incidents)</li>
              <li><strong>Service Providers:</strong> With trusted third-party service providers who assist in operating our infrastructure (e.g., database hosting, CDN services), subject to strict data processing agreements</li>
              <li><strong>Server Administrators:</strong> Server administrators have access to aggregated statistics about their server through normal bot commands and the web dashboard</li>
            </ul>
            <p className="docs-text">We never share individual user data between different servers unless required for technical operations (e.g., tracking user migration between servers).</p>

            <h2 id="children" className="docs-heading">9. Children's Privacy</h2>
            <p className="docs-text">Stats is not directed at individuals below Discord's minimum age requirements (13 years old, or 16 in the European Economic Area). We do not knowingly collect data from users prohibited by applicable law. If we become aware that we have collected data from a user below the minimum age, we will take steps to delete that information promptly. Parents or guardians who believe their child has provided us with data should contact us immediately.</p>

            <h2 id="compliance" className="docs-heading">10. Compliance with Discord Requirements</h2>
            <p className="docs-text">Stats requests only permissions and privileged intents necessary to operate, and strictly follows:</p>
            <ul className="docs-list">
              <li><a href="https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy" target="_blank" rel="noopener noreferrer" className="docs-link">Discord Developer Policy</a></li>
              <li><a href="https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service" target="_blank" rel="noopener noreferrer" className="docs-link">Discord Developer Terms of Service</a></li>
              <li>Discord API guidelines and privileged intent requirements</li>
              <li>Discord's requirements for bot verification and data handling</li>
            </ul>
            <p className="docs-text">We use the following privileged intents responsibly and only as needed:</p>
            <ul className="docs-list">
              <li><strong>Guild Members Intent:</strong> To track member joins/leaves and role changes</li>
              <li><strong>Presence Intent:</strong> To track user activity (gaming, streaming, etc.)</li>
              <li><strong>Message Content Intent:</strong> Limited to counting messages and detecting emoji usage (content is never stored)</li>
            </ul>

            <h2 id="changes" className="docs-heading">11. Changes to This Policy</h2>
            <p className="docs-text">We may update this Privacy Policy from time to time to reflect changes in our practices, technology, legal requirements, or the features we offer. Updates are reflected in the "Last Updated" date at the top of this policy. For significant changes, we will provide notice through our Discord support server or other appropriate channels. Continued use of Stats after changes constitutes acceptance of the revised Privacy Policy. We encourage you to review this policy periodically.</p>

            <h2 id="contact" className="docs-heading">12. Contact Information</h2>
            <p className="docs-text">For questions about this Privacy Policy, data subject requests, or any privacy concerns:</p>
            <ul className="docs-list">
              <li><strong>Discord Support Server:</strong> <a href="https://discord.gg/hreJvck8cK" className="docs-link" target="_blank" rel="noopener noreferrer">Join our support server</a> and create a post in the support channel.</li>
            </ul>
          </div>
        );

      case "Terms Of Service":
        return (
          <div className="docs-content">
            <h1 id="terms" className="docs-main-title">Terms of Service</h1>
            
            <p className="docs-text">
              <strong>Effective Date:</strong> 25 February 2026<br />
              <strong>Last Updated:</strong> 25 February 2026
            </p>

            <p className="docs-text">
              These Terms of Service ("Terms") govern your use of the <strong>Stats</strong> Discord bot ("we," "us," or "our") and the related Service. By adding or interacting with Stats on Discord, you agree to these Terms.
            </p>

            <p className="docs-text">
              Stats operates in accordance with Discord's Developer Policies and Terms of Service:
            </p>

            <ul className="docs-list">
              <li><a href="https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy" target="_blank" rel="noopener noreferrer" className="docs-link">Discord Developer Policy</a></li>
              <li><a href="https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service" target="_blank" rel="noopener noreferrer" className="docs-link">Discord Developer Terms of Service</a></li>
            </ul>

            <h2 id="acceptance" className="docs-heading">1. Acceptance of Terms</h2>
            <p className="docs-text">By using Stats, you confirm that you:</p>
            <ul className="docs-list">
              <li>Have read, understood, and agreed to these Terms</li>
              <li>Are authorized to grant permissions for any server where Stats is used</li>
              <li>Meet the minimum age requirements imposed by Discord</li>
            </ul>
            <p className="docs-text">If you do not agree, do not add or use Stats.</p>

            <h2 id="description" className="docs-heading">2. Description of the Service</h2>
            <p className="docs-text">Stats provides statistical analytics, engagement tracking, leaderboards, and operational insights for Discord servers.</p>
            <p className="docs-text">We may update, suspend, or discontinue features without prior notice, but will maintain overall service functionality.</p>

            <h2 id="responsibilities" className="docs-heading">3. User Responsibilities</h2>
            <p className="docs-text">You agree to:</p>
            <ul className="docs-list">
              <li>Use Stats only in compliance with Discord rules, applicable law, and these Terms</li>
              <li>Not exploit Stats to collect unauthorized data, spam, or disrupt servers</li>
              <li>Ensure only authorized administrators add or manage Stats in servers</li>
              <li>Maintain security of your Discord account credentials</li>
            </ul>

            <h2 id="management" className="docs-heading">4. Account and Server Management</h2>
            <p className="docs-text">Admins are responsible for:</p>
            <ul className="docs-list">
              <li>Proper configuration of Stats in servers</li>
              <li>Managing permissions and user roles related to Stats</li>
              <li>Executing any data deletion or reset commands as desired</li>
            </ul>
            <p className="docs-text">Stats does not manage Discord accounts or enforce server rules outside of analytics.</p>

            <h2 id="prohibited" className="docs-heading">5. Prohibited Conduct</h2>
            <p className="docs-text">You may not:</p>
            <ul className="docs-list">
              <li>Attempt to reverse-engineer or exploit Stats</li>
              <li>Use Stats to harass or track individuals outside server contexts</li>
              <li>Share or sell access to Stats without explicit permission</li>
              <li>Circumvent security or modify the bot code</li>
            </ul>
            <p className="docs-text">Violations may result in bot removal, account suspension, or legal action.</p>

            <h2 id="intellectual" className="docs-heading">6. Intellectual Property</h2>
            <p className="docs-text">All Stats content, code, and branding are our intellectual property.</p>
            <p className="docs-text">You may not reproduce, distribute, or create derivative works without explicit written consent.</p>

            <h2 id="liability" className="docs-heading">7. Liability Limitation</h2>
            <p className="docs-text">Stats is provided "as is." We are not liable for:</p>
            <ul className="docs-list">
              <li>Any indirect, incidental, or consequential damages</li>
              <li>Loss of data, server disruption, or downtime</li>
              <li>Actions of server users outside the bot's intended functionality</li>
            </ul>

            <h2 id="indemnification" className="docs-heading">8. Indemnification</h2>
            <p className="docs-text">You agree to indemnify and hold Stats, its developers, and affiliates harmless from:</p>
            <ul className="docs-list">
              <li>Claims, damages, or losses resulting from your use of Stats</li>
              <li>Violation of these Terms or applicable law</li>
            </ul>

            <h2 id="changes-tos" className="docs-heading">9. Changes to the Service</h2>
            <p className="docs-text">Stats may update, modify, or remove features at any time.</p>
            <p className="docs-text">We will aim to communicate significant changes via our support channels, but ongoing use constitutes acceptance of updates.</p>

            <h2 id="termination" className="docs-heading">10. Termination</h2>
            <p className="docs-text">Stats may terminate or suspend access for:</p>
            <ul className="docs-list">
              <li>Violations of these Terms</li>
              <li>Breach of Discord policies</li>
              <li>Requests by authorized server admins for removal</li>
            </ul>
            <p className="docs-text">Data deletion may require explicit use of the <strong>Reset server and reset user</strong> features.</p>

            <h2 id="governing" className="docs-heading">11. Governing Law and Contact</h2>
            <p className="docs-text">These Terms are governed by applicable laws of the bot's operational jurisdiction.</p>
            <p className="docs-text">For questions or disputes, contact the developers and owner of Stats through the <a href="https://discord.gg/hreJvck8cK" className="docs-link" target="_blank" rel="noopener noreferrer">support discord server</a>.</p>
          </div>
        );

      case "Cookie Policy":
        return (
          <div className="docs-content">
            <h1 id="cookie-policy" className="docs-main-title">Cookie Policy</h1>
            
            <p className="docs-text">
              <strong>Effective Date:</strong> 22 February 2026<br />
              <strong>Last Updated:</strong> 22 February 2026
            </p>

            <h2 id="cookie-introduction" className="docs-heading">1. Introduction</h2>
            <p className="docs-text">
              This Cookie Policy explains how <strong>Stats</strong> ("we", "us", or "our") uses cookies and similar technologies on our website and web application (the "Service"). This policy provides you with clear information about what cookies are, how we use them, and your choices regarding their use.
            </p>
            <p className="docs-text">
              By using our Service, you consent to our use of cookies in accordance with this Cookie Policy.
            </p>

            <h2 id="what-are-cookies" className="docs-heading">2. What Are Cookies?</h2>
            <p className="docs-text">
              Cookies are small text files that are stored on your computer or mobile device when you visit a website. They are widely used to make websites work more efficiently and provide information to the website owners. Cookies help us:
            </p>
            <ul className="docs-list">
              <li>Keep you logged in securely</li>
              <li>Remember your preferences</li>
              <li>Understand how you use our Service</li>
              <li>Improve your user experience</li>
            </ul>

            <h2 id="types-of-cookies" className="docs-heading">3. Types of Cookies We Use</h2>
            
            <h3 className="docs-subheading">3.1 Essential Cookies (Strictly Necessary)</h3>
            <p className="docs-text">
              These cookies are essential for the Service to function properly and cannot be switched off in our systems. They are usually set in response to actions you take, such as logging in or filling in forms.
            </p>

            <div className="docs-table-container">
              <table className="docs-table">
                <thead>
                  <tr>
                    <th>Cookie Name</th>
                    <th>Purpose</th>
                    <th>Duration</th>
                    <th>Domain</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><code>session</code></td>
                    <td>Authenticates your identity and keeps you logged in. Contains a secure, randomly generated session identifier that links to your authenticated session on our servers.</td>
                    <td>30 days</td>
                    <td>statsbot.xyz</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="docs-text">
              <strong>Technical Details:</strong>
            </p>
            <ul className="docs-list">
              <li><strong>Type:</strong> HTTP-only cookie (cannot be accessed by JavaScript)</li>
              <li><strong>Security:</strong> Transmitted only over HTTPS in production</li>
              <li><strong>Content:</strong> Only contains a random session ID, never personal information</li>
              <li><strong>Required:</strong> Yes, without this cookie you cannot log in or use authenticated features</li>
            </ul>

            <h3 className="docs-subheading">3.2 Authentication Flow Cookies</h3>
            <p className="docs-text">
              These cookies are temporarily set during the Discord OAuth2 authentication process:
            </p>

            <div className="docs-table-container">
              <table className="docs-table">
                <thead>
                  <tr>
                    <th>Cookie Name</th>
                    <th>Purpose</th>
                    <th>Duration</th>
                    <th>Domain</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><code>state</code></td>
                    <td>Security cookie used during Discord login to prevent CSRF attacks</td>
                    <td>Session (deleted when browser closes)</td>
                    <td>statsbot.xyz</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="docs-subheading">3.3 Analytics and Performance Cookies</h3>
            <p className="docs-text">
              We may use analytics cookies to understand how visitors interact with our Service and improve its performance:
            </p>

            <div className="docs-table-container">
              <table className="docs-table">
                <thead>
                  <tr>
                    <th>Cookie Name</th>
                    <th>Purpose</th>
                    <th>Duration</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><code>_ga</code></td>
                    <td>Used to distinguish users (Google Analytics)</td>
                    <td>2 years</td>
                    <td>Google Analytics</td>
                  </tr>
                  <tr>
                    <td><code>_gid</code></td>
                    <td>Used to distinguish users (Google Analytics)</td>
                    <td>24 hours</td>
                    <td>Google Analytics</td>
                  </tr>
                  <tr>
                    <td><code>_gat</code></td>
                    <td>Used to throttle request rate (Google Analytics)</td>
                    <td>1 minute</td>
                    <td>Google Analytics</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="docs-text">
              <em>Note: These analytics cookies are optional and only set with your consent.</em>
            </p>

            <h2 id="third-party-cookies" className="docs-heading">4. Third-Party Cookies</h2>
            
            <h3 className="docs-subheading">4.1 Discord Cookies</h3>
            <p className="docs-text">
              When you log in through Discord, Discord may set its own cookies. These are governed by Discord's Privacy Policy and Cookie Policy:
            </p>
            <ul className="docs-list">
              <li><a href="https://discord.com/privacy" className="docs-link" target="_blank" rel="noopener noreferrer">Discord Privacy Policy</a></li>
              <li><a href="https://discord.com/cookie-policy" className="docs-link" target="_blank" rel="noopener noreferrer">Discord Cookie Policy</a></li>
            </ul>

            <h3 className="docs-subheading">4.2 Analytics Providers</h3>
            <p className="docs-text">
              If you consent to analytics, third-party providers like Google Analytics may set cookies. You can learn more about Google Analytics cookies here:
            </p>
            <ul className="docs-list">
              <li><a href="https://developers.google.com/analytics/devguides/collection/analyticsjs/cookie-usage" className="docs-link" target="_blank" rel="noopener noreferrer">Google Analytics Cookie Usage</a></li>
            </ul>

            <h2 id="how-we-use-cookies" className="docs-heading">5. How We Use Cookies</h2>
            <p className="docs-text">
              We use cookies to:
            </p>

            <h3 className="docs-subheading">5.1 Authentication and Security</h3>
            <ul className="docs-list">
              <li>Keep you securely logged in across sessions</li>
              <li>Protect against unauthorized access to your account</li>
              <li>Maintain the security of your authentication tokens</li>
              <li>Prevent CSRF (Cross-Site Request Forgery) attacks</li>
            </ul>

            <h3 className="docs-subheading">5.2 User Experience</h3>
            <ul className="docs-list">
              <li>Remember your selected Discord server between visits</li>
              <li>Maintain your session preferences</li>
              <li>Provide seamless navigation after login</li>
            </ul>

            <h3 className="docs-subheading">5.3 Analytics and Improvement (with consent)</h3>
            <ul className="docs-list">
              <li>Understand how users interact with our Service</li>
              <li>Identify technical issues and improve performance</li>
              <li>Analyze usage patterns to enhance features</li>
            </ul>

            <h2 id="your-cookie-choices" className="docs-heading">6. Your Cookie Choices</h2>

            <h3 className="docs-subheading">6.1 Browser Controls</h3>
            <p className="docs-text">
              Most web browsers allow you to control cookies through their settings. You can:
            </p>
            <ul className="docs-list">
              <li>View cookies stored on your device</li>
              <li>Delete individual or all cookies</li>
              <li>Block cookies from specific sites</li>
              <li>Block all third-party cookies</li>
              <li>Set preferences for cookie acceptance</li>
            </ul>

            <p className="docs-text">
              <strong>Browser-specific instructions:</strong>
            </p>
            <ul className="docs-list">
              <li><a href="https://support.google.com/chrome/answer/95647" className="docs-link" target="_blank" rel="noopener noreferrer">Chrome</a></li>
              <li><a href="https://support.mozilla.org/en-US/kb/enhanced-tracking-protection-firefox-desktop" className="docs-link" target="_blank" rel="noopener noreferrer">Firefox</a></li>
              <li><a href="https://support.apple.com/guide/safari/manage-cookies-sfri11471/mac" className="docs-link" target="_blank" rel="noopener noreferrer">Safari</a></li>
              <li><a href="https://support.microsoft.com/en-us/microsoft-edge/delete-cookies-in-microsoft-edge-63947406-40ac-c3b8-57b9-2a946a29ae09" className="docs-link" target="_blank" rel="noopener noreferrer">Edge</a></li>
            </ul>

            <h3 className="docs-subheading">6.2 Essential Cookies</h3>
            <p className="docs-text">
              Please note that blocking essential cookies (like our <code>session</code> cookie) will prevent you from using core features of our Service, including:
            </p>
            <ul className="docs-list">
              <li>Logging in to your account</li>
              <li>Accessing your Discord server statistics</li>
              <li>Using authenticated API endpoints</li>
            </ul>

            <h3 className="docs-subheading">6.3 Analytics Opt-Out</h3>
            <p className="docs-text">
              To opt-out of Google Analytics tracking across all websites:
            </p>
            <ul className="docs-list">
              <li><a href="https://tools.google.com/dlpage/gaoptout" className="docs-link" target="_blank" rel="noopener noreferrer">Google Analytics Opt-out Browser Add-on</a></li>
            </ul>

            <h2 id="data-stored" className="docs-heading">7. Data Stored in Our Cookies</h2>

            <h3 className="docs-subheading">7.1 What We DON'T Store in Cookies:</h3>
            <ul className="docs-list">
              <li>❌ Your Discord password</li>
              <li>❌ Your Discord access tokens</li>
              <li>❌ Your email address</li>
              <li>❌ Your personal messages</li>
              <li>❌ Financial information</li>
              <li>❌ Any permanently identifying information</li>
            </ul>

            <h3 className="docs-subheading">7.2 What We DO Store:</h3>
            <ul className="docs-list">
              <li>✅ <strong>Session Cookie:</strong> Only a randomly generated session identifier (e.g., "x7f8d9a3b2c1e5f6a8b9c0d1e2f3a4b5c")</li>
            </ul>

            <h3 className="docs-subheading">7.3 What's Stored on Our Servers:</h3>
            <p className="docs-text">
              When you're authenticated, we securely store on our servers:
            </p>
            <ul className="docs-list">
              <li>Your Discord user ID (public identifier)</li>
              <li>Your Discord username and avatar (public information)</li>
              <li>Your session expiration time</li>
              <li>Your IP address (temporarily for security auditing)</li>
            </ul>

            <h2 id="cookie-duration" className="docs-heading">8. Cookie Duration</h2>

            <div className="docs-table-container">
              <table className="docs-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Duration</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Authentication Cookie</td>
                    <td>30 days</td>
                    <td>Allows you to stay logged in without re-authenticating every visit</td>
                  </tr>
                  <tr>
                    <td>Session Cookie</td>
                    <td>Until browser close</td>
                    <td>Temporary cookies needed for specific operations</td>
                  </tr>
                  <tr>
                    <td>Persistent Preferences</td>
                    <td>Up to 30 days</td>
                    <td>Remembers your selected server between visits</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h2 id="security-measures" className="docs-heading">9. Security Measures</h2>
            <p className="docs-text">
              We implement the following security measures for our cookies:
            </p>
            <ul className="docs-list">
              <li><strong>HTTP-only Flag:</strong> Prevents JavaScript access to authentication cookies</li>
              <li><strong>Secure Flag:</strong> Cookies only transmitted over HTTPS (in production)</li>
              <li><strong>SameSite=Lax:</strong> Protects against CSRF attacks</li>
              <li><strong>Encryption:</strong> All cookie data is encrypted in transit</li>
              <li><strong>Random Generation:</strong> Session identifiers are cryptographically random</li>
              <li><strong>Server-side Validation:</strong> All cookies are validated on the server</li>
            </ul>

            <h2 id="cookie-policy-changes" className="docs-heading">10. Changes to This Policy</h2>
            <p className="docs-text">
              We may update this Cookie Policy from time to time to reflect changes in technology, legislation, or our practices. We encourage you to review this policy periodically. The "Last Updated" date at the top of this policy indicates when it was last revised.
            </p>

            <h2 id="your-rights-cookies" className="docs-heading">11. Your Rights</h2>
            <p className="docs-text">
              Depending on your location, you may have certain rights regarding your data:
            </p>

            <h3 className="docs-subheading">European Economic Area (GDPR)</h3>
            <ul className="docs-list">
              <li>Right to access your data</li>
              <li>Right to rectification</li>
              <li>Right to erasure ("right to be forgotten")</li>
              <li>Right to restrict processing</li>
              <li>Right to data portability</li>
            </ul>

            <h3 className="docs-subheading">California (CCPA/CPRA)</h3>
            <ul className="docs-list">
              <li>Right to know what personal information is collected</li>
              <li>Right to delete personal information</li>
              <li>Right to opt-out of the sale of personal information</li>
              <li>Right to non-discrimination</li>
            </ul>

            <h2 id="cookie-contact" className="docs-heading">12. Contact Us</h2>
            <p className="docs-text">
              If you have questions about our use of cookies or this policy, please contact us:
            </p>
            <ul className="docs-list">
              <li><strong>Discord:</strong> Join our <a href="https://discord.gg/hreJvck8cK" className="docs-link" target="_blank" rel="noopener noreferrer">Support Server</a></li>
            </ul>

            <h2 id="cookie-consent" className="docs-heading">13. Consent</h2>
            <p className="docs-text">
              By continuing to use our Service after this Cookie Policy has been displayed, you consent to our use of cookies as described in this policy.
            </p>

            <h3 className="docs-subheading">13.1 Consent Withdrawal</h3>
            <p className="docs-text">
              You can withdraw your consent at any time by:
            </p>
            <ul className="docs-list">
              <li>Clearing your browser cookies</li>
              <li>Adjusting your browser settings</li>
              <li>Contacting us for assistance</li>
            </ul>

            <h3 className="docs-subheading">Appendix: Cookie Details Reference Table</h3>
            
            <div className="docs-table-container">
              <table className="docs-table">
                <thead>
                  <tr>
                    <th>Cookie Name</th>
                    <th>Category</th>
                    <th>Purpose</th>
                    <th>Data Contained</th>
                    <th>Duration</th>
                    <th>HTTP-only</th>
                    <th>SameSite</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><code>session</code></td>
                    <td>Essential</td>
                    <td>Authentication</td>
                    <td>Random session ID</td>
                    <td>30 days</td>
                    <td>Yes</td>
                    <td>Lax</td>
                  </tr>
                  <tr>
                    <td><code>state</code></td>
                    <td>Essential</td>
                    <td>CSRF protection</td>
                    <td>Random token</td>
                    <td>Session</td>
                    <td>Yes</td>
                    <td>Strict</td>
                  </tr>
                  <tr>
                    <td><code>_ga</code></td>
                    <td>Analytics</td>
                    <td>Google Analytics ID</td>
                    <td>Anonymous ID</td>
                    <td>2 years</td>
                    <td>No</td>
                    <td>Lax</td>
                  </tr>
                  <tr>
                    <td><code>_gid</code></td>
                    <td>Analytics</td>
                    <td>Google Analytics ID</td>
                    <td>Anonymous ID</td>
                    <td>24 hours</td>
                    <td>No</td>
                    <td>Lax</td>
                  </tr>
                  <tr>
                    <td><code>_gat</code></td>
                    <td>Analytics</td>
                    <td>Rate limiting</td>
                    <td>Anonymous</td>
                    <td>1 minute</td>
                    <td>No</td>
                    <td>Lax</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="docs-text">
              <strong>Jurisdiction-Specific Notices:</strong>
            </p>
            <ul className="docs-list">
              <li><strong>For EU Users:</strong> We process cookies based on your consent (GDPR Article 6(1)(a)). Essential cookies are necessary for the provision of our Service (GDPR Article 6(1)(b)).</li>
              <li><strong>For California Users:</strong> We do not sell your personal information. Our use of cookies is for business purposes as defined by the CCPA.</li>
            </ul>

            <p className="docs-text">
              This Cookie Policy is part of and incorporated into our <a href="?page=privacy" className="docs-link">Privacy Policy</a> and <a href="?page=terms" className="docs-link">Terms of Service</a>.
            </p>
          </div>
        );

      default:
        return null;
    }
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

    /* Fixed Navbar Styles */
    .navbar-fixed-wrapper {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 1000;
      background-color: #0a0a0a;
    }

    .navbar-spacer {
      height: 80px;
    }

    .docs-page {
      background-color: #0a0a0a;
      min-height: calc(100vh - 200px);
      color: #ffffff;
    }

    .docs-container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 0 40px 60px;
    }

    /* Page Intro */
    .page-intro {
      text-align: center;
      margin-bottom: 30px;
      padding-top: 20px;
    }

    .page-title {
      font-size: 48px;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 16px;
      letter-spacing: -0.02em;
      position: relative;
      display: inline-block;
    }

    .page-title::after {
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

    .page-description {
      font-size: 20px;
      line-height: 1.6;
      color: #b0b0b0;
      max-width: 700px;
      margin: 0 auto;
    }

    .docs-main-content {
      display: flex;
      gap: 40px;
      position: relative;
    }

    /* Left Column - Menu */
    .docs-left {
      width: 240px;
      flex-shrink: 0;
    }

    .docs-menu {
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 20px;
      position: sticky;
      top: 100px;
      max-height: calc(100vh - 120px);
      overflow-y: auto;
      backdrop-filter: blur(10px);
    }

    .menu-category {
      margin-bottom: 20px;
    }

    .menu-category:last-child {
      margin-bottom: 0;
    }

    .category-title {
      font-size: 14px;
      font-weight: 600;
      color: #aa00ff;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 10px;
      padding-left: 4px;
    }

    .category-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .category-item {
      width: 100%;
      padding: 8px 12px;
      background: none;
      border: none;
      border-radius: 6px;
      color: #b0b0b0;
      font-size: 14px;
      text-align: left;
      cursor: pointer;
      transition: all 0.2s ease;
      margin-bottom: 2px;
    }

    .category-item:hover {
      background-color: #2a2a2a;
      color: #ffffff;
    }

    .category-item.active {
      color: #aa00ff;
      background-color: rgba(170, 0, 255, 0.1);
      font-weight: 500;
    }

    /* Center Column */
    .docs-center {
      flex: 1;
      max-width: 700px;
      margin: 0 auto;
    }

    /* Right Column - Table of Contents */
    .docs-right {
      width: 240px;
      flex-shrink: 0;
    }

    .docs-toc {
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 20px;
      position: sticky;
      top: 100px;
      max-height: calc(100vh - 120px);
      overflow-y: auto;
      backdrop-filter: blur(10px);
    }

    .toc-title {
      font-size: 16px;
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid #2a2a2a;
      padding-left: 4px;
    }

    .toc-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .toc-item {
      width: 100%;
      padding: 6px 12px;
      background: none;
      border: none;
      border-radius: 4px;
      color: #b0b0b0;
      font-size: 13px;
      text-align: left;
      cursor: pointer;
      transition: all 0.2s ease;
      margin-bottom: 2px;
      line-height: 1.4;
    }

    .toc-item:hover {
      background-color: #2a2a2a;
      color: #ffffff;
    }

    .toc-item.active {
      color: #aa00ff;
      background-color: rgba(170, 0, 255, 0.1);
      font-weight: 500;
    }

    /* Mobile TOC */
    .mobile-toc {
      display: none;
      margin-bottom: 30px;
    }

    .mobile-toc-toggle {
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 20px;
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      color: #ffffff;
      font-size: 16px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .mobile-toc-toggle:hover {
      border-color: #aa00ff;
      background-color: #222;
    }

    .mobile-toc-toggle svg {
      transition: transform 0.3s ease;
    }

    .mobile-toc-menu {
      margin-top: 10px;
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      padding: 16px;
      animation: slideDown 0.3s ease;
    }

    .mobile-toc-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .mobile-toc-item {
      width: 100%;
      padding: 12px 16px;
      background: none;
      border: none;
      border-radius: 8px;
      color: #b0b0b0;
      font-size: 14px;
      text-align: left;
      cursor: pointer;
      transition: all 0.2s ease;
      margin-bottom: 4px;
    }

    .mobile-toc-item:hover {
      background-color: #2a2a2a;
      color: #ffffff;
    }

    .mobile-toc-item.active {
      color: #aa00ff;
      background-color: rgba(170, 0, 255, 0.1);
      font-weight: 500;
    }

    @keyframes slideDown {
      from {
        opacity: 0;
        transform: translateY(-10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    /* Pagination */
    .pagination {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 40px 0;
      padding: 20px;
      background-color: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 12px;
      backdrop-filter: blur(10px);
    }

    .top-pagination {
      margin-bottom: 40px;
    }

    .bottom-pagination {
      margin-top: 60px;
    }

    .pagination-button {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 24px;
      background: none;
      border: 1px solid #2a2a2a;
      border-radius: 8px;
      color: #ffffff;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .pagination-button:not(.disabled):hover {
      background-color: #2a2a2a;
      border-color: #aa00ff;
      color: #aa00ff;
    }

    .pagination-button.disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    .pagination-pages {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: center;
    }

    .pagination-page {
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: none;
      border: 1px solid #2a2a2a;
      border-radius: 8px;
      color: #b0b0b0;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .pagination-page:hover {
      background-color: #2a2a2a;
      border-color: #aa00ff;
      color: #ffffff;
    }

    .pagination-page.active {
      background-color: #aa00ff;
      border-color: #aa00ff;
      color: #ffffff;
    }

    /* Content Wrapper */
    .docs-content-wrapper {
      min-height: 500px;
      animation: fadeIn 0.3s ease;
    }

    @keyframes fadeIn {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    /* Content Styles */
    .docs-content {
      color: #ffffff;
    }

    .docs-main-title {
      font-size: 42px;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 30px;
      letter-spacing: -0.02em;
      position: relative;
      display: inline-block;
    }

    .docs-main-title::after {
      content: '';
      position: absolute;
      bottom: -8px;
      left: 0;
      width: 80px;
      height: 3px;
      background-color: #aa00ff;
      border-radius: 2px;
    }

    .docs-heading {
      font-size: 32px;
      font-weight: 700;
      color: #ffffff;
      margin: 40px 0 20px;
      letter-spacing: -0.01em;
      position: relative;
      display: inline-block;
    }

    .docs-heading::after {
      content: '';
      position: absolute;
      bottom: -8px;
      left: 0;
      width: 60px;
      height: 3px;
      background-color: #aa00ff;
      border-radius: 2px;
    }

    .docs-subheading {
      font-size: 24px;
      font-weight: 600;
      color: #ffffff;
      margin: 30px 0 15px;
    }

    .docs-text {
      font-size: 16px;
      line-height: 1.7;
      color: #b0b0b0;
      margin-bottom: 20px;
    }

    .docs-list {
      list-style-type: none;
      padding: 0;
      margin: 20px 0 30px;
    }

    .docs-list li {
      font-size: 16px;
      line-height: 1.7;
      color: #b0b0b0;
      margin-bottom: 10px;
      padding-left: 24px;
      position: relative;
    }

    .docs-list li::before {
      content: '•';
      color: #aa00ff;
      font-size: 20px;
      position: absolute;
      left: 0;
      top: -2px;
    }

    .docs-list li strong {
      color: #ffffff;
    }

    .docs-link {
      color: #aa00ff;
      text-decoration: none;
      transition: color 0.2s ease;
    }

    .docs-link:hover {
      color: #8800cc;
      text-decoration: underline;
    }

    /* Table styles */
    .docs-table-container {
      overflow-x: auto;
      margin: 30px 0;
      border-radius: 12px;
      border: 1px solid #2a2a2a;
      background-color: #1a1a1a;
    }

    .docs-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }

    .docs-table th {
      background-color: #2a2a2a;
      color: #aa00ff;
      font-weight: 600;
      padding: 12px;
      text-align: left;
      border-bottom: 1px solid #3a3a3a;
    }

    .docs-table td {
      padding: 12px;
      color: #b0b0b0;
      border-bottom: 1px solid #2a2a2a;
    }

    .docs-table tr:last-child td {
      border-bottom: none;
    }

    .docs-table code {
      background-color: #2a2a2a;
      color: #aa00ff;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 13px;
    }

    .docs-table tr:hover td {
      background-color: #2a2a2a;
    }

    /* Loading States */
    .loading-container {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 400px;
      background-color: #0a0a0a;
    }

    /* Desktop Only */
    .desktop-only {
      display: block;
    }

    /* Scrollbar Styling */
    .docs-menu::-webkit-scrollbar,
    .docs-toc::-webkit-scrollbar {
      width: 8px;
    }

    .docs-menu::-webkit-scrollbar-track,
    .docs-toc::-webkit-scrollbar-track {
      background: #1a1a1a;
    }

    .docs-menu::-webkit-scrollbar-thumb,
    .docs-toc::-webkit-scrollbar-thumb {
      background: #2a2a2a;
      border-radius: 4px;
    }

    .docs-menu::-webkit-scrollbar-thumb:hover,
    .docs-toc::-webkit-scrollbar-thumb:hover {
      background: #aa00ff;
    }

    /* Responsive Design */
    @media (max-width: 1200px) {
      .docs-main-content {
        gap: 30px;
      }

      .docs-left,
      .docs-right {
        width: 200px;
      }
    }

    @media (max-width: 968px) {
      .docs-main-content {
        flex-direction: column;
      }

      .desktop-only {
        display: none;
      }

      .mobile-toc {
        display: block;
      }

      .docs-left,
      .docs-right {
        width: 100%;
      }

      .docs-center {
        max-width: 100%;
      }

      .docs-menu,
      .docs-toc {
        position: static;
        max-height: none;
        overflow-y: visible;
      }
    }

    @media (max-width: 768px) {
      .docs-container {
        padding: 0 20px 40px;
      }

      .page-title {
        font-size: 36px;
      }

      .page-description {
        font-size: 18px;
      }

      .pagination {
        flex-direction: column;
        gap: 20px;
      }

      .pagination-pages {
        order: -1;
        gap: 6px;
      }

      .pagination-page {
        width: 32px;
        height: 32px;
        font-size: 12px;
      }

      .pagination-button {
        padding: 10px 20px;
        font-size: 14px;
      }

      .docs-main-title {
        font-size: 32px;
      }

      .docs-heading {
        font-size: 28px;
      }

      .docs-subheading {
        font-size: 22px;
      }
    }

    @media (max-width: 480px) {
      .page-title {
        font-size: 28px;
      }

      .docs-main-title {
        font-size: 26px;
      }

      .docs-heading {
        font-size: 24px;
      }

      .docs-subheading {
        font-size: 20px;
      }

      .pagination-button {
        padding: 8px 16px;
        font-size: 13px;
      }

      .pagination-page {
        width: 35px;
        height: 35px;
        font-size: 14px;
      }

      .mobile-toc-toggle {
        padding: 14px 16px;
        font-size: 15px;
      }

      .mobile-toc-item {
        padding: 10px 14px;
        font-size: 13px;
      }

      .docs-table {
        font-size: 12px;
      }

      .docs-table th,
      .docs-table td {
        padding: 8px;
      }

      .docs-table code {
        font-size: 11px;
      }
    }
  `;

  return (
    <>
      <div className="navbar-fixed-wrapper" ref={navbarRef}>
        <NavBar isScrolled={isScrolled} />
      </div>
      
      <div className="navbar-spacer" />
      
      <div className="docs-page">
        <div className="docs-container">
          <div className="page-intro">
            <h1 className="page-title">{pageIntro.title}</h1>
            <p className="page-description">{pageIntro.description}</p>
          </div>

          {pageSections.length > 0 && (
            <div className="mobile-toc">
              <button 
                className="mobile-toc-toggle"
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              >
                <span>Page Contents</span>
                <svg 
                  width="20" 
                  height="20" 
                  viewBox="0 0 20 20" 
                  fill="currentColor"
                  style={{ transform: isMobileMenuOpen ? 'rotate(180deg)' : 'none' }}
                >
                  <path d="M5 7L10 12L15 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              
              {isMobileMenuOpen && (
                <div className="mobile-toc-menu">
                  <ul className="mobile-toc-list">
                    {pageSections.map((section) => (
                      <li key={section.id}>
                        <button
                          className={`mobile-toc-item ${activeSection === section.id ? 'active' : ''}`}
                          onClick={() => scrollToSection(section.id)}
                        >
                          {section.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="docs-main-content">
            <div className="docs-left desktop-only">
              <div className="docs-menu" ref={leftMenuRef}>
                {Object.entries(categories).map(([category, categoryPages]) => (
                  <div key={category} className="menu-category">
                    <h4 className="category-title">{category}</h4>
                    <ul className="category-list">
                      {categoryPages.map((page) => (
                        <li key={page}>
                          <button
                            className={`category-item ${currentPage === page ? 'active' : ''}`}
                            onClick={() => handlePageChange(page)}
                          >
                            {page}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>

            <div className="docs-center">
              <div className="pagination top-pagination">
                <button 
                  className={`pagination-button ${currentIndex === 0 ? 'disabled' : ''}`}
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                >
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Previous
                </button>
                
                <div className="pagination-pages">
                  {pages.map((page, index) => (
                    <button
                      key={page}
                      className={`pagination-page ${currentPage === page ? 'active' : ''}`}
                      onClick={() => handlePageChange(page)}
                    >
                      {index + 1}
                    </button>
                  ))}
                </div>
                
                <button 
                  className={`pagination-button ${currentIndex === totalPages - 1 ? 'disabled' : ''}`}
                  onClick={handleNext}
                  disabled={currentIndex === totalPages - 1}
                >
                  Next
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M8 4L14 10L8 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>

              <div className="docs-content-wrapper">
                {renderContent()}
              </div>

              <div className="pagination bottom-pagination">
                <button 
                  className={`pagination-button ${currentIndex === 0 ? 'disabled' : ''}`}
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                >
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Previous
                </button>
                
                <div className="pagination-pages">
                  {pages.map((page, index) => (
                    <button
                      key={page}
                      className={`pagination-page ${currentPage === page ? 'active' : ''}`}
                      onClick={() => handlePageChange(page)}
                    >
                      {index + 1}
                    </button>
                  ))}
                </div>
                
                <button 
                  className={`pagination-button ${currentIndex === totalPages - 1 ? 'disabled' : ''}`}
                  onClick={handleNext}
                  disabled={currentIndex === totalPages - 1}
                >
                  Next
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M8 4L14 10L8 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>

            <div className="docs-right desktop-only">
              {pageSections.length > 0 && (
                <div className="docs-toc" ref={rightTocRef}>
                  <h3 className="toc-title">On this page</h3>
                  <ul className="toc-list">
                    {pageSections.map((section) => (
                      <li key={section.id}>
                        <button
                          className={`toc-item ${activeSection === section.id ? 'active' : ''}`}
                          onClick={() => scrollToSection(section.id)}
                        >
                          {section.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <Footer />

      <style>{styles}</style>
    </>
  );
};

const root = createRoot(document.getElementById("app"));
root.render(
  <React.StrictMode>
    <DocsPage />
  </React.StrictMode>
);

export default DocsPage;