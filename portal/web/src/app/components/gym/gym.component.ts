import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Meta } from '@angular/platform-browser';
import { GymBarsComponent, GymDonutComponent } from './gym-charts.component';

type Tab = 'dash' | 'year' | 'members' | 'coaches' | 'sports' | 'expenses' | 'data';

const STATUS_FR: Record<string, string> = { paid: 'payé', partial: 'partiel', unpaid: 'pas payé', 'n/a': '-' };
const CATEGORIES = ['Loyer', 'Femme de ménage', 'Administration', 'Électricité & eau', 'Autre'];

// ---- Excel columns (the same layout is used by export, template and import) ----
const HEAD = {
  Sports: ['Nom', 'Cotisation (DT)'],
  Coachs: ['Nom', 'E-mail', 'Téléphone', 'Commission (%)'],
  Membres: ['Nom', 'E-mail', 'Téléphone', 'Sport', 'Coach', 'Cotisation (DT)', 'Date inscription', 'Actif', 'Remarques'],
  Paiements: ['Membre', 'Mois (AAAA-MM)', 'Montant (DT)', 'Mode', 'Remarque'],
  Charges: ['Catégorie', 'Libellé', 'Montant (DT)', 'Mois (AAAA-MM)', 'Récurrent (oui/non)', 'Fin (AAAA-MM)'],
};
const ALIASES: Record<string, Record<string, string[]>> = {
  sports: { name: ['nom', 'sport'], monthlyFee: ['cotisation', 'tarif', 'prix'] },
  coaches: { name: ['nom', 'coach'], email: ['email', 'mail'], phone: ['telephone', 'tel'], commissionPct: ['commission', 'pourcentage'] },
  members: { name: ['nom', 'membre'], email: ['email', 'mail'], phone: ['telephone', 'tel'], sport: ['sport'], coach: ['coach', 'entraineur'], monthlyFee: ['cotisation', 'tarif'], joinedAt: ['dateinscription', 'inscription', 'date'], active: ['actif'], notes: ['remarques', 'remarque', 'notes'] },
  payments: { member: ['membre', 'nom'], month: ['mois', 'periode'], amount: ['montant'], method: ['mode', 'methode'], note: ['remarque', 'remarques', 'note'] },
  expenses: { category: ['categorie', 'type'], label: ['libelle', 'description'], amount: ['montant'], month: ['mois', 'debut', 'periode'], recurring: ['recurrent', 'mensuel'], endMonth: ['fin'] },
};
const SHEET_OF: Record<string, string> = { sport: 'sports', coach: 'coaches', membre: 'members', paiement: 'payments', charge: 'expenses' };

