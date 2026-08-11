import type { HudState, TargetState } from './hudState';
import { ACQUIRE_MS, EXIT_MS } from './hudState';
import { THEME } from './theme';

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

/** Corner-bracket length as a fraction of the box's shorter side. */
const BRACKET_RATIO = 0.24;
/** 45-degree chamfer on each bracket corner — the cut corner is most of what
 * separates "instrument" from "screenshot annotation". */
const CHAMFER = 7;
/** How far outside the box brackets start on acquire / end up on release,
 * as a fraction of the box's shorter side. */
const OUTSET_RATIO = 0.55;
/** Non-primary targets dim to this opacity so the primary reads as "focused". */
const SECONDARY_ALPHA = 0.45;
/** Glow (shadowBlur) is real draw cost — reserve it for the primary target
 * only rather than paying it per-bracket, per-target, every frame. See
 * decisions.md / day5-poc.md for the measured before/after. */
const PRIMARY_GLOW = 12;

function formatAge(ageMs: number): string {
  return `${(ageMs / 1000).toFixed(1)}s`;
}

function font(ctx: CanvasRenderingContext2D, weight: number, size: number, spacing = '0px') {
  ctx.font = `${weight} ${size}px ${MONO}`;
  // Supported in Chromium; a no-op elsewhere. Caps + tracking is half the look.
  ctx.letterSpacing = spacing;
}

/** Stable per-label accent so the same object keeps the same colour. */
function accentFor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  // Narrow teal->cyan band. A wider band reached muddy blues that lost all
  // contrast against real camera footage.
  const hue = 168 + (Math.abs(hash) % 26);
  return `hsl(${hue} 95% 66%)`;
}

function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

/**
 * Four chamfered corner brackets. `outset` expands the geometry outward from
 * the true box — positive during acquire (converging in) and release (fanning
 * out).
 */
function drawBrackets(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  color: string, alpha: number, outset: number, glow: number, weight: number,
) {
  const bx = x - outset;
  const by = y - outset;
  const bw = w + outset * 2;
  const bh = h + outset * 2;
  const len = Math.max(10, Math.min(bw, bh) * BRACKET_RATIO);
  const c = Math.min(CHAMFER, len / 2);

  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = weight;
  ctx.lineJoin = 'miter';
  ctx.shadowColor = color;
  ctx.shadowBlur = glow;
  ctx.beginPath();
  ctx.moveTo(bx, by + len); ctx.lineTo(bx, by + c); ctx.lineTo(bx + c, by); ctx.lineTo(bx + len, by);
  ctx.moveTo(bx + bw - len, by); ctx.lineTo(bx + bw - c, by); ctx.lineTo(bx + bw, by + c); ctx.lineTo(bx + bw, by + len);
  ctx.moveTo(bx + bw, by + bh - len); ctx.lineTo(bx + bw, by + bh - c); ctx.lineTo(bx + bw - c, by + bh); ctx.lineTo(bx + bw - len, by + bh);
  ctx.moveTo(bx + len, by + bh); ctx.lineTo(bx + c, by + bh); ctx.lineTo(bx, by + bh - c); ctx.lineTo(bx, by + bh - len);
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Inner hairline echo — depth, and it reads as a machined edge.
  ctx.globalAlpha = alpha * 0.35;
  ctx.lineWidth = 1;
  const g = 4;
  ctx.beginPath();
  ctx.moveTo(bx + g, by + len * 0.6); ctx.lineTo(bx + g, by + g); ctx.lineTo(bx + len * 0.6, by + g);
  ctx.moveTo(bx + bw - len * 0.6, by + g); ctx.lineTo(bx + bw - g, by + g); ctx.lineTo(bx + bw - g, by + len * 0.6);
  ctx.moveTo(bx + bw - g, by + bh - len * 0.6); ctx.lineTo(bx + bw - g, by + bh - g); ctx.lineTo(bx + bw - len * 0.6, by + bh - g);
  ctx.moveTo(bx + len * 0.6, by + bh - g); ctx.lineTo(bx + g, by + bh - g); ctx.lineTo(bx + g, by + bh - len * 0.6);
  ctx.stroke();
  ctx.globalAlpha = 1;
}

