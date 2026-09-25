import * as THREE from 'three';

// Una caparazon hueca de malla irregular, con luz ambar localizada como
// brasas, niebla adentro, particulas de distinto tamano y foco, y anillos
// finisimos alrededor: la referencia OPTIMIND (docs/referencias/orbe) pasada
// a fondo oscuro. La malla es casi apagada y solo brilla donde hay luz.
const SHELL_COUNT = 720;
const NEIGHBORS = 4;
const SHELL_RADIUS = 0.84;
const DUST_COUNT = 300;
const FOG_COUNT = 30;
const HOTSPOTS = 3;

// Pensar gira rapido y las brasas corren por la superficie; contestar gira
// lento y deja que el brillo lo marque la voz (via `level`). `heat` es cuanta
// luz emiten los focos, `wander` cuan rapido se mueven.
const STATE_PARAMS = {
  idle: { amp: 0.02, speed: 0.3, spin: 0.0015, jitter: 0.012, heat: 0.5, wander: 0.15, flow: 0.4 },
  thinking: { amp: 0.05, speed: 3.4, spin: 0.009, jitter: 0.03, heat: 0.85, wander: 1.1, flow: 2.2 },
  speaking: { amp: 0.14, speed: 0.8, spin: 0.003, jitter: 0.02, heat: 0.7, wander: 0.3, flow: 1.0 },
  awaiting: { amp: 0.04, speed: 0.5, spin: 0.002, jitter: 0.014, heat: 0.75, wander: 0.2, flow: 0.6 },
};

// Cuanto de la diferencia se cubre por frame al cambiar de estado: sin esto
// el giro y el brillo cambiarian de golpe.
const FADE = 0.06;

// Degradacion: si el frame promedio pasa de este tiempo, se apagan primero la
// niebla y el pixel ratio, despues la mitad de las particulas.
const SLOW_FRAME_MS = 24;
const SLOW_FRAMES_TO_DEGRADE = 45;

/** Pseudoaleatorio determinista: la misma nube en cada carga. */
function noiseAt(i) {
  return Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1);
}

/** Reparte `count` direcciones parejo sobre la esfera (espiral de Fibonacci). */
function fibonacciDirection(i, count) {
  const y = 1 - (i / (count - 1)) * 2;
  const ring = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = Math.PI * (1 + Math.sqrt(5)) * i;
  return [Math.cos(theta) * ring, y, Math.sin(theta) * ring];
}

/**
 * Teje una malla de superficie: une cada nodo con sus `k` vecinos mas
 * cercanos, sin repetir aristas. Sobre la cascara eso da triangulos
 * irregulares, y como los nodos estan a radios distintos la malla se ve
 * arrugada. Se calcula una sola vez sobre las posiciones de reposo; despues
 * solo hay que mover los extremos.
 */
export function buildSurfaceMesh(positions, count, k = NEIGHBORS) {
  const seen = new Set();
  const edges = [];
  const nearest = new Float32Array(k);
  const nearestIndex = new Int32Array(k);

  for (let a = 0; a < count; a += 1) {
    nearest.fill(Infinity);
    nearestIndex.fill(-1);
    for (let b = 0; b < count; b += 1) {
      if (a === b) continue;
      const dx = positions[a * 3] - positions[b * 3];
      const dy = positions[a * 3 + 1] - positions[b * 3 + 1];
      const dz = positions[a * 3 + 2] - positions[b * 3 + 2];
      const distance = dx * dx + dy * dy + dz * dz;
      if (distance >= nearest[k - 1]) continue;
      // Insercion ordenada en la lista corta de los k mas cercanos.
      let slot = k - 1;
      while (slot > 0 && nearest[slot - 1] > distance) {
        nearest[slot] = nearest[slot - 1];
        nearestIndex[slot] = nearestIndex[slot - 1];
        slot -= 1;
      }
      nearest[slot] = distance;
      nearestIndex[slot] = b;
    }
    for (let n = 0; n < k; n += 1) {
      const b = nearestIndex[n];
      if (b < 0) continue;
      const key = a < b ? a * count + b : b * count + a;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push(a, b);
    }
  }

  return Uint16Array.from(edges);
}

// Sprite blando: la niebla no es mas que manchas grandes y translucidas.
const POINT_VERTEX = `
  attribute float aSize;
  attribute float aFocus;
  attribute vec3 aColor;
  uniform float uScale;
  uniform float uMinPx;
  varying vec3 vColor;
  varying float vFocus;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = max(uMinPx, aSize * uScale / -mv.z);
    vColor = aColor;
    vFocus = aFocus;
  }
`;

