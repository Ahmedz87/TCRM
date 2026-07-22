/* qrcode.ts — tiny self-contained QR encoder (byte mode, ECC level M, auto version 1-10).
   Returns a boolean matrix. No dependencies. Enough for URLs up to ~270 bytes. */

// Galois field (GF(256)) tables for Reed-Solomon
const EXP = new Array(512), LOG = new Array(256);
(() => { let x = 1; for (let i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11d; }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255]; })();
const gmul = (a: number, b: number) => (a === 0 || b === 0) ? 0 : EXP[LOG[a] + LOG[b]];

function rsGen(deg: number): number[] {
  let poly = [1];
  for (let i = 0; i < deg; i++) {
    const np = new Array(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j++) { np[j] ^= gmul(poly[j], 1); np[j + 1] ^= gmul(poly[j], EXP[i]); }
    poly = np;
  }
  return poly;
}
function rsEncode(data: number[], ecLen: number): number[] {
  const gen = rsGen(ecLen), res = new Array(ecLen).fill(0);
  for (const d of data) {
    const factor = d ^ res[0];
    res.shift(); res.push(0);
    for (let i = 0; i < ecLen; i++) res[i] ^= gmul(gen[i], factor);
  }
  return res;
}

// version specs for ECC level M: [totalCodewords, ecPerBlock, numBlocks1, dataPerBlock1, numBlocks2, dataPerBlock2]
const VER_M: any = {
  1: [26, 10, 1, 16, 0, 0], 2: [44, 16, 1, 28, 0, 0], 3: [70, 26, 1, 44, 0, 0],
  4: [100, 18, 2, 32, 0, 0], 5: [134, 24, 2, 43, 0, 0], 6: [172, 16, 4, 27, 0, 0],
  7: [196, 18, 4, 31, 0, 0], 8: [242, 22, 2, 38, 2, 39], 9: [292, 22, 3, 36, 2, 37],
  10: [346, 26, 4, 43, 1, 44],
};
const ALIGN: any = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
  7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50] };

function pickVersion(len: number): number {
  for (let v = 1; v <= 10; v++) {
    const s = VER_M[v]; const dataCw = s[2] * s[3] + s[4] * s[5];
    const capacity = dataCw - 2 - (v >= 10 ? 1 : 0);   // header ~2 bytes
    if (len <= capacity) return v;
  }
  throw new Error('QR: data too long');
}