/** Ring of radial ticks — the "graduated instrument" read. Major ticks every
 * `majorEvery`, and four gaps so it reads as segmented rather than solid. */
function drawTickRing(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, r: number,
  count: number, rotation: number,
  color: string, alpha: number,
) {
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i < count; i++) {
    // Four 3-tick gaps at the diagonals.
    if (i % (count / 4) < 3) continue;
    const major = i % 5 === 0;
    const a = rotation + (i / count) * Math.PI * 2;
    const inner = r - (major ? 8 : 4);
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    ctx.moveTo(cx + cos * inner, cy + sin * inner);
    ctx.lineTo(cx + cos * r, cy + sin * r);
  }
  ctx.stroke();
  ctx.globalAlpha = 1;
}

/** Four-arc ring with gaps at the diagonals, slowly rotating. */
function drawSegmentedRing(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, r: number, rotation: number,
  color: string, alpha: number, width: number, gap: number,
) {
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  for (let k = 0; k < 4; k++) {
    const start = rotation + (k * Math.PI) / 2 + gap;
    // arc() draws a connecting line from the current point — start each
    // segment's subpath exactly on its own first point.
    ctx.moveTo(cx + Math.cos(start) * r, cy + Math.sin(start) * r);
    ctx.arc(cx, cy, r, start, start + Math.PI / 2 - gap * 2);
  }
  ctx.stroke();
  ctx.globalAlpha = 1;
}

/**
 * Confidence arc — arc length is the real `Detection.score`, with a cap dot at
 * the live end and a faint full-circle track behind it.
 */
function drawConfidenceRing(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, r: number, score: number,
  color: string, alpha: number,
) {
  const start = -Math.PI / 2;
  const end = start + Math.PI * 2 * score;

  ctx.globalAlpha = alpha * 0.18;
  ctx.strokeStyle = THEME.text;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();

  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineCap = 'butt';
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, end);
  ctx.stroke();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(cx + Math.cos(end) * r, cy + Math.sin(end) * r, 2.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
}

interface CardRow { k: string; v: string; bar?: number }

/**
 * Offset data card on an elbow leader line. Every row is a real measurement —
 * see `drawPrimaryTelemetry` for where each number comes from.
 */
