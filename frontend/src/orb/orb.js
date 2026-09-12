import * as THREE from 'three';

const PARTICLE_COUNT = 900;

// Cuantos vecinos se conecta cada particula y hasta que distancia. Con dos
// vecinos la nube se lee como un grafo; con mas, las aristas se tapan entre
// si y vuelve a verse como un bulto solido.
const EDGE_NEIGHBORS = 2;
const EDGE_MAX_DISTANCE = 0.26;

// Pensar es rapido y conectado; contestar es mas lento y vibra al ritmo de
// la voz (la amplitud la maneja `level`, no la velocidad).
const STATE_PARAMS = {
  idle: { amp: 0.02, speed: 0.3, opacity: 0.45, edges: 0.0 },
  thinking: { amp: 0.05, speed: 3.4, opacity: 0.75, edges: 0.55 },
  speaking: { amp: 0.18, speed: 0.8, opacity: 1.0, edges: 0.0 },
  awaiting: { amp: 0.04, speed: 0.5, opacity: 1.0, edges: 0.12 },
};

// Cuanto de la diferencia se cubre por frame al cambiar de estado: sin esto
// las aristas aparecerian de golpe.
const EDGE_FADE = 0.08;

/**
 * Arma las aristas del grafo uniendo cada particula con sus vecinas mas
 * cercanas. Se calcula una sola vez sobre las posiciones de reposo: la nube
 * respira y rota entera, asi que la topologia sigue siendo valida y cada
 * frame solo hay que mover los extremos. Recalcular proximidad en cada
 * cuadro costaria O(n²) por frame y ademas haria titilar las aristas.
 */
export function buildEdges(base, count, neighbors = EDGE_NEIGHBORS, maxDistance = EDGE_MAX_DISTANCE) {
  const maxDistanceSq = maxDistance * maxDistance;
  const edges = [];
  const seen = new Set();

  for (let i = 0; i < count; i += 1) {
    const candidates = [];
    for (let j = 0; j < count; j += 1) {
      if (j === i) continue;
      const dx = base[i * 3] - base[j * 3];
      const dy = base[i * 3 + 1] - base[j * 3 + 1];
      const dz = base[i * 3 + 2] - base[j * 3 + 2];
      const distanceSq = dx * dx + dy * dy + dz * dz;
      if (distanceSq <= maxDistanceSq) candidates.push({ j, distanceSq });
    }
    candidates.sort((a, b) => a.distanceSq - b.distanceSq);

    for (const candidate of candidates.slice(0, neighbors)) {
      const key = i < candidate.j ? `${i}:${candidate.j}` : `${candidate.j}:${i}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push(i, candidate.j);
    }
  }

  return Uint16Array.from(edges);
}

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

  const edges = buildEdges(base, PARTICLE_COUNT);
  const edgePositions = new Float32Array(edges.length * 3);
  const edgeGeometry = new THREE.BufferGeometry();
  edgeGeometry.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3));
  const edgeMaterial = new THREE.LineBasicMaterial({
    color: new THREE.Color('#f2a03d'),
    transparent: true,
    opacity: 0,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const lines = new THREE.LineSegments(edgeGeometry, edgeMaterial);
  lines.visible = false;

  // Puntos y aristas van en el mismo grupo para que roten juntos: si se
  // rotaran por separado, las aristas se despegarian de sus particulas.
  const cloud = new THREE.Group();
  cloud.add(points);
  cloud.add(lines);
  scene.add(cloud);

  let state = 'idle';
  let level = 0;
  // Fase acumulada en vez de `time * speed`: al cambiar de estado la
  // velocidad cambia, y multiplicar por el tiempo absoluto haria saltar la
  // animacion a otra parte de la onda.
  let phase = 0;
  let edgeOpacity = 0;
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
    const params = STATE_PARAMS[state] || STATE_PARAMS.idle;
    const drive = state === 'speaking' ? level : 1;
    phase += 0.016 * params.speed;
    const array = geometry.attributes.position.array;

    for (let i = 0; i < PARTICLE_COUNT; i += 1) {
      const i3 = i * 3;
      const bx = base[i3];
      const by = base[i3 + 1];
      const bz = base[i3 + 2];
      const noise = Math.sin(phase + bx * 4) * Math.cos(phase + by * 4);
      const scale = 1 + noise * params.amp * drive;
      array[i3] = bx * scale;
      array[i3 + 1] = by * scale;
      array[i3 + 2] = bz * scale;
    }
    geometry.attributes.position.needsUpdate = true;

    edgeOpacity += (params.edges - edgeOpacity) * EDGE_FADE;
    lines.visible = edgeOpacity > 0.01;
    if (lines.visible) {
      // Las aristas siguen a sus particulas: cada vertice copia la posicion
      // ya calculada del punto en el que nace.
      for (let e = 0; e < edges.length; e += 1) {
        const from = edges[e] * 3;
        const to = e * 3;
        edgePositions[to] = array[from];
        edgePositions[to + 1] = array[from + 1];
        edgePositions[to + 2] = array[from + 2];
      }
      edgeGeometry.attributes.position.needsUpdate = true;
      edgeMaterial.opacity = edgeOpacity;
    }

    material.opacity = params.opacity * (0.7 + 0.3 * drive);
    cloud.rotation.y += 0.0015;
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
      edgeGeometry.dispose();
      edgeMaterial.dispose();
      glowTexture?.dispose();
      renderer.dispose();
    },
  };
}
