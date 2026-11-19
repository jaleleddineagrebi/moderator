import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface MonthPoint { month: string; collected: number; commissions: number; expenses: number; net: number; }
export interface Slice { label: string; value: number; }

const MONTHS_FR = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'];
export const PALETTE = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#0ea5e9', '#a855f7', '#84cc16', '#ec4899'];

/** Monthly bars (encaissé vs dépenses) with the net result as a line. Pure SVG, no library. */
@Component({
  selector: 'app-gym-bars',
  standalone: true,
  imports: [CommonModule],
  template: `
    <svg viewBox="0 0 720 280" role="img" aria-label="Encaissé, dépenses et résultat net par mois" class="chart">
      <g *ngFor="let t of ticks">
        <line [attr.x1]="40" [attr.x2]="710" [attr.y1]="t.y" [attr.y2]="t.y" class="grid" />
        <text [attr.x]="34" [attr.y]="t.y + 4" class="axis" text-anchor="end">{{ t.label }}</text>
      </g>
      <line x1="40" x2="710" [attr.y1]="zeroY" [attr.y2]="zeroY" class="zero" />
      <g *ngFor="let b of bars">
        <rect [attr.x]="b.x" [attr.y]="b.inY" [attr.width]="b.w" [attr.height]="b.inH" rx="3" class="in"><title>{{ b.name }} : encaissé {{ b.inV | number:'1.0-0' }} DT</title></rect>
        <rect [attr.x]="b.x + b.w + 2" [attr.y]="b.outY" [attr.width]="b.w" [attr.height]="b.outH" rx="3" class="out"><title>{{ b.name }} : dépenses {{ b.outV | number:'1.0-0' }} DT</title></rect>
        <text [attr.x]="b.x + b.w" [attr.y]="268" class="axis" text-anchor="middle">{{ b.name }}</text>
      </g>
      <polyline [attr.points]="netPoints" class="net" fill="none" />
      <circle *ngFor="let p of netDots" [attr.cx]="p.x" [attr.cy]="p.y" r="3.5" class="netdot"><title>{{ p.name }} : net {{ p.v | number:'1.0-0' }} DT</title></circle>
    </svg>
    <div class="legend">
      <span><i class="sw in"></i>Encaissé</span><span><i class="sw out"></i>Dépenses (commissions + charges)</span><span><i class="sw net"></i>Résultat net</span>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .chart { width: 100%; height: auto; }
    .grid { stroke: var(--line, #e2e8f0); stroke-width: 1; } .zero { stroke: var(--muted, #94a3b8); stroke-width: 1.2; }
    .axis { fill: var(--muted, #64748b); font-size: 11px; }
    .in { fill: #10b981; } .out { fill: #f59e0b; } .net { stroke: #6366f1; stroke-width: 2.5; } .netdot { fill: #6366f1; stroke: var(--card, #fff); stroke-width: 1.5; }
    .legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: .8rem; color: var(--muted, #64748b); margin-top: 4px; }
    .sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }
    .sw.in { background: #10b981; } .sw.out { background: #f59e0b; } .sw.net { background: #6366f1; }
  `]
})
export class GymBarsComponent {
  ticks: { y: number; label: string }[] = [];
  bars: any[] = [];
  netPoints = '';
  netDots: { x: number; y: number; v: number; name: string }[] = [];
  zeroY = 240;

  @Input() set months(list: MonthPoint[] | null) { this.build(list || []); }

  private build(list: MonthPoint[]): void {
    const top = 16, bottom = 240, left = 40, right = 710;
    const outflow = list.map((m) => m.commissions + m.expenses);
    const max = Math.max(1, ...list.map((m) => m.collected), ...outflow, ...list.map((m) => m.net));
    const min = Math.min(0, ...list.map((m) => m.net));
    const span = max - min || 1;
    const y = (v: number) => bottom - ((v - min) / span) * (bottom - top);
    this.zeroY = y(0);
    this.ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const v = min + span * f;
      return { y: y(v), label: Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v)) };
    });
    const slot = (right - left) / Math.max(list.length, 1);
    const w = Math.min(18, slot / 2.6);
    this.bars = list.map((m, i) => {
      const x = left + slot * i + (slot - 2 * w - 2) / 2;
      const out = m.commissions + m.expenses;
      return {
        x, w, name: MONTHS_FR[Number(m.month.slice(5, 7)) - 1],
        inV: m.collected, inY: y(m.collected), inH: Math.max(0, this.zeroY - y(m.collected)),
        outV: out, outY: y(out), outH: Math.max(0, this.zeroY - y(out)),
      };
    });
    this.netDots = list.map((m, i) => ({ x: left + slot * i + slot / 2, y: y(m.net), v: m.net, name: MONTHS_FR[Number(m.month.slice(5, 7)) - 1] }));
    this.netPoints = this.netDots.map((p) => `${p.x},${p.y}`).join(' ');
  }
}

/** Donut chart with legend, used for the expense breakdown. */
@Component({
  selector: 'app-gym-donut',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="wrap" *ngIf="total > 0; else empty">
      <svg viewBox="0 0 42 42" class="donut" role="img" aria-label="Répartition des charges">
        <circle cx="21" cy="21" r="15.9155" fill="none" class="ring" stroke-width="6" />
        <circle *ngFor="let s of arcs" cx="21" cy="21" r="15.9155" fill="none" stroke-width="6"
                [attr.stroke]="s.color" [attr.stroke-dasharray]="s.dash" [attr.stroke-dashoffset]="s.offset" transform="rotate(-90 21 21)">
          <title>{{ s.label }} : {{ s.value | number:'1.0-0' }} DT</title>
        </circle>
        <text x="21" y="22.5" text-anchor="middle" class="center">{{ total | number:'1.0-0' }}</text>
      </svg>
      <ul>
        <li *ngFor="let s of arcs"><i [style.background]="s.color"></i>{{ s.label }} <b>{{ s.value | number:'1.0-0' }} DT</b> <span>{{ s.pct }}%</span></li>
      </ul>
    </div>
    <ng-template #empty><p class="none">Aucune charge enregistrée.</p></ng-template>
  `,
  styles: [`
    .wrap { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
    .donut { width: 150px; height: 150px; flex: none; }
    .ring { stroke: var(--line, #e2e8f0); } .center { font-size: 5px; font-weight: 700; fill: var(--text, #0f172a); }
    ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; font-size: .88rem; }
    li i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 8px; }
    li span { color: var(--muted, #64748b); } .none { color: var(--muted, #64748b); font-size: .9rem; }
  `]
})
export class GymDonutComponent {
  arcs: any[] = [];
  total = 0;

  @Input() set data(map: Record<string, number> | null) {
    const entries: Slice[] = Object.entries(map || {}).filter(([, v]) => v > 0).map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
    this.total = entries.reduce((a, e) => a + e.value, 0);
    let acc = 0;
    this.arcs = entries.map((e, i) => {
      const pct = (e.value / this.total) * 100;
      const arc = { ...e, color: PALETTE[i % PALETTE.length], dash: `${pct} ${100 - pct}`, offset: -acc, pct: Math.round(pct) };
      acc += pct;
      return arc;
    });
  }
}
