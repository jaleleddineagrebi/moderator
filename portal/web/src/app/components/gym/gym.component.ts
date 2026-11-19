import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { GOOGLE_CLIENT_ID } from '../../services/auth.service';

declare const google: any;

type Tab = 'month' | 'members' | 'coaches' | 'sports' | 'admins';

@Component({
  selector: 'app-gym',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
  <div class="gym container">
    <h1>Gym back office</h1>

    <ng-container *ngIf="!token()">
      <p class="muted">Restricted to admin accounts. Sign in with the Google account that is on the admin list.</p>
      <button class="btn primary" (click)="signIn()">Sign in with Google</button>
      <p class="err" *ngIf="error()">{{ error() }}</p>
    </ng-container>

    <ng-container *ngIf="token() && s() as d">
      <div class="bar">
        <label>Month <input type="month" [ngModel]="month()" (ngModelChange)="setMonth($event)"></label>
        <label>Currency <input class="cur" [(ngModel)]="currency" (ngModelChange)="saveCurrency()" maxlength="4"></label>
        <span class="muted">{{ d.me }}</span>
      </div>
      <p class="err" *ngIf="error()">{{ error() }}</p>

      <nav class="tabs">
        <button *ngFor="let t of tabs" [class.on]="tab() === t[0]" (click)="tab.set(t[0])">{{ t[1] }}</button>
      </nav>

      <!-- MONTHLY CALCULATION -->
      <section *ngIf="tab() === 'month'">
        <div class="kpis">
          <div class="kpi"><span>Active members</span><b>{{ d.report.activeMembers }}</b></div>
          <div class="kpi"><span>Fees due</span><b>{{ money(d.report.due) }}</b></div>
          <div class="kpi"><span>Collected</span><b>{{ money(d.report.collected) }}</b></div>
          <div class="kpi warn"><span>Outstanding</span><b>{{ money(d.report.outstanding) }}</b></div>
          <div class="kpi"><span>Coach commissions</span><b>{{ money(d.report.commissions) }}</b></div>
          <div class="kpi"><span>Still to pay coaches</span><b>{{ money(d.report.commissionsToPay) }}</b></div>
          <div class="kpi good"><span>Net for the gym</span><b>{{ money(d.report.net) }}</b></div>
        </div>
        <p class="muted">Commission = coach % × fees actually collected from that coach's members this month. Net = collected − commissions.</p>

        <h2>Coaches</h2>
        <table>
          <tr><th>Coach</th><th>%</th><th>Members</th><th>Due</th><th>Collected</th><th>Commission</th><th>If all paid</th><th>Paid out</th><th>Balance</th><th></th></tr>
          <tr *ngFor="let c of d.report.coaches">
            <td>{{ c.name }}</td><td>{{ c.commissionPct }}%</td><td>{{ c.members }}</td>
            <td>{{ money(c.due) }}</td><td>{{ money(c.collected) }}</td><td><b>{{ money(c.commission) }}</b></td>
            <td class="muted">{{ money(c.potential) }}</td><td>{{ money(c.paidOut) }}</td><td>{{ money(c.balance) }}</td>
            <td class="nowrap">
              <button class="btn sm" (click)="payCoach(c)" [disabled]="c.balance <= 0">Mark paid</button>
              <button class="btn sm ghost" *ngIf="c.paidOut > 0" (click)="post({action:'payout_delete', coachId:c.id, period:month()})">Undo</button>
            </td>
          </tr>
          <tr *ngIf="!d.report.coaches.length"><td colspan="10" class="muted">No coaches yet.</td></tr>
        </table>

        <h2>Members this month</h2>
        <table>
          <tr><th>Member</th><th>Sport</th><th>Coach</th><th>Due</th><th>Paid</th><th>Status</th><th></th></tr>
          <ng-container *ngFor="let m of d.members">
            <tr *ngIf="m.billed || m.paid > 0">
              <td>{{ m.name }}</td><td>{{ sportName(m.sportId) }}</td><td>{{ coachName(m.coachId) }}</td>
              <td>{{ money(m.due) }}</td><td>{{ money(m.paid) }}</td>
              <td><span class="pill" [ngClass]="m.status">{{ m.status }}</span></td>
              <td class="nowrap">
                <button class="btn sm" (click)="pay(m, m.due)" *ngIf="m.status !== 'paid'">Mark paid</button>
                <button class="btn sm ghost" (click)="payCustom(m)">Amount…</button>
                <button class="btn sm ghost" *ngIf="m.paid > 0" (click)="post({action:'payment_delete', memberId:m.id, period:month()})">Undo</button>
              </td>
            </tr>
          </ng-container>
        </table>

        <h2>By sport</h2>
        <table>
          <tr><th>Sport</th><th>Members</th><th>Due</th><th>Collected</th></tr>
          <tr *ngFor="let sp of d.report.sports"><td>{{ sp.name }}</td><td>{{ sp.members }}</td><td>{{ money(sp.due) }}</td><td>{{ money(sp.collected) }}</td></tr>
        </table>
      </section>

      <!-- MEMBERS -->
      <section *ngIf="tab() === 'members'">
        <h2>{{ mForm.id ? 'Edit member' : 'Add member' }}</h2>
        <form class="grid" (ngSubmit)="saveMember()">
          <input placeholder="Full name *" [(ngModel)]="mForm.name" name="n" required>
          <input placeholder="E-mail" [(ngModel)]="mForm.email" name="e">
          <input placeholder="Phone" [(ngModel)]="mForm.phone" name="p">
          <select [(ngModel)]="mForm.sportId" name="s" (ngModelChange)="onSportPick($event)">
            <option [ngValue]="null">Sport…</option>
            <option *ngFor="let sp of d.sports" [ngValue]="sp.id">{{ sp.name }}</option>
          </select>
          <select [(ngModel)]="mForm.coachId" name="c">
            <option [ngValue]="null">Coach…</option>
            <option *ngFor="let c of d.coaches" [ngValue]="c.id">{{ c.name }}</option>
          </select>
          <input type="number" min="0" step="0.01" placeholder="Monthly fee" [(ngModel)]="mForm.monthlyFee" name="f">
          <input type="date" [(ngModel)]="mForm.joinedAt" name="j" required>
          <label class="chk"><input type="checkbox" [(ngModel)]="mForm.active" name="a"> Active</label>
          <input placeholder="Notes" [(ngModel)]="mForm.notes" name="no">
          <span><button class="btn primary" type="submit">Save</button> <button class="btn ghost" type="button" *ngIf="mForm.id" (click)="resetMember()">Cancel</button></span>
        </form>
        <table>
          <tr><th>Name</th><th>Contact</th><th>Sport</th><th>Coach</th><th>Fee</th><th>Joined</th><th>Active</th><th></th></tr>
          <tr *ngFor="let m of d.members" [class.dim]="!m.active">
            <td>{{ m.name }}</td><td>{{ m.email || m.phone || '' }}</td><td>{{ sportName(m.sportId) }}</td><td>{{ coachName(m.coachId) }}</td>
            <td>{{ money(m.monthlyFee) }}</td><td>{{ m.joinedAt }}</td><td>{{ m.active ? 'yes' : 'no' }}</td>
            <td class="nowrap"><button class="btn sm" (click)="editMember(m)">Edit</button> <button class="btn sm danger" (click)="del('member_delete', m.id, m.name)">Delete</button></td>
          </tr>
        </table>
      </section>

      <!-- COACHES -->
      <section *ngIf="tab() === 'coaches'">
        <h2>{{ cForm.id ? 'Edit coach' : 'Add coach' }}</h2>
        <form class="grid" (ngSubmit)="saveCoach()">
          <input placeholder="Full name *" [(ngModel)]="cForm.name" name="n" required>
          <input placeholder="E-mail" [(ngModel)]="cForm.email" name="e">
          <input placeholder="Phone" [(ngModel)]="cForm.phone" name="p">
          <input type="number" min="0" max="100" step="0.1" placeholder="Commission % of fees" [(ngModel)]="cForm.commissionPct" name="pc">
          <label class="chk"><input type="checkbox" [(ngModel)]="cForm.active" name="a"> Active</label>
          <span><button class="btn primary" type="submit">Save</button> <button class="btn ghost" type="button" *ngIf="cForm.id" (click)="resetCoach()">Cancel</button></span>
        </form>
        <table>
          <tr><th>Name</th><th>Contact</th><th>Commission</th><th>Active</th><th></th></tr>
          <tr *ngFor="let c of d.coaches" [class.dim]="!c.active">
            <td>{{ c.name }}</td><td>{{ c.email || c.phone || '' }}</td><td>{{ c.commissionPct }}%</td><td>{{ c.active ? 'yes' : 'no' }}</td>
            <td class="nowrap"><button class="btn sm" (click)="editCoach(c)">Edit</button> <button class="btn sm danger" (click)="del('coach_delete', c.id, c.name)">Delete</button></td>
          </tr>
        </table>
      </section>

      <!-- SPORTS -->
      <section *ngIf="tab() === 'sports'">
        <h2>{{ spForm.id ? 'Edit sport' : 'Add sport' }}</h2>
        <form class="grid" (ngSubmit)="saveSport()">
          <input placeholder="Sport name *" [(ngModel)]="spForm.name" name="n" required>
          <input type="number" min="0" step="0.01" placeholder="Default monthly fee" [(ngModel)]="spForm.monthlyFee" name="f">
          <span><button class="btn primary" type="submit">Save</button> <button class="btn ghost" type="button" *ngIf="spForm.id" (click)="resetSport()">Cancel</button></span>
        </form>
        <table>
          <tr><th>Sport</th><th>Default fee</th><th></th></tr>
          <tr *ngFor="let sp of d.sports">
            <td>{{ sp.name }}</td><td>{{ money(sp.monthlyFee) }}</td>
            <td class="nowrap"><button class="btn sm" (click)="editSport(sp)">Edit</button> <button class="btn sm danger" (click)="del('sport_delete', sp.id, sp.name)">Delete</button></td>
          </tr>
        </table>
      </section>

      <!-- ADMINS -->
      <section *ngIf="tab() === 'admins'">
        <h2>Admin accounts ({{ d.fixedAdmins.length + d.admins.length }})</h2>
        <p class="muted">Only these Google accounts can open this page. Owner accounts are set on the server and cannot be removed here.</p>
        <ul>
          <li *ngFor="let e of d.fixedAdmins">{{ e }} <span class="pill paid">owner</span></li>
          <li *ngFor="let e of d.admins">{{ e }}
            <button class="btn sm danger" *ngIf="d.canManageAdmins" (click)="post({action:'admin_remove', email:e})">Remove</button></li>
        </ul>
        <form class="grid" *ngIf="d.canManageAdmins" (ngSubmit)="addAdmin()">
          <input type="email" placeholder="Google e-mail of the new admin" [(ngModel)]="newAdmin" name="ad" required>
          <span><button class="btn primary" type="submit">Add admin</button></span>
        </form>
      </section>
    </ng-container>
  </div>
  `,
  styles: [`
    .gym { padding: 24px 16px 64px; max-width: 1100px; margin: 0 auto; }
    h1 { margin: 0 0 12px; } h2 { margin: 28px 0 8px; font-size: 1.15rem; }
    .muted { color: #64748b; font-size: .9rem; } .err { color: #b91c1c; }
    .bar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
    .cur { width: 56px; }
    .tabs { display: flex; gap: 4px; flex-wrap: wrap; border-bottom: 1px solid #cbd5e1; margin: 12px 0; }
    .tabs button { background: none; border: 0; padding: 10px 14px; cursor: pointer; font: inherit; border-bottom: 3px solid transparent; }
    .tabs button.on { border-color: #4f46e5; font-weight: 600; }
    .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
    .kpi { background: #f1f5f9; border-radius: 10px; padding: 12px; display: flex; flex-direction: column; }
    .kpi span { font-size: .78rem; color: #475569; } .kpi b { font-size: 1.25rem; color: #0f172a; }
    .kpi.warn b { color: #b45309; } .kpi.good b { color: #15803d; }
    table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: .9rem; display: block; overflow-x: auto; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; white-space: nowrap; }
    tr.dim { opacity: .55; } .nowrap { white-space: nowrap; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; align-items: center; margin-bottom: 16px; }
    input, select { padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font: inherit; background: #fff; color: #0f172a; }
    .chk { display: flex; gap: 6px; align-items: center; }
    .btn { padding: 8px 14px; border-radius: 8px; border: 1px solid #cbd5e1; background: #fff; color: #0f172a; cursor: pointer; font: inherit; }
    .btn.primary { background: #4f46e5; border-color: #4f46e5; color: #fff; }
    .btn.sm { padding: 4px 9px; font-size: .8rem; } .btn.ghost { background: none; }
    .btn.danger { color: #b91c1c; border-color: #fecaca; } .btn:disabled { opacity: .4; cursor: default; }
    .pill { padding: 2px 8px; border-radius: 999px; font-size: .75rem; background: #e2e8f0; }
    .pill.paid { background: #dcfce7; color: #166534; } .pill.partial { background: #fef3c7; color: #92400e; } .pill.unpaid { background: #fee2e2; color: #991b1b; }
  `]
})
export class GymComponent implements OnInit {
  private readonly http = inject(HttpClient);

  readonly tabs: [Tab, string][] = [['month', 'Monthly'], ['members', 'Members'], ['coaches', 'Coaches'], ['sports', 'Sports'], ['admins', 'Admins']];
  readonly tab = signal<Tab>('month');
  readonly token = signal<string>('');
  readonly error = signal<string>('');
  readonly s = signal<any>(null);
  readonly month = signal<string>(new Date().toISOString().slice(0, 7));
  currency = '€';
  newAdmin = '';

  mForm: any = this.blankMember();
  cForm: any = { id: null, name: '', email: '', phone: '', commissionPct: 0, active: true };
  spForm: any = { id: null, name: '', monthlyFee: 0 };

  private tokenClient: any;
  private tokenExpiry = 0;

  ngOnInit(): void {
    try { this.currency = localStorage.getItem('gym_currency') || '€'; } catch { /* storage unavailable */ }
  }

  // ---------- auth: a Google access token, verified by the server on every call ----------
  signIn(): void {
    this.error.set('');
    if (typeof google === 'undefined' || !google.accounts?.oauth2) {
      this.error.set('Google sign-in is still loading, try again in a moment.');
      return;
    }
    this.tokenClient = this.tokenClient || google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: 'openid email profile',
      callback: (r: any) => {
        if (r?.access_token) {
          this.token.set(r.access_token);
          this.tokenExpiry = Date.now() + (Number(r.expires_in) || 3000) * 1000;
          this.load();
        } else {
          this.error.set('Google sign-in was cancelled.');
        }
      },
    });
    this.tokenClient.requestAccessToken({ prompt: '' });
  }

  private headers() { return { Authorization: `Bearer ${this.token()}` }; }

  private fail(err: any): void {
    if (err?.status === 403) {
      this.token.set('');
      this.s.set(null);
      this.error.set('This Google account is not on the admin list.');
    } else {
      this.error.set(err?.error?.error || 'Request failed');
    }
  }

  load(): void {
    if (this.tokenExpiry && Date.now() > this.tokenExpiry) { this.token.set(''); this.error.set('Session expired, sign in again.'); return; }
    this.http.get<any>('/api/gym', { headers: this.headers(), params: { month: this.month() } }).subscribe({
      next: (d) => { this.s.set(d); this.error.set(''); },
      error: (e) => this.fail(e),
    });
  }

  post(body: any, then?: () => void): void {
    this.http.post('/api/gym', body, { headers: this.headers() }).subscribe({
      next: () => { then?.(); this.load(); },
      error: (e) => this.fail(e),
    });
  }

  setMonth(m: string): void { if (m) { this.month.set(m); this.load(); } }
  saveCurrency(): void { try { localStorage.setItem('gym_currency', this.currency); } catch { /* ignore */ } }
  money(n: number): string { return `${(n ?? 0).toFixed(2)} ${this.currency}`; }
  sportName(id: string | null): string { return this.s()?.sports.find((x: any) => x.id === id)?.name || '-'; }
  coachName(id: string | null): string { return this.s()?.coaches.find((x: any) => x.id === id)?.name || '-'; }

  del(action: string, id: string, name: string): void {
    if (confirm(`Delete "${name}"? This cannot be undone.`)) this.post({ action, id });
  }

  // ---------- payments ----------
  pay(m: any, amount: number): void {
    this.post({ action: 'payment_set', memberId: m.id, period: this.month(), amount, method: 'cash' });
  }
  payCustom(m: any): void {
    const v = prompt(`Amount received from ${m.name} for ${this.month()}`, String(m.due || m.monthlyFee));
    const n = v === null ? NaN : Number(v.replace(',', '.'));
    if (Number.isFinite(n) && n >= 0) this.pay(m, n);
  }
  payCoach(c: any): void {
    this.post({ action: 'payout_set', coachId: c.id, period: this.month(), amount: c.commission });
  }

  // ---------- members ----------
  private blankMember() {
    return { id: null, name: '', email: '', phone: '', sportId: null, coachId: null, monthlyFee: 0, joinedAt: new Date().toISOString().slice(0, 10), active: true, notes: '' };
  }
  onSportPick(id: string | null): void {
    const sp = this.s()?.sports.find((x: any) => x.id === id);
    if (sp && !this.mForm.monthlyFee) this.mForm.monthlyFee = sp.monthlyFee;
  }
  editMember(m: any): void { this.mForm = { ...m }; window.scrollTo({ top: 0, behavior: 'smooth' }); }
  resetMember(): void { this.mForm = this.blankMember(); }
  saveMember(): void { this.post({ action: 'member_save', ...this.mForm }, () => this.resetMember()); }

  // ---------- coaches ----------
  editCoach(c: any): void { this.cForm = { ...c }; }
  resetCoach(): void { this.cForm = { id: null, name: '', email: '', phone: '', commissionPct: 0, active: true }; }
  saveCoach(): void { this.post({ action: 'coach_save', ...this.cForm }, () => this.resetCoach()); }

  // ---------- sports ----------
  editSport(sp: any): void { this.spForm = { ...sp }; }
  resetSport(): void { this.spForm = { id: null, name: '', monthlyFee: 0 }; }
  saveSport(): void { this.post({ action: 'sport_save', ...this.spForm }, () => this.resetSport()); }

  // ---------- admins ----------
  addAdmin(): void { this.post({ action: 'admin_add', email: this.newAdmin }, () => (this.newAdmin = '')); }
}
