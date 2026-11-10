import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './components/header/header.component';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, HeaderComponent, MatIconModule],
  template: `
    <div class="app-layout">
      <!-- Angular Material Header -->
      <app-header></app-header>

      <!-- Main Router Outlet -->
      <main class="main-content">
        <router-outlet></router-outlet>
      </main>

      <!-- Material Footer -->
      <footer class="app-footer">
        <div class="container footer-content">
          <div class="footer-brand">
            <div class="brand-row">
              <mat-icon class="footer-icon">psychology</mat-icon>
              <span class="footer-title">MIND DECODED</span>
            </div>
            <p class="footer-desc">
              Daily automated cognitive synthesis & YouTube Shorts bridging psychology and generative artificial intelligence.
            </p>
          </div>

          <div class="footer-links">
            <span class="footer-heading">Platform & Syndication</span>
            <a href="/">Daily Insights</a>
            <a href="/shorts">YouTube Shorts</a>
            <a href="/rss.xml" target="_blank" rel="noopener">RSS Feed</a>
            <a href="/sitemap.xml" target="_blank" rel="noopener">XML Sitemap</a>
            <a href="https://www.youtube.com/channel/UCzjz2ArvjE4RgR_2k2o53mg" target="_blank" rel="noopener noreferrer">
              YouTube Channel ↗
            </a>
          </div>

          <div class="footer-bottom">
            <p>© 2026 Psychology & AI Research Portal. Powered by Google Gemini & Angular Material Design.</p>
          </div>
        </div>
      </footer>
    </div>
  `,
  styles: [`
    .app-layout {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }

    .main-content {
      flex: 1;
    }

    .app-footer {
      background-color: #0f172a;
      color: #94a3b8;
      padding: 48px 0 32px 0;
      border-top: 1px solid #1e293b;
    }

    .footer-content {
      display: grid;
      grid-template-columns: 1fr;
      gap: 36px;

      @media (min-width: 768px) {
        grid-template-columns: 2fr 1fr;
      }
    }

    .brand-row {
      display: flex;
      align-items: center;
      gap: 8px;
      color: #ffffff;
      margin-bottom: 8px;
    }

    .footer-icon {
      color: #3b82f6;
    }

    .footer-title {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }

    .footer-desc {
      font-size: 14px;
      line-height: 1.6;
      max-width: 480px;
      margin: 0;
    }

    .footer-links {
      display: flex;
      flex-direction: column;
      gap: 10px;

      .footer-heading {
        color: #ffffff;
        font-weight: 700;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
      }

      a {
        color: #94a3b8;
        text-decoration: none;
        font-size: 14px;
        transition: color 0.2s;

        &:hover {
          color: #38bdf8;
        }
      }
    }

    .footer-bottom {
      grid-column: 1 / -1;
      padding-top: 24px;
      border-top: 1px solid #1e293b;
      font-size: 12px;
      text-align: center;
      color: #64748b;
    }
  `]
})
export class AppComponent {}

