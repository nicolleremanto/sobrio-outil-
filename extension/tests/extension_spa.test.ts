/**
 * Boucle 3 — cycle de vie SPA & mémoire par conversation : clés d'URL,
 * registre multi-conversations, détecteur de navigation, contrôleur,
 * re-scan à l'arrivée mid-fil, indépendance multi-onglets, zéro texte.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ConversationMemory, type PageView } from '../src/conversationMemory';
import { ConversationRegistry, MAX_CONVERSATIONS } from '../src/conversationRegistry';
import { createConversationController } from '../src/conversationController';
import { conversationKeyFromPath, observeConversationChanges } from '../src/spaLifecycle';
import { loadFixture } from '../test/loadFixture';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('conversationKeyFromPath — clés stables', () => {
  it('extrait l’id de /chat/<id>', () => {
    expect(conversationKeyFromPath('/chat/abc-123')).toBe('chat:abc-123');
    expect(conversationKeyFromPath('/chat/abc-123?x=1')).toBe('chat:abc-123');
  });
  it('gère /project/<id> et la nouvelle conversation', () => {
    expect(conversationKeyFromPath('/project/p9')).toBe('project:p9');
    expect(conversationKeyFromPath('/')).toBe('new');
    expect(conversationKeyFromPath('/new')).toBe('new');
  });
});

describe('ConversationRegistry — états distincts et persistants', () => {
  it('mémoires distinctes par clé, restituées à la réactivation', () => {
    const reg = new ConversationRegistry();
    const a = reg.activate('chat:a');
    a.noteRecoShown();
    a.noteRecoShown();
    const b = reg.activate('chat:b');
    b.noteRecoShown();

    expect(reg.size()).toBe(2);
    expect(reg.activate('chat:a').toSignals().recos_shown).toBe(2); // intact
    expect(reg.activate('chat:b').toSignals().recos_shown).toBe(1);
  });

  it('éviction LRU au-delà du plafond, sans toucher l’active', () => {
    const reg = new ConversationRegistry(() => new ConversationMemory(), 3);
    reg.activate('k0');
    reg.activate('k1');
    reg.activate('k2');
    reg.activate('k2'); // k2 active
    reg.activate('k3'); // dépasse : évince le plus ancien non-actif (k0)
    expect(reg.size()).toBe(3);
    // k0 évincé → réactiver crée une mémoire neuve.
    expect(reg.activate('k0').toSignals().recos_shown).toBe(0);
  });

  it('deux registres (deux onglets) sont indépendants', () => {
    const tab1 = new ConversationRegistry();
    const tab2 = new ConversationRegistry();
    tab1.activate('chat:x').noteRecoShown();
    expect(tab2.activate('chat:x').toSignals().recos_shown).toBe(0);
    expect(MAX_CONVERSATIONS).toBeGreaterThan(0);
  });
});

describe('observeConversationChanges — navigation SPA', () => {
  it('notifie sur pushState et popstate, jamais au démarrage', () => {
    let path = '/chat/a';
    const target = new EventTarget() as unknown as Window;
    const hist = {
      pushState: vi.fn(),
      replaceState: vi.fn(),
    } as unknown as History;
    const onChange = vi.fn();

    const life = observeConversationChanges(onChange, {
      getPath: () => path,
      history: hist,
      target,
    });
    expect(life.currentKey()).toBe('chat:a');
    expect(onChange).not.toHaveBeenCalled();

    path = '/chat/b';
    hist.pushState({}, '', '/chat/b'); // le wrap déclenche check()
    expect(onChange).toHaveBeenLastCalledWith('chat:b');
    expect(life.currentKey()).toBe('chat:b');

    path = '/chat/c';
    target.dispatchEvent(new Event('popstate'));
    expect(onChange).toHaveBeenLastCalledWith('chat:c');

    life.stop();
  });

  it('stop() détache les écouteurs (plus de notification)', () => {
    let path = '/chat/a';
    const target = new EventTarget() as unknown as Window;
    const onChange = vi.fn();
    const life = observeConversationChanges(onChange, { getPath: () => path, target });
    life.stop();
    path = '/chat/z';
    target.dispatchEvent(new Event('popstate'));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('createConversationController — intégration', () => {
  it('bascule la mémoire active au changement de fil et conserve les états', () => {
    let path = '/chat/a';
    const target = new EventTarget() as unknown as Window;
    const changes: string[] = [];
    const controller = createConversationController({
      getPath: () => path,
      target,
      onConversationChange: (key) => changes.push(key),
    });

    // Fil A : deux recos affichées.
    controller.currentMemory().noteRecoShown();
    controller.currentMemory().noteRecoShown();
    expect(controller.currentKey()).toBe('chat:a');

    // Navigation SPA vers le fil B (popstate).
    path = '/chat/b';
    target.dispatchEvent(new Event('popstate'));
    expect(controller.currentKey()).toBe('chat:b');
    expect(changes).toEqual(['chat:b']);
    expect(controller.currentMemory().toSignals().recos_shown).toBe(0); // fil neuf

    // Retour sur le fil A : son état est intact.
    path = '/chat/a';
    target.dispatchEvent(new Event('popstate'));
    expect(controller.currentMemory().toSignals().recos_shown).toBe(2);
    expect(controller.size()).toBe(2);
    controller.stop();
  });

  it('re-scan mid-fil : la mémoire se reconstruit depuis les bulles visibles', () => {
    const path = loadFixture('nominal');
    const controller = createConversationController({ getPath: () => path });
    const memory = controller.currentMemory();
    memory.updateFromPage(collectFromDom(path));
    const signals = memory.toSignals();
    expect(signals.msg_count).toBeGreaterThanOrEqual(4);
    expect(signals.seen_math).toBe(true); // fil mathématique reconstruit
    controller.stop();
  });
});

describe('Zéro texte — la mémoire reconstruite ne transporte aucun contenu', () => {
  it('aucune string > 24 caractères dans les signaux de conversation', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage({
      threadId: 'chat:secret',
      modelLabel: 'Claude Opus 4.8',
      bubbles: [{ role: 'user', text: 'SENTINELLE_XYZ contrat de 4,2 M€ démontre la clause 7.3' }],
    });
    const serialized = JSON.stringify(memory.toSignals());
    expect(serialized).not.toContain('SENTINELLE');
    expect(serialized).not.toContain('clause');
    for (const value of Object.values(memory.toSignals())) {
      if (typeof value === 'string') expect(value.length).toBeLessThanOrEqual(24);
    }
  });
});

/** Construit une PageView depuis le DOM courant (comme le fait selectors). */
function collectFromDom(path: string): PageView {
  const bubbles = [...document.querySelectorAll('[data-message-author-role]')].map((el) => ({
    role: (el.getAttribute('data-message-author-role') ??
      'unknown') as PageView['bubbles'][number]['role'],
    text: el.textContent ?? '',
  }));
  const model = document.querySelector('[data-testid="model-selector-dropdown"]');
  return {
    threadId: path.replace('/chat/', ''),
    bubbles,
    modelLabel: model?.textContent?.trim() ?? null,
  };
}
