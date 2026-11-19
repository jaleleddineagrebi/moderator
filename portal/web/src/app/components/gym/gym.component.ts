import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Meta } from '@angular/platform-browser';

type Tab = 'month' | 'members' | 'coaches' | 'sports';

const STATUS_FR: Record<string, string> = { paid: 'payé', partial: 'partiel', unpaid: 'impayé', 'n/a': '-' };

@Component({
  selector: 'app-gym',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
  <div class="gym container">
    <h1>Gestion de la salle</h1>

    <ng-container *ngIf="!token()">
      <p class="muted">Espace réservé. Connectez-vous avec votre identifiant et votre mot de passe.</p>
      <form class="login" (ngSubmit)="login()">
        <input type="text" autocomplete="username" autocapitalize="none" placeholder="Identifiant" [(ngModel)]="username" name="us" required>
        <input type="password" autocomplete="current-password" placeholder="Mot de passe" [(ngModel)]="password" name="pw" required>
        <button class="btn primary" type="submit" [disabled]="busy()">Se connecter</button>
      </form>
      <p class="err" *ngIf="error()">{{ error() }}</p>
    </ng-container>

    <ng-container *ngIf="token() && s()">
      <ng-container *ngIf="s() as d">
      <div class="bar">
        <label>Mois <input type="month" [ngModel]="month()" (ngModelChange)="setMonth($event)"></label>
        <span class="muted">{{ d.me }}</span>
        <button class="btn sm ghost" (click)="logout()">Se déconnecter</button>
      </div>
      <p class="err" *ngIf="error()">{{ error() }}</p>

      <nav class="tabs">
        <button *ngFor="let t of tabs" [class.on]="tab() === t[0]" (click)="tab.set(t[0])">{{ t[1] }}</button>
      </nav>

      <!-- CALCUL MENSUEL -->
      <section *ngIf="tab() === 'month'">
        <div class="kpis">
          <div class="kpi"><span>Membres actifs</span><b>{{ d.report.activeMembers }}</b></div>
          <div class="kpi"><span>Cotisations dues</span><b>{{ money(d.report.due) }}</b></div>
          <div class="kpi"><span>Encaissé</span><b>{{ money(d.report.collected) }}</b></div>
          <div class="kpi warn"><span>Reste à encaisser</span><b>{{ money(d.report.outstanding) }}</b></div>
          <div class="kpi"><span>Commissions coachs</span><b>{{ money(d.report.commissions) }}</b></div>
          <div class="kpi"><span>Reste à payer aux coachs</span><b>{{ money(d.report.commissionsToPay) }}</b></div>
          <div class="kpi good"><span>Net pour la salle</span><b>{{ money(d.report.net) }}</b></div>
        </div>
        <p class="muted">Commission = % du coach × cotisations réellement encaissées auprès de ses membres ce mois-ci. Net = encaissé − commissions.</p>

        <h2>Coachs</h2>
        <table>
          <tr><th>Coach</th><th>%</th><th>Membres</th><th>Dû</th><th>Encaissé</th><th>Commission</th><th>Si tout payé</th><th>Déjà versé</th><th>Solde</th><th></th></tr>
          <tr *ngFor="let c of d.report.coaches">
            <td>{{ c.name }}</td><td>{{ c.commissionPct }}%</td><td>{{ c.members }}</td>
            <td>{{ money(c.due) }}</td><td>{{ money(c.collected) }}</td><td><b>{{ money(c.commission) }}</b></td>
            <td class="muted">{{ money(c.potential) }}</td><td>{{ money(c.paidOut) }}</td><td>{{ money(c.balance) }}</td>
            <td class="nowrap">
              <button class="btn sm" (click)="payCoach(c)" [disabled]="c.balance <= 0">Marquer payé</button>
              <button class="btn sm ghost" *ngIf="c.paidOut > 0" (click)="post({action:'payout_delete', coachId:c.id, period:month()})">Annuler</button>
            </td>
          </tr>
          <tr *ngIf="!d.report.coaches.length"><td colspan="10" class="muted">Aucun coach pour le moment.</td></tr>
        </table>

        <h2>Membres ce mois-ci</h2>
        <table>
          <tr><th>Membre</th><th>Sport</th><th>Coach</th><th>Dû</th><th>Payé</th><th>Statut</th><th></th></tr>
          <ng-container *ngFor="let m of d.members">
            <tr *ngIf="m.billed || m.paid > 0">
              <td>{{ m.name }}</td><td>{{ sportName(m.sportId) }}</td><td>{{ coachName(m.coachId) }}</td>
              <td>{{ money(m.due) }}</td><td>{{ money(m.paid) }}</td>
              <td><span class="pill" [ngClass]="m.status">{{ statusFr(m.status) }}</span></td>
              <td class="nowrap">
                <button class="btn sm" (click)="pay(m, m.due)" *ngIf="m.status !== 'paid'">Marquer payé</button>
                <button class="btn sm ghost" (click)="payCustom(m)">Montant…</button>
                <button class="btn sm ghost" *ngIf="m.paid > 0" (click)="post({action:'payment_delete', memberId:m.id, period:month()})">Annuler</button>
              </td>
            </tr>
          </ng-container>
        </table>

        <h2>Par sport</h2>
        <table>
          <tr><th>Sport</th><th>Membres</th><th>Dû</th><th>Encaissé</th></tr>
          <tr *ngFor="let sp of d.report.sports"><td>{{ sp.name }}</td><td>{{ sp.members }}</td><td>{{ money(sp.due) }}</td><td>{{ money(sp.collected) }}</td></tr>
        </table>
      </section>

      <!-- MEMBRES -->
      <section *ngIf="tab() === 'members'">
        <h2>{{ mForm.id ? 'Modifier le membre' : 'Ajouter un membre' }}</h2>
        <form class="grid" (ngSubmit)="saveMember()">
          <input placeholder="Nom complet *" [(ngModel)]="mForm.name" name="n" required>
          <input placeholder="E-mail" [(ngModel)]="mForm.email" name="e">
          <input placeholder="Téléphone" [(ngModel)]="mForm.phone" name="p">
          <select [(ngModel)]="mForm.sportId" name="s" (ngModelChange)="onSportPick($event)">
            <option [ngValue]="null">Sport…</option>
            <option *ngFor="let sp of d.sports" [ngValue]="sp.id">{{ sp.name }}</option>
          </select>
          <select [(ngModel)]="mForm.coachId" name="c">
            <option [ngValue]="null">Coach…</option>
            <option *ngFor="let c of d.coaches" [ngValue]="c.id">{{ c.name }}</option>
          </select>
          <input type="number" min="0" step="0.001" placeholder="Cotisation mensuelle (DT)" [(ngModel)]="mForm.monthlyFee" name="f">
          <input type="date" [(ngModel)]="mForm.joinedAt" name="j" required>
          <label class="chk"><input type="checkbox" [(ngModel)]="mForm.active" name="a"> Actif</label>
          <input placeholder="Remarques" [(ngModel)]="mForm.notes" name="no">
          <span><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="mForm.id" (click)="resetMember()">Annuler</button></span>
        </form>
        <table>
          <tr><th>Nom</th><th>Contact</th><th>Sport</th><th>Coach</th><th>Cotisation</th><th>Inscrit le</th><th>Actif</th><th></th></tr>
          <tr *ngFor="let m of d.members" [class.dim]="!m.active">
            <td>{{ m.name }}</td><td>{{ m.email || m.phone || '' }}</td><td>{{ sportName(m.sportId) }}</td><td>{{ coachName(m.coachId) }}</td>
            <td>{{ money(m.monthlyFee) }}</td><td>{{ m.joinedAt }}</td><td>{{ m.active ? 'oui' : 'non' }}</td>
            <td class="nowrap"><button class="btn sm" (click)="editMember(m)">Modifier</button> <button class="btn sm danger" (click)="del('member_delete', m.id, m.name)">Supprimer</button></td>
          </tr>
        </table>
      </section>

      <!-- COACHS -->
      <section *ngIf="tab() === 'coaches'">
        <h2>{{ cForm.id ? 'Modifier le coach' : 'Ajouter un coach' }}</h2>
        <form class="grid" (ngSubmit)="saveCoach()">
          <input placeholder="Nom complet *" [(ngModel)]="cForm.name" name="n" required>
          <input placeholder="E-mail" [(ngModel)]="cForm.email" name="e">
          <input placeholder="Téléphone" [(ngModel)]="cForm.phone" name="p">
          <input type="number" min="0" max="100" step="0.1" placeholder="Commission en % des cotisations" [(ngModel)]="cForm.commissionPct" name="pc">
          <label class="chk"><input type="checkbox" [(ngModel)]="cForm.active" name="a"> Actif</label>
          <span><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="cForm.id" (click)="resetCoach()">Annuler</button></span>
        </form>
        <table>
          <tr><th>Nom</th><th>Contact</th><th>Commission</th><th>Actif</th><th></th></tr>
          <tr *ngFor="let c of d.coaches" [class.dim]="!c.active">
            <td>{{ c.name }}</td><td>{{ c.email || c.phone || '' }}</td><td>{{ c.commissionPct }}%</td><td>{{ c.active ? 'oui' : 'non' }}</td>
            <td class="nowrap"><button class="btn sm" (click)="editCoach(c)">Modifier</button> <button class="btn sm danger" (click)="del('coach_delete', c.id, c.name)">Supprimer</button></td>
          </tr>
        </table>
      </section>

      <!-- SPORTS -->
      <section *ngIf="tab() === 'sports'">
        <h2>{{ spForm.id ? 'Modifier le sport' : 'Ajouter un sport' }}</h2>
        <form class="grid" (ngSubmit)="saveSport()">
          <input placeholder="Nom du sport *" [(ngModel)]="spForm.name" name="n" required>
          <input type="number" min="0" step="0.001" placeholder="Cotisation mensuelle par défaut (DT)" [(ngModel)]="spForm.monthlyFee" name="f">
          <span><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="spForm.id" (click)="resetSport()">Annuler</button></span>
        </form>
        <table>
          <tr><th>Sport</th><th>Cotisation par défaut</th><th></th></tr>
          <tr *ngFor="let sp of d.sports">
            <td>{{ sp.name }}</td><td>{{ money(sp.monthlyFee) }}</td>
            <td class="nowrap"><button class="btn sm" (click)="editSport(sp)">Modifier</button> <button class="btn sm danger" (click)="del('sport_delete', sp.id, sp.name)">Supprimer</button></td>
          </tr>
        </table>
      </section>

      </ng-container>
    </ng-container>
  </div>
  `,
  styles: [`
    .gym { padding: 24px 16px 64px; max-width: 1100px; margin: 0 auto; }
    h1 { margin: 0 0 12px; } h2 { margin: 28px 0 8px; font-size: 1.15rem; }
    .muted { color: #64748b; font-size: .9rem; } .err { color: #b91c1c; }
    .login { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; max-width: 560px; margin: 12px 0; }
    .login input { flex: 1; min-width: 220px; }
    .bar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
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
  private readonly meta = inject(Meta);

  readonly tabs: [Tab, string][] = [['month', 'Mensuel'], ['members', 'Membres'], ['coaches', 'Coachs'], ['sports', 'Sports']];
  readonly tab = signal<Tab>('month');
  readonly token = signal<string>('');
  readonly error = signal<string>('');
  readonly s = signal<any>(null);
  readonly month = signal<string>(new Date().toISOString().slice(0, 7));
  readonly busy = signal(false);
  username = '';
  password = '';

  mForm: any = this.blankMember();
  cForm: any = { id: null, name: '', email: '', phone: '', commissionPct: 0, active: true };
  spForm: any = { id: null, name: '', monthlyFee: 0 };

  private tokenExpiry = 0;

  ngOnInit(): void {
    this.meta.updateTag({ name: 'robots', content: 'noindex,nofollow' });
    try {
      const saved = JSON.parse(sessionStorage.getItem('gym_session') || 'null');
      if (saved?.token && saved.expiresAt > Date.now()) {
        this.token.set(saved.token);
        this.tokenExpiry = saved.expiresAt;
        this.load();
      }
    } catch { /* storage unavailable */ }
  }

  // ---------- connexion : identifiant + mot de passe ----------
  login(): void {
    this.error.set(''); this.busy.set(true);
    this.http.post<any>('/api/gym', { action: 'login', username: this.username, password: this.password }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.token.set(r.token);
        this.tokenExpiry = r.expiresAt;
        try { sessionStorage.setItem('gym_session', JSON.stringify({ token: r.token, expiresAt: r.expiresAt })); } catch { /* ignore */ }
        this.password = '';
        this.load();
      },
      error: (e) => { this.busy.set(false); this.password = ''; this.error.set(e?.error?.error || 'Connexion impossible'); },
    });
  }

  logout(): void {
    this.token.set(''); this.s.set(null);
    try { sessionStorage.removeItem('gym_session'); } catch { /* ignore */ }
  }

  private headers() { return { Authorization: `Bearer ${this.token()}` }; }

  private fail(err: any): void {
    if (err?.status === 403) {
      this.logout();
      this.error.set('Session expirée ou accès retiré, reconnectez-vous.');
    } else {
      this.error.set(err?.error?.error || 'La requête a échoué');
    }
  }

  load(): void {
    if (this.tokenExpiry && Date.now() > this.tokenExpiry) { this.logout(); this.error.set('Session expirée, reconnectez-vous.'); return; }
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
  /** Dinar tunisien: 3 décimales (millimes). */
  money(n: number): string {
    return `${(n ?? 0).toLocaleString('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} DT`;
  }
  statusFr(st: string): string { return STATUS_FR[st] || st; }
  sportName(id: string | null): string { return this.s()?.sports.find((x: any) => x.id === id)?.name || '-'; }
  coachName(id: string | null): string { return this.s()?.coaches.find((x: any) => x.id === id)?.name || '-'; }

  del(action: string, id: string, name: string): void {
    if (confirm(`Supprimer « ${name} » ? Cette action est définitive.`)) this.post({ action, id });
  }

  // ---------- paiements ----------
  pay(m: any, amount: number): void {
    this.post({ action: 'payment_set', memberId: m.id, period: this.month(), amount, method: 'espèces' });
  }
  payCustom(m: any): void {
    const v = prompt(`Montant reçu de ${m.name} pour ${this.month()} (DT)`, String(m.due || m.monthlyFee));
    const n = v === null ? NaN : Number(v.replace(',', '.'));
    if (Number.isFinite(n) && n >= 0) this.pay(m, n);
  }
  payCoach(c: any): void {
    this.post({ action: 'payout_set', coachId: c.id, period: this.month(), amount: c.commission });
  }

  // ---------- membres ----------
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

  // ---------- coachs ----------
  editCoach(c: any): void { this.cForm = { ...c }; }
  resetCoach(): void { this.cForm = { id: null, name: '', email: '', phone: '', commissionPct: 0, active: true }; }
  saveCoach(): void { this.post({ action: 'coach_save', ...this.cForm }, () => this.resetCoach()); }

  // ---------- sports ----------
  editSport(sp: any): void { this.spForm = { ...sp }; }
  resetSport(): void { this.spForm = { id: null, name: '', monthlyFee: 0 }; }
  saveSport(): void { this.post({ action: 'sport_save', ...this.spForm }, () => this.resetSport()); }
}
