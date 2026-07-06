import React from "react";

const Footer = () => {
  return (
    <footer className="footer">
      <div className="footer-container">
        <div className="footer-links">
          <a 
            href="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=277293943856&integration_type=0&scope=bot+applications.commands" 
            target="_blank" 
            rel="noopener noreferrer"
            className="footer-link"
          >
            Invite bot
          </a>
          <span className="footer-separator">|</span>
          
          <a 
            href="https://discord.gg/hreJvck8cK" 
            target="_blank" 
            rel="noopener noreferrer"
            className="footer-link"
          >
            Support
          </a>
          <span className="footer-separator">|</span>
          
          <a 
            href="/Premium/" 
            className="footer-link premium-link"
          >
            Premium
          </a>
          <span className="footer-separator">|</span>
          
          <a 
            href="/docs/?page=privacy" 
            className="footer-link"
          >
            Privacy Policy
          </a>
          <span className="footer-separator">|</span>
          
          <a 
            href="/docs/?page=terms" 
            className="footer-link"
          >
            Terms Of Service
          </a>
          <span className="footer-separator">|</span>
          
          <a 
            href="/docs/?page=cookies" 
            className="footer-link"
          >
            Cookie Policy
          </a>
        </div>
        
        <div className="footer-copyright">
          <span className="copyright-symbol">©️</span> 2026 StatsHQ. All Rights Reserved.
        </div>
      </div>

      <style jsx>{`
        .footer {
          background-color: #0a0a0a;
          border-top: 1px solid #232323;
          padding: 40px 0 30px;
          margin-top: 60px;
          width: 100%;
        }

        .footer-container {
          max-width: 1400px;
          margin: 0 auto;
          padding: 0 40px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 20px;
        }

        .footer-links {
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          align-items: center;
          gap: 15px;
        }

        .footer-link {
          color: #b0b0b0;
          text-decoration: none;
          font-size: 16px;
          transition: all 0.2s ease;
          white-space: nowrap;
        }

        .footer-link:hover {
          color: #aa00ff;
        }

        .premium-link {
          position: relative;
          font-weight: 500;
        }

        .premium-link:hover {
          color: #ffd700;
          text-shadow: 0 0 10px rgba(255, 215, 0, 0.5);
        }

        .footer-separator {
          color: #404040;
          font-size: 16px;
        }

        .footer-copyright {
          color: #808080;
          font-size: 14px;
          display: flex;
          align-items: center;
          gap: 5px;
        }

        .copyright-symbol {
          font-size: 16px;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
          .footer {
            padding: 30px 0 20px;
          }

          .footer-container {
            padding: 0 20px;
          }

          .footer-links {
            gap: 10px;
          }

          .footer-link {
            font-size: 14px;
          }

          .footer-separator {
            font-size: 14px;
          }

          .footer-copyright {
            font-size: 13px;
            text-align: center;
          }
        }

        @media (max-width: 480px) {
          .footer-links {
            gap: 8px;
          }

          .footer-link {
            font-size: 13px;
          }

          .footer-separator {
            font-size: 13px;
          }
        }
      `}</style>
    </footer>
  );
};

export default Footer;