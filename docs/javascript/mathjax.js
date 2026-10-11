window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true,
  },
  options: {
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex",
  },
};

document$.subscribe(() => {
  if (typeof MathJax.typesetPromise !== "function") return;
  if (MathJax.startup && MathJax.startup.output) MathJax.startup.output.clearCache();
  if (typeof MathJax.typesetClear === "function") MathJax.typesetClear();
  if (typeof MathJax.texReset === "function") MathJax.texReset();
  MathJax.typesetPromise();
});
