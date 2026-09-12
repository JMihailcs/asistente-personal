import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createOrb, buildRadialTree } from './orb.js';

// Three.js necesita WebGL, que jsdom no provee: se mockea el renderer.
vi.mock('three', async () => {
  const actual = await vi.importActual('three');
  return {
    ...actual,
    WebGLRenderer: class {
      setPixelRatio() {}
      setSize() {}
      render() {}
      dispose() {}
      domElement = { width: 100, height: 100 };
    },
  };
});

describe('buildRadialTree', () => {
  // Nodos a distancias crecientes del centro, en distintas direcciones.
  const cloud = Float32Array.from([
    0.1, 0, 0,
    0.4, 0.1, 0,
    0, 0.5, 0.1,
    0.8, 0.2, 0,
    0, 0.9, 0.2,
    0.2, 0.2, 0.95,
  ]);
  const COUNT = 6;

  function pairs(edges) {
    const out = [];
    for (let i = 0; i < edges.length; i += 2) out.push([edges[i], edges[i + 1]]);
    return out;
  }

  const distance = (i) => Math.hypot(cloud[i * 3], cloud[i * 3 + 1], cloud[i * 3 + 2]);

  it('conecta todos los nodos en un solo arbol', () => {
    // Un arbol que cubre N nodos tiene exactamente N-1 aristas: ni un bosque
    // de trozos sueltos, ni ciclos.
    expect(buildRadialTree(cloud, COUNT).length / 2).toBe(COUNT - 1);
  });

  it('hace crecer las ramas del centro hacia afuera', () => {
    for (const [parent, child] of pairs(buildRadialTree(cloud, COUNT))) {
      expect(distance(parent)).toBeLessThanOrEqual(distance(child));
    }
  });

  it('le da un solo padre a cada nodo', () => {
    const children = pairs(buildRadialTree(cloud, COUNT)).map(([, child]) => child);

    expect(new Set(children).size).toBe(children.length);
  });

  it('deja al nodo mas interno como raiz, sin padre', () => {
    const children = new Set(pairs(buildRadialTree(cloud, COUNT)).map(([, child]) => child));
    const root = [...Array(COUNT).keys()].sort((a, b) => distance(a) - distance(b))[0];

    expect(children.has(root)).toBe(false);
  });

  it('nunca conecta un nodo consigo mismo', () => {
    for (const [parent, child] of pairs(buildRadialTree(cloud, COUNT))) {
      expect(parent).not.toBe(child);
    }
  });

  it('no deja indices fuera de la nube', () => {
    for (const index of buildRadialTree(cloud, COUNT)) {
      expect(index).toBeGreaterThanOrEqual(0);
      expect(index).toBeLessThan(COUNT);
    }
  });
});

describe('createOrb', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    );
  });

  it('expone la API mínima', () => {
    const orb = createOrb(document.createElement('canvas'));
    expect(typeof orb.setState).toBe('function');
    expect(typeof orb.setLevel).toBe('function');
    expect(typeof orb.dispose).toBe('function');
    orb.dispose();
  });

  it('cancela su loop de animación al destruirse', () => {
    const orb = createOrb(document.createElement('canvas'));
    orb.dispose();
    expect(cancelAnimationFrame).toHaveBeenCalled();
  });

  it('acepta niveles fuera de rango sin romperse', () => {
    const orb = createOrb(document.createElement('canvas'));
    expect(() => {
      orb.setLevel(-5);
      orb.setLevel(42);
      orb.setLevel(NaN);
    }).not.toThrow();
    orb.dispose();
  });

  it('ignora estados desconocidos en vez de romperse', () => {
    const orb = createOrb(document.createElement('canvas'));
    expect(() => orb.setState('no-existe')).not.toThrow();
    orb.dispose();
  });
});
