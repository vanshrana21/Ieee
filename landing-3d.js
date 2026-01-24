(function() {
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x120a06);
    scene.fog = new THREE.Fog(0x120a06, 6, 16);

    var camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(0, 3.2, 7.8);
    camera.lookAt(0, 1.2, 0);

    var renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    document.getElementById('canvas-container').appendChild(renderer.domElement);

    var ambientLight = new THREE.AmbientLight(0x3b2416, 0.15);
    scene.add(ambientLight);

    var spotLight = new THREE.SpotLight(0xffd7a1, 1.6);
    spotLight.position.set(0, 5.5, 3.2);
    spotLight.target.position.set(0, 1.4, -1.6);
    spotLight.angle = 0.45;
    spotLight.penumbra = 0.7;
    spotLight.castShadow = true;
    spotLight.shadow.mapSize.width = 2048;
    spotLight.shadow.mapSize.height = 2048;
    spotLight.shadow.camera.near = 0.5;
    spotLight.shadow.camera.far = 20;
    spotLight.shadow.bias = -0.0001;
    scene.add(spotLight);
    scene.add(spotLight.target);

    var deskGeometry = new THREE.BoxGeometry(6.2, 0.18, 3.4);
    var deskMaterial = new THREE.MeshStandardMaterial({
        color: 0xcfa984,
        roughness: 0.75,
        metalness: 0.0
    });
    var desk = new THREE.Mesh(deskGeometry, deskMaterial);
    desk.position.set(0, 1.0, 0);
    desk.castShadow = true;
    desk.receiveShadow = true;
    scene.add(desk);

    var deskLegGeometry = new THREE.BoxGeometry(5.8, 0.9, 3.0);
    var deskLegMaterial = new THREE.MeshStandardMaterial({
        color: 0x8b5a3c,
        roughness: 0.8,
        metalness: 0.0
    });
    var deskBase = new THREE.Mesh(deskLegGeometry, deskLegMaterial);
    deskBase.position.set(0, 0.45, 0);
    deskBase.castShadow = true;
    deskBase.receiveShadow = true;
    scene.add(deskBase);

    var backWallGeometry = new THREE.PlaneGeometry(12, 6);
    var backWallMaterial = new THREE.MeshStandardMaterial({
        color: 0x120906,
        roughness: 1.0,
        metalness: 0.0
    });
    var backWall = new THREE.Mesh(backWallGeometry, backWallMaterial);
    backWall.position.set(0, 3, -1.8);
    backWall.receiveShadow = true;
    scene.add(backWall);

    var floorGeometry = new THREE.PlaneGeometry(20, 20);
    var floorMaterial = new THREE.MeshStandardMaterial({
        color: 0x2c1b12,
        roughness: 0.9,
        metalness: 0.0
    });
    var floor = new THREE.Mesh(floorGeometry, floorMaterial);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0;
    floor.receiveShadow = true;
    scene.add(floor);

    var shelfYPositions = [1.9, 2.7, 3.5];
    var shelfGeometry = new THREE.BoxGeometry(10, 0.12, 0.45);
    var shelfMaterial = new THREE.MeshStandardMaterial({
        color: 0x4b2f1b,
        roughness: 0.8,
        metalness: 0.0
    });

    for (var i = 0; i < shelfYPositions.length; i++) {
        var shelf = new THREE.Mesh(shelfGeometry, shelfMaterial);
        shelf.position.set(0, shelfYPositions[i], -1.9);
        shelf.castShadow = true;
        shelf.receiveShadow = true;
        scene.add(shelf);
    }

    var bookColors = [0x6b4a35, 0x7f5a3f, 0x9b7a5b, 0xc9b49b];

    function createBooksOnShelf(shelfY) {
        var numBooks = 8 + Math.floor(Math.random() * 3);
        var startX = -4.5;
        var currentX = startX;

        for (var i = 0; i < numBooks; i++) {
            var bookWidth = 0.18 + Math.random() * 0.17;
            var bookHeight = 0.35 + Math.random() * 0.40;
            var bookDepth = 0.28;

            var bookGeometry = new THREE.BoxGeometry(bookWidth, bookHeight, bookDepth);
            var colorIndex = Math.floor(Math.random() * bookColors.length);
            var bookMaterial = new THREE.MeshStandardMaterial({
                color: bookColors[colorIndex],
                roughness: 0.85,
                metalness: 0.0
            });

            var book = new THREE.Mesh(bookGeometry, bookMaterial);
            book.position.set(
                currentX + bookWidth / 2,
                shelfY + 0.06 + bookHeight / 2,
                -1.9 + 0.05
            );
            book.castShadow = true;
            book.receiveShadow = true;
            scene.add(book);

            currentX += bookWidth + 0.02 + Math.random() * 0.08;

            if (currentX > 4.5) break;
        }
    }

    for (var j = 0; j < shelfYPositions.length; j++) {
        createBooksOnShelf(shelfYPositions[j]);
    }

    var leftWallGeometry = new THREE.PlaneGeometry(6, 6);
    var leftWallMaterial = new THREE.MeshStandardMaterial({
        color: 0x1a0f08,
        roughness: 1.0,
        metalness: 0.0
    });
    var leftWall = new THREE.Mesh(leftWallGeometry, leftWallMaterial);
    leftWall.position.set(-5.5, 3, 0);
    leftWall.rotation.y = Math.PI / 2;
    leftWall.receiveShadow = true;
    scene.add(leftWall);

    var rightWall = new THREE.Mesh(leftWallGeometry, leftWallMaterial);
    rightWall.position.set(5.5, 3, 0);
    rightWall.rotation.y = -Math.PI / 2;
    rightWall.receiveShadow = true;
    scene.add(rightWall);

    function createSideShelvesWithBooks(xPos, rotationY) {
        var sideShelfGeometry = new THREE.BoxGeometry(4, 0.1, 0.4);
        var sideShelfMaterial = new THREE.MeshStandardMaterial({
            color: 0x3d2517,
            roughness: 0.85,
            metalness: 0.0
        });

        var sideShelfYPositions = [1.5, 2.2, 2.9, 3.6, 4.3];

        for (var i = 0; i < sideShelfYPositions.length; i++) {
            var sideShelf = new THREE.Mesh(sideShelfGeometry, sideShelfMaterial);
            if (xPos < 0) {
                sideShelf.position.set(xPos + 0.2, sideShelfYPositions[i], -0.5);
            } else {
                sideShelf.position.set(xPos - 0.2, sideShelfYPositions[i], -0.5);
            }
            sideShelf.rotation.y = rotationY;
            sideShelf.castShadow = true;
            sideShelf.receiveShadow = true;
            scene.add(sideShelf);

            var numSideBooks = 5 + Math.floor(Math.random() * 4);
            for (var b = 0; b < numSideBooks; b++) {
                var sBookWidth = 0.15 + Math.random() * 0.12;
                var sBookHeight = 0.3 + Math.random() * 0.35;
                var sBookDepth = 0.25;

                var sBookGeometry = new THREE.BoxGeometry(sBookWidth, sBookHeight, sBookDepth);
                var sColorIndex = Math.floor(Math.random() * bookColors.length);
                var sBookMaterial = new THREE.MeshStandardMaterial({
                    color: bookColors[sColorIndex],
                    roughness: 0.85,
                    metalness: 0.0
                });

                var sBook = new THREE.Mesh(sBookGeometry, sBookMaterial);
                var bookXOffset = -1.5 + b * 0.35 + Math.random() * 0.1;
                if (xPos < 0) {
                    sBook.position.set(
                        xPos + 0.2 + bookXOffset,
                        sideShelfYPositions[i] + 0.05 + sBookHeight / 2,
                        -0.5
                    );
                } else {
                    sBook.position.set(
                        xPos - 0.2 + bookXOffset,
                        sideShelfYPositions[i] + 0.05 + sBookHeight / 2,
                        -0.5
                    );
                }
                sBook.rotation.y = rotationY;
                sBook.castShadow = true;
                sBook.receiveShadow = true;
                scene.add(sBook);
            }
        }
    }

    createSideShelvesWithBooks(-4.8, 0.3);
    createSideShelvesWithBooks(4.8, -0.3);

    var ceilingGeometry = new THREE.PlaneGeometry(12, 10);
    var ceilingMaterial = new THREE.MeshStandardMaterial({
        color: 0x0a0604,
        roughness: 1.0,
        metalness: 0.0
    });
    var ceiling = new THREE.Mesh(ceilingGeometry, ceilingMaterial);
    ceiling.rotation.x = Math.PI / 2;
    ceiling.position.set(0, 6, 0);
    scene.add(ceiling);

    function render() {
        renderer.render(scene, camera);
    }

    render();

    window.addEventListener('resize', function() {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        render();
    });
})();
