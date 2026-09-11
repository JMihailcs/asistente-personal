import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createOrb } from './orb.js';

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
