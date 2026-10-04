/* ============================================================================
   diagram-steps.js: a figure that builds itself step by step as it scrolls in.

   Markup:
     <figure class="steps-fig" data-steps>
       <svg> ... <g data-step="1">...</g> <path data-step="2" data-draw .../> ... </svg>
       <ol class="steps-legend"><li data-step="1">...</li> ...</ol>   (optional)
     </figure>
   - Every element with data-step="k" (k = 1..N) fades in as the figure scrolls
     from entering the viewport to sitting around its middle.
   - A path or line with data-draw is drawn along its length instead of faded;
     its marker-end (arrowhead) appears only when the line has arrived.
   - Legend items with the same data-step get .on while their step is the
     newest one shown, .done after.
   - Reduced motion: everything shows at once, nothing moves.
   Scroll-driven, no timer: scrolling back takes the steps back.
   ============================================================================ */
(function () {
  "use strict";
  var figs = [].slice.call(document.querySelectorAll("[data-steps]"));
  if (!figs.length) return;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var clamp = function (a, b, v) { return v < a ? a : v > b ? b : v; };

  var all = figs.map(function (fig) {
    var els = [].slice.call(fig.querySelectorAll("[data-step]"));
    var n = els.reduce(function (m, e) { return Math.max(m, +e.getAttribute("data-step") || 0); }, 0);
    var items = els.map(function (e) {
      var o = { el: e, k: +e.getAttribute("data-step"), legend: e.tagName === "LI", draw: e.hasAttribute("data-draw"), len: 0,
        marker: e.getAttribute("marker-end"), markerOn: true };
      if (o.draw && e.getTotalLength) { o.len = e.getTotalLength(); e.style.strokeDasharray = o.len + " " + o.len; }
      return o;
    });
    // a figure that starts inside the first screen (a hero figure) builds completely on load
    var hero = fig.getBoundingClientRect().top + scrollY < innerHeight * .75;
    return { fig: fig, n: Math.max(1, n), items: items, cur: reduce ? 1 : 0, hero: hero };
  });

  function paint(f, p) {
    var shown = p * f.n;                                  // how many steps are in, fractional
    f.items.forEach(function (o) {
      var k = clamp(0, 1, shown - (o.k - 1));
      if (o.legend) { o.el.classList.toggle("on", k > 0 && k < 1 || (k >= 1 && Math.ceil(shown) === o.k)); o.el.classList.toggle("done", k >= 1 && Math.ceil(shown) !== o.k); return; }
      if (o.draw) {
        o.el.style.strokeDashoffset = (o.len * (1 - k)).toFixed(1); o.el.style.opacity = k > 0 ? 1 : 0;
        var on = k > .97;                               // the arrowhead only once the line has arrived
        if (o.marker && on !== o.markerOn) { if (on) o.el.setAttribute("marker-end", o.marker); else o.el.removeAttribute("marker-end"); o.markerOn = on; }
      }
      else { o.el.style.opacity = k.toFixed(3); o.el.style.transform = "translateY(" + ((1 - k) * 8).toFixed(1) + "px)"; }
    });
  }
  function target(fig, hero) {
    if (hero) return 1;
    var r = fig.getBoundingClientRect(), vh = innerHeight;
    return clamp(0, 1, (vh * .9 - r.top) / (vh * .9 - vh * .45 + r.height * .5));
  }
  if (reduce) { all.forEach(function (f) { paint(f, 1); }); return; }
  // A figure already on screen at load builds itself once from zero, then follows the scroll.
  all.forEach(function (f) { f.cur = 0; paint(f, 0); });
  var running = false;
  function tick() {
    var moving = false;
    all.forEach(function (f) {
      var t = target(f.fig, f.hero), d = t - f.cur;
      if (Math.abs(d) > .0005) { f.cur += d * .09; moving = true; paint(f, f.cur); }
    });
    if (moving) requestAnimationFrame(tick); else running = false;
  }
  function kick() { if (!running) { running = true; requestAnimationFrame(tick); } }
  addEventListener("scroll", kick, { passive: true });
  addEventListener("resize", kick);
  kick();
})();
