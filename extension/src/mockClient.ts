/**
 * Client MOCK — la « fausse API » locale de la V0, conforme au contrat.
 *
 * Tout se développe et se démontre sans serveur : les règles vivent dans
 * src/mockRules.ts (pures), ce module ajoute la forme du contrat (reco_id,
 * fourchettes d'impact, budget), une latence simulée et un mode « panne »
 * pour tester la règle 3 (jamais bloquant : échec ⇒ null silencieux).
 *
 * Règle 5 : tout coût/énergie est un min–max — jamais de valeur unique.
 */
import type { Budget, ExtensionConfig, ImpactEstimate, RecoEvent } from './api';
import { decide } from './mockRules';
import type { Signals } from './signals';

/** Réponse de recommandation V0 (contrat de ce prompt — cf. RFC v1.1). */
export interface RecoV0 {
  reco_id: string;
  recommended_model: string;
  confidence: number;
  rule: string;
  impact_estimate: ImpactEstimate;
  budget: Budget | null;
  suggest_new_conversation: boolean;
}

/** Signaux de santé de l'extension — nom fermé, AUCUNE autre donnée. */
export type HealthSignal = 'selector_broken';

/** Interface commune mock/api — consommée par le content script. */
export interface RecoClientV0 {
  recommend(signals: Signals): Promise<RecoV0 | null>;
  /** Fire-and-forget : ne retourne rien, n'affecte jamais l'utilisateur. */
  sendRecoEvent(event: RecoEvent): void;
  /** Livraison avec accusé (utilisée par la file de télémétrie persistante). */
  deliverRecoEvent(event: RecoEvent): Promise<boolean>;
  getConfig(): Promise<ExtensionConfig | null>;
  /**
   * Signal de santé léger (ex. sélecteurs cassés) — OPTIONNEL. Le contrat
   * v1.0 ne le prévoit pas : le client API réel ne l'implémente PAS
   * (proposé par la RFC v1.1) ; le mock le capture localement.
   */
  sendHealthSignal?(signal: HealthSignal): void;
}

/**
 * Tarifs/énergie du mock — mêmes ordres de grandeur que
 * contracts/model_catalog.yaml (USD/Mtok et Wh/ktok de sortie, min–max).
 * Le mock est local : pas de dépendance au fichier de contrat au runtime.
 */
const MOCK_CATALOG: Readonly<
  Record<string, { inUsd: number; outUsd: number; whMin: number; whMax: number; visible?: boolean }>
> = {
  'claude-haiku-4-5': { inUsd: 1.0, outUsd: 5.0, whMin: 0.3, whMax: 1.4 },
  // Sonnet 5 : tarif DURABLE (standard) retenu volontairement, pas le prix
  // d'introduction 2/10 actif jusqu'au 2026-08-31 — un outil de maîtrise de
  // coût doit refléter le coût en régime permanent (décision, docs/decisions.md).
  'claude-sonnet-5': { inUsd: 3.0, outUsd: 15.0, whMin: 0.8, whMax: 3.5 },
  'claude-opus-4-8': { inUsd: 5.0, outUsd: 25.0, whMin: 1.5, whMax: 6.0 },
  // visible: false — gardé pour le chiffrage/impact, non proposé à la
  // dérogation (sobriété), aligné sur `visible: false` du catalogue/API.
  'claude-fable-5': { inUsd: 10.0, outUsd: 50.0, whMin: 2.5, whMax: 9.0, visible: false },
};

/** Taux fixe — même convention que le monorepo. TODO(V1) : source datée. */
const EUR_PER_USD = 0.92;

/** Hypothèse V0 de tokens de sortie. TODO(V1) : calibrer sur l'historique. */
function estimateTokensOut(tokensIn: number): number {
  return Math.min(2000, Math.max(150, tokensIn));
}