// Foco 1: nucleo nitido con halo. Foco 0: disco desenfocado de bokeh, mas
// claro en el borde, como un lente fuera de plano. Niebla: mancha gaussiana.
const POINT_FRAGMENT = `
  uniform float uFog;
  uniform float uOpacity;
  varying vec3 vColor;
  varying float vFocus;
  void main() {
    float r = length(gl_PointCoord - 0.5) * 2.0;
    if (r > 1.0) discard;
    float alpha;
    if (uFog > 0.5) {
      alpha = exp(-r * r * 3.2);
    } else {
      float sharp = exp(-r * r * 9.0) + 0.25 * exp(-r * r * 2.5);
      float disc = smoothstep(1.0, 0.82, r) * (0.28 + 0.5 * smoothstep(0.55, 0.95, r));
      alpha = mix(disc, sharp, vFocus);
    }
    gl_FragColor = vec4(vColor, alpha * uOpacity);
  }
`;

function createPointMaterial({ fog = false, blending, opacity = 1, minPx = 1.5 }) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uScale: { value: 100 },
      uMinPx: { value: minPx },
      uFog: { value: fog ? 1 : 0 },
      uOpacity: { value: opacity },
    },
    vertexShader: POINT_VERTEX,
    fragmentShader: POINT_FRAGMENT,
    transparent: true,
    depthWrite: false,
    blending,
  });
}

function createPointCloud(count, material) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  geometry.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(count), 1));
  geometry.setAttribute('aFocus', new THREE.BufferAttribute(new Float32Array(count).fill(1), 1));
  geometry.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  const points = new THREE.Points(geometry, material);
  // Las posiciones se reescriben cada frame: la esfera de recorte calculada
  // una vez no vale.
  points.frustumCulled = false;
  return points;
}

// De brasa a blanco caliente segun cuanta luz recibe el punto (0..1+).
function emberColor(heat, out, offset, gain = 1) {
  const h = Math.min(1.4, heat);
  const white = Math.max(0, h - 0.65) / 0.75;
  out[offset] = Math.min(1, 0.95 * h + 0.1) * gain;
  out[offset + 1] = Math.min(1, (0.42 + 0.5 * white) * h) * gain;
  out[offset + 2] = Math.min(1, (0.12 + 0.72 * white) * h) * gain;
}