const norm = (v: unknown) => String(v ?? '').replace(/\(.*?\)/g, '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
const isEmpty = (v: unknown) => v === null || v === undefined || String(v).trim() === '';
const pad = (n: number) => String(n).padStart(2, '0');
function toDay(v: any): string | undefined {
  if (isEmpty(v)) return undefined;
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  const t = String(v).trim();
  const fr = t.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  return fr ? `${fr[3]}-${pad(+fr[2])}-${pad(+fr[1])}` : t;
}
function toMonth(v: any): string | undefined {
  if (isEmpty(v)) return undefined;
  if (v instanceof Date) return v.toISOString().slice(0, 7);
  const t = String(v).trim();
  const fr = t.match(/^(\d{1,2})[/.-](\d{4})$/);
  return fr ? `${fr[2]}-${pad(+fr[1])}` : t.slice(0, 7);
}
function toNum(v: any): number | undefined {
  if (isEmpty(v)) return undefined;
  if (typeof v === 'number') return v;
  const n = Number(String(v).replace(/\s|DT|€/gi, '').replace(',', '.'));
  return Number.isFinite(n) ? n : (v as any);
}
const toBool = (v: any) => (isEmpty(v) ? undefined : typeof v === 'boolean' ? v : !/^(non|no|false|0|faux)$/i.test(String(v).trim()));

@Component({
  selector: 'app-gym',
  standalone: true,
  imports: [CommonModule, FormsModule, GymBarsComponent, GymDonutComponent],
  template: `
  <div class="gym">
    <!-- ============ CONNEXION ============ -->
    <div class="login-page" *ngIf="!token()">
      <form class="login-card" (ngSubmit)="login()">
        <div class="logo"><span class="material-icons">fitness_center</span></div>
        <h1>Gestion de la salle</h1>
        <p class="muted">Espace réservé aux administrateurs</p>
        <input type="text" autocomplete="username" autocapitalize="none" placeholder="Identifiant" [(ngModel)]="username" name="us" required>
        <input type="password" autocomplete="current-password" placeholder="Mot de passe" [(ngModel)]="password" name="pw" required>
        <button class="btn primary block" type="submit" [disabled]="busy()">{{ busy() ? 'Connexion…' : 'Se connecter' }}</button>
        <p class="err" *ngIf="error()">{{ error() }}</p>
      </form>
    </div>

    <!-- ============ APPLICATION ============ -->
    <ng-container *ngIf="token()">
      <header class="topbar">
        <div class="brand"><span class="material-icons">fitness_center</span><b>Ma salle</b></div>
        <div class="period">
          <button class="icon" (click)="shiftMonth(-1)" aria-label="Mois précédent"><span class="material-icons">chevron_left</span></button>
          <input type="month" [ngModel]="month()" (ngModelChange)="setMonth($event)">
          <button class="icon" (click)="shiftMonth(1)" aria-label="Mois suivant"><span class="material-icons">chevron_right</span></button>
        </div>
        <div class="who"><span class="muted">{{ s()?.me }}</span>
          <button class="btn sm ghost" *ngIf="finToken()" (click)="lockFinance()"><span class="material-icons">lock</span> Verrouiller</button>
          <button class="btn sm ghost" (click)="logout()">Se déconnecter</button></div>
      </header>

      <nav class="tabs">
        <button *ngFor="let t of tabs" [class.on]="tab() === t.id" (click)="tab.set(t.id)"><span class="material-icons">{{ t.icon }}</span><span class="lbl">{{ t.label }}</span></button>
      </nav>

      <main *ngIf="s() as d">
        <p class="err" *ngIf="error()">{{ error() }}</p>
        <p class="ok" *ngIf="notice()">{{ notice() }}</p>

        <!-- ---------- CODE D'ACCÈS (tableau de bord + année) ---------- -->
        <section class="card lockbox" *ngIf="(tab() === 'dash' || tab() === 'year') && !d.report">
          <span class="material-icons big">lock</span>
          <h3>Code d'accès requis</h3>
          <p class="muted" *ngIf="d.financeConfigured !== false">Entrez le code d'accès pour voir le tableau de bord et l'année.</p>
          <p class="err" *ngIf="d.financeConfigured === false">Le code d'accès n'est pas encore configuré sur le serveur (variable GYM_FINANCE_CODE).</p>
          <form class="login-inline" (ngSubmit)="unlock()" *ngIf="d.financeConfigured !== false">
            <input type="password" inputmode="numeric" autocomplete="off" placeholder="Code d'accès" [(ngModel)]="finCode" name="fc" required>
            <button class="btn primary" type="submit" [disabled]="busy()">Déverrouiller</button>
          </form>
        </section>

        <!-- ---------- TABLEAU DE BORD ---------- -->
        <section *ngIf="tab() === 'dash' && d.report">
          <h2 class="title">{{ monthLabel() }}</h2>
          <div class="kpis">
            <div class="kpi"><span class="material-icons">groups</span><div><small>Membres actifs</small><b>{{ d.report.activeMembers }}</b></div></div>
            <div class="kpi"><span class="material-icons">receipt_long</span><div><small>Cotisations dues</small><b>{{ money(d.report.due) }}</b></div></div>
            <div class="kpi good"><span class="material-icons">payments</span><div><small>Encaissé</small><b>{{ money(d.report.collected) }}</b></div></div>
            <div class="kpi warn"><span class="material-icons">hourglass_top</span><div><small>Reste à encaisser</small><b>{{ money(d.report.outstanding) }}</b></div></div>
            <div class="kpi"><span class="material-icons">sports</span><div><small>Commissions coachs</small><b>{{ money(d.report.commissions) }}</b></div></div>
            <div class="kpi"><span class="material-icons">home_work</span><div><small>Autres charges</small><b>{{ money(d.report.expenses) }}</b></div></div>
            <div class="kpi big" [class.neg]="d.report.net < 0"><span class="material-icons">account_balance_wallet</span><div><small>Résultat net du mois</small><b>{{ money(d.report.net) }}</b></div></div>
          </div>
          <p class="muted small">Résultat net = encaissé − commissions des coachs − autres charges (loyer, ménage, administration…).</p>

          <div class="cols">
            <div class="card"><h3>Année {{ d.year }} : mois par mois</h3><app-gym-bars [months]="barData(d)"></app-gym-bars></div>
            <div class="card"><h3>Charges du mois</h3><app-gym-donut [data]="d.report.expensesByCategory"></app-gym-donut></div>
          </div>

          <div class="card">
            <h3>Coachs</h3>
            <div class="scroll"><table>
              <tr><th>Coach</th><th>%</th><th>Membres</th><th>Dû</th><th>Encaissé</th><th>Commission</th><th>Si tout payé</th><th>Déjà versé</th><th>Solde</th><th></th></tr>
              <tr *ngFor="let c of d.report.coaches">
                <td><b>{{ c.name }}</b></td><td>{{ c.commissionPct }}%</td><td>{{ c.members }}</td>
                <td>{{ money(c.due) }}</td><td>{{ money(c.collected) }}</td><td><b>{{ money(c.commission) }}</b></td>
                <td class="muted">{{ money(c.potential) }}</td><td>{{ money(c.paidOut) }}</td><td>{{ money(c.balance) }}</td>
                <td class="nowrap">
                  <button class="btn sm" (click)="payCoach(c)" [disabled]="c.balance <= 0">Marquer payé</button>
                  <button class="btn sm ghost" *ngIf="c.paidOut > 0" (click)="post({action:'payout_delete', coachId:c.id, period:month()})">Annuler</button>
                </td>
              </tr>
              <tr *ngIf="!d.report.coaches.length"><td colspan="10" class="muted">Aucun coach pour le moment.</td></tr>
            </table></div>
          </div>

          <div class="card">
            <h3>Cotisations des membres</h3>
            <div class="scroll"><table>
              <tr><th>Membre</th><th>Sport</th><th>Coach</th><th>Dû</th><th>Payé</th><th>Statut</th><th></th></tr>
              <ng-container *ngFor="let m of d.members">
                <tr *ngIf="m.billed || m.paid > 0">
                  <td><b>{{ m.name }}</b></td><td>{{ sportName(m.sportId) }}</td><td>{{ coachName(m.coachId) }}</td>
                  <td>{{ money(m.due) }}</td><td>{{ money(m.paid) }}</td>
                  <td><span class="pill" [ngClass]="m.status">{{ statusFr(m.status) }}</span></td>
                  <td class="nowrap">
                    <button class="btn sm" (click)="pay(m, m.due)" *ngIf="m.status !== 'paid'">Marquer payé</button>
                    <button class="btn sm ghost" (click)="payCustom(m)">Montant…</button>
                    <button class="btn sm ghost" *ngIf="m.paid > 0" (click)="post({action:'payment_delete', memberId:m.id, period:month()})">Annuler</button>
                  </td>
                </tr>
              </ng-container>
            </table></div>
          </div>

          <div class="card">
            <h3>Par sport</h3>
            <div class="scroll"><table>
              <tr><th>Sport</th><th>Membres</th><th>Dû</th><th>Encaissé</th></tr>
              <tr *ngFor="let sp of d.report.sports"><td><b>{{ sp.name }}</b></td><td>{{ sp.members }}</td><td>{{ money(sp.due) }}</td><td>{{ money(sp.collected) }}</td></tr>
            </table></div>
          </div>
        </section>

        <!-- ---------- ANNÉE ---------- -->
        <section *ngIf="tab() === 'year' && d.yearReport">
          <div class="yearbar">
            <button class="icon" (click)="shiftYear(-1)"><span class="material-icons">chevron_left</span></button>
            <h2 class="title">Année {{ d.year }}</h2>
            <button class="icon" (click)="shiftYear(1)"><span class="material-icons">chevron_right</span></button>
          </div>
          <div class="kpis">
            <div class="kpi"><span class="material-icons">receipt_long</span><div><small>Cotisations dues</small><b>{{ money(d.yearReport.totals.due) }}</b></div></div>
            <div class="kpi good"><span class="material-icons">payments</span><div><small>Encaissé</small><b>{{ money(d.yearReport.totals.collected) }}</b></div></div>
            <div class="kpi"><span class="material-icons">sports</span><div><small>Commissions coachs</small><b>{{ money(d.yearReport.totals.commissions) }}</b></div></div>
            <div class="kpi"><span class="material-icons">home_work</span><div><small>Autres charges</small><b>{{ money(d.yearReport.totals.expenses) }}</b></div></div>
            <div class="kpi big" [class.neg]="d.yearReport.totals.net < 0"><span class="material-icons">account_balance_wallet</span><div><small>Résultat net de l'année</small><b>{{ money(d.yearReport.totals.net) }}</b></div></div>
          </div>
          <div class="cols">
            <div class="card"><h3>Évolution mensuelle</h3><app-gym-bars [months]="barData(d)"></app-gym-bars></div>
            <div class="card"><h3>Charges de l'année</h3><app-gym-donut [data]="d.yearReport.expensesByCategory"></app-gym-donut></div>
          </div>
          <div class="card">
            <h3>Détail par mois</h3>
            <div class="scroll"><table>
              <tr><th>Mois</th><th>Membres</th><th>Dû</th><th>Encaissé</th><th>Commissions</th><th>Autres charges</th><th>Résultat net</th></tr>
              <tr *ngFor="let m of d.yearReport.months" class="click" (click)="setMonth(m.month); tab.set('dash')">
                <td><b>{{ monthName(m.month) }}</b></td><td>{{ m.activeMembers }}</td><td>{{ money(m.due) }}</td><td>{{ money(m.collected) }}</td>
                <td>{{ money(m.commissions) }}</td><td>{{ money(m.expenses) }}</td><td [class.negtxt]="m.net < 0"><b>{{ money(m.net) }}</b></td>
              </tr>
              <tr class="total"><td>Total</td><td></td><td>{{ money(d.yearReport.totals.due) }}</td><td>{{ money(d.yearReport.totals.collected) }}</td>
                <td>{{ money(d.yearReport.totals.commissions) }}</td><td>{{ money(d.yearReport.totals.expenses) }}</td><td [class.negtxt]="d.yearReport.totals.net < 0">{{ money(d.yearReport.totals.net) }}</td></tr>
            </table></div>
          </div>
        </section>

        <!-- ---------- MEMBRES ---------- -->
        <section *ngIf="tab() === 'members'">
          <div class="card">
            <h3>{{ mForm.id ? 'Modifier le membre' : 'Ajouter un membre' }}</h3>
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
              <span class="actions"><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="mForm.id" (click)="resetMember()">Annuler</button></span>
            </form>
          </div>
          <div class="card">
            <h3>Membres : paiement de {{ monthLabel() }}
              <span class="pill paid">{{ countOf(d, 'paid') }} payé(s)</span>
              <span class="pill partial" *ngIf="countOf(d, 'partial')">{{ countOf(d, 'partial') }} partiel(s)</span>
              <span class="pill unpaid">{{ countOf(d, 'unpaid') }} pas payé(s)</span>
            </h3>
            <div class="scroll"><table>
              <tr><th>Nom</th><th>Contact</th><th>Sport</th><th>Coach</th><th>Cotisation</th><th>Paiement</th><th>Montant payé</th><th>Inscrit le</th><th>Actif</th><th></th></tr>
              <tr *ngFor="let m of d.members" [class.dim]="!m.active">
                <td><b>{{ m.name }}</b></td><td>{{ m.email || m.phone || '' }}</td><td>{{ sportName(m.sportId) }}</td><td>{{ coachName(m.coachId) }}</td>
                <td>{{ money(m.monthlyFee) }}</td>
                <td><span class="pill" [ngClass]="m.status">{{ statusFr(m.status) }}</span></td>
                <td><b *ngIf="m.billed || m.paid > 0">{{ money(m.paid) }}</b><span class="muted small" *ngIf="m.status === 'partial'"> sur {{ money(m.due) }}</span></td>
                <td>{{ m.joinedAt }}</td><td>{{ m.active ? 'oui' : 'non' }}</td>
                <td class="nowrap">
                  <ng-container *ngIf="m.billed || m.paid > 0">
                    <button class="btn sm" (click)="pay(m, m.due)" *ngIf="m.status !== 'paid'">Marquer payé</button>
                    <button class="btn sm ghost" (click)="payCustom(m)">Montant…</button>
                    <button class="btn sm ghost" *ngIf="m.paid > 0" (click)="post({action:'payment_delete', memberId:m.id, period:month()})">Annuler</button>
                  </ng-container>
                  <button class="btn sm" (click)="editMember(m)">Modifier</button> <button class="btn sm danger" (click)="del('member_delete', m.id, m.name)">Supprimer</button>
                </td>
              </tr>
            </table></div>
          </div>
        </section>

        <!-- ---------- COACHS ---------- -->
        <section *ngIf="tab() === 'coaches'">
          <div class="card">
            <h3>{{ cForm.id ? 'Modifier le coach' : 'Ajouter un coach' }}</h3>
            <form class="grid" (ngSubmit)="saveCoach()">
              <input placeholder="Nom complet *" [(ngModel)]="cForm.name" name="n" required>
              <input placeholder="E-mail" [(ngModel)]="cForm.email" name="e">
              <input placeholder="Téléphone" [(ngModel)]="cForm.phone" name="p">
              <input type="number" min="0" max="100" step="0.1" placeholder="Commission en % des cotisations" [(ngModel)]="cForm.commissionPct" name="pc">
              <label class="chk"><input type="checkbox" [(ngModel)]="cForm.active" name="a"> Actif</label>
              <span class="actions"><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="cForm.id" (click)="resetCoach()">Annuler</button></span>
            </form>
          </div>
          <div class="card"><div class="scroll"><table>
            <tr><th>Nom</th><th>Contact</th><th>Commission</th><th>Actif</th><th></th></tr>
            <tr *ngFor="let c of d.coaches" [class.dim]="!c.active">
              <td><b>{{ c.name }}</b></td><td>{{ c.email || c.phone || '' }}</td><td>{{ c.commissionPct }}%</td><td>{{ c.active ? 'oui' : 'non' }}</td>
              <td class="nowrap"><button class="btn sm" (click)="editCoach(c)">Modifier</button> <button class="btn sm danger" (click)="del('coach_delete', c.id, c.name)">Supprimer</button></td>
            </tr>
          </table></div></div>
        </section>

        <!-- ---------- SPORTS ---------- -->
        <section *ngIf="tab() === 'sports'">
          <div class="card">
            <h3>{{ spForm.id ? 'Modifier le sport' : 'Ajouter un sport' }}</h3>
            <form class="grid" (ngSubmit)="saveSport()">
              <input placeholder="Nom du sport *" [(ngModel)]="spForm.name" name="n" required>
              <input type="number" min="0" step="0.001" placeholder="Cotisation mensuelle par défaut (DT)" [(ngModel)]="spForm.monthlyFee" name="f">
              <span class="actions"><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="spForm.id" (click)="resetSport()">Annuler</button></span>
            </form>
          </div>
          <div class="card"><div class="scroll"><table>
            <tr><th>Sport</th><th>Cotisation par défaut</th><th></th></tr>
            <tr *ngFor="let sp of d.sports">
              <td><b>{{ sp.name }}</b></td><td>{{ money(sp.monthlyFee) }}</td>
              <td class="nowrap"><button class="btn sm" (click)="editSport(sp)">Modifier</button> <button class="btn sm danger" (click)="del('sport_delete', sp.id, sp.name)">Supprimer</button></td>
            </tr>
          </table></div></div>
        </section>

        <!-- ---------- CHARGES ---------- -->
        <section *ngIf="tab() === 'expenses'">
          <div class="card">
            <h3>{{ eForm.id ? 'Modifier la charge' : 'Ajouter une charge' }}</h3>
            <form class="grid" (ngSubmit)="saveExpense()">
              <select [(ngModel)]="eForm.cat" name="cat">
                <option *ngFor="let c of categories" [ngValue]="c">{{ c }}</option>
              </select>
              <input *ngIf="eForm.cat === 'Autre'" placeholder="Nom de la catégorie *" [(ngModel)]="eForm.custom" name="cu" required>
              <input placeholder="Libellé (facultatif)" [(ngModel)]="eForm.label" name="lb">
              <input type="number" min="0" step="0.001" placeholder="Montant (DT) *" [(ngModel)]="eForm.amount" name="am" required>
              <label class="fld">{{ eForm.recurring ? 'À partir de' : 'Mois' }} <input type="month" [(ngModel)]="eForm.period" name="pe" required></label>
              <label class="chk"><input type="checkbox" [(ngModel)]="eForm.recurring" name="rc"> Chaque mois (ex. loyer)</label>
              <label class="fld" *ngIf="eForm.recurring">Jusqu'à (facultatif) <input type="month" [(ngModel)]="eForm.endPeriod" name="en"></label>
              <span class="actions"><button class="btn primary" type="submit">Enregistrer</button> <button class="btn ghost" type="button" *ngIf="eForm.id" (click)="resetExpense()">Annuler</button></span>
            </form>
          </div>
          <div class="card" *ngIf="d.report">
            <h3>Charges prises en compte en {{ monthLabel() }} : {{ money(d.report.expenses) }}</h3>
            <div class="scroll"><table>
              <tr><th>Catégorie</th><th>Libellé</th><th>Montant</th></tr>
              <tr *ngFor="let e of d.report.expenseRows"><td><b>{{ e.category }}</b></td><td>{{ e.label }}</td><td>{{ money(e.amount) }}</td></tr>
              <tr *ngIf="!d.report.expenseRows.length"><td colspan="3" class="muted">Aucune charge ce mois-ci.</td></tr>
            </table></div>
          </div>
          <div class="card">
            <h3>Toutes les charges enregistrées</h3>
            <div class="scroll"><table>
              <tr><th>Catégorie</th><th>Libellé</th><th>Montant</th><th>Période</th><th></th></tr>
              <tr *ngFor="let e of d.expenses">
                <td><b>{{ e.category }}</b></td><td>{{ e.label }}</td><td>{{ money(e.amount) }}</td>
                <td>{{ expensePeriod(e) }}</td>
                <td class="nowrap"><button class="btn sm" (click)="editExpense(e)">Modifier</button> <button class="btn sm danger" (click)="del('expense_delete', e.id, e.category)">Supprimer</button></td>
              </tr>
              <tr *ngIf="!d.expenses.length"><td colspan="5" class="muted">Aucune charge enregistrée.</td></tr>
            </table></div>
          </div>
        </section>

        <!-- ---------- IMPORT / EXPORT ---------- -->
        <section *ngIf="tab() === 'data'">
          <div class="cols">
            <div class="card">
              <h3><span class="material-icons">download</span> Exporter vers Excel</h3>
              <p class="muted">Un fichier avec les feuilles Sports, Coachs, Membres, Paiements de {{ d.year }}, Charges{{ d.yearReport ? ' et un rapport mensuel ' + d.year : ' (le rapport mensuel n\'est inclus qu\'après saisie du code d\'accès)' }}.</p>
              <div class="actions">
                <button class="btn primary" (click)="exportXlsx()" [disabled]="busy()">Télécharger les données (.xlsx)</button>
                <button class="btn ghost" (click)="downloadTemplate()" [disabled]="busy()">Modèle vide</button>
              </div>
            </div>
            <div class="card">
              <h3><span class="material-icons">upload</span> Importer depuis Excel</h3>
              <p class="muted">Utilisez le fichier exporté ou le modèle. Feuilles reconnues : Sports, Coachs, Membres, Paiements, Charges. Les lignes existantes (même nom) sont mises à jour, les autres ajoutées. Si une ligne est invalide, rien n'est importé et l'erreur est affichée.</p>
              <input type="file" accept=".xlsx" (change)="onFile($event)" [disabled]="busy()">
            </div>
          </div>
        </section>
      </main>
    </ng-container>
  </div>
  `,
  styles: [`
    :host { --bg:#f1f5f9; --card:#fff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0; --accent:#4f46e5; --good:#10b981; --warn:#f59e0b; --bad:#ef4444; --soft:#f8fafc;
            display:block; background:var(--bg); color:var(--text); min-height:100vh; font-family:Inter, system-ui, sans-serif; }
    @media (prefers-color-scheme: dark) {
      :host { --bg:#0b1120; --card:#111a2e; --text:#e2e8f0; --muted:#94a3b8; --line:#1f2b45; --accent:#818cf8; --soft:#0f172a; }
    }
    .material-icons { font-size: 20px; vertical-align: middle; }
    .muted { color: var(--muted); } .small { font-size: .82rem; } .err { color: var(--bad); font-weight: 500; }
    .ok { background: #dcfce7; color: #166534; padding: 10px 14px; border-radius: 10px; }
    h1, h2, h3 { margin: 0; } h3 { font-size: 1rem; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
    .title { font-size: 1.35rem; margin: 8px 0 14px; }

    /* login */
    .login-page { min-height: 100vh; display: grid; place-items: center; padding: 16px; background: linear-gradient(135deg, #4338ca, #0ea5e9); }
    .login-card { background: var(--card); width: 100%; max-width: 380px; padding: 32px 28px; border-radius: 18px; display: grid; gap: 12px; box-shadow: 0 20px 50px rgba(0,0,0,.25); text-align: center; }
    .logo { width: 56px; height: 56px; border-radius: 16px; background: var(--accent); color: #fff; display: grid; place-items: center; margin: 0 auto; }
    .logo .material-icons { font-size: 30px; }
    .block { width: 100%; }
    .lockbox { max-width: 420px; margin: 40px auto; text-align: center; display: grid; gap: 10px; justify-items: center; }
    .lockbox h3 { justify-content: center; margin: 0; } .material-icons.big { font-size: 40px; color: var(--accent); }
    .login-inline { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }

    /* top bar + tabs */
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 12px 20px; background: var(--card); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 5; }
    .brand { display: flex; align-items: center; gap: 8px; color: var(--accent); font-size: 1.1rem; }
    .period { display: flex; align-items: center; gap: 4px; }
    .who { display: flex; align-items: center; gap: 10px; font-size: .85rem; }
    .tabs { display: flex; gap: 4px; padding: 8px 20px 0; overflow-x: auto; background: var(--card); border-bottom: 1px solid var(--line); }
    .tabs button { display: flex; align-items: center; gap: 6px; background: none; border: 0; padding: 10px 14px; cursor: pointer; font: inherit; color: var(--muted); border-bottom: 3px solid transparent; white-space: nowrap; }
    .tabs button.on { color: var(--accent); border-color: var(--accent); font-weight: 600; }
    main { max-width: 1180px; margin: 0 auto; padding: 20px 16px 64px; }

    /* cards & KPIs */
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; margin: 16px 0; box-shadow: 0 1px 2px rgba(0,0,0,.03); }
    .cols { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; } .cols .card { margin: 16px 0 0; }
    @media (max-width: 860px) { .cols { grid-template-columns: 1fr; } }
    .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
    .kpi { display: flex; gap: 12px; align-items: center; background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }
    .kpi > .material-icons { background: var(--soft); color: var(--accent); border-radius: 12px; padding: 10px; font-size: 22px; }
    .kpi small { display: block; color: var(--muted); font-size: .75rem; } .kpi b { font-size: 1.15rem; }
    .kpi.good > .material-icons { color: var(--good); } .kpi.warn > .material-icons { color: var(--warn); }
    .kpi.big { background: linear-gradient(135deg, #4f46e5, #0ea5e9); border: 0; color: #fff; }
    .kpi.big > .material-icons { background: rgba(255,255,255,.2); color: #fff; } .kpi.big small { color: rgba(255,255,255,.85); }
    .kpi.big.neg { background: linear-gradient(135deg, #dc2626, #f97316); }
    .yearbar { display: flex; align-items: center; gap: 12px; } .yearbar .title { margin: 0; }

    /* tables & forms */
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    th { text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 600; font-size: .78rem; text-transform: uppercase; letter-spacing: .03em; border-bottom: 1px solid var(--line); white-space: nowrap; }
    td { padding: 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
    tr.dim { opacity: .55; } tr.click { cursor: pointer; } tr.click:hover td { background: var(--soft); }
    tr.total td { font-weight: 700; background: var(--soft); } .negtxt { color: var(--bad); } .nowrap { white-space: nowrap; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; align-items: end; }
    .fld { display: grid; gap: 4px; font-size: .78rem; color: var(--muted); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    input, select { padding: 9px 11px; border: 1px solid var(--line); border-radius: 9px; font: inherit; background: var(--soft); color: var(--text); min-width: 0; }
    input:focus, select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
    .chk { display: flex; gap: 8px; align-items: center; }
    .btn { padding: 9px 16px; border-radius: 9px; border: 1px solid var(--line); background: var(--card); color: var(--text); cursor: pointer; font: inherit; }
    .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    .btn.sm { padding: 4px 10px; font-size: .8rem; } .btn.ghost { background: none; }
    .btn.danger { color: var(--bad); border-color: rgba(239,68,68,.35); } .btn:disabled { opacity: .45; cursor: default; }
    .icon { background: none; border: 1px solid var(--line); border-radius: 9px; padding: 4px; cursor: pointer; color: var(--text); display: grid; place-items: center; }
    .pill { padding: 2px 10px; border-radius: 999px; font-size: .75rem; background: var(--line); }
    .pill.paid { background: #dcfce7; color: #166534; } .pill.partial { background: #fef3c7; color: #92400e; } .pill.unpaid { background: #fee2e2; color: #991b1b; }
    @media (max-width: 640px) { .tabs .lbl { display: none; } .topbar { padding: 10px 12px; } }
  `]
})
export class GymComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly meta = inject(Meta);

  readonly tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'dash', label: 'Tableau de bord', icon: 'dashboard' },
    { id: 'year', label: 'Année', icon: 'insights' },
    { id: 'members', label: 'Membres', icon: 'groups' },
    { id: 'coaches', label: 'Coachs', icon: 'sports' },
    { id: 'sports', label: 'Sports', icon: 'sports_gymnastics' },
    { id: 'expenses', label: 'Charges', icon: 'home_work' },
    { id: 'data', label: 'Excel', icon: 'table_view' },
  ];
  readonly categories = CATEGORIES;
  readonly tab = signal<Tab>('dash');
  readonly token = signal<string>('');
  readonly error = signal<string>('');
  readonly notice = signal<string>('');
  readonly s = signal<any>(null);
  readonly month = signal<string>(new Date().toISOString().slice(0, 7));
  readonly busy = signal(false);
  readonly finToken = signal<string>(''); // access code unlock, kept in memory only
  private finExpiry = 0;
  finCode = '';
  username = '';
  password = '';

  mForm: any = this.blankMember();
  cForm: any = { id: null, name: '', email: '', phone: '', commissionPct: 0, active: true };
  spForm: any = { id: null, name: '', monthlyFee: 0 };
  eForm: any = this.blankExpense();

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
    this.token.set(''); this.s.set(null); this.finToken.set(''); this.finExpiry = 0;
    try { sessionStorage.removeItem('gym_session'); } catch { /* ignore */ }
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { Authorization: `Bearer ${this.token()}` };
    if (this.finToken() && Date.now() < this.finExpiry) h['X-Finance-Token'] = this.finToken();
    return h;
  }

  // ---------- code d'accès : tableau de bord + année ----------
  unlock(): void {
    this.error.set(''); this.busy.set(true);
    this.http.post<any>('/api/gym', { action: 'unlock', code: this.finCode }, { headers: this.headers() }).subscribe({
      next: (r) => {
        this.busy.set(false); this.finCode = '';
        this.finToken.set(r.financeToken); this.finExpiry = r.financeExpiresAt;
        this.load();
      },
      error: (e) => { this.busy.set(false); this.finCode = ''; this.fail(e); },
    });
  }
  lockFinance(): void { this.finToken.set(''); this.finExpiry = 0; this.load(); }

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

  post(body: any, then?: (r: any) => void): void {
    this.notice.set('');
    this.http.post<any>('/api/gym', body, { headers: this.headers() }).subscribe({
      next: (r) => { then?.(r); this.load(); },
      error: (e) => { this.busy.set(false); this.fail(e); },
    });
  }

  // ---------- période ----------
  setMonth(m: string): void { if (m) { this.month.set(m); this.load(); } }
  shiftMonth(delta: number): void {
    const [y, m] = this.month().split('-').map(Number);
    const d = new Date(Date.UTC(y, m - 1 + delta, 1));
    this.setMonth(`${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`);
  }
  shiftYear(delta: number): void { this.setMonth(`${Number(this.month().slice(0, 4)) + delta}-${this.month().slice(5, 7)}`); }
  monthName(m: string): string {
    return new Date(Date.UTC(Number(m.slice(0, 4)), Number(m.slice(5, 7)) - 1, 1)).toLocaleDateString('fr-FR', { month: 'long', timeZone: 'UTC' });
  }
  monthLabel(): string {
    const m = this.month();
    return `${this.monthName(m).replace(/^./, (c) => c.toUpperCase())} ${m.slice(0, 4)}`;
  }

  // ---------- affichage ----------
  /** Dinar tunisien: 3 décimales (millimes). */
  money(n: number): string {
    return `${(n ?? 0).toLocaleString('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} DT`;
  }
  statusFr(st: string): string { return STATUS_FR[st] || st; }
  sportName(id: string | null): string { return this.s()?.sports.find((x: any) => x.id === id)?.name || '-'; }
  coachName(id: string | null): string { return this.s()?.coaches.find((x: any) => x.id === id)?.name || '-'; }
  barData(d: any): any[] { return d.yearReport?.months || []; }
  countOf(d: any, status: string): number { return d.members.filter((m: any) => m.status === status).length; }
  expensePeriod(e: any): string {
    return e.recurring ? `chaque mois depuis ${e.period}${e.endPeriod ? " jusqu'à " + e.endPeriod : ''}` : e.period;
  }

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
  editCoach(c: any): void { this.cForm = { ...c }; window.scrollTo({ top: 0, behavior: 'smooth' }); }
  resetCoach(): void { this.cForm = { id: null, name: '', email: '', phone: '', commissionPct: 0, active: true }; }
  saveCoach(): void { this.post({ action: 'coach_save', ...this.cForm }, () => this.resetCoach()); }

  // ---------- sports ----------
  editSport(sp: any): void { this.spForm = { ...sp }; window.scrollTo({ top: 0, behavior: 'smooth' }); }
  resetSport(): void { this.spForm = { id: null, name: '', monthlyFee: 0 }; }
  saveSport(): void { this.post({ action: 'sport_save', ...this.spForm }, () => this.resetSport()); }

  // ---------- charges ----------
  private blankExpense() {
    return { id: null, cat: 'Loyer', custom: '', label: '', amount: null, period: this.month(), recurring: false, endPeriod: '' };
  }
  editExpense(e: any): void {
    const known = CATEGORIES.includes(e.category);
    this.eForm = { id: e.id, cat: known ? e.category : 'Autre', custom: known ? '' : e.category, label: e.label || '', amount: e.amount, period: e.period, recurring: e.recurring, endPeriod: e.endPeriod || '' };
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  resetExpense(): void { this.eForm = this.blankExpense(); }
  saveExpense(): void {
    const f = this.eForm;
    this.post({ action: 'expense_save', id: f.id, category: f.cat === 'Autre' ? f.custom : f.cat, label: f.label, amount: f.amount, period: f.period, recurring: f.recurring, endPeriod: f.recurring ? f.endPeriod : null },
      () => this.resetExpense());
  }

  // ---------- Excel : export / modèle / import ----------
  private async writeSheets(sheets: { sheet: string; data: any[][] }[], fileName: string): Promise<void> {
    const mod: any = await import('write-excel-file/browser');
    await (mod.default || mod)(sheets).toFile(fileName);
  }
  private head(cols: string[]) { return cols.map((value) => ({ value, fontWeight: 'bold' })); }
  private cell(v: any) { return v === undefined || v === '' ? null : v; }

  async exportXlsx(): Promise<void> {
    const d = this.s(); if (!d) return;
    this.busy.set(true);
    try {
      const nameOf = new Map<string, string>(d.members.map((m: any) => [m.id, m.name]));
      const sport = (id: string | null) => (this.sportName(id) === '-' ? null : this.sportName(id));
      const coach = (id: string | null) => (this.coachName(id) === '-' ? null : this.coachName(id));
      await this.writeSheets([
        { sheet: 'Sports', data: [this.head(HEAD.Sports), ...d.sports.map((x: any) => [x.name, x.monthlyFee])] },
        { sheet: 'Coachs', data: [this.head(HEAD.Coachs), ...d.coaches.map((x: any) => [x.name, this.cell(x.email), this.cell(x.phone), x.commissionPct])] },
        { sheet: 'Membres', data: [this.head(HEAD.Membres), ...d.members.map((m: any) => [m.name, this.cell(m.email), this.cell(m.phone), sport(m.sportId), coach(m.coachId), m.monthlyFee, m.joinedAt, m.active ? 'oui' : 'non', this.cell(m.notes)])] },
        { sheet: 'Paiements', data: [this.head(HEAD.Paiements), ...d.payments.map((p: any) => [nameOf.get(p.memberId) || '', p.period, p.amount, this.cell(p.method), this.cell(p.note)])] },
        { sheet: 'Charges', data: [this.head(HEAD.Charges), ...d.expenses.map((e: any) => [e.category, this.cell(e.label), e.amount, e.period, e.recurring ? 'oui' : 'non', this.cell(e.endPeriod)])] },
        ...(d.yearReport ? [{ sheet: `Rapport ${d.year}`, data: [
          this.head(['Mois', 'Membres', 'Dû (DT)', 'Encaissé (DT)', 'Commissions (DT)', 'Autres charges (DT)', 'Résultat net (DT)']),
          ...d.yearReport.months.map((m: any) => [m.month, m.activeMembers, m.due, m.collected, m.commissions, m.expenses, m.net]),
          ['Total', null, d.yearReport.totals.due, d.yearReport.totals.collected, d.yearReport.totals.commissions, d.yearReport.totals.expenses, d.yearReport.totals.net],
        ] }] : []),
      ], `salle-${d.year}.xlsx`);
    } catch { this.error.set('Export impossible'); }
    this.busy.set(false);
  }

  async downloadTemplate(): Promise<void> {
    this.busy.set(true);
    try {
      const y = this.month().slice(0, 4);
      await this.writeSheets([
        { sheet: 'Sports', data: [this.head(HEAD.Sports), ['Boxe', 60]] },
        { sheet: 'Coachs', data: [this.head(HEAD.Coachs), ['Ali Ben Salah', null, '20123456', 40]] },
        { sheet: 'Membres', data: [this.head(HEAD.Membres), ['Sami Trabelsi', null, '98123456', 'Boxe', 'Ali Ben Salah', 60, `${y}-01-15`, 'oui', null]] },
        { sheet: 'Paiements', data: [this.head(HEAD.Paiements), ['Sami Trabelsi', `${y}-01`, 60, 'espèces', null]] },
        { sheet: 'Charges', data: [this.head(HEAD.Charges), ['Loyer', null, 1500, `${y}-01`, 'oui', null], ['Femme de ménage', null, 300, `${y}-01`, 'oui', null], ['Administration', 'Comptable', 200, `${y}-01`, 'oui', null]] },
      ], 'modele-salle.xlsx');
    } catch { this.error.set('Création du modèle impossible'); }
    this.busy.set(false);
  }

  async onFile(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.error.set(''); this.notice.set(''); this.busy.set(true);
    try {
      const mod: any = await import('read-excel-file/browser');
      const sheets: { sheet: string; data: any[][] }[] = await (mod.default || mod)(file);
      const out: Record<string, any[]> = {};
      for (const sh of sheets) {
        const kind = Object.entries(SHEET_OF).find(([k]) => norm(sh.sheet).startsWith(k))?.[1];
        if (!kind || !sh.data.length) continue;
        out[kind] = this.rowsOf(kind, sh.data);
      }
      if (!Object.values(out).some((r) => r.length)) throw new Error('Aucune feuille reconnue (Sports, Coachs, Membres, Paiements, Charges)');
      this.post({ action: 'import_data', data: out }, (r) => {
        this.busy.set(false);
        const c = r.imported || {};
        this.notice.set(`Import terminé : ${c.sports || 0} sport(s), ${c.coaches || 0} coach(s), ${c.members || 0} membre(s), ${c.payments || 0} paiement(s), ${c.expenses || 0} charge(s).`);
      });
    } catch (e: any) {
      this.busy.set(false);
      this.error.set(e?.message || 'Fichier illisible');
    }
    input.value = '';
  }

  /** Turns a sheet (header row + rows) into objects using the column aliases above. */
  private rowsOf(kind: string, data: any[][]): any[] {
    const spec = ALIASES[kind];
    const header = data[0].map(norm);
    const col: Record<string, number> = {};
    for (const [field, names] of Object.entries(spec)) {
      const i = header.findIndex((h) => names.includes(h));
      if (i >= 0) col[field] = i;
    }
    const conv: Record<string, (v: any) => any> = {
      monthlyFee: toNum, commissionPct: toNum, amount: toNum, joinedAt: toDay, month: toMonth, endMonth: toMonth, active: toBool,
    };
    return data.slice(1)
      .filter((row) => row.some((v) => !isEmpty(v)))
      .map((row) => {
        const o: any = {};
        for (const [field, i] of Object.entries(col)) {
          const v = row[i];
          o[field] = isEmpty(v) ? undefined : (conv[field] ? conv[field](v) : typeof v === 'string' ? v.trim() : v);
        }
        return o;
      });
  }
}