/** Fourchettes coût/énergie pour un modèle donné (règle 5 : min–max). */
export function mockImpactEstimate(model: string, tokensIn: number): ImpactEstimate {
  const entry = MOCK_CATALOG[model] ?? MOCK_CATALOG['claude-sonnet-5']!;
  const tokensOut = estimateTokensOut(tokensIn);
  const costPointEur =
    ((tokensIn * entry.inUsd + tokensOut * entry.outUsd) / 1_000_000) * EUR_PER_USD;
  return {
    // Bande ±20 % : l'estimation est incertaine et on l'assume (ton humble).
    cost_eur_min: round6(costPointEur * 0.8),
    cost_eur_max: round6(costPointEur * 1.2),
    energy_wh_min: round6((entry.whMin * tokensOut) / 1000),
    energy_wh_max: round6((entry.whMax * tokensOut) / 1000),
  };
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

export interface MockClientOptions {
  /** Latence simulée (ms) — doit rester sous les 400 ms du timeout. */
  latencyMs?: number;
  /** Mode panne (règle 3) : 'mute' = null silencieux, 'error' = rejet. */
  failure?: 'none' | 'mute' | 'error';
  /** Budget renvoyé ('absent' pour tester l'état sans budget). */
  budget?: Budget | 'absent';
  /** Kill-switch de la config mock. */
  enabled?: boolean;
}

/** Compteur local pour des reco_id lisibles et uniques en démo. */
let mockRecoCounter = 0;

export class MockClient implements RecoClientV0 {
  private readonly options: Required<MockClientOptions>;

  /** Événements capturés — inspection en tests et en démo (jamais réseau). */
  readonly sentEvents: RecoEvent[] = [];

  /** Signaux de santé capturés (ex. selector_broken). */
  readonly healthSignals: HealthSignal[] = [];

  constructor(options: MockClientOptions = {}) {
    this.options = {
      latencyMs: options.latencyMs ?? 120,
      failure: options.failure ?? 'none',
      budget: options.budget ?? { team_label: 'Équipe démo', pct_used: 42 },
      enabled: options.enabled ?? true,
    };
  }

  private async simulateLatency(): Promise<void> {
    if (this.options.latencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.options.latencyMs));
    }
  }

  async recommend(signals: Signals): Promise<RecoV0 | null> {
    await this.simulateLatency();
    if (this.options.failure === 'mute') return null;
    if (this.options.failure === 'error') throw new Error('mock: panne simulée');

    const decision = decide(signals);
    mockRecoCounter += 1;
    return {
      reco_id: `mock-${String(mockRecoCounter).padStart(6, '0')}`,
      recommended_model: decision.recommended_model,
      confidence: decision.confidence,
      rule: decision.rule,
      impact_estimate: mockImpactEstimate(decision.recommended_model, signals.prompt.token_est),
      budget: this.options.budget === 'absent' ? null : this.options.budget,
      suggest_new_conversation: decision.suggest_new_conversation,
    };
  }

  sendRecoEvent(event: RecoEvent): void {
    if (this.options.failure !== 'none') return; // panne : perdu, sans bruit
    this.sentEvents.push(event);
  }

  async deliverRecoEvent(event: RecoEvent): Promise<boolean> {
    if (this.options.failure !== 'none') return false; // livraison échouée
    this.sentEvents.push(event);
    return true;
  }

  sendHealthSignal(signal: HealthSignal): void {
    if (this.options.failure !== 'none') return;
    this.healthSignals.push(signal);
  }

  async getConfig(): Promise<ExtensionConfig | null> {
    await this.simulateLatency();
    if (this.options.failure !== 'none') return null;
    return {
      enabled: this.options.enabled,
      mode: 'equilibre',
      // Modèles proposables (dérogation) : ceux dont `visible !== false` —
      // sémantique alignée sur le champ `visible` du catalogue/API (Fable 5
      // exclu par sobriété, gardé pour le chiffrage).
      models_visible: Object.entries(MOCK_CATALOG)
        .filter(([, entry]) => entry.visible !== false)
        .map(([id]) => id),
      send_prompt_text: false,
      messages: { fr: {} },
      min_extension_version: '0.1.0',
    };
  }
}
