/**
 * formatRange — MIROIR de src/panel.ts formatRange. Module PUR (aucun effet de
 * bord) : importé par le harnais de capture (scripts/capture-visual.mjs) ET par
 * un test de parité (tests/extension_theme.test.ts) qui échoue si les deux
 * implémentations divergent. Fourchette FR : décimale virgule + tiret
 * demi-cadratin sans espaces (charte §4). 4 déc. si max<0,01 · 3 si <1 · 1 sinon.
 */
export function formatRange(min, max) {
  const digits = max < 0.01 ? 4 : max < 1 ? 3 : 1;
  const fr = (n) => n.toFixed(digits).replace('.', ',');
  return `${fr(min)}–${fr(max)}`;
}
