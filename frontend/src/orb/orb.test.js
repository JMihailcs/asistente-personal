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
  // Octaedro: 6 direcciones sobre la esfera. Su triangulacion tiene 8 caras
  // y 12 aristas (Euler: V - E + F = 2).
  const octahedron = Float32Array.from([1, 0, 0, -1, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 1, 0, 0, -1]);
  const COUNT = 6;

  function pairs(edges) {
    const out = [];
    for (let i = 0; i < edges.length; i += 2) out.push([edges[i], edges[i + 1]]);
    return out;
  }

  it('triangula la superficie: 3V - 6 aristas', () => {
    expect(buildSurfaceMesh(octahedron, COUNT).length / 2).toBe(12);
  });

  it('no repite aristas ni conecta un nodo consigo mismo', () => {
    const list = pairs(buildSurfaceMesh(octahedron, COUNT));
    const keys = list.map(([a, b]) => `${Math.min(a, b)}-${Math.max(a, b)}`);

    expect(new Set(keys).size).toBe(keys.length);
    for (const [a, b] of list) expect(a).not.toBe(b);
  });

  it('nunca une puntos opuestos de la esfera', () => {
    // Los antipodas (0-1, 2-3, 4-5) no comparten cara.
    const keys = pairs(buildSurfaceMesh(octahedron, COUNT)).map(([a, b]) => `${Math.min(a, b)}-${Math.max(a, b)}`);

    expect(keys).not.toContain('0-1');
    expect(keys).not.toContain('2-3');
    expect(keys).not.toContain('4-5');
  });

  it('no deja indices fuera de la nube', () => {
    for (const index of buildSurfaceMesh(octahedron, COUNT)) {
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
