/**
 * Auto-apply opt-in (amendement règle 2 du 2026-07-16) — le commutateur de
 * modèle : succès vérifié, abandons silencieux, et OPT-IN strict dans le flux
 * (sans opt-in : lecture seule, aucun clic).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationMemory } from '../src/conversationMemory';
import { runRecommendationFlow, type FlowDeps } from '../src/content-main';
import { FR_MESSAGES } from '../src/messages';
import { MockClient } from '../src/mockClient';
import { applyModelInPage } from '../src/modelSwitcher';

/** Monte un sélecteur de modèle factice imitant claude.ai (menu au clic). */
function mountFakeModelSelector(initial = 'Claude Opus 4.8', itemsRespond = true): void {
  document.body.innerHTML = '<main></main>';
  const button = document.createElement('button');
  button.setAttribute('data-testid', 'model-selector');
  button.textContent = initial;
  document.body.appendChild(button);

  const menu = document.createElement('div');
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  for (const label of ['Claude Haiku 4.5', 'Claude Sonnet 5', 'Claude Opus 4.8']) {
    const item = document.createElement('button');
    item.setAttribute('role', 'menuitem');
    item.textContent = label;
    if (itemsRespond) {
      item.addEventListener('click', () => {
        button.textContent = label;
        menu.hidden = true;
      });
    }
    menu.appendChild(item);
  }
  button.addEventListener('click', () => {
    menu.hidden = !menu.hidden;
  });
  document.body.appendChild(menu);
}

/**
 * Variante à DEUX niveaux imitant claude.ai : le premier niveau ne contient
 * que le modèle vedette + « Plus de modèles › » ; les items du sous-menu sont
 * MONTÉS DYNAMIQUEMENT à l'ouverture (comme Radix), au survol ou au clic.
 */
function mountNestedModelSelector(initial = 'Fable 5 Max'): void {
  document.body.innerHTML = '<main></main>';
  const button = document.createElement('button');
  button.setAttribute('data-testid', 'model-selector-dropdown');
  button.textContent = initial;
  document.body.appendChild(button);

  const menu = document.createElement('div');
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  const featured = document.createElement('button');
  featured.setAttribute('role', 'menuitem');
  featured.textContent = 'Fable 5 — Pour vos défis les plus difficiles';
  menu.appendChild(featured);
  const more = document.createElement('button');
  more.setAttribute('role', 'menuitem');
  more.setAttribute('aria-haspopup', 'menu');
  more.textContent = 'Plus de modèles ›';
  menu.appendChild(more);
  document.body.appendChild(menu);

  button.addEventListener('click', () => {
    menu.hidden = false;
  });

  let submenu: HTMLElement | null = null;
  const openSubmenu = () => {
    if (submenu) return;
    submenu = document.createElement('div');
    submenu.setAttribute('role', 'menu');
    for (const label of ['Claude Haiku 4.5', 'Claude Sonnet 5', 'Claude Opus 4.8']) {
      const item = document.createElement('button');
      item.setAttribute('role', 'menuitem');
      item.textContent = label;
      item.addEventListener('click', () => {
        button.textContent = label;
        menu.hidden = true;
        submenu?.remove();
        submenu = null;
      });
      submenu.appendChild(item);
    }
    document.body.appendChild(submenu);
  };
  more.addEventListener('pointerover', openSubmenu);
  more.addEventListener('click', openSubmenu);
}

const FAST = { menuTimeoutMs: 200, settleMs: 0 };

describe('applyModelInPage — succès vérifié', () => {
  it('ouvre le menu, clique le bon item et vérifie le résultat', async () => {
    mountFakeModelSelector('Claude Opus 4.8');
    await expect(applyModelInPage('claude-sonnet-5', FAST)).resolves.toBe(true);
    expect(document.querySelector('[data-testid="model-selector"]')?.textContent).toBe(
      'Claude Sonnet 5',
    );
  });

  it('menu à DEUX niveaux (claude.ai réel) : ouvre « Plus de modèles » et sélectionne', async () => {
    mountNestedModelSelector('Fable 5 Max');
    await expect(applyModelInPage('claude-sonnet-5', FAST)).resolves.toBe(true);
    expect(document.querySelector('[data-testid="model-selector-dropdown"]')?.textContent).toBe(
      'Claude Sonnet 5',
    );
  });

  it('modèle déjà sélectionné : true sans aucun clic', async () => {
    mountFakeModelSelector('Claude Sonnet 5');
    const button = document.querySelector<HTMLElement>('[data-testid="model-selector"]')!;
    const clickSpy = vi.spyOn(button, 'click');
    await expect(applyModelInPage('claude-sonnet-5', FAST)).resolves.toBe(true);
    expect(clickSpy).not.toHaveBeenCalled();
  });
});