function drawDataCard(
  ctx: CanvasRenderingContext2D,
  ax: number, ay: number, side: 'left' | 'right',
  title: string, rows: CardRow[],
  color: string, alpha: number, canvasW: number, canvasH: number,
) {
  const cw = 148;
  const headerH = 16;
  const rowH = 15;
  const ch = headerH + rows.length * rowH + 6;
  const dir = side === 'right' ? 1 : -1;

  // Elbow: diagonal away from the box, then horizontal into the card edge.
  const e1x = ax + dir * 20;
  const e1y = ay - 20;
  const e2x = e1x + dir * 18;
  const cardX = Math.max(6, Math.min(canvasW - cw - 6, side === 'right' ? e2x : e2x - cw));
  const cardY = Math.max(6, Math.min(canvasH - ch - 6, e1y - headerH / 2));

  ctx.globalAlpha = alpha * 0.6;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(e1x, e1y);
  ctx.lineTo(e2x, e1y);
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(ax, ay, 2, 0, Math.PI * 2);
  ctx.fill();

  ctx.globalAlpha = alpha;
  ctx.fillStyle = 'rgba(4, 10, 18, 0.72)';
  ctx.fillRect(cardX, cardY, cw, ch);

  // Header bar: colour fill, dark text — the readable-at-a-glance anchor.
  ctx.fillStyle = color;
  ctx.fillRect(cardX, cardY, cw, headerH);
  ctx.fillStyle = '#04070d';
  font(ctx, 700, 10, '1.4px');
  ctx.fillText(title, cardX + 6, cardY + 11);

  // Registration ticks on the card's lower corners.
  ctx.strokeStyle = color;
  ctx.globalAlpha = alpha * 0.7;
  ctx.beginPath();
  ctx.moveTo(cardX, cardY + ch - 6); ctx.lineTo(cardX, cardY + ch); ctx.lineTo(cardX + 6, cardY + ch);
  ctx.moveTo(cardX + cw - 6, cardY + ch); ctx.lineTo(cardX + cw, cardY + ch); ctx.lineTo(cardX + cw, cardY + ch - 6);
  ctx.stroke();

  rows.forEach((row, i) => {
    const ry = cardY + headerH + 11 + i * rowH;
    ctx.globalAlpha = alpha * 0.55;
    ctx.fillStyle = THEME.text;
    font(ctx, 500, 9, '0.8px');
    ctx.fillText(row.k, cardX + 6, ry);

    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    font(ctx, 700, 10, '0.5px');
    const vw = ctx.measureText(row.v).width;
    ctx.fillText(row.v, cardX + cw - 6 - vw, ry);

    if (row.bar !== undefined) {
      const barY = ry + 3;
      const barW = cw - 12;
      ctx.globalAlpha = alpha * 0.18;
      ctx.fillStyle = THEME.text;
      ctx.fillRect(cardX + 6, barY, barW, 2);
      ctx.globalAlpha = alpha * 0.9;
      ctx.fillStyle = color;
      ctx.fillRect(cardX + 6, barY, barW * row.bar, 2);
    }
  });
  ctx.globalAlpha = 1;
  ctx.letterSpacing = '0px';
}

function drawLabel(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  label: string, id: number, ageMs: number,
  color: string, alpha: number,
) {
  const text = `${label.toUpperCase()} #${id}`;
  const sub = formatAge(ageMs);
  font(ctx, 700, 11, '1.2px');
  const width = ctx.measureText(text).width;
  font(ctx, 500, 10, '0.6px');
  const subWidth = ctx.measureText(sub).width;
  const boxW = width + subWidth + 22;
  const boxH = 18;
  const cut = 5;
  // Flip the tag below the box if it would clip off the top edge.
  const ty = y - boxH - 6 < 0 ? y + 6 : y - boxH - 6;

  ctx.globalAlpha = alpha;
  ctx.fillStyle = 'rgba(4, 10, 18, 0.78)';
  ctx.beginPath();
  ctx.moveTo(x, ty);
  ctx.lineTo(x + boxW, ty);
  ctx.lineTo(x + boxW, ty + boxH - cut);
  ctx.lineTo(x + boxW - cut, ty + boxH);
  ctx.lineTo(x, ty + boxH);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = color;
  ctx.fillRect(x, ty, 2.5, boxH);
  font(ctx, 700, 11, '1.2px');
  ctx.fillText(text, x + 8, ty + 13);
  ctx.globalAlpha = alpha * 0.55;
  ctx.fillStyle = THEME.text;
  font(ctx, 500, 10, '0.6px');
  ctx.fillText(sub, x + 14 + width, ty + 13);
  ctx.globalAlpha = 1;
  ctx.letterSpacing = '0px';
}

// ---------------------------------------------------------------------------
// Frame chrome
// ---------------------------------------------------------------------------

/** Graduated rulers on the frame edges. These are a scale of the frame itself
 * — real by construction — and give the primary target's position something
 * to be measured against. */
function drawRulers(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const m = 16;
  ctx.strokeStyle = rgba(THEME.cyan, 0.28);
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i <= 20; i++) {
    const major = i % 5 === 0;
    const x = m + ((w - m * 2) * i) / 20;
    ctx.moveTo(x, h - m); ctx.lineTo(x, h - m - (major ? 9 : 4));
    const y = m + ((h - m * 2) * i) / 20;
    ctx.moveTo(m, y); ctx.lineTo(m + (major ? 9 : 4), y);
  }
  ctx.stroke();

  // Graduations, in percent of frame — the scale the primary target's POS
  // readout is measured against.
  ctx.fillStyle = rgba(THEME.cyan, 0.4);
  font(ctx, 500, 8, '1px');
  for (let i = 5; i <= 15; i += 5) {
    const v = String(i * 5);
    const x = m + ((w - m * 2) * i) / 20;
    ctx.fillText(v, x - ctx.measureText(v).width / 2, h - m - 13);
    ctx.fillText(v, m + 13, m + ((h - m * 2) * i) / 20 + 3);
  }
  ctx.letterSpacing = '0px';
}

