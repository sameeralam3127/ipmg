// Runs before first paint: apply the saved theme and forward old demo links.
(function () {
  var root = document.documentElement;
  root.classList.add("js");

  try {
    var theme = localStorage.getItem("ipmg-theme");
    if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
  } catch (e) {
    /* storage blocked: follow the system theme */
  }

  // The dashboard demo used to live at the site root with hash routes such as
  // #/history. Keep those shared links working now that it lives at demo/.
  if (/^#\/.+/.test(location.hash)) location.replace("demo/" + location.hash);
})();
