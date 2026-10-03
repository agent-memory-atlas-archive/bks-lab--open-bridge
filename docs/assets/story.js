/* ============================================================================
   story.js: the command-bridge stage at the top of the landing page.

   One pinned stage, six scenes, driven by scroll (GSAP ScrollTrigger, scrub):
     0  the finished bridge: agents left, the rest of your world around it
     1  cold start: the links drop, loose files drift
     2  the substrate: the files gather into the bridge (identity, workflow, infra, work)
     3  the links come back one by one, data flows
     4  session start: pulses run to the agents (read), then back (write), the log grows
     5  many bridges on one shared CORE, upstream only for scope:core

   three.js is loaded only when the stage actually runs. Colours come from the
   --stage-* tokens in brand.css, so light and dark both work and a palette
   change needs no edit here. Reduced motion or no WebGL: the captions stand
   stacked and a static list of the stations replaces the scene.
   Self-contained: everything is served from assets/, no network request.
   ============================================================================ */
(function () {
  "use strict";
  var root = document.documentElement;
  var stage = document.getElementById("story-stage");
  if (!stage || !window.gsap || !window.ScrollTrigger) return;

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var glOK = (function () { try { var c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; } })();
  if (reduce || !glOK) { root.classList.add("story-static"); return; }

  gsap.registerPlugin(ScrollTrigger, SplitText);
  ScrollTrigger.config({ ignoreMobileResize: true });

  /* header offset: the sticky top bar sits over the page, the stage starts below it */
  var topbar = document.querySelector(".topbar");
  var hdr = function () { return topbar ? Math.round(topbar.getBoundingClientRect().height) : 0; };
  var setHdr = function () { stage.style.setProperty("--hdr", hdr() + "px"); };
  setHdr();

  var caps = gsap.utils.toArray("#story .cap");
  var capParts = caps.map(function (c) {
    var words = [];
    c.querySelectorAll("h1,h2").forEach(function (h) {
      words = words.concat(SplitText.create(h, { type: "words", mask: "words", wordsClass: "sw", aria: "auto" }).words);
    });
    return { eyebrow: c.querySelector(".eyebrow"), words: words, rest: c.querySelectorAll(".cap-rest") };
  });

  var EN = function (en, de) { return '<span data-lang="en">' + en + '</span><span data-lang="de">' + de + "</span>"; };
  var STATIONS = [
    { t: "Claude Code", s: EN("reads at session start", "liest beim Start"), a: 162, agent: true },
    { t: "Codex", s: EN("reads AGENTS.md", "liest AGENTS.md"), a: 182, agent: true },
    { t: "Copilot CLI", s: EN("reads AGENTS.md", "liest AGENTS.md"), a: 202, agent: true },
    { t: EN("Calendar", "Kalender"), s: EN("scheduled sends", "geplanter Versand"), a: 124 },
    { t: EN("Channels", "Kanäle"), s: "Mail · Telegram · iMessage", a: 90 },
    { t: "Wiki", s: EN("docs · minutes", "Doku · Protokolle"), a: 54 },
    { t: "Repos", s: "ecosystem.yaml", a: 18 },
    { t: "Boards", s: "GitHub Projects · ADO", a: 342 },
    { t: "Secret stores", s: EN("by URI only", "nur per URI"), a: 306 },
    { t: EN("Machines", "Maschinen"), s: "infra/remotes", a: 270 },
    { t: "Backups", s: "infra/backups", a: 236 }
  ];
  var CHAOS = ["chat-export-final.txt", "notes (3).md", "prompt that worked.txt", "todo-maybe.md", "client stuff.docx", "chat-export-final-v2.txt", "untitled.md"];
  var LAYERS = ["identity/", "workflow/", "infra/", "work/"];
  var LOG = [["09:14", "Decision", "bigcorp", "scoped the inbound pipeline"], ["11:02", "Fix", "startupxyz", "retry on 429, backoff added"], ["14:22", "Decision", "bigcorp", "Pinned the schema to v2"]];

  var S = { p: 0, tilt: .55, cam: 1, hub: 1, draw: 1, flow: .35, stOther: 1, chaos: 0, gather: 0, sub: 0, rwAmp: 0, rw: 0, log: 0, fleet: 0 };
  var vel = 0;

  import("./vendor/three.module.min.js").then(function (THREE) { build(THREE); }).catch(function (e) {
    console.error(e); root.classList.add("story-static");
  });

  function build(THREE) {
    THREE.ColorManagement.enabled = false;                 // tokens land 1:1
    var canvas = document.getElementById("story-gl");
    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, powerPreference: "high-performance" });
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    var mobile = innerWidth < 900;
    renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.5 : 2));
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(32, 1, .1, 200);
    var TAN = Math.tan(THREE.MathUtils.degToRad(16));
    var rig = new THREE.Group(); scene.add(rig);
    var deck = new THREE.Group(); rig.add(deck);

    /* colours from CSS tokens, re-read on theme change */
    var col = {};
    var tok = function (n, f) { var v = getComputedStyle(root).getPropertyValue(n).trim(); return new THREE.Color(v || f); };
    var mats = { link: [], linkAgent: [], line: [], strong: [], core: [], sweep: [] };
    function readColors() {
      col.surface = tok("--stage-surface", "#101419"); col.line = tok("--stage-line", "#345373");
      col.link = tok("--stage-link", "#5690D2"); col.hi = tok("--stage-hi", "#5FA0D9");
      col.core = tok("--stage-core", "#182A40"); col.dust = tok("--stage-dust", "#333E4C");
      renderer.setClearColor(col.surface, 1);
      mats.link.forEach(function (m) { m.uniforms.uCol.value.copy(col.line); m.uniforms.uHi.value.copy(col.hi); });
      mats.linkAgent.forEach(function (m) { m.uniforms.uCol.value.copy(col.link); m.uniforms.uHi.value.copy(col.hi); });
      mats.line.forEach(function (m) { m.color.copy(col.line); });
      mats.strong.forEach(function (m) { m.color.copy(col.link); });
      mats.core.forEach(function (m) { m.color.copy(col.core); });
      mats.sweep.forEach(function (m) { m.color.copy(col.line); });
      if (pulses) pulses.material.uniforms.uCol.value.copy(col.hi);
      if (dust) dust.material.color.copy(col.dust);
    }
    var pulses = null, dust = null;
    readColors();

    var RX = mobile ? 3.6 : 5.6, RY = mobile ? 4.2 : 3.3;
    var rad = function (a) { return a * Math.PI / 180; };
    var posOf = function (a) { return new THREE.Vector3(Math.cos(rad(a)) * RX, Math.sin(rad(a)) * RY, 0); };

    function lineMat(agent) {
      var m = new THREE.ShaderMaterial({
        transparent: true, depthWrite: false,
        uniforms: { uDraw: { value: 1 }, uFlow: { value: 0 }, uDir: { value: 1 }, uTime: { value: 0 }, uA: { value: 1 },
          uCol: { value: (agent ? col.link : col.line).clone() }, uHi: { value: col.hi.clone() } },
        vertexShader: "attribute float aT; varying float vT; void main(){ vT=aT; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }",
        fragmentShader: "uniform float uDraw,uFlow,uDir,uTime,uA; uniform vec3 uCol,uHi; varying float vT;" +
          "void main(){ if(vT>uDraw) discard; float f=fract(vT*2.2-uTime*.45*uDir); float p=smoothstep(.78,1.,f)*uFlow;" +
          "gl_FragColor=vec4(mix(uCol,uHi,p),(.6+.4*p)*uA); }"
      });
      (agent ? mats.linkAgent : mats.link).push(m);
      return m;
    }
    function makeLink(p0, p2, bend, agent) {
      var mid = p0.clone().add(p2).multiplyScalar(.5);
      var perp = new THREE.Vector3(-(p2.y - p0.y), p2.x - p0.x, 0).normalize().multiplyScalar(bend);
      var curve = new THREE.QuadraticBezierCurve3(p0, mid.add(perp), p2);
      var pts = curve.getPoints(80);
      var g = new THREE.BufferGeometry().setFromPoints(pts);
      g.setAttribute("aT", new THREE.Float32BufferAttribute(pts.map(function (_, i) { return i / 80; }), 1));
      return { line: new THREE.Line(g, lineMat(agent)), curve: curve, draw: 0, flow: 0, dir: 1, a: 1 };
    }

    var stations = STATIONS.map(function (st, i) {
      var p = posOf(st.a);
      var link = makeLink(new THREE.Vector3(Math.cos(rad(st.a)) * 1.45, Math.sin(rad(st.a)) * 1.45, 0), p.clone().multiplyScalar(.9), i % 2 ? .35 : -.35, st.agent);
      deck.add(link.line);
      return { t: st.t, s: st.s, agent: st.agent, p: p, link: link };
    });

    function circle(r, strong) {
      var pts = []; for (var i = 0; i <= 128; i++) { var a = i / 128 * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0)); }
      var m = new THREE.LineBasicMaterial({ color: strong ? col.link : col.line, transparent: true });
      (strong ? mats.strong : mats.line).push(m);
      return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), m);
    }
    function makeHub() {
      var g = new THREE.Group();
      var rings = [circle(.55, true), circle(.95, false), circle(1.4, false)];
      rings.forEach(function (r) { g.add(r); });
      var tk = []; for (var i = 0; i < 72; i++) { var a = i / 72 * Math.PI * 2, l = i % 6 ? 1.52 : 1.62;
        tk.push(new THREE.Vector3(Math.cos(a) * 1.45, Math.sin(a) * 1.45, 0), new THREE.Vector3(Math.cos(a) * l, Math.sin(a) * l, 0)); }
      var tm = new THREE.LineBasicMaterial({ color: col.line, transparent: true }); mats.line.push(tm);
      var ticks = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(tk), tm); g.add(ticks);
      var cm = new THREE.MeshBasicMaterial({ color: col.core, transparent: true }); mats.core.push(cm);
      var core = new THREE.Mesh(new THREE.CircleGeometry(.55, 64), cm); core.position.z = -.01; g.add(core);
      var sm = new THREE.MeshBasicMaterial({ color: col.line, transparent: true, side: THREE.DoubleSide }); mats.sweep.push(sm);
      var sweep = new THREE.Mesh(new THREE.RingGeometry(.97, 1.38, 64, 1, 0, Math.PI / 7), sm); g.add(sweep);
      return { g: g, ticks: ticks, sweep: sweep, set: function (a) {
        rings.forEach(function (r, i) { r.material.opacity = a * [1, .9, .7][i]; });
        ticks.material.opacity = a * .8; core.material.opacity = a; sweep.material.opacity = a * .22; } };
    }
    var hub = makeHub(); deck.add(hub.g);
    var peers = [makeHub(), makeHub()]; peers.forEach(function (h) { deck.add(h.g); });

    function rrect(w, h, r) {
      var s = new THREE.Shape(); s.moveTo(-w / 2 + r, -h / 2); s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
      s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2); s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
      s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
      var m = new THREE.LineBasicMaterial({ color: col.link, transparent: true }); mats.strong.push(m);
      return new THREE.Line(new THREE.BufferGeometry().setFromPoints(s.getPoints(16)), m);
    }
    var FX = mobile ? 2.6 : 4.4, FY = 1.5, CY = -2.0, UX = mobile ? 3.2 : 7.6;
    var coreBox = rrect(mobile ? 6.4 : 11, 1.0, .18); coreBox.position.set(0, CY, 0); deck.add(coreBox);
    var fleetLinks = [-FX, 0, FX].map(function (x, i) {
      var l = makeLink(new THREE.Vector3(x, CY + .5, 0), new THREE.Vector3(x, FY - (i === 1 ? 1.0 : .7), 0), 0, false); deck.add(l.line); return l; });
    var upLink = makeLink(new THREE.Vector3(mobile ? 3.2 : 5.5, CY, 0), new THREE.Vector3(UX, CY - 1.4, 0), .3, true);
    if (mobile) upLink.line.visible = false;
    deck.add(upLink.line);

    var allLinks = stations.map(function (s) { return s.link; }).concat(fleetLinks, [upLink]);
    var PN = allLinks.length * 2;
    var pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(PN * 3), 3));
    pGeo.setAttribute("aA", new THREE.BufferAttribute(new Float32Array(PN), 1));
    pulses = new THREE.Points(pGeo, new THREE.ShaderMaterial({ transparent: true, depthWrite: false,
      uniforms: { uPx: { value: renderer.getPixelRatio() }, uCol: { value: col.hi.clone() } },
      vertexShader: "attribute float aA; varying float vA; uniform float uPx; void main(){ vA=aA; gl_PointSize=uPx*(5.+4.*aA); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }",
      fragmentShader: "uniform vec3 uCol; varying float vA; void main(){ float d=length(gl_PointCoord-.5); if(d>.5) discard; gl_FragColor=vec4(uCol, vA*smoothstep(.5,.15,d)); }" }));
    deck.add(pulses);

    var DN = mobile ? 60 : 120, dpos = new Float32Array(DN * 3);
    for (var i = 0; i < DN; i++) { dpos[i * 3] = (Math.random() - .5) * 26; dpos[i * 3 + 1] = (Math.random() - .5) * 16; dpos[i * 3 + 2] = -2 - Math.random() * 10; }
    var dGeo = new THREE.BufferGeometry(); dGeo.setAttribute("position", new THREE.BufferAttribute(dpos, 3));
    dust = new THREE.Points(dGeo, new THREE.PointsMaterial({ color: col.dust, size: 2, sizeAttenuation: false }));
    scene.add(dust);

    /* HTML labels pinned to 3D points (crisp text, page fonts, both languages) */
    var labelsEl = document.getElementById("story-labels");
    var L = [];
    function addLabel(html, cls, pos, anchor) {
      var el = document.createElement("div"); el.className = "lb"; el.innerHTML = '<div class="' + cls + '">' + html + "</div>";
      labelsEl.appendChild(el); var o = { el: el, pos: pos, a: 0, anchor: anchor || "c", scale: 1 }; L.push(o); return o;
    }
    stations.forEach(function (s) { s.lb = addLabel("<b></b><span>" + s.t + "<small>" + s.s + "</small></span>", "st" + (s.agent ? " agent" : ""), s.p); });
    var hubLb = addLabel("<span>open-bridge</span><small>" + EN("plain text in git", "Plain Text in Git") + "</small>", "hubl", new THREE.Vector3());
    var layerLbs = LAYERS.map(function (t) { return addLabel(t, "dir", new THREE.Vector3()); });
    var chaos = CHAOS.map(function (t, i) { var a = (i / CHAOS.length) * Math.PI * 2 + .4, r = 2.4 + (i % 3) * .7;
      return { from: new THREE.Vector3(Math.cos(a) * r * (mobile ? .75 : 1.25), Math.sin(a) * r * .8, .4), lb: addLabel(t, "fl", new THREE.Vector3()), seed: i * 1.7 }; });
    var logLb = addLabel('<div class="log"><div class="h">work/log.md · ' + EN("written back", "zurückgeschrieben") + "</div>" +
      LOG.map(function (r) { return '<div class="r">| ' + r[0] + " | <em>" + r[1] + "</em> " + r[2] + " | " + r[3] + "</div>"; }).join("") + "</div>", "", new THREE.Vector3(), mobile ? "c" : "l");
    var logRows = [].slice.call(logLb.el.querySelectorAll(".r"));
    var fleetLbs = [
      addLabel("<b></b><span>user/client-a<small>" + EN("one bridge per client", "eine Bridge pro Kunde") + "</small></span>", "st", new THREE.Vector3(-FX, FY - 1.0, 0)),
      addLabel("<b></b><span>user/you<small>" + EN("your context (USER)", "dein Kontext (USER)") + "</small></span>", "st agent", new THREE.Vector3(0, FY - 1.3, 0)),
      addLabel("<b></b><span>user/client-b<small>" + EN("separate data", "getrennte Daten") + "</small></span>", "st", new THREE.Vector3(FX, FY - 1.0, 0)),
      addLabel("<b></b><span>main (CORE)<small>skills · docs · schemas · standing orders</small></span>", "st core", new THREE.Vector3(0, CY, 0)),
      addLabel("<b></b><span>upstream<small>bks-lab/open-bridge · /bridge-promote</small></span>", "st", new THREE.Vector3(UX, CY - 1.4, 0))
    ];
    if (mobile) fleetLbs[4].el.style.display = "none";

    var baseCam = 20;
    function fit() {
      var asp = canvas.clientWidth / Math.max(1, canvas.clientHeight);
      var needW = RX + (mobile ? 1.4 : 2.2), needH = RY * Math.cos(.5) + 1.2;
      var share = mobile ? .36 : .40;                       // share of the height above the captions
      baseCam = Math.max(needW / (TAN * asp), needH / (TAN * share));
    }

    var v = 0, v3 = new THREE.Vector3();
    function layout(time) {
      var cam = baseCam * S.cam, halfH = TAN * cam;
      camera.position.z = cam;
      rig.position.y = halfH * (mobile ? .56 : .52);
      deck.rotation.x = -S.tilt * .9;

      hub.g.position.set(0, S.fleet * FY, 0); hub.g.scale.setScalar(1 - .38 * S.fleet);
      hub.set(.25 + .75 * S.hub);
      hub.ticks.rotation.z = S.p * 2.4 + time * .015; hub.sweep.rotation.z = -time * .35 - S.p * 6;
      peers.forEach(function (h, i) { h.g.position.set(i ? FX : -FX, FY * .95, 0); h.g.scale.setScalar(.48); h.set(S.fleet);
        h.ticks.rotation.z = -time * .02 * (i ? 1 : -1); h.sweep.rotation.z = -time * .35 + i * 2; h.g.visible = S.fleet > .01; });
      coreBox.material.opacity = S.fleet; coreBox.visible = S.fleet > .01;

      var N = stations.length, st = .32, fade = 1 - S.fleet;
      stations.forEach(function (s, i) {
        var on = s.agent ? 1 : S.stOther, k = s.link;
        var d = gsap.utils.clamp(0, 1, S.draw * (1 + st * (N - 1)) - i * st);
        k.draw = d * on; k.a = fade * on;
        if (s.agent && S.rwAmp > 0) { k.flow = Math.max(S.flow, S.rwAmp); k.dir = S.rw < 1 ? 1 : -1; }
        else { k.flow = S.flow * (1 - .6 * S.rwAmp); k.dir = 1; }
        s.lb.a = fade * on;
      });
      fleetLinks.forEach(function (k) { k.draw = S.fleet; k.flow = S.fleet * .8; k.dir = -1; k.a = S.fleet; });
      upLink.draw = gsap.utils.clamp(0, 1, S.fleet * 2 - 1); upLink.flow = S.fleet; upLink.dir = 1; upLink.a = S.fleet;

      var pi = 0, P = pGeo.attributes.position.array, A = pGeo.attributes.aA.array;
      allLinks.forEach(function (k, li) {
        var m = k.line.material.uniforms;
        m.uDraw.value = k.draw; m.uFlow.value = k.flow; m.uDir.value = k.dir; m.uTime.value = time; m.uA.value = k.a;
        k.line.visible = k.a > .01 && k.draw > .001 && !(mobile && k === upLink);
        for (var j = 0; j < 2; j++) {
          var t = (time * (.22 + .5 * Math.abs(v)) + j * .5 + li * .137) % 1; if (k.dir < 0) t = 1 - t;
          var pt = k.curve.getPoint(t); P[pi * 3] = pt.x; P[pi * 3 + 1] = pt.y; P[pi * 3 + 2] = pt.z;
          A[pi] = t < k.draw && k.line.visible ? k.flow * k.a * Math.sin(Math.PI * Math.min(1, t / Math.max(k.draw, .001))) : 0; pi++;
        }
      });
      pGeo.attributes.position.needsUpdate = true; pGeo.attributes.aA.needsUpdate = true;

      hubLb.pos = new THREE.Vector3(0, S.fleet * FY, 0); hubLb.a = (1 - S.fleet) * (.35 + .65 * S.hub);
      LAYERS.forEach(function (_, i) { var a = rad(45 + i * 90), r = (mobile ? 1.45 : .95) + .75 * (1 - S.sub);
        layerLbs[i].pos = new THREE.Vector3(Math.cos(a) * r * 1.25, Math.sin(a) * r, 0); layerLbs[i].a = S.sub * fade; });
      chaos.forEach(function (c) {
        var g = S.gather;
        c.lb.pos = c.from.clone().multiplyScalar(1 - g).add(new THREE.Vector3(Math.sin(time * .4 + c.seed) * .12, Math.cos(time * .3 + c.seed) * .1, 0));
        c.lb.a = S.chaos * (1 - g) * (1 - g); c.lb.scale = 1 - .6 * g;
      });
      logLb.pos = new THREE.Vector3(mobile ? 1.1 : 2.0, mobile ? -2.4 : -.55, .2);
      logLb.a = gsap.utils.clamp(0, 1, S.log * 3) * fade;
      logRows.forEach(function (r, i) { r.style.opacity = gsap.utils.clamp(0, 1, S.log - i); });
      fleetLbs.forEach(function (l) { l.a = S.fleet; });

      rig.updateMatrixWorld(true); camera.updateMatrixWorld(true);
      var w = canvas.clientWidth, h = canvas.clientHeight;
      L.forEach(function (o) {
        if (o.a < .01) { if (o.el.style.opacity !== "0") o.el.style.opacity = 0; return; }
        v3.copy(o.pos).applyMatrix4(deck.matrixWorld).project(camera);
        var x = (v3.x * .5 + .5) * w, y = (-v3.y * .5 + .5) * h;
        o.el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(" + (o.anchor === "l" ? "0%" : "-50%") + ",-50%) scale(" + o.scale.toFixed(3) + ")";
        o.el.style.opacity = o.a.toFixed(3);
      });
    }

    /* ---------- dramaturgy ---------- */
    var active = true;
    var steps = [].slice.call(document.querySelectorAll("#story .story-steps b"));
    var ease = "power3.inOut";
    var tl = gsap.timeline({ defaults: { ease: "none" }, scrollTrigger: {
      trigger: "#story-stage", pin: true, start: function () { return "top " + hdr(); },
      end: function () { return "+=" + innerHeight * 8.5; }, scrub: 1,
      onToggle: function (self) { active = self.isActive; },
      onUpdate: function (self) {
        S.p = self.progress; vel = self.getVelocity();
        var marks = [0, .12, .3, .48, .64, .82], s = 0;
        marks.forEach(function (m, i) { if (self.progress >= m) s = i; });
        steps.forEach(function (b, i) { b.classList.toggle("on", i === s); });
      } } });

    function show(i, at) { var c = capParts[i];
      tl.set(caps[i], { visibility: "visible" }, at)
        .fromTo(c.eyebrow, { autoAlpha: 0, y: 14 }, { autoAlpha: 1, y: 0, duration: .35 }, at)
        .fromTo(c.words, { yPercent: 118 }, { yPercent: 0, duration: .6, stagger: .03, ease: "power3.out" }, at + .05)
        .fromTo(c.rest, { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: .5 }, at + .35); }
    function hide(i, at) { var c = capParts[i];
      tl.to(c.words, { yPercent: -118, duration: .4, stagger: .012, ease: "power2.in" }, at)
        .to([c.eyebrow].concat([].slice.call(c.rest)), { autoAlpha: 0, y: -14, duration: .3 }, at)
        .set(caps[i], { visibility: "hidden" }, at + .6); }
    capParts.slice(1).forEach(function (c) { gsap.set([c.eyebrow].concat([].slice.call(c.rest)), { autoAlpha: 0 }); gsap.set(c.words, { yPercent: 118 }); });

    hide(0, .3);                                                             // 0 the finished bridge
    tl.to(S, { draw: 0, flow: 0, stOther: 0, hub: 0, duration: 1.1, ease: ease }, .3)  // 1 cold start
      .to(S, { chaos: 1, tilt: .3, duration: 1.0, ease: ease }, .7);
    show(1, 1.3); hide(1, 2.5);
    tl.to(S, { gather: 1, hub: 1, duration: 1.2, ease: ease }, 2.5)          // 2 substrate
      .to(S, { sub: 1, duration: .8, ease: "power3.out" }, 3.2);
    show(2, 3.4); hide(2, 4.6);
    tl.to(S, { sub: 0, duration: .5 }, 4.6)                                  // 3 the links
      .to(S, { stOther: 1, tilt: .55, duration: .8, ease: ease }, 4.7)
      .to(S, { draw: 1, duration: 1.6, ease: "power2.inOut" }, 4.8)
      .to(S, { flow: .9, duration: .8 }, 5.8);
    show(3, 5.6); hide(3, 7.0);
    tl.to(S, { rwAmp: 1, flow: .3, stOther: .12, duration: .5 }, 7.0)       // 4 read, then write back
      .to(S, { rw: 1, duration: 1.0 }, 7.2)
      .set(S, { rw: 1.01 }, 8.2)
      .to(S, { log: 3, duration: 1.4 }, 8.2);
    show(4, 7.4); hide(4, 9.8);
    tl.to(S, { rwAmp: 0, stOther: 1, duration: .4 }, 9.8)                   // 5 many bridges
      .to(S, { fleet: 1, cam: 1.08, tilt: .2, duration: 1.5, ease: ease }, 9.9);
    show(5, 10.9);
    tl.to({}, { duration: .9 });

    function resize() { setHdr(); var w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); fit(); }
    addEventListener("resize", resize); resize();
    new MutationObserver(readColors).observe(root, { attributes: true, attributeFilter: ["class"] });

    var qx = gsap.quickTo(rig.rotation, "y", { duration: 1.4, ease: "power3.out" });
    var qy = gsap.quickTo(rig.rotation, "x", { duration: 1.4, ease: "power3.out" });
    if (!mobile) stage.addEventListener("pointermove", function (e) { qx((e.clientX / innerWidth - .5) * .08); qy((e.clientY / innerHeight - .5) * .05); });

    gsap.ticker.add(function () {
      if (!active && S.p > 0) return;
      var now = performance.now() / 1000;
      v += (gsap.utils.clamp(-1, 1, vel / 4000) - v) * .08;
      layout(now); renderer.render(scene, camera);
    });
    layout(performance.now() / 1000); renderer.render(scene, camera);
    root.classList.add("story-ready");
    ScrollTrigger.refresh();
  }
})();