/** Marker riding the edge rulers at the primary target's real centre. */
function drawAxisMarkers(
  ctx: CanvasRenderingContext2D,
  h: number, px: number, py: number, color: string, alpha: number,
) {
  const m = 16;
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 5]);
  ctx.beginPath();
  ctx.moveTo(px, py); ctx.lineTo(px, h - m);
  ctx.moveTo(px, py); ctx.lineTo(m, py);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.beginPath();
  ctx.moveTo(px, h - m - 7); ctx.lineTo(px - 4, h - m); ctx.lineTo(px + 4, h - m); ctx.closePath();
  ctx.moveTo(m + 7, py); ctx.lineTo(m, py - 4); ctx.lineTo(m, py + 4); ctx.closePath();
  ctx.fill();
  ctx.globalAlpha = 1;
}

function drawChrome(
  ctx: CanvasRenderingContext2D, w: number, h: number,
  t: number, reducedMotion: boolean, trackCount: number,
) {
  const cx = w / 2;
  const cy = h / 2;

  // Faint grid — depth without competing with the frame.
  ctx.strokeStyle = rgba(THEME.cyan, 0.045);
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 60; x < w; x += 60) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
  for (let y = 60; y < h; y += 60) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
  ctx.stroke();

  // Chamfered frame corners, doubled.
  const m = 16;
  const l = 42;
  const c = 10;
  ctx.strokeStyle = rgba(THEME.cyan, 0.55);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(m, m + l); ctx.lineTo(m, m + c); ctx.lineTo(m + c, m); ctx.lineTo(m + l, m);
  ctx.moveTo(w - m - l, m); ctx.lineTo(w - m - c, m); ctx.lineTo(w - m, m + c); ctx.lineTo(w - m, m + l);
  ctx.moveTo(w - m, h - m - l); ctx.lineTo(w - m, h - m - c); ctx.lineTo(w - m - c, h - m); ctx.lineTo(w - m - l, h - m);
  ctx.moveTo(m + l, h - m); ctx.lineTo(m + c, h - m); ctx.lineTo(m, h - m - c); ctx.lineTo(m, h - m - l);
  ctx.stroke();

  drawRulers(ctx, w, h);

  // Centre reticle: ticks, a hairline box, and a diamond.
  ctx.strokeStyle = rgba(THEME.cyan, 0.4);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - 20, cy); ctx.lineTo(cx - 7, cy);
  ctx.moveTo(cx + 7, cy); ctx.lineTo(cx + 20, cy);
  ctx.moveTo(cx, cy - 20); ctx.lineTo(cx, cy - 7);
  ctx.moveTo(cx, cy + 7); ctx.lineTo(cx, cy + 20);
  ctx.moveTo(cx, cy - 5); ctx.lineTo(cx + 5, cy); ctx.lineTo(cx, cy + 5); ctx.lineTo(cx - 5, cy); ctx.closePath();
  ctx.stroke();

  // Corner slug: real track count, so even the chrome is bound to data.
  ctx.globalAlpha = 0.65;
  ctx.fillStyle = THEME.cyan;
  font(ctx, 700, 9, '1.6px');
  ctx.fillText(`TRK ${String(trackCount).padStart(2, '0')}`, m + 4, h - m - 16);
  ctx.letterSpacing = '0px';
  ctx.globalAlpha = 1;

  if (reducedMotion) return;

  const sy = ((t / 3600) % 1) * h;
  const grad = ctx.createLinearGradient(0, sy - 60, 0, sy);
  grad.addColorStop(0, rgba(THEME.cyan, 0));
  grad.addColorStop(1, rgba(THEME.cyan, 0.09));
  ctx.fillStyle = grad;
  ctx.fillRect(0, sy - 60, w, 60);
  ctx.strokeStyle = rgba(THEME.cyan, 0.22);
  ctx.beginPath();
  ctx.moveTo(0, sy); ctx.lineTo(w, sy);
  ctx.stroke();
}

