import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../services/auth.service';
import { AnalyticsService } from '../../services/analytics.service';
import { Title, Meta } from '@angular/platform-browser';

@Component({
  selector: 'app-contact',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <div class="contact-page container">
      <!-- Header -->
      <header class="contact-hero">
        <div class="hero-badge">
          <mat-icon class="badge-icon">mail_outline</mat-icon>
          <span>Connect with Mind Decoded</span>
        </div>
        <h1 class="hero-title">
          Get in <span class="text-gradient">Touch</span>
        </h1>
        <p class="hero-subtitle">
          Have a cognitive science topic we should decode next, a research collaboration, or a sponsorship inquiry? Send us a message below.
        </p>
      </header>

      <div class="contact-grid">
        <!-- Left Column: Contact Form Card -->
        <mat-card class="contact-form-card mat-elevation-z2">
          <div *ngIf="submitted()" class="success-banner">
            <div class="success-icon-wrap">
              <mat-icon class="success-icon">check_circle</mat-icon>
            </div>
            <h3>Message Sent Successfully!</h3>
            <p>{{ successMessage() }}</p>
            <button mat-stroked-button color="primary" (click)="resetForm()">
              <mat-icon>add_comment</mat-icon>
              <span>Send Another Message</span>
            </button>
          </div>

          <form *ngIf="!submitted()" (ngSubmit)="onSubmit()" class="contact-form" novalidate>
            <h2 class="form-heading">Send a Message</h2>

            <div class="form-row-two">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Your Name</mat-label>
                <input
                  matInput
                  name="name"
                  [(ngModel)]="name"
                  placeholder="Dr. Jane Doe"
                  required
                  maxlength="120"
                />
                <mat-icon matSuffix>person_outline</mat-icon>
              </mat-form-field>

              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Email Address</mat-label>
                <input
                  matInput
                  type="email"
                  name="email"
                  [(ngModel)]="email"
                  placeholder="you@domain.com"
                  required
                  maxlength="160"
                />
                <mat-icon matSuffix>alternate_email</mat-icon>
              </mat-form-field>
            </div>

            <div class="form-row-two">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Inquiry Category</mat-label>
                <mat-select name="category" [(ngModel)]="category">
                  <mat-option value="topic_suggestion">Suggest a Video / Article Topic</mat-option>
                  <mat-option value="research">Research & AI Collaboration</mat-option>
                  <mat-option value="sponsorship">Sponsorship & Media Inquiry</mat-option>
                  <mat-option value="feedback">Portal Feedback / Support</mat-option>
                </mat-select>
              </mat-form-field>

              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Subject</mat-label>
                <input
                  matInput
                  name="subject"
                  [(ngModel)]="subject"
                  placeholder="What is this regarding?"
                  maxlength="200"
                />
                <mat-icon matSuffix>subject</mat-icon>
              </mat-form-field>
            </div>

            <!-- Hidden honeypot field against bots -->
            <input
              type="text"
              name="website"
              [(ngModel)]="websiteHoneypot"
              tabindex="-1"
              autocomplete="off"
              class="honeypot-field"
            />

            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Your Message</mat-label>
              <textarea
                matInput
                name="message"
                [(ngModel)]="message"
                rows="6"
                placeholder="Share your question, psychological phenomenon suggestion, or collaboration details..."
                required
                maxlength="4000"
              ></textarea>
              <mat-hint align="end">{{ message.length }} / 4000</mat-hint>
            </mat-form-field>

            <div *ngIf="errorMessage()" class="error-banner">
              <mat-icon>error_outline</mat-icon>
              <span>{{ errorMessage() }}</span>
            </div>

            <div class="form-actions">
              <button
                mat-flat-button
                color="primary"
                type="submit"
                class="submit-btn"
                [disabled]="isSubmitting()"
              >
                <mat-spinner *ngIf="isSubmitting()" diameter="20" class="btn-spinner"></mat-spinner>
                <mat-icon *ngIf="!isSubmitting()">send</mat-icon>
                <span>{{ isSubmitting() ? 'Sending...' : 'Send Message' }}</span>
              </button>
            </div>
          </form>
        </mat-card>

        <!-- Right Column: Channel & Research Info Cards -->
        <aside class="contact-sidebar">
          <div class="info-card">
            <div class="info-icon-box blue-box">
              <mat-icon>psychology</mat-icon>
            </div>
            <div>
              <h3>Suggest a Brain Test or Paradox</h3>
              <p>
                Our AI + neuroscience pipeline publishes daily articles and YouTube Shorts. Tell us which cognitive bias or AI paradox we should dissect next.
              </p>
            </div>
          </div>

          <div class="info-card">
            <div class="info-icon-box red-box">
              <mat-icon>smart_display</mat-icon>
            </div>
            <div>
              <h3>Official YouTube Channel</h3>
              <p>Watch daily 60-second Shorts and deep-dive widescreen documentaries on Mind Decoded.</p>
              <a
                href="https://www.youtube.com/channel/UCzjz2ArvjE4RgR_2k2o53mg"
                target="_blank"
                rel="noopener noreferrer"
                class="info-link"
              >
                <span>Visit Mind Decoded on YouTube</span>
                <mat-icon>open_in_new</mat-icon>
              </a>
            </div>
          </div>

          <div class="info-card">
            <div class="info-icon-box purple-box">
              <mat-icon>rss_feed</mat-icon>
            </div>
            <div>
              <h3>Research Syndication & RSS</h3>
              <p>Subscribe to our automated XML feed to integrate daily cognitive science insights into your reader.</p>
              <a href="/rss.xml" target="_blank" rel="noopener" class="info-link">
                <span>Open RSS 2.0 Feed</span>
                <mat-icon>arrow_forward</mat-icon>
              </a>
            </div>
          </div>
        </aside>
      </div>
    </div>
  `,
  styles: [`
    .contact-page {
      padding: 44px 16px 88px 16px;
      max-width: 1120px;
    }

    .contact-hero {
      text-align: center;
      max-width: 720px;
      margin: 0 auto 44px auto;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #2563eb;
      background-color: #eff6ff;
      padding: 6px 16px;
      border-radius: 9999px;
      margin-bottom: 16px;

      .badge-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }
    }

    .hero-title {
      font-size: 38px;
      font-weight: 800;
      color: #0f172a;
      margin: 0 0 12px 0;
      letter-spacing: -0.02em;

      @media (min-width: 768px) {
        font-size: 46px;
      }
    }

    .text-gradient {
      background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #7c3aed 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero-subtitle {
      font-size: 17px;
      color: #64748b;
      line-height: 1.6;
      margin: 0;
    }

    .contact-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 32px;
      align-items: start;

      @media (min-width: 960px) {
        grid-template-columns: 1.6fr 1fr;
      }
    }

    .contact-form-card {
      padding: 32px 28px;
      border-radius: 20px;
      border: 1px solid #e2e8f0;
      background: #ffffff;
    }

    .form-heading {
      font-size: 22px;
      font-weight: 700;
      color: #0f172a;
      margin: 0 0 24px 0;
    }

    .form-row-two {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;

      @media (min-width: 640px) {
        grid-template-columns: 1fr 1fr;
      }
    }

    .full-width {
      width: 100%;
    }

    .honeypot-field {
      position: absolute;
      left: -9999px;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }

    .error-banner {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 16px;
      margin: 8px 0 16px 0;
      border-radius: 12px;
      background-color: #fef2f2;
      border: 1px solid #fecaca;
      color: #b91c1c;
      font-size: 14px;
      font-weight: 500;
    }

    .form-actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 12px;
    }

    .submit-btn {
      height: 46px;
      padding: 0 28px;
      border-radius: 12px;
      font-weight: 600;
      font-size: 15px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .btn-spinner {
      display: inline-block;
      margin-right: 8px;
    }

    .success-banner {
      text-align: center;
      padding: 36px 16px;

      .success-icon-wrap {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        background-color: #dcfce7;
        color: #16a34a;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 16px auto;
      }

      .success-icon {
        font-size: 36px;
        width: 36px;
        height: 36px;
      }

      h3 {
        font-size: 24px;
        font-weight: 800;
        color: #0f172a;
        margin: 0 0 8px 0;
      }

      p {
        font-size: 15px;
        color: #475569;
        max-width: 420px;
        margin: 0 auto 24px auto;
        line-height: 1.6;
      }
    }

    .contact-sidebar {
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .info-card {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      padding: 22px;
      border-radius: 18px;
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      box-shadow: 0 4px 12px -4px rgba(15, 23, 42, 0.05);

      h3 {
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 6px 0;
      }

      p {
        font-size: 14px;
        color: #64748b;
        line-height: 1.55;
        margin: 0;
      }
    }

    .info-icon-box {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;

      &.blue-box {
        background-color: #eff6ff;
        color: #2563eb;
      }
      &.red-box {
        background-color: #fef2f2;
        color: #dc2626;
      }
      &.purple-box {
        background-color: #f3e8ff;
        color: #7c3aed;
      }
    }

    .info-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-top: 10px;
      font-size: 13px;
      font-weight: 700;
      color: #2563eb;
      text-decoration: none;

      &:hover {
        text-decoration: underline;
      }

      mat-icon {
        font-size: 15px;
        width: 15px;
        height: 15px;
      }
    }
  `]
})
export class ContactComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly analytics = inject(AnalyticsService);
  private readonly titleService = inject(Title);
  private readonly metaService = inject(Meta);

  name = '';
  email = '';
  category = 'topic_suggestion';
  subject = '';
  message = '';
  websiteHoneypot = '';

  isSubmitting = signal<boolean>(false);
  submitted = signal<boolean>(false);
  errorMessage = signal<string>('');
  successMessage = signal<string>('Thank you! Your message has been received by the Mind Decoded team.');

  ngOnInit(): void {
    this.titleService.setTitle('Contact Us — Mind Decoded | Psychology & AI Research Portal');
    this.metaService.updateTag({
      name: 'description',
      content: 'Contact Mind Decoded to suggest a psychology or AI topic, collaborate on cognitive science research, or inquire about sponsorships.'
    });

    const user = this.auth.currentUser();
    if (user) {
      this.name = user.name || '';
      this.email = user.email || '';
    }

    this.analytics.loadVisibilitySummary();
    this.analytics.trackPageView('/contact');
  }

  onSubmit(): void {
    this.errorMessage.set('');

    if (!this.name.trim() || this.name.trim().length < 2) {
      this.errorMessage.set('Please enter your name.');
      return;
    }
    if (!this.email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim())) {
      this.errorMessage.set('Please enter a valid email address.');
      return;
    }
    if (!this.message.trim() || this.message.trim().length < 10) {
      this.errorMessage.set('Please write a message of at least 10 characters.');
      return;
    }

    this.isSubmitting.set(true);
    this.http.post<{ ok: boolean; message?: string; error?: string }>('/api/contact', {
      name: this.name.trim(),
      email: this.email.trim(),
      category: this.category,
      subject: this.subject.trim(),
      message: this.message.trim(),
      website: this.websiteHoneypot,
    }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.submitted.set(true);
        if (res?.message) {
          this.successMessage.set(res.message);
        }
        this.analytics.trackEvent('contact_submit', {
          category: this.category,
        });
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.errorMessage.set(err?.error?.error || 'Could not send message right now. Please try again.');
      }
    });
  }

  resetForm(): void {
    this.subject = '';
    this.message = '';
    this.errorMessage.set('');
    this.submitted.set(false);
  }
}

