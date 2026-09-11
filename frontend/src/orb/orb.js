import * as THREE from 'three';

const PARTICLE_COUNT = 900;

const STATE_PARAMS = {
  idle: { amp: 0.02, speed: 0.3, opacity: 0.45 },
  thinking: { amp: 0.06, speed: 1.4, opacity: 0.75 },
  speaking: { amp: 0.18, speed: 2.2, opacity: 1.0 },
  awaiting: { amp: 0.04, speed: 0.5, opacity: 1.0 },
};

// Sprite de glow radial generado en memoria: da a cada particula el halo
// de luz emitida del diseno de referencia, sin depender de un asset.
function createGlowTexture() {
  const size = 64;
  const element = document.createElement('canvas');
  element.width = size;
  element.height = size;
  const context = element.getContext('2d');
  if (!context) return null;

  const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0.0, 'rgba(255, 217, 160, 1)');
  gradient.addColorStop(0.25, 'rgba(242, 160, 61, 0.75)');
  gradient.addColorStop(1.0, 'rgba(242, 160, 61, 0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);

  return new THREE.CanvasTexture(element);
}

export function createOrb(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 3.2;

  // Distribucion de Fibonacci: reparte los puntos parejo sobre la esfera,
  // sin los polos apretados que da una grilla lat/lon. El radio se varia
  // por particula para que la nube tenga volumen y se vea a traves, en vez
  // de leerse como una cascara solida.
  const base = new Float32Array(PARTICLE_COUNT * 3);
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  for (let i = 0; i < PARTICLE_COUNT; i += 1) {
    const y = 1 - (i / (PARTICLE_COUNT - 1)) * 2;
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    // Pseudoaleatorio determinista: misma nube en cada carga.
    const jitter = (Math.sin(i * 12.9898) * 43758.5453) % 1;
    const radius = 0.62 + Math.abs(jitter) * 0.38;
    const x = Math.cos(theta) * ring * radius;
    const z = Math.sin(theta) * ring * radius;
    base.set([x, y * radius, z], i * 3);
    positions.set([x, y * radius, z], i * 3);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const glowTexture = createGlowTexture();
  const material = new THREE.PointsMaterial({
    size: 0.09,
    map: glowTexture,
    color: new THREE.Color('#f2a03d'),
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });

  const points = new THREE.Points(geometry, material);
  scene.add(points);

  let state = 'idle';
  let level = 0;
  let time = 0;
  let rafId = null;

  const reduceMotion =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function resize() {
    const { clientWidth, clientHeight } = canvas;
    if (!clientWidth || !clientHeight) return;
    renderer.setSize(clientWidth, clientHeight, false);
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
  }

  function frame() {
    time += 0.016;
    const params = STATE_PARAMS[state] || STATE_PARAMS.idle;
    const drive = state === 'speaking' ? level : 1;
    const array = geometry.attributes.position.array;

    for (let i = 0; i < PARTICLE_COUNT; i += 1) {
      const i3 = i * 3;
      const bx = base[i3];
      const by = base[i3 + 1];
      const bz = base[i3 + 2];
      const noise = Math.sin(time * params.speed + bx * 4) * Math.cos(time * params.speed + by * 4);
      const scale = 1 + noise * params.amp * drive;
      array[i3] = bx * scale;
      array[i3 + 1] = by * scale;
      array[i3 + 2] = bz * scale;
    }

    geometry.attributes.position.needsUpdate = true;
    material.opacity = params.opacity * (0.7 + 0.3 * drive);
    points.rotation.y += 0.0015;
    renderer.render(scene, camera);
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId === null) rafId = requestAnimationFrame(frame);
  }

  function stop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  // Si la pestana no esta visible no tiene sentido quemar GPU de fondo.
  function onVisibility() {
    if (document.hidden) stop();
    else start();
  }

  resize();
  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', onVisibility);

  if (reduceMotion) {
    renderer.render(scene, camera);
  } else {
    start();
  }

  return {
    setState(next) {
      if (next in STATE_PARAMS) state = next;
    },
    setLevel(next) {
      const value = Number(next);
      level = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
    },
    dispose() {
      stop();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      geometry.dispose();
      material.dispose();
      glowTexture?.dispose();
      renderer.dispose();
    },
  };
}
