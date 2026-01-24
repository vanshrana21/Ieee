const canvas = document.getElementById("scene");

/* ---------- SCENE ---------- */
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x120a06, 6, 16);

/* ---------- CAMERA ---------- */
const camera = new THREE.PerspectiveCamera(
  38,
  window.innerWidth / window.innerHeight,
  0.1,
  50
);
camera.position.set(0, 3.2, 7.8);
camera.lookAt(0, 1.2, 0);

/* ---------- RENDERER ---------- */
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true
});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

/* ---------- LIGHTING ---------- */
const spot = new THREE.SpotLight(0xffd7a1, 1.6);
spot.position.set(0, 5.5, 3.2);
spot.target.position.set(0, 1.4, -1.6);
spot.angle = 0.45;
spot.penumbra = 0.7;
spot.castShadow = true;
spot.shadow.mapSize.set(2048, 2048);
scene.add(spot);
scene.add(spot.target);

scene.add(new THREE.AmbientLight(0x3b2416, 0.15));

/* ---------- FLOOR ---------- */
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.MeshStandardMaterial({ color: 0x2c1b12 })
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

/* ---------- DESK ---------- */
const desk = new THREE.Mesh(
  new THREE.BoxGeometry(6.2, 0.18, 3.4),
  new THREE.MeshStandardMaterial({
    color: 0xcfa984,
    roughness: 0.75
  })
);
desk.position.y = 1.0;
desk.castShadow = true;
desk.receiveShadow = true;
sce
