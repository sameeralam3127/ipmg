/* IPMG landing — theme, nav, tabs, copy, terminal typing, reveal. No deps. */
(function () {
  "use strict";

  var root = document.documentElement;

  /* ---------------------------------------------------------- theme */
  var THEME_KEY = "ipmg-theme";
  try {
    var saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (e) { /* storage blocked */ }

  function currentTheme() {
    var attr = root.getAttribute("data-theme");
    if (attr) return attr;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest("[data-theme-toggle]");
    if (!t) return;
    var next = currentTheme() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  });

  /* ---------------------------------------------------------- sticky header shadow */
  var header = document.querySelector("header.site");
  function onScroll() {
    if (header) header.classList.toggle("scrolled", window.scrollY > 8);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------------------------------------------------------- mobile nav */
  var menuBtn = document.querySelector("[data-menu]");
  var navLinks = document.getElementById("nav-links");
  if (menuBtn && navLinks) {
    menuBtn.addEventListener("click", function () {
      navLinks.classList.toggle("open");
    });
    navLinks.addEventListener("click", function (ev) {
      if (ev.target.tagName === "A") navLinks.classList.remove("open");
    });
  }

  /* ---------------------------------------------------------- code tabs */
  document.querySelectorAll("[data-tabs]").forEach(function (group) {
    var tabs = group.querySelectorAll(".tab");
    var panes = group.querySelectorAll("pre[data-pane]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.setAttribute("aria-selected", "false"); });
        tab.setAttribute("aria-selected", "true");
        var name = tab.getAttribute("data-tab");
        panes.forEach(function (p) { p.hidden = p.getAttribute("data-pane") !== name; });
      });
    });
  });

  /* ---------------------------------------------------------- copy buttons */
  var copyIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
  var checkIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  function wireCopy(btn, getText) {
    btn.addEventListener("click", function () {
      var text = getText();
      var done = function () {
        var original = btn.dataset.label ? checkIcon + "<span>Copied</span>" : checkIcon;
        btn.classList.add("copied");
        btn.innerHTML = original;
        setTimeout(function () {
          btn.classList.remove("copied");
          btn.innerHTML = btn.dataset.label ? copyIcon + "<span>Copy</span>" : copyIcon;
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, done);
      } else {
        var ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (e) {}
        document.body.removeChild(ta); done();
      }
    });
  }

  document.querySelectorAll("[data-copy-target]").forEach(function (btn) {
    wireCopy(btn, function () {
      var sel = btn.getAttribute("data-copy-target");
      var pane = document.querySelector(sel);
      // For tab groups, copy the visible pane.
      if (btn.dataset.copyGroup) {
        var group = btn.closest("[data-tabs]");
        var visible = group && group.querySelector("pre[data-pane]:not([hidden])");
        if (visible) pane = visible;
      }
      return pane ? pane.innerText.trim() : "";
    });
  });

  document.querySelectorAll("[data-copy-text]").forEach(function (btn) {
    wireCopy(btn, function () { return btn.getAttribute("data-copy-text"); });
  });

  /* ---------------------------------------------------------- reveal on scroll */
  var reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.12 });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------------------------------------------------------- terminal typing */
  var term = document.getElementById("term-body");
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (term) {
    var lines = [
      { html: '<span class="prompt">$</span> ipmg <span class="flag">--discover</span> <span class="flag">--resolve</span>', pause: 380 },
      { html: '<span class="muted">  ICMP probes only — scan only networks you are authorized to scan.</span>', pause: 240 },
      { html: '&nbsp;', pause: 120 },
      { html: '  Source   <span class="ok">auto-discovery</span>', pause: 90 },
      { html: '  Targets  254 hosts', pause: 90 },
      { html: '  Config   50 threads · 2s timeout · reverse DNS', pause: 260 },
      { html: '&nbsp;', pause: 100 },
      { html: '  Results', pause: 120 },
      { html: '  <span class="ok">● Active</span>   198  <span class="bar-a">━━━━━━━━━━━━━━━</span><span class="bar-e">─────</span>  78.0%', pause: 90 },
      { html: '  <span class="warn">● Timeout</span>  56  <span class="bar-a">━━━━</span><span class="bar-e">────────────────</span>  22.0%', pause: 260 },
      { html: '&nbsp;', pause: 100 },
      { html: '  254 hosts · 78.0% active · 6.4 ms avg · 3.1s', pause: 160 },
      { html: '  Saved    <span class="ok">results_20260813_004512.xlsx</span>', pause: 100 }
    ];
    var i = 0;
    var cursorLine = document.createElement("div");
    cursorLine.className = "row";
    cursorLine.innerHTML = '<span class="cursor"></span>';
    term.appendChild(cursorLine);

    function typeNext() {
      if (i >= lines.length) { return; }
      var line = lines[i++];
      var div = document.createElement("div");
      div.className = "row";
      div.innerHTML = line.html;
      term.insertBefore(div, cursorLine);
      term.scrollTop = term.scrollHeight;
      setTimeout(typeNext, line.pause);
    }
    if (reduceMotion) {
      // Render everything at once, no animation.
      lines.forEach(function (line) {
        var div = document.createElement("div");
        div.className = "row";
        div.innerHTML = line.html;
        term.insertBefore(div, cursorLine);
      });
      cursorLine.remove();
    } else if ("IntersectionObserver" in window) {
      var started = false;
      var tio = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting && !started) { started = true; setTimeout(typeNext, 300); }
        });
      }, { threshold: 0.3 });
      tio.observe(term);
    } else {
      setTimeout(typeNext, 300);
    }
  }

  /* ---------------------------------------------------------- year */
  var yr = document.getElementById("year");
  if (yr) yr.textContent = String(new Date().getFullYear());
})();
