import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createOrb, buildSurfaceMesh } from './orb.js';

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

describe('buildSurfaceMesh', () => {
  // Cuatro nodos de un tetraedro y uno lejano: la malla tiene que unir
  // vecinos, no todos con todos.
  const cloud = Float32Array.from([
    0, 0, 0,
    0.1, 0, 0,
    0, 0.1, 0,
    0, 0, 0.1,
    5, 5, 5,
  ]);
  const COUNT = 5;

  function pairs(edges) {
    const out = [];
    for (let i = 0; i < edges.length; i += 2) out.push([edges[i], edges[i + 1]]);
    return out;
  }

  it('no repite aristas', () => {
    const keys = pairs(buildSurfaceMesh(cloud, COUNT, 2)).map(([a, b]) => `${Math.min(a, b)}-${Math.max(a, b)}`);

    expect(new Set(keys).size).toBe(keys.length);
  });

  it('nunca conecta un nodo consigo mismo', () => {
    for (const [a, b] of pairs(buildSurfaceMesh(cloud, COUNT, 2))) {
      expect(a).not.toBe(b);
    }
  });

  it('une cada nodo con sus vecinos mas cercanos', () => {
    const edges = pairs(buildSurfaceMesh(cloud, COUNT, 1));

    // El nodo lejano se engancha con el que tiene mas a mano, no queda suelto.
    expect(edges.some(([a, b]) => a === 4 || b === 4)).toBe(true);
    expect(edges.length).toBeLessThanOrEqual(COUNT);
  });

  it('no deja indices fuera de la nube', () => {
    for (const index of buildSurfaceMesh(cloud, COUNT, 3)) {
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