// ---------------------------------------------------------------------------
// Primary target
// ---------------------------------------------------------------------------

/**
 * The full instrument treatment, primary target only. Every printed number is
 * a real measurement: `CONF` is `Detection.score`, `AREA` is box area over
 * frame area, `POS` is the box centre as a percentage of frame dimensions,
 * `AGE` is the tracker's own track age. Deliberately no distance in metres —
 * a bigger box only means "nearer" for a known object at a known focal
 * length, which this project has neither, so printing metres would be the
 * first untrue number this HUD ever showed.
 */
function drawPrimaryTelemetry(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  target: TargetState, color: string, alpha: number,
  frameW: number, frameH: number, canvasW: number, canvasH: number,
  t: number, reducedMotion: boolean, settle: number,
) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const base = Math.min(w, h) / 2;
  // Rings sit outside the box and slide in as the lock completes.
  const r = base + 18 + (1 - settle) * 40;
  const spin = reducedMotion ? 0 : t / 9000;

  drawSegmentedRing(ctx, cx, cy, r + 12, spin + target.phase, color, alpha * 0.55, 1.5, 0.22);
  drawTickRing(ctx, cx, cy, r + 6, 60, -spin * 1.6 + target.phase, color, alpha * 0.7);
  drawConfidenceRing(ctx, cx, cy, r, target.score, color, alpha);

  // Radial notches pointing inward at the diagonals.
  ctx.globalAlpha = alpha * 0.6;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let k = 0; k < 4; k++) {
    const a = Math.PI / 4 + (k * Math.PI) / 2;
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    ctx.moveTo(cx + cos * (r + 22), cy + sin * (r + 22));
    ctx.lineTo(cx + cos * (r + 30), cy + sin * (r + 30));
  }
  ctx.stroke();
  ctx.globalAlpha = 1;

  const frameArea = frameW * frameH;
  const areaPct = frameArea > 0 ? ((target.bbox[2] * target.bbox[3]) / frameArea) * 100 : 0;
  const posX = frameW > 0 ? Math.round(((target.bbox[0] + target.bbox[2] / 2) / frameW) * 100) : 0;
  const posY = frameH > 0 ? Math.round(((target.bbox[1] + target.bbox[3] / 2) / frameH) * 100) : 0;

  const side: 'left' | 'right' = cx > canvasW / 2 ? 'left' : 'right';
  const anchorX = side === 'right' ? x + w : x;
  drawDataCard(
    ctx, anchorX, y + 6, side,
    `${target.label.toUpperCase()} · LOCK`,
    [
      { k: 'CONF', v: `${Math.round(target.score * 100)}%`, bar: target.score },
      { k: 'AREA', v: `${areaPct.toFixed(1)}% FRAME` },
      { k: 'POS', v: `${posX} / ${posY}` },
      { k: 'AGE', v: formatAge(target.ageMs) },
    ],
    color, alpha, canvasW, canvasH,
  );
}

// ---------------------------------------------------------------------------

export interface DrawHudOptions {
  ctx: CanvasRenderingContext2D;
  hudState: HudState;
  canvasW: number;
  canvasH: number;
  /** Video pixel space -> canvas pixel space. */
  scaleX: number;
  scaleY: number;
  /** Video frame dimensions, pixel space — for the honest relative readouts. */
  frameW: number;
  frameH: number;
  /** Wall-clock ms, for ambient chrome/telemetry motion. */
  t: number;
  mirrored: boolean;
  /** When true, sweeps/pulses/rotation freeze to a static state. */
  reducedMotion: boolean;
}

