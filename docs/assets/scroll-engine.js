/* ============================================================================
   scroll-engine.js: scroll-driven storytelling without an animation library.
   MIT. No dependencies, no network request. About 200 lines.

   What it does
   - Holds a stage in place while the story plays: CSS position: sticky inside a
     section that the engine makes as tall as the story needs.
   - Maps the scroll position to story time t (0 .. total) and lets t glide
     after the scroll a little, which smooths wheel steps.
   - Evaluates a list of transitions [at, dur, {key: target}, ease] at time t
     into a plain state object. A pure function of t: scrolling back and forth
     always lands on the same picture.
   - Captions: words rise out of a mask (own splitter that keeps <em>, <a>,
     <span> intact and sets aria-label), eyebrow and body fade in and out.
   - Step dots, and a render loop that only runs while the section is on screen.

   What it does not do
   - It draws nothing itself. onFrame(state, t, info) is where a scene (three.js,
     canvas, DOM) reads the state and paints.
   - Reduced motion and a missing WebGL are the caller's decision; check them
     before create() and render a static version instead.

   Usage
     var story = ScrollEngine.create({
       section: el, stage: el,          // stage is position:sticky inside section
       screens: 8.5,                    // scroll length in viewport heights
       total: 11.8,                     // story time at the end of the scroll
       offset: function(){ return 64 }, // sticky top (a fixed header), optional
       initial: { spread: 0 },
       tweens: [[.3, 1.1, { spread: 1 }, "inOut3"], ...],
       captions: { els: [...], times: [[-1, .3], [1.3, 2.5], ...] },   // show, hide
       steps: { els: [...], at: [0, 1.3, ...] },
       onFrame: function (S, t, info) { ... }   // info: { now, dt, vel, progress }
     });
   CSS the caller provides:
     .stage{position:sticky;top:var(--story-top,0);height:calc(100svh - var(--story-top,0px))}
     .sw-mask{display:inline-block;overflow:clip;vertical-align:top;padding-bottom:.22em;margin-bottom:-.22em}
     .sw{display:inline-block;will-change:transform}
   ============================================================================ */
