/**
 * Génère les icônes placeholder de l'extension — ZÉRO dépendance.
 * PNG encodé à la main (zlib natif de Node) : carré sobre #2b2a27 avec un
 * « S » clair tracé sur une grille 5×7. Usage : node dev/make-icons.mjs
 */
import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT_DIR = join(fileURLToPath(new URL('..', import.meta.url)), 'public', 'icon');
const SIZES = [16, 32, 48, 128];

// Grille 5×7 du « S » (1 = pixel clair).
const GLYPH = ['01111', '10000', '10000', '01110', '00001', '00001', '11110'].map((row) =>
  [...row].map(Number),
);

const DARK = [0x2b, 0x2a, 0x27, 0xff];
const LIGHT = [0xfa, 0xf8, 0xf5, 0xff];

/** CRC32 (polynôme PNG). */
const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const typed = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typed));
  return Buffer.concat([length, typed, crc]);
}

function makeIcon(size) {
  // Fond arrondi (coins coupés simples) + glyphe centré.
  const pixels = Buffer.alloc(size * size * 4);
  const corner = Math.max(1, Math.round(size / 8));
  const cell = Math.max(1, Math.floor((size * 0.6) / 7));
  const glyphW = cell * 5;
  const glyphH = cell * 7;
  const offsetX = Math.floor((size - glyphW) / 2);
  const offsetY = Math.floor((size - glyphH) / 2);

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const index = (y * size + x) * 4;
      // Coins « arrondis » : on laisse transparent un petit triangle.
      const dx = Math.min(x, size - 1 - x);
      const dy = Math.min(y, size - 1 - y);
      if (dx + dy < corner) continue; // alpha 0 (transparent)

      let color = DARK;
      const gx = Math.floor((x - offsetX) / cell);
      const gy = Math.floor((y - offsetY) / cell);
      if (gx >= 0 && gx < 5 && gy >= 0 && gy < 7 && GLYPH[gy][gx] === 1) color = LIGHT;
      pixels.set(color, index);
    }
  }

  // Scanlines avec filtre 0.
  const raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y += 1) {
    raw[y * (size * 4 + 1)] = 0;
    pixels.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // profondeur
  ihdr[9] = 6; // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

mkdirSync(OUT_DIR, { recursive: true });
for (const size of SIZES) {
  writeFileSync(join(OUT_DIR, `${size}.png`), makeIcon(size));
  console.log(`icône ${size}×${size} → public/icon/${size}.png`);
}