export function createOrb(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  let pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(pixelRatio);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 3.2;

  // Cascara: direccion pareja mas un relieve suave (dos ondas cruzadas) y un
  // poco de ruido, para que la malla se vea arrugada y no una esfera lisa.
  const shellBase = new Float32Array(SHELL_COUNT * 3);
  const shellDir = new Float32Array(SHELL_COUNT * 3);
  const shellPositions = new Float32Array(SHELL_COUNT * 3);
  const driftPhase = new Float32Array(SHELL_COUNT * 3);
  const driftRate = new Float32Array(SHELL_COUNT * 3);
  for (let i = 0; i < SHELL_COUNT; i += 1) {
    const [dx, dy, dz] = fibonacciDirection(i, SHELL_COUNT);
    const relief =
      0.09 * Math.sin(dx * 4.1 + dy * 2.3) * Math.cos(dz * 3.7 - dy * 1.9) +
      (noiseAt(i + 7000) - 0.5) * 0.09;
    const radius = SHELL_RADIUS * (1 + relief);
    shellDir.set([dx, dy, dz], i * 3);
    shellBase.set([dx * radius, dy * radius, dz * radius], i * 3);
    for (let axis = 0; axis < 3; axis += 1) {
      driftPhase[i * 3 + axis] = noiseAt(i * 3 + axis + 20000) * Math.PI * 2;
      driftRate[i * 3 + axis] = 0.6 + noiseAt(i * 3 + axis + 40000) * 1.3;
    }
  }
  shellPositions.set(shellBase);

  const edges = buildSurfaceMesh(shellBase, SHELL_COUNT);
  const edgePositions = new Float32Array(edges.length * 3);
  const edgeColors = new Float32Array(edges.length * 3);
  const positionAttribute = new THREE.BufferAttribute(edgePositions, 3);

  // Dos capas sobre los mismos vertices: la malla apagada (gris calido,
  // mezcla normal, es el "negro" de la referencia) y encima la misma malla
  // en aditivo, teñida solo donde llega la luz.
  const meshGeometry = new THREE.BufferGeometry();
  meshGeometry.setAttribute('position', positionAttribute);
  const meshMaterial = new THREE.LineBasicMaterial({
    color: new THREE.Color('#3d352f'),
    transparent: true,
    opacity: 0.55,
    depthWrite: false,
  });
  const meshLines = new THREE.LineSegments(meshGeometry, meshMaterial);

  const litGeometry = new THREE.BufferGeometry();
  litGeometry.setAttribute('position', positionAttribute);
  litGeometry.setAttribute('color', new THREE.BufferAttribute(edgeColors, 3));
  const litMaterial = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const litLines = new THREE.LineSegments(litGeometry, litMaterial);

  // Nodos de la cascara: motas chiquitas, casi apagadas salvo bajo la luz.
  const nodeMaterial = createPointMaterial({ blending: THREE.AdditiveBlending, minPx: 1.6 });
  const nodes = createPointCloud(SHELL_COUNT, nodeMaterial);
  nodes.geometry.setAttribute('position', new THREE.BufferAttribute(shellPositions, 3));
  const nodeSize = nodes.geometry.attributes.aSize.array;
  const nodeColor = nodes.geometry.attributes.aColor.array;
  for (let i = 0; i < SHELL_COUNT; i += 1) nodeSize[i] = 0.014 + noiseAt(i + 900) * 0.012;

  // Polvo interior: muchas motas diminutas, algunas medianas y pocos discos
  // grandes desenfocados. Dos modos de movimiento: una mitad fluye hacia el
  // centro, la otra cae hacia el foco de luz.
  const dustMaterial = createPointMaterial({ blending: THREE.AdditiveBlending, minPx: 1.4 });
  const dust = createPointCloud(DUST_COUNT, dustMaterial);
  const dustPosition = dust.geometry.attributes.position.array;
  const dustSize = dust.geometry.attributes.aSize.array;
  const dustFocus = dust.geometry.attributes.aFocus.array;
  const dustColor = dust.geometry.attributes.aColor.array;
  const dustMode = new Uint8Array(DUST_COUNT);
  const dustSpeed = new Float32Array(DUST_COUNT);
  const dustTint = new Float32Array(DUST_COUNT);
  let respawn = 1;

  // `hot` son las direcciones de los focos, `heatAmount` su intensidad.
  const hot = Array.from({ length: HOTSPOTS }, () => new THREE.Vector3(1, 0, 0));
  const hotAmount = [1, 0.55, 0.4];
  const hotPhase = [0.6, 3.2, 5.1];
  const hotPitch = [-0.35, 0.5, -0.1];
  let wanderClock = 0;

  function placeHotspots() {
    for (let h = 0; h < HOTSPOTS; h += 1) {
      const theta = hotPhase[h] + wanderClock * (0.7 + h * 0.35);
      const phi = hotPitch[h] + 0.45 * Math.sin(wanderClock * 0.6 + h * 2);
      hot[h].set(Math.cos(phi) * Math.cos(theta), Math.sin(phi), Math.cos(phi) * Math.sin(theta));
    }
  }
  placeHotspots();

  function spawnDust(i, fresh) {
    respawn += 1;
    const n = (offset) => noiseAt(respawn * 7 + offset);
    const kind = noiseAt(i + 3000);
    // 62% motas diminutas, 30% medianas, 8% bokeh.
    if (kind < 0.62) {
      dustSize[i] = 0.014 + n(1) * 0.012;
      dustFocus[i] = 1;
    } else if (kind < 0.92) {
      dustSize[i] = 0.035 + n(1) * 0.03;
      dustFocus[i] = 0.75 + n(2) * 0.25;
    } else {
      dustSize[i] = 0.11 + n(1) * 0.12;
      dustFocus[i] = 0.02 + n(2) * 0.12;
    }
    dustMode[i] = noiseAt(i + 3500) < 0.5 ? 0 : 1;
    dustSpeed[i] = 0.03 + n(3) * 0.09;
    dustTint[i] = n(4);

    // Se agrupan donde esta la luz: el nacimiento se inclina hacia un foco.
    const focus = hot[Math.floor(n(5) * HOTSPOTS) % HOTSPOTS];
    const spread = 0.9;
    const dx = focus.x + (n(6) - 0.5) * spread;
    const dy = focus.y + (n(7) - 0.5) * spread;
    const dz = focus.z + (n(8) - 0.5) * spread;
    const length = Math.hypot(dx, dy, dz) || 1;
    const radius = fresh ? 0.1 + n(9) * 0.7 : 0.7 + n(9) * 0.12;
    dustPosition[i * 3] = (dx / length) * radius;
    dustPosition[i * 3 + 1] = (dy / length) * radius;
    dustPosition[i * 3 + 2] = (dz / length) * radius;
  }
  for (let i = 0; i < DUST_COUNT; i += 1) spawnDust(i, true);

  // Niebla interior: manchas grandes de humo calido oscuro, mas densas al
  // centro. Mezcla normal, asi aclara el fondo en vez de sumar luz.
  const fogMaterial = createPointMaterial({
    fog: true,
    blending: THREE.NormalBlending,
    opacity: 0.16,
    minPx: 1,
  });
  const fog = createPointCloud(FOG_COUNT, fogMaterial);
  const fogBase = new Float32Array(FOG_COUNT * 3);
  const fogPosition = fog.geometry.attributes.position.array;
  const fogSize = fog.geometry.attributes.aSize.array;
  const fogColor = fog.geometry.attributes.aColor.array;
  const fogPhase = new Float32Array(FOG_COUNT);
  for (let i = 0; i < FOG_COUNT; i += 1) {
    const [dx, dy, dz] = fibonacciDirection(i, FOG_COUNT);
    // Exponente > 1: mas manchas cerca del centro.
    const radius = Math.pow(noiseAt(i + 5000), 1.6) * 0.5;
    fogBase.set([dx * radius, dy * radius, dz * radius], i * 3);
    fogSize[i] = 0.9 - radius * 0.7 + noiseAt(i + 5500) * 0.3;
    fogPhase[i] = noiseAt(i + 6000) * Math.PI * 2;
    const tone = 0.22 + noiseAt(i + 6500) * 0.1;
    fogColor.set([tone * 1.15, tone * 0.85, tone * 0.62], i * 3);
  }
  fogPosition.set(fogBase);

  // Anillos concentricos finisimos: encuadran la figura sin competir.
  const ringMaterial = new THREE.LineBasicMaterial({
    color: new THREE.Color('#8a837c'),
    transparent: true,
    opacity: 0.16,
    depthWrite: false,
  });
  const rings = new THREE.Group();
  [
    [1.08, 0, 0],
    [1.2, 0.12, 0.05],
    [1.32, -0.08, 0.1],
  ].forEach(([radius, tiltX, tiltY]) => {
    const points = [];
    for (let s = 0; s < 160; s += 1) {
      const angle = (s / 160) * Math.PI * 2;
      points.push(new THREE.Vector3(Math.cos(angle) * radius, Math.sin(angle) * radius, 0));
    }
    const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points), ringMaterial);
    ring.rotation.x = tiltX;
    ring.rotation.y = tiltY;
    rings.add(ring);
  });
  scene.add(rings);

  // Todo lo interior gira junto: si cada capa rotara por su cuenta, la malla
  // se despegaria de sus nodos.
  const cloud = new THREE.Group();
  cloud.add(fog);
  cloud.add(meshLines);
  cloud.add(litLines);
  cloud.add(nodes);
  cloud.add(dust);
  scene.add(cloud);

  let state = 'idle';
  let level = 0;
  // Fase acumulada en vez de `tiempo * velocidad`: al cambiar de estado la
  // velocidad cambia, y multiplicar por el tiempo absoluto haria saltar la
  // animacion a otra parte de la onda.
  let phase = 0;
  // Reloj propio del temblor: nunca se detiene, solo se acelera.
  let drift = 0;
  let spin = STATE_PARAMS.idle.spin;
  let heat = STATE_PARAMS.idle.heat;
  let flow = STATE_PARAMS.idle.flow;
  let rafId = null;

  // Calidad: 0 completa, 1 sin niebla y pixel ratio 1, 2 ademas mitad del polvo.
  let quality = 0;
  let lastTime = 0;
  let slowFrames = 0;

  const reduceMotion =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function resize() {
    const { clientWidth, clientHeight } = canvas;
    if (!clientWidth || !clientHeight) return;
    renderer.setSize(clientWidth, clientHeight, false);
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
    // Pixeles por unidad de mundo a distancia 1: el tamano de las particulas
    // se expresa en unidades de la escena, no en pixeles.
    const scale = (clientHeight * pixelRatio) / (2 * Math.tan((camera.fov * Math.PI) / 360));
    for (const material of [nodeMaterial, dustMaterial, fogMaterial]) {
      material.uniforms.uScale.value = scale;
      material.uniforms.uMinPx.value = material === fogMaterial ? 1 : 1.5 * pixelRatio;
    }
  }

  function degrade() {
    if (quality >= 2) return;
    quality += 1;
    if (quality === 1) {
      fog.visible = false;
      pixelRatio = 1;
      renderer.setPixelRatio(1);
      resize();
    } else {
      dust.geometry.setDrawRange(0, DUST_COUNT / 2);
    }
    slowFrames = 0;
  }

  function trackFrameTime(now) {
    const delta = now - lastTime;
    lastTime = now;
    // Un salto enorme es la pestana volviendo del fondo, no un orbe lento.
    if (delta > 250 || delta <= 0) return;
    slowFrames = delta > SLOW_FRAME_MS ? slowFrames + 1 : Math.max(0, slowFrames - 2);
    if (slowFrames > SLOW_FRAMES_TO_DEGRADE) degrade();
  }

  const heatScratch = new Float32Array(SHELL_COUNT);

  function frame(now) {
    if (now !== undefined) trackFrameTime(now);
    const params = STATE_PARAMS[state] || STATE_PARAMS.idle;
    const drive = state === 'speaking' ? level : 1;
    phase += 0.016 * params.speed;
    drift += 0.016 * (0.9 + params.speed * 0.4);
    wanderClock += 0.016 * params.wander;
    placeHotspots();

    // Las brasas se encienden con el nivel al hablar y laten al esperar.
    let targetHeat = params.heat;
    if (state === 'speaking') targetHeat += level * 0.55;
    if (state === 'awaiting') targetHeat += Math.sin(drift * 1.6) * 0.12;
    heat += (targetHeat - heat) * FADE;
    flow += (params.flow - flow) * FADE;

    // Cascara: respira y tiembla, y calcula cuanta luz recibe cada nodo.
    for (let i = 0; i < SHELL_COUNT; i += 1) {
      const i3 = i * 3;
      const bx = shellBase[i3];
      const by = shellBase[i3 + 1];
      const bz = shellBase[i3 + 2];
      const wobble = Math.sin(phase + bx * 4) * Math.cos(phase + by * 4);
      const scale = 1 + wobble * params.amp * drive;
      shellPositions[i3] = bx * scale + Math.sin(drift * driftRate[i3] + driftPhase[i3]) * params.jitter;
      shellPositions[i3 + 1] =
        by * scale + Math.sin(drift * driftRate[i3 + 1] + driftPhase[i3 + 1]) * params.jitter;
      shellPositions[i3 + 2] =
        bz * scale + Math.sin(drift * driftRate[i3 + 2] + driftPhase[i3 + 2]) * params.jitter;

      let light = 0;
      for (let h = 0; h < HOTSPOTS; h += 1) {
        const align = shellDir[i3] * hot[h].x + shellDir[i3 + 1] * hot[h].y + shellDir[i3 + 2] * hot[h].z;
        light += hotAmount[h] * Math.exp((align - 1) * 11);
      }
      // Chispas: cada nodo parpadea a su ritmo, y la luz nunca es pareja.
      const flicker = 0.7 + 0.3 * Math.sin(drift * (2 + driftRate[i3] * 2) + driftPhase[i3 + 1]);
      const lit = light * heat * flicker;
      heatScratch[i] = lit;
      emberColor(lit, nodeColor, i3, lit > 0.02 ? 1 : 0);
      // Un piso de gris calido para que la malla apagada se lea como estructura.
      nodeColor[i3] += 0.1;
      nodeColor[i3 + 1] += 0.085;
      nodeColor[i3 + 2] += 0.07;
      nodeSize[i] = (0.014 + noiseAt(i + 900) * 0.012) * (1 + Math.min(2.2, lit * 1.4));
    }
    nodes.geometry.attributes.position.needsUpdate = true;
    nodes.geometry.attributes.aColor.needsUpdate = true;
    nodes.geometry.attributes.aSize.needsUpdate = true;

    // Aristas: copian la posicion del nodo y toman el brillo de sus extremos.
    for (let e = 0; e < edges.length; e += 1) {
      const from = edges[e] * 3;
      const to = e * 3;
      edgePositions[to] = shellPositions[from];
      edgePositions[to + 1] = shellPositions[from + 1];
      edgePositions[to + 2] = shellPositions[from + 2];
      // Cada arista brilla segun la media de sus dos nodos: se compara con el
      // indice del otro extremo del par.
      const partner = edges[e % 2 === 0 ? e + 1 : e - 1];
      const edgeHeat = (heatScratch[edges[e]] + heatScratch[partner]) * 0.5;
      emberColor(edgeHeat * 0.9, edgeColors, to, edgeHeat > 0.03 ? 1 : 0);
    }
    positionAttribute.needsUpdate = true;
    litGeometry.attributes.color.needsUpdate = true;

    // Polvo: fluye hacia el centro o cae hacia el foco mas cercano.
    const dt = 0.016 * flow;
    for (let i = 0; i < DUST_COUNT; i += 1) {
      const i3 = i * 3;
      let x = dustPosition[i3];
      let y = dustPosition[i3 + 1];
      let z = dustPosition[i3 + 2];
      let best = hot[0];
      let bestDistance = Infinity;
      for (let h = 0; h < HOTSPOTS; h += 1) {
        const d = (hot[h].x * 0.7 - x) ** 2 + (hot[h].y * 0.7 - y) ** 2 + (hot[h].z * 0.7 - z) ** 2;
        if (d < bestDistance) {
          bestDistance = d;
          best = hot[h];
        }
      }
      if (dustMode[i] === 0) {
        const pull = 1 - dustSpeed[i] * dt * 2.2;
        x *= pull;
        y *= pull;
        z *= pull;
        // Un poco de giro, para que no baje en linea recta.
        const swirl = dustSpeed[i] * dt * 1.5;
        const cx = x * Math.cos(swirl) - z * Math.sin(swirl);
        z = x * Math.sin(swirl) + z * Math.cos(swirl);
        x = cx;
        if (x * x + y * y + z * z < 0.012) {
          spawnDust(i, false);
          continue;
        }
      } else {
        const rate = dustSpeed[i] * dt * 2.5;
        x += (best.x * 0.7 - x) * rate;
        y += (best.y * 0.7 - y) * rate;
        z += (best.z * 0.7 - z) * rate;
        if (bestDistance < 0.02) {
          spawnDust(i, true);
          continue;
        }
      }
      dustPosition[i3] = x;
      dustPosition[i3 + 1] = y;
      dustPosition[i3 + 2] = z;

      // Brillan mas cerca de la luz; una parte son blancas, el resto brasa.
      const near = Math.exp(-bestDistance * 3.5);
      const glow = (0.5 + near * 1.5) * heat * (dustFocus[i] > 0.5 ? 1 : 0.7);
      emberColor(glow, dustColor, i3, 1);
      if (dustTint[i] > 0.82) {
        dustColor[i3 + 1] = Math.min(1, dustColor[i3 + 1] + 0.3 * glow);
        dustColor[i3 + 2] = Math.min(1, dustColor[i3 + 2] + 0.45 * glow);
      }
    }
    dust.geometry.attributes.position.needsUpdate = true;
    dust.geometry.attributes.aSize.needsUpdate = true;
    dust.geometry.attributes.aFocus.needsUpdate = true;
    dust.geometry.attributes.aColor.needsUpdate = true;

    // Niebla: se agita despacio y respira con el nivel de la voz.
    if (fog.visible) {
      for (let i = 0; i < FOG_COUNT; i += 1) {
        const i3 = i * 3;
        const t = drift * 0.25 + fogPhase[i];
        fogPosition[i3] = fogBase[i3] + Math.sin(t) * 0.08;
        fogPosition[i3 + 1] = fogBase[i3 + 1] + Math.cos(t * 1.3) * 0.08;
        fogPosition[i3 + 2] = fogBase[i3 + 2] + Math.sin(t * 0.8 + 1) * 0.08;
      }
      fog.geometry.attributes.position.needsUpdate = true;
    }
    fogMaterial.uniforms.uOpacity.value = 0.16 + 0.05 * drive * (state === 'speaking' ? 1 : 0);

    litMaterial.opacity = 0.9;
    ringMaterial.opacity = 0.14 + 0.06 * Math.min(1, heat);

    spin += (params.spin - spin) * FADE;
    cloud.rotation.y += spin;
    rings.rotation.z += spin * 0.25;

    renderer.render(scene, camera);
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    lastTime = 0;
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
    frame();
    stop();
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
    /** Nivel de calidad actual (0 completa, 2 la mas degradada): para medir. */
    get quality() {
      return quality;
    },
    dispose() {
      stop();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      for (const object of [nodes, dust, fog, meshLines, litLines]) object.geometry.dispose();
      for (const material of [nodeMaterial, dustMaterial, fogMaterial, meshMaterial, litMaterial, ringMaterial]) {
        material.dispose();
      }
      rings.children.forEach((ring) => ring.geometry.dispose());
      renderer.dispose();
    },
  };
}
