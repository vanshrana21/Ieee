(function() {
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0604);
    scene.fog = new THREE.Fog(0x0a0604, 8, 22);

    var camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(0, 2.8, 8.5);
    camera.lookAt(0, 2.0, 0);

    var renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.9;
    document.getElementById('canvas-container').appendChild(renderer.domElement);

    var ambientLight = new THREE.AmbientLight(0x3b2416, 0.12);
    scene.add(ambientLight);

    var spotLight = new THREE.SpotLight(0xffd7a1, 2.5);
    spotLight.position.set(0, 7, 2);
    spotLight.target.position.set(0, 1.0, 0);
    spotLight.angle = 0.35;
    spotLight.penumbra = 0.8;
    spotLight.decay = 1.5;
    spotLight.castShadow = true;
    spotLight.shadow.mapSize.width = 2048;
    spotLight.shadow.mapSize.height = 2048;
    spotLight.shadow.camera.near = 0.5;
    spotLight.shadow.camera.far = 20;
    spotLight.shadow.bias = -0.0001;
    scene.add(spotLight);
    scene.add(spotLight.target);

    var fillLight = new THREE.PointLight(0xffa060, 0.3);
    fillLight.position.set(0, 4, 0);
    scene.add(fillLight);

    var floorGeometry = new THREE.PlaneGeometry(30, 30);
    var floorMaterial = new THREE.MeshStandardMaterial({
        color: 0x2a1a0f,
        roughness: 0.95,
        metalness: 0.0
    });
    var floor = new THREE.Mesh(floorGeometry, floorMaterial);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.5;
    floor.receiveShadow = true;
    scene.add(floor);

    var deskGeometry = new THREE.BoxGeometry(7, 0.25, 4);
    var deskMaterial = new THREE.MeshStandardMaterial({
        color: 0xb8875a,
        roughness: 0.6,
        metalness: 0.05
    });
    var desk = new THREE.Mesh(deskGeometry, deskMaterial);
    desk.position.set(0, 0.5, 1.5);
    desk.castShadow = true;
    desk.receiveShadow = true;
    scene.add(desk);

    var deskBaseGeometry = new THREE.BoxGeometry(6.5, 1.0, 3.5);
    var deskBaseMaterial = new THREE.MeshStandardMaterial({
        color: 0x6b4a2a,
        roughness: 0.75,
        metalness: 0.0
    });
    var deskBase = new THREE.Mesh(deskBaseGeometry, deskBaseMaterial);
    deskBase.position.set(0, -0.1, 1.5);
    deskBase.castShadow = true;
    deskBase.receiveShadow = true;
    scene.add(deskBase);

    var backWallGeometry = new THREE.PlaneGeometry(16, 10);
    var backWallMaterial = new THREE.MeshStandardMaterial({
        color: 0x1a0f08,
        roughness: 1.0,
        metalness: 0.0
    });
    var backWall = new THREE.Mesh(backWallGeometry, backWallMaterial);
    backWall.position.set(0, 4, -4);
    backWall.receiveShadow = true;
    scene.add(backWall);

    var ceilingGeometry = new THREE.PlaneGeometry(16, 16);
    var ceilingMaterial = new THREE.MeshStandardMaterial({
        color: 0x0a0604,
        roughness: 1.0,
        metalness: 0.0
    });
    var ceiling = new THREE.Mesh(ceilingGeometry, ceilingMaterial);
    ceiling.rotation.x = Math.PI / 2;
    ceiling.position.set(0, 8, 0);
    scene.add(ceiling);

    var bookColors = [
        0x8b6b4a, 0x7a5a3a, 0x6b4a2a, 0x5a3a1a,
        0x9b7b5a, 0x4a2a1a, 0x8a6a4a, 0x7b5b3b,
        0x6a4a2a, 0x5b3b2b, 0x9a7a5a, 0x8b6b4b
    ];

    function createBookshelfSection(xPos, zPos, width, rotationY) {
        var shelfGroup = new THREE.Group();
        
        var backPanelGeometry = new THREE.BoxGeometry(width, 6.5, 0.15);
        var woodMaterial = new THREE.MeshStandardMaterial({
            color: 0x3d2517,
            roughness: 0.85,
            metalness: 0.0
        });
        var backPanel = new THREE.Mesh(backPanelGeometry, woodMaterial);
        backPanel.position.set(0, 3.5, -0.4);
        backPanel.castShadow = true;
        backPanel.receiveShadow = true;
        shelfGroup.add(backPanel);

        var sidePanelGeometry = new THREE.BoxGeometry(0.12, 6.5, 0.9);
        var leftSide = new THREE.Mesh(sidePanelGeometry, woodMaterial);
        leftSide.position.set(-width/2 + 0.06, 3.5, 0);
        leftSide.castShadow = true;
        leftSide.receiveShadow = true;
        shelfGroup.add(leftSide);

        var rightSide = new THREE.Mesh(sidePanelGeometry, woodMaterial);
        rightSide.position.set(width/2 - 0.06, 3.5, 0);
        rightSide.castShadow = true;
        rightSide.receiveShadow = true;
        shelfGroup.add(rightSide);

        var shelfHeights = [0.8, 1.8, 2.8, 3.8, 4.8, 5.8];
        
        for (var s = 0; s < shelfHeights.length; s++) {
            var shelfGeometry = new THREE.BoxGeometry(width - 0.1, 0.08, 0.75);
            var shelf = new THREE.Mesh(shelfGeometry, woodMaterial);
            shelf.position.set(0, shelfHeights[s], 0);
            shelf.castShadow = true;
            shelf.receiveShadow = true;
            shelfGroup.add(shelf);

            var shelfWidth = width - 0.3;
            var currentX = -shelfWidth / 2;
            var bookCount = 0;
            var maxBooks = 25;

            while (currentX < shelfWidth / 2 && bookCount < maxBooks) {
                var bookWidth = 0.08 + Math.random() * 0.12;
                var bookHeight = 0.5 + Math.random() * 0.35;
                var bookDepth = 0.45 + Math.random() * 0.15;

                if (currentX + bookWidth > shelfWidth / 2) break;

                var bookGeometry = new THREE.BoxGeometry(bookWidth, bookHeight, bookDepth);
                var colorIdx = Math.floor(Math.random() * bookColors.length);
                var bookMaterial = new THREE.MeshStandardMaterial({
                    color: bookColors[colorIdx],
                    roughness: 0.8 + Math.random() * 0.15,
                    metalness: 0.0
                });

                var book = new THREE.Mesh(bookGeometry, bookMaterial);
                book.position.set(
                    currentX + bookWidth / 2,
                    shelfHeights[s] + 0.04 + bookHeight / 2,
                    0.05
                );
                
                if (Math.random() > 0.9) {
                    book.rotation.z = (Math.random() - 0.5) * 0.1;
                }
                
                book.castShadow = true;
                book.receiveShadow = true;
                shelfGroup.add(book);

                currentX += bookWidth + 0.01;
                bookCount++;
            }
        }

        shelfGroup.position.set(xPos, 0, zPos);
        shelfGroup.rotation.y = rotationY;
        scene.add(shelfGroup);
    }

    createBookshelfSection(-5.5, -2.5, 3.5, 0.25);
    createBookshelfSection(-2.5, -3.2, 3.5, 0);
    createBookshelfSection(0.5, -3.2, 3.5, 0);
    createBookshelfSection(3.5, -3.2, 3.5, 0);
    createBookshelfSection(6.5, -2.5, 3.5, -0.25);

    createBookshelfSection(-7, -1, 2.5, 0.5);
    createBookshelfSection(8, -1, 2.5, -0.5);

    var BOOK_WIDTH = 0.9;
    var BOOK_HEIGHT = 0.5625;
    var BOOK_THICKNESS = 0.10125;

    var coverMaterial = new THREE.MeshStandardMaterial({
        color: 0x2a1a10,
        roughness: 0.55,
        metalness: 0.05
    });

    var spineMaterial = new THREE.MeshStandardMaterial({
        color: 0x1a0f08,
        roughness: 0.6,
        metalness: 0.05
    });

    var pagesMaterial = new THREE.MeshStandardMaterial({
        color: 0xf2eadf,
        roughness: 0.9,
        metalness: 0.0
    });

    var bookGroup = new THREE.Group();

    var backCoverGeometry = new THREE.BoxGeometry(BOOK_WIDTH, 0.015, BOOK_HEIGHT);
    var backCover = new THREE.Mesh(backCoverGeometry, coverMaterial);
    backCover.position.set(0, 0, 0);
    backCover.castShadow = true;
    backCover.receiveShadow = true;
    bookGroup.add(backCover);

    var spineGeometry = new THREE.BoxGeometry(0.025, BOOK_THICKNESS, BOOK_HEIGHT);
    var spine = new THREE.Mesh(spineGeometry, spineMaterial);
    spine.position.set(-BOOK_WIDTH / 2 + 0.0125, BOOK_THICKNESS / 2, 0);
    spine.castShadow = true;
    spine.receiveShadow = true;
    bookGroup.add(spine);

    var pagesGeometry = new THREE.BoxGeometry(BOOK_WIDTH - 0.07, BOOK_THICKNESS - 0.03, BOOK_HEIGHT - 0.04);
    var pagesBlock = new THREE.Mesh(pagesGeometry, pagesMaterial);
    pagesBlock.position.set(0.02, BOOK_THICKNESS / 2, 0);
    pagesBlock.castShadow = true;
    pagesBlock.receiveShadow = true;
    bookGroup.add(pagesBlock);

    var frontCoverPivot = new THREE.Group();
    frontCoverPivot.position.set(-BOOK_WIDTH / 2, BOOK_THICKNESS, 0);
    bookGroup.add(frontCoverPivot);

    var frontCoverGeometry = new THREE.BoxGeometry(BOOK_WIDTH, 0.015, BOOK_HEIGHT);
    var frontCover = new THREE.Mesh(frontCoverGeometry, coverMaterial);
    frontCover.position.set(BOOK_WIDTH / 2, 0, 0);
    frontCover.castShadow = true;
    frontCover.receiveShadow = true;
    frontCoverPivot.add(frontCover);

    var leftPagesPivot = new THREE.Group();
    leftPagesPivot.position.set(-BOOK_WIDTH / 2 + 0.025, BOOK_THICKNESS, 0);
    bookGroup.add(leftPagesPivot);

    var leftPagesGeometry = new THREE.BoxGeometry(BOOK_WIDTH * 0.42, 0.03, BOOK_HEIGHT - 0.05);
    var leftPages = new THREE.Mesh(leftPagesGeometry, pagesMaterial);
    leftPages.position.set(BOOK_WIDTH * 0.21, 0.015, 0);
    leftPages.castShadow = true;
    leftPages.receiveShadow = true;
    leftPagesPivot.add(leftPages);

    var rightPagesPivot = new THREE.Group();
    rightPagesPivot.position.set(-BOOK_WIDTH / 2 + 0.025, BOOK_THICKNESS, 0);
    bookGroup.add(rightPagesPivot);

    var rightPagesGeometry = new THREE.BoxGeometry(BOOK_WIDTH * 0.42, 0.03, BOOK_HEIGHT - 0.05);
    var rightPages = new THREE.Mesh(rightPagesGeometry, pagesMaterial);
    rightPages.position.set(BOOK_WIDTH * 0.21, 0.015, 0);
    rightPages.castShadow = true;
    rightPages.receiveShadow = true;
    rightPagesPivot.add(rightPages);

    var goldTrimMaterial = new THREE.MeshStandardMaterial({
        color: 0xc9a86c,
        roughness: 0.3,
        metalness: 0.6
    });

    var trimGeometry1 = new THREE.BoxGeometry(BOOK_WIDTH - 0.1, 0.004, 0.025);
    var goldTrimTop = new THREE.Mesh(trimGeometry1, goldTrimMaterial);
    goldTrimTop.position.set(0, 0.008, BOOK_HEIGHT / 2 - 0.05);
    frontCover.add(goldTrimTop);

    var goldTrimBottom = new THREE.Mesh(trimGeometry1, goldTrimMaterial);
    goldTrimBottom.position.set(0, 0.008, -BOOK_HEIGHT / 2 + 0.05);
    frontCover.add(goldTrimBottom);

    var centerEmblemGeometry = new THREE.BoxGeometry(0.06, 0.004, 0.04);
    var centerEmblem = new THREE.Mesh(centerEmblemGeometry, goldTrimMaterial);
    centerEmblem.position.set(0, 0.008, 0);
    frontCover.add(centerEmblem);

    var bookStartY = 0.625 + BOOK_THICKNESS / 2 + 0.01;
    bookGroup.position.set(0, bookStartY, 1.5);
    scene.add(bookGroup);

    var dustParticles = [];
    var dustGeometry = new THREE.SphereGeometry(0.006, 4, 4);
    var dustMaterial = new THREE.MeshBasicMaterial({
        color: 0xffd7a1,
        transparent: true,
        opacity: 0.25
    });

    for (var d = 0; d < 80; d++) {
        var dust = new THREE.Mesh(dustGeometry, dustMaterial);
        dust.position.set(
            (Math.random() - 0.5) * 10,
            1 + Math.random() * 5,
            (Math.random() - 0.5) * 8
        );
        dust.userData = {
            baseY: dust.position.y,
            speed: 0.0002 + Math.random() * 0.0004,
            offset: Math.random() * Math.PI * 2,
            driftX: (Math.random() - 0.5) * 0.0003
        };
        scene.add(dust);
        dustParticles.push(dust);
    }

    var scrollTarget = 0;
    var scrollCurrent = 0;
    var lerpFactor = 0.08;
    var baseIntensity = 2.5;
    var time = 0;

    function smoothstep(edge0, edge1, x) {
        var t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
        return t * t * (3 - 2 * t);
    }

    function cubicEaseOut(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function cubicEaseInOut(t) {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    function updateBookAnimation(t) {
        var levitateProgress = smoothstep(0.2, 0.4, t);
        var levitateHeight = cubicEaseOut(levitateProgress) * 0.7;
        var yPos = bookStartY + levitateHeight;

        var tiltProgress = smoothstep(0.4, 0.55, t);
        var yRotation = cubicEaseInOut(tiltProgress) * (8 * Math.PI / 180);

        var coverOpenProgress = smoothstep(0.55, 0.7, t);
        var coverAngle = cubicEaseOut(coverOpenProgress) * (-Math.PI * 0.85);

        var pageSpreadProgress = smoothstep(0.7, 0.9, t);
        var pageSpread = cubicEaseInOut(pageSpreadProgress);
        var leftPageAngle = -Math.PI * 0.42 * pageSpread;
        var rightPageAngle = -Math.PI * 0.02 * pageSpread;

        var settleProgress = smoothstep(0.9, 1.0, t);
        var settleFactor = 1 - (1 - settleProgress) * 0.02;

        bookGroup.position.y = yPos * settleFactor;
        bookGroup.rotation.y = yRotation;

        frontCoverPivot.rotation.z = coverAngle;

        leftPagesPivot.rotation.z = coverOpenProgress > 0.3 ? leftPageAngle : 0;
        rightPagesPivot.rotation.z = coverOpenProgress > 0.3 ? rightPageAngle : 0;

        pagesBlock.visible = coverOpenProgress < 0.5;

        var glowIncrease = smoothstep(0.9, 1.0, t) * 0.4;
        spotLight.intensity = baseIntensity + glowIncrease;
    }

    function onScroll() {
        var scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
        if (scrollHeight > 0) {
            scrollTarget = window.scrollY / scrollHeight;
        }
        scrollTarget = Math.max(0, Math.min(1, scrollTarget));
    }

    window.addEventListener('scroll', onScroll, { passive: true });

    function animate() {
        requestAnimationFrame(animate);

        time += 0.016;

        scrollCurrent += (scrollTarget - scrollCurrent) * lerpFactor;

        updateBookAnimation(scrollCurrent);

        for (var i = 0; i < dustParticles.length; i++) {
            var dust = dustParticles[i];
            dust.position.y = dust.userData.baseY + Math.sin(time * dust.userData.speed * 100 + dust.userData.offset) * 0.2;
            dust.position.x += dust.userData.driftX;
            if (dust.position.x > 5) dust.position.x = -5;
            if (dust.position.x < -5) dust.position.x = 5;
        }

        renderer.render(scene, camera);
    }

    animate();

    window.addEventListener('resize', function() {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
})();
