import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createOrb, buildEdges } from './orb.js';

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

describe('buildEdges', () => {
  // Cuatro puntos en linea, separados por 1: solo los contiguos caen dentro
  // de una distancia maxima de 1.5.
  const line = Float32Array.from([0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 0, 0]);

  function pairs(edges) {
    const out = [];
    for (let i = 0; i < edges.length; i += 2) out.push([edges[i], edges[i + 1]]);
    return out;
  }

  it('nunca conecta una particula consigo misma', () => {
    for (const [a, b] of pairs(buildEdges(line, 4, 2, 1.5))) {
      expect(a).not.toBe(b);
    }
  });

  it('no repite la misma arista en los dos sentidos', () => {
    const keys = pairs(buildEdges(line, 4, 2, 1.5)).map(([a, b]) =>
      a < b ? `${a}:${b}` : `${b}:${a}`,
    );

    expect(new Set(keys).size).toBe(keys.length);
  });

  it('no une particulas mas lejanas que el maximo', () => {
    for (const [a, b] of pairs(buildEdges(line, 4, 3, 1.5))) {
      expect(Math.abs(line[a * 3] - line[b * 3])).toBeLessThanOrEqual(1.5);
    }
  });

  it('no deja indices fuera de la nube', () => {
    const edges = buildEdges(line, 4, 2, 1.5);
    for (const index of edges) {
      expect(index).toBeGreaterThanOrEqual(0);
      expect(index).toBeLessThan(4);
    }
  });

  it('devuelve pares completos', () => {
    expect(buildEdges(line, 4, 2, 1.5).length % 2).toBe(0);
  });

  it('no arma nada si ninguna particula tiene vecinos cerca', () => {
    expect(buildEdges(line, 4, 2, 0.5).length).toBe(0);
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