/**
 * Renders one HUD frame. Pure draw call — takes state, touches no other
 * state. Consumes `HudState` (per-target acquire/exit/interpolation,
 * computed once per tick by `hudState.ts`) rather than a raw `Frame`.
 */
export function drawHud(opts: DrawHudOptions): void {
  const { ctx, hudState, canvasW, canvasH, scaleX, scaleY, frameW, frameH, t, mirrored, reducedMotion } = opts;

  ctx.clearRect(0, 0, canvasW, canvasH);

  const targets = [...hudState.targets.values()];
  const liveCount = targets.filter((tg) => !tg.exiting).length;
  drawChrome(ctx, canvasW, canvasH, t, reducedMotion, liveCount);

  // The video preview is mirrored for a natural selfie view. We mirror the
  // box *coordinates* rather than the canvas itself — flipping the canvas
  // would flip the label text along with it and render it backwards.
  const flipX = (bx: number, bw: number) => (mirrored ? canvasW - bx - bw : bx);

  // Primary last, so its rings and card sit above every other target.
  targets.sort((a, b) => Number(a.id === hudState.primaryId) - Number(b.id === hudState.primaryId));

  let primaryCentre: { x: number; y: number; color: string; alpha: number } | null = null;

  for (const target of targets) {
    const [tbx, tby, tbw, tbh] = target.bbox;
    const w = tbw * scaleX;
    const h = tbh * scaleY;
    const x = flipX(tbx * scaleX, w);
    const y = tby * scaleY;
    const color = target.label === 'person' ? THEME.amber : accentFor(target.label);
    const isPrimary = target.id === hudState.primaryId;

    const acquireProgress = Math.min(1, target.acquireMs / ACQUIRE_MS);
    const exitProgress = target.exiting ? Math.min(1, target.exitMs / EXIT_MS) : 0;
    const maxOutset = OUTSET_RATIO * Math.min(w, h);
    const outset = (1 - acquireProgress) * maxOutset + exitProgress * maxOutset;

    const dim = SECONDARY_ALPHA + (1 - SECONDARY_ALPHA) * target.primaryProgress;
    const alpha = dim * (1 - exitProgress);

    // Per-target breathing so tracking reads as alive, not static — phased
    // per id so targets don't pulse in lockstep.
    const breathe = reducedMotion ? 1 : Math.sin(t / 900 + target.phase) * 0.5 + 0.5;
    const glow = isPrimary ? PRIMARY_GLOW * (reducedMotion ? 1 : 0.6 + breathe * 0.4) : 0;

    drawBrackets(ctx, x, y, w, h, color, alpha, outset, glow, isPrimary ? 2 : 1.25);
    drawLabel(ctx, x, y, target.label, target.id, target.ageMs, color, alpha * (0.4 + acquireProgress * 0.6));

    if (isPrimary && exitProgress === 0) {
      drawPrimaryTelemetry(
        ctx, x, y, w, h, target, color, alpha * target.primaryProgress,
        frameW, frameH, canvasW, canvasH, t, reducedMotion, target.primaryProgress * acquireProgress,
      );
      primaryCentre = { x: x + w / 2, y: y + h / 2, color, alpha: alpha * target.primaryProgress };
    } else if (!isPrimary) {
      // Secondary targets get a centre pip only — cheap, and it keeps the
      // hierarchy readable rather than crowding the frame with instruments.
      ctx.globalAlpha = alpha * 0.7;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      const px = x + w / 2;
      const py = y + h / 2;
      ctx.beginPath();
      ctx.moveTo(px, py - 4); ctx.lineTo(px + 4, py); ctx.lineTo(px, py + 4); ctx.lineTo(px - 4, py); ctx.closePath();
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }

  if (primaryCentre) {
    drawAxisMarkers(ctx, canvasH, primaryCentre.x, primaryCentre.y, primaryCentre.color, primaryCentre.alpha * 0.5);
  }
}