(function (global) {
  "use strict";

  var clamp = function (a, b, v) { return v < a ? a : v > b ? b : v; };
  var lerp = function (a, b, k) { return a + (b - a) * k; };
  var EASE = {
    none: function (k) { return k; },
    out2: function (k) { return 1 - (1 - k) * (1 - k); },
    out3: function (k) { return 1 - Math.pow(1 - k, 3); },
    in2: function (k) { return k * k; },
    in3: function (k) { return k * k * k; },
    inOut2: function (k) { return k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; },
    inOut3: function (k) { return k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; }
  };

  /* Split a heading into word masks. Walks text nodes only, so inline elements
     (<em>, <a>, <span class="accent">) stay where they are with their words inside. */
  function splitWords(h) {
    if (h.__sw) return h.__sw;
    h.setAttribute("aria-label", h.textContent.replace(/\s+/g, " ").trim());
    var words = [];
    (function walk(node) {
      [].slice.call(node.childNodes).forEach(function (n) {
        if (n.nodeType === 1) { walk(n); return; }
        if (n.nodeType !== 3) return;
        var frag = document.createDocumentFragment();
        n.nodeValue.split(/([ \t\r\n]+)/).forEach(function (p) {     // &nbsp; stays inside a word on purpose
          if (!p) return;
          if (/^[ \t\r\n]+$/.test(p)) { frag.appendChild(document.createTextNode(" ")); return; }
          var m = document.createElement("span"); m.className = "sw-mask"; m.setAttribute("aria-hidden", "true");
          var w = document.createElement("span"); w.className = "sw"; w.textContent = p;
          m.appendChild(w); frag.appendChild(m); words.push(w);
        });
        node.replaceChild(frag, n);
      });
    })(h);
    h.__sw = words;
    return words;
  }

  function create(o) {
    var section = o.section, stage = o.stage, total = o.total || 1;
    var offset = o.offset || function () { return 0; };
    var glide = o.glide == null ? 5.5 : o.glide;              // higher follows the scroll tighter
    var initial = o.initial || {};
    var tweens = (o.tweens || []).map(function (e) { return { at: e[0], dur: Math.max(e[1], 1e-4), to: e[2], ease: EASE[e[3] || "none"] || EASE.none }; })
      .sort(function (a, b) { return a.at - b.at; });

    function stateAt(t) {
      var S = {}, k, i, e;
      for (k in initial) S[k] = initial[k];
      for (i = 0; i < tweens.length; i++) {
        e = tweens[i]; if (t <= e.at) continue;
        var q = e.ease(clamp(0, 1, (t - e.at) / e.dur));
        for (k in e.to) S[k] = lerp(S[k] == null ? 0 : S[k], e.to[k], q);
      }
      return S;
    }

    /* captions */
    var caps = ((o.captions && o.captions.els) || []).map(function (c, i) {
      var lists = [].slice.call(c.querySelectorAll("h1,h2,h3")).map(splitWords);
      return { el: c, eyebrow: c.querySelector(".eyebrow"), lists: lists, rest: [].slice.call(c.querySelectorAll(".cap-rest")),
        show: o.captions.times[i][0], hide: o.captions.times[i][1], vis: null };
    });
    function capsAt(t) {
      caps.forEach(function (c, i) {
        var s = c.show, h = c.hide, first = s < 0;
        var vis = t >= s - .001 && t < h + .6;
        if (vis !== c.vis) { c.el.style.visibility = vis ? "visible" : "hidden"; c.vis = vis; }
        if (!vis) return;
        var kin = first ? 1 : EASE.out3(clamp(0, 1, (t - s) / .35)), kout = EASE.in2(clamp(0, 1, (t - h) / .3));
        if (c.eyebrow) { c.eyebrow.style.opacity = (kin * (1 - kout)).toFixed(3); c.eyebrow.style.transform = "translateY(" + ((1 - kin) * 14 - kout * 14).toFixed(1) + "px)"; }
        c.lists.forEach(function (list) {
          list.forEach(function (w, j) {
            var wi = first ? 1 : EASE.out3(clamp(0, 1, (t - (s + .05 + j * .03)) / .6));
            var wo = EASE.in2(clamp(0, 1, (t - (h + j * .012)) / .4));
            w.style.transform = "translateY(" + (118 * (1 - wi) - 118 * wo).toFixed(1) + "%)";
          });
        });
        var rin = first ? 1 : EASE.out3(clamp(0, 1, (t - (s + .35)) / .5));
        c.rest.forEach(function (r) { r.style.opacity = (rin * (1 - kout)).toFixed(3); r.style.transform = "translateY(" + ((1 - rin) * 18 - kout * 14).toFixed(1) + "px)"; });
      });
    }

    var stepEls = (o.steps && o.steps.els) || [], stepAt = (o.steps && o.steps.at) || [], stepOn = -1;
    function stepsAt(t) {
      var s = 0; stepAt.forEach(function (m, i) { if (t >= m) s = i; });
      if (s !== stepOn) { stepEls.forEach(function (b, i) { b.classList.toggle("on", i === s); }); stepOn = s; }
    }

    /* geometry: the section is as tall as the scroll the story needs */
    var top = 0;
    function measure() {
      top = offset();
      stage.style.setProperty("--story-top", top + "px");
      section.style.height = (stage.offsetHeight + innerHeight * (o.screens || 4)) + "px";
    }
    function targetT() {
      var r = section.getBoundingClientRect();
      return clamp(0, 1, (top - r.top) / Math.max(1, r.height - stage.offsetHeight)) * total;
    }

    measure();
    var t = targetT(), tPrev = t, last = performance.now(), running = false, visible = true, dead = false;
    capsAt(t); stepsAt(t);

    function frame(now) {
      if (!visible || dead) { running = false; return; }
      var dt = Math.min(.05, (now - last) / 1000); last = now;
      var target = targetT();
      t += (target - t) * (1 - Math.exp(-dt * glide));
      if (Math.abs(target - t) < .0005) t = target;
      var vel = (t - tPrev) / Math.max(dt, .001); tPrev = t;
      capsAt(t); stepsAt(t);
      if (o.onFrame) o.onFrame(stateAt(t), t, { now: now / 1000, dt: dt, vel: vel, progress: t / total });
      requestAnimationFrame(frame);
    }
    function kick() { if (!running && !dead) { running = true; last = performance.now(); requestAnimationFrame(frame); } }

    var io = new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) kick(); }, { rootMargin: "120px" });
    io.observe(section);
    var onResize = function () { measure(); };
    addEventListener("resize", onResize);
    kick();

    return {
      stateAt: stateAt,
      get t() { return t; },
      refresh: measure,
      destroy: function () { dead = true; io.disconnect(); removeEventListener("resize", onResize); section.style.height = ""; }
    };
  }

  global.ScrollEngine = { create: create, splitWords: splitWords, ease: EASE, clamp: clamp, lerp: lerp };
})(window);