describe('applyModelInPage — abandons silencieux', () => {
  it('aucun sélecteur de modèle dans la page → false, sans throw', async () => {
    document.body.innerHTML = '<main></main>';
    await expect(applyModelInPage('claude-sonnet-5', FAST)).resolves.toBe(false);
  });

  it('le clic ne change pas le modèle (menu inerte) → false après vérification', async () => {
    mountFakeModelSelector('Claude Opus 4.8', false); // items sans effet
    await expect(applyModelInPage('claude-sonnet-5', FAST)).resolves.toBe(false);
    // Le libellé n'a pas bougé : l'utilisateur garde la main.
    expect(document.querySelector('[data-testid="model-selector"]')?.textContent).toBe(
      'Claude Opus 4.8',
    );
  });

  it('modèle absent du menu → false dans le délai imparti', async () => {
    mountFakeModelSelector('Claude Opus 4.8');
    await expect(applyModelInPage('modele-inconnu-9', FAST)).resolves.toBe(false);
  });
});

describe('Flux : OPT-IN strict (amendement règle 2)', () => {
  function deps(
    overrides: Partial<Omit<FlowDeps, 'client'>> = {},
  ): FlowDeps & { client: MockClient } {
    return {
      client: new MockClient({ latencyMs: 0 }),
      memory: new ConversationMemory(),
      config: {
        enabled: true,
        mode: 'equilibre',
        models_visible: ['claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'],
        send_prompt_text: false,
        messages: { fr: {} },
        min_extension_version: '0.1.0',
      },
      messages: FR_MESSAGES,
      ...overrides,
    };
  }

  function shadow(): ShadowRoot {
    return document.getElementById('sobrio-reco-host')!.shadowRoot!;
  }

  beforeEach(() => {
    document.body.innerHTML = '<main></main>';
  });

  it('opt-in activé : « Utiliser » déclenche applyModel avec le modèle recommandé', async () => {
    const applyModel = vi.fn().mockResolvedValue(true);
    const flowDeps = deps({ applyModel });
    const reco = await runRecommendationFlow('Quelle heure est-il ?', flowDeps);
    (shadow().querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();
    expect(applyModel).toHaveBeenCalledWith(reco!.recommended_model);
  });

  it('opt-in activé : la dérogation applique le modèle choisi', async () => {
    const applyModel = vi.fn().mockResolvedValue(true);
    await runRecommendationFlow('Quelle heure est-il ?', deps({ applyModel }));
    const select = shadow().querySelector<HTMLSelectElement>('[data-sobrio-override]')!;
    select.value = 'claude-opus-4-8';
    select.dispatchEvent(new Event('change'));
    expect(applyModel).toHaveBeenCalledWith('claude-opus-4-8');
  });

  it("SANS opt-in (défaut) : lecture seule stricte — la page hôte n'est jamais touchée", async () => {
    mountFakeModelSelector('Claude Opus 4.8');
    const main = document.createElement('main');
    document.body.appendChild(main);
    const flowDeps = deps(); // applyModel ABSENT = défaut
    await runRecommendationFlow('Quelle heure est-il ?', flowDeps);
    (shadow().querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();
    await new Promise((resolve) => setTimeout(resolve, 20));
    // Le sélecteur de la page hôte n'a pas bougé, la télémétrie est partie.
    expect(document.querySelector('[data-testid="model-selector"]')?.textContent).toBe(
      'Claude Opus 4.8',
    );
    expect(flowDeps.client.sentEvents).toHaveLength(1);
  });
});