export function qrMatrix(text: string): boolean[][] {
  const bytes: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c < 128) bytes.push(c);
    else if (c < 2048) { bytes.push(192 | (c >> 6), 128 | (c & 63)); }
    else { bytes.push(224 | (c >> 12), 128 | ((c >> 6) & 63), 128 | (c & 63)); }
  }
  const ver = pickVersion(bytes.length);
  const spec = VER_M[ver];
  const [totalCw, ecLen, nb1, dc1, nb2, dc2] = spec;
  const size = 17 + ver * 4;
  const lenBits = ver < 10 ? 8 : 16;

  // build bit stream: mode(0100) + length + data + terminator
  const bits: number[] = [];
  const push = (val: number, n: number) => { for (let i = n - 1; i >= 0; i--) bits.push((val >> i) & 1); };
  push(4, 4); push(bytes.length, lenBits);
  for (const b of bytes) push(b, 8);
  const totalData = nb1 * dc1 + nb2 * dc2;
  const cap = totalData * 8;
  for (let i = 0; i < 4 && bits.length < cap; i++) bits.push(0);
  while (bits.length % 8) bits.push(0);
  const dataCw: number[] = [];
  for (let i = 0; i < bits.length; i += 8) { let b = 0; for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j]; dataCw.push(b); }
  const pad = [0xec, 0x11]; let pi = 0;
  while (dataCw.length < totalData) dataCw.push(pad[pi++ % 2]);

  // split into blocks, compute EC
  const blocks: number[][] = [], ecBlocks: number[][] = [];
  let idx = 0;
  for (let b = 0; b < nb1; b++) { const d = dataCw.slice(idx, idx + dc1); idx += dc1; blocks.push(d); ecBlocks.push(rsEncode(d, ecLen)); }
  for (let b = 0; b < nb2; b++) { const d = dataCw.slice(idx, idx + dc2); idx += dc2; blocks.push(d); ecBlocks.push(rsEncode(d, ecLen)); }

  // interleave
  const finalCw: number[] = [];
  const maxD = Math.max(dc1, dc2);
  for (let i = 0; i < maxD; i++) for (const bl of blocks) if (i < bl.length) finalCw.push(bl[i]);
  for (let i = 0; i < ecLen; i++) for (const ec of ecBlocks) finalCw.push(ec[i]);

  // module matrix
  const m: (boolean | null)[][] = Array.from({ length: size }, () => new Array(size).fill(null));
  const setFinder = (r: number, c: number) => {
    for (let i = -1; i <= 7; i++) for (let j = -1; j <= 7; j++) {
      const rr = r + i, cc = c + j; if (rr < 0 || rr >= size || cc < 0 || cc >= size) continue;
      const on = (i >= 0 && i <= 6 && (j === 0 || j === 6)) || (j >= 0 && j <= 6 && (i === 0 || i === 6)) || (i >= 2 && i <= 4 && j >= 2 && j <= 4);
      m[rr][cc] = on;
    }
  };
  setFinder(0, 0); setFinder(0, size - 7); setFinder(size - 7, 0);
  for (let i = 8; i < size - 8; i++) { m[6][i] = i % 2 === 0; m[i][6] = i % 2 === 0; }
  const al = ALIGN[ver];
  for (const r of al) for (const c of al) {
    if ((r <= 8 && c <= 8) || (r <= 8 && c >= size - 9) || (r >= size - 9 && c <= 8)) continue;
    for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++)
      m[r + i][c + j] = Math.max(Math.abs(i), Math.abs(j)) !== 1;
  }
  m[size - 8][8] = true;   // dark module

  // reserve format areas (mark non-null placeholder = false)
  const reserve = () => { for (let i = 0; i < 9; i++) { if (m[8][i] === null) m[8][i] = false; if (m[i][8] === null) m[i][8] = false; }
    for (let i = 0; i < 8; i++) { if (m[8][size - 1 - i] === null) m[8][size - 1 - i] = false; if (m[size - 1 - i][8] === null) m[size - 1 - i][8] = false; } };
  reserve();

  // place data with mask 0 ((r+c)%2==0)
  let bit = 0; const stream: number[] = [];
  for (const cw of finalCw) for (let i = 7; i >= 0; i--) stream.push((cw >> i) & 1);
  let up = true;
  for (let col = size - 1; col > 0; col -= 2) {
    if (col === 6) col--;
    for (let n = 0; n < size; n++) {
      const row = up ? size - 1 - n : n;
      for (let c = 0; c < 2; c++) {
        const cc = col - c;
        if (m[row][cc] === null) {
          let v = bit < stream.length ? stream[bit++] === 1 : false;
          if ((row + cc) % 2 === 0) v = !v;   // mask 0
          m[row][cc] = v;
        }
      }
    }
    up = !up;
  }

  // format info (ECC M = 00, mask 0) → 15 bits
  const fmt = 0x5412;   // precomputed for (M, mask0): 000 pattern → 101000010010010
  for (let i = 0; i < 15; i++) {
    const b = ((fmt >> i) & 1) === 1;
    if (i < 6) m[8][i] = b; else if (i < 8) m[8][i + 1] = b; else if (i === 8) m[7][8] = b;
    else m[14 - i][8] = b;
    if (i < 8) m[size - 1 - i][8] = b; else m[8][size - 15 + i] = b;
  }

  return m.map(row => row.map(v => v === true));
}

/** Render a QR to an inline SVG string. */
export function qrSVG(text: string, px = 220, dark = '#111', light = '#fff'): string {
  const m = qrMatrix(text); const n = m.length; const q = 4; const total = n + q * 2;
  const cell = px / total;
  let rects = '';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (m[r][c])
    rects += `<rect x="${((c + q) * cell).toFixed(2)}" y="${((r + q) * cell).toFixed(2)}" width="${cell.toFixed(2)}" height="${cell.toFixed(2)}"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${px}" height="${px}" viewBox="0 0 ${px} ${px}">`
    + `<rect width="${px}" height="${px}" fill="${light}"/><g fill="${dark}">${rects}</g></svg>`;
}
