/* ============================================================================
   page-motion.js: the shared motion layer of the site's inner pages.

   Opt-in by attribute, so no page logic is touched by accident:
     data-reveal           the element rises and fades in when it scrolls into view
     data-reveal="stagger" its direct children do that one after another
     data-count="1234"     a number counts up once when it comes into view
                           (optional data-count-locale="de-DE")
   Automatic:
     .page-hero h1         words rise out of a mask on load (aria-label keeps
                           the sentence whole for screen readers)
     a thin reading-progress line under the header (CSS scroll timeline where
     the browser has it, otherwise a scroll listener)
   Reduced motion: nothing moves, everything is visible.
   Without JavaScript nothing is hidden: the hiding CSS only applies under
   html.pm, which this script sets.
   ============================================================================ */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;
  root.classList.add("pm");

  /* reading progress */
  var bar = document.createElement("div"); bar.className = "pm-progress"; bar.setAttribute("aria-hidden", "true");
  document.body.appendChild(bar);
  if (!(window.CSS && CSS.supports && CSS.supports("animation-timeline: scroll()"))) {
    var setBar = function () { var h = document.documentElement.scrollHeight - innerHeight; bar.style.transform = "scaleX(" + (h > 0 ? scrollY / h : 0).toFixed(4) + ")"; };
    addEventListener("scroll", setBar, { passive: true }); addEventListener("resize", setBar); setBar();
  }

  /* hero headline: words rise out of a mask */
  [].slice.call(document.querySelectorAll(".page-hero h1")).forEach(function (h) {
    if (h.__pm) return; h.__pm = true;
    /* Screen readers get the sentence whole, in the active language only:
       one hidden plain copy per language variant, the split words are aria-hidden. */
    var variants = h.hasAttribute("data-lang") ? [] : [].slice.call(h.querySelectorAll("[data-lang]"));
    if (!variants.length) h.setAttribute("aria-label", h.textContent.replace(/\s+/g, " ").trim());
    variants.forEach(function (v) {
      var sr = document.createElement("span"); sr.className = "pm-sr"; sr.setAttribute("data-lang", v.getAttribute("data-lang"));
      sr.textContent = v.textContent.replace(/\s+/g, " ").trim();
      v.parentNode.insertBefore(sr, v); v.setAttribute("aria-hidden", "true");
    });
    var i = 0;
    (function walk(node) {
      [].slice.call(node.childNodes).forEach(function (n) {
        if (n.nodeType === 1) { if (!n.classList.contains("pm-sr")) walk(n); return; }
        if (n.nodeType !== 3) return;
        var frag = document.createDocumentFragment();
        n.nodeValue.split(/([ \t\r\n]+)/).forEach(function (p) {
          if (!p) return;
          if (/^[ \t\r\n]+$/.test(p)) { frag.appendChild(document.createTextNode(" ")); return; }
          var m = document.createElement("span"); m.className = "pm-mask"; m.setAttribute("aria-hidden", "true");
          var w = document.createElement("span"); w.className = "pm-word"; w.textContent = p;
          w.style.animationDelay = (60 + (i++ % 14) * 45) + "ms";
          m.appendChild(w); frag.appendChild(m);
        });
        node.replaceChild(frag, n);
      });
    })(h);
  });

  /* reveal on scroll, once */
  var targets = [];
  [].slice.call(document.querySelectorAll("[data-reveal]")).forEach(function (el) {
    if (el.getAttribute("data-reveal") === "stagger") {
      [].slice.call(el.children).forEach(function (c, i) { c.classList.add("pm-r"); c.style.transitionDelay = Math.min(i, 8) * 70 + "ms"; targets.push(c); });
    } else { el.classList.add("pm-r"); targets.push(el); }
  });
  var counters = [].slice.call(document.querySelectorAll("[data-count]"));
  function count(el) {
    var to = +el.getAttribute("data-count"), loc = el.getAttribute("data-count-locale") || undefined, t0 = performance.now(), dur = 1400;
    (function step(now) {
      var k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(to * e).toLocaleString(loc);
      if (k < 1) requestAnimationFrame(step);
    })(t0);
  }
  if (!("IntersectionObserver" in window)) { targets.forEach(function (t) { t.classList.add("pm-in"); }); return; }
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      if (e.target.hasAttribute("data-count")) count(e.target); else e.target.classList.add("pm-in");
      io.unobserve(e.target);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: .08 });
  targets.forEach(function (t) { io.observe(t); });
  counters.forEach(function (c) { io.observe(c); });
})();
