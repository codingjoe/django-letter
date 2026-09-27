const KEY = "django-letter:preview-theme";
const COUNTER_ID = "django-letter-frame-invert";
/** The frame is inverted as a whole; media undo that for themselves. */
const INVERT_CSS = "img, video, svg { filter: invert(1) hue-rotate(180deg) }";
const PREFERENCE = /prefers-color-scheme/i;
/** "invert" shows the light variant, then filters it. */
const EMAIL_SCHEME = { light: "light", invert: "light", author: "dark" };

const originals = new WeakMap();

/** @returns {string|null} The stored theme, or null when storage is refused. */
function storedTheme() {
  try {
    const stored = localStorage.getItem(KEY);
    return ["light", "invert", "author"].includes(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Resolve the theme from storage, then the system preference. */
const stored = storedTheme();
if (stored) {
  document.documentElement.dataset.theme = stored;
} else if (matchMedia("(prefers-color-scheme: dark)").matches) {
  document.documentElement.dataset.theme = "invert";
}

/**
 * A media list is a disjunction, a query a conjunction: the forced scheme drops the
 * condition it satisfies and a query it contradicts, and holds if a branch holds.
 *
 * @param {string} text - A `MediaList.mediaText` snapshot.
 * @param {string} scheme - The scheme to force, `light` or `dark`.
 * @returns {string} The rewritten text, for `mediaText`.
 */
function forceScheme(text, scheme) {
  const satisfied = new RegExp(`:\\s*${scheme}\\b`, "i");
  const kept = [];
  for (const query of text.split(",")) {
    const terms = query
      .split(/\s+and\s+/i)
      .map((part) => part.trim())
      .filter((term) => term !== "all");
    const schemes = terms.filter((term) => PREFERENCE.test(term));
    if (schemes.some((term) => !satisfied.test(term))) continue;
    const rest = terms.filter((term) => !PREFERENCE.test(term));
    if (!rest.length) return "all";
    kept.push(rest.join(" and "));
  }
  return kept.join(", ") || "not all";
}

/**
 * Rewrite one framed message, starting from the conditions it shipped.
 *
 * @param {Document} doc - The message document.
 * @param {string} scheme - The scheme to force.
 */
function applyScheme(doc, scheme) {
  doc.documentElement.style.colorScheme = scheme;
  for (const sheet of doc.styleSheets) {
    let rules;
    try {
      rules = [...sheet.cssRules];
    } catch {
      continue; // Unreadable stylesheet.
    }
    for (const media of [sheet.media, ...rules.map((rule) => rule.media)]) {
      if (!media) continue;
      // Forced text no longer names the scheme, so the shipped one decides.
      if (!originals.has(media)) {
        if (!PREFERENCE.test(media.mediaText)) continue;
        originals.set(media, media.mediaText);
      }
      media.mediaText = forceScheme(originals.get(media), scheme);
    }
  }
}

function applyToFrame({ contentDocument: doc }, theme) {
  applyScheme(doc, EMAIL_SCHEME[theme]);
  const counter = doc.getElementById(COUNTER_ID);
  if (theme !== "invert") {
    counter?.remove();
  } else if (!counter) {
    const style = doc.createElement("style");
    style.id = COUNTER_ID;
    style.textContent = INVERT_CSS;
    doc.head.append(style);
  }
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  for (const radio of document.querySelectorAll('input[name="theme"]')) {
    radio.checked = radio.value === theme;
  }
  for (const frame of document.querySelectorAll("main iframe")) {
    applyToFrame(frame, theme);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  for (const radio of document.querySelectorAll('input[name="theme"]')) {
    radio.addEventListener("change", () => {
      try {
        localStorage.setItem(KEY, radio.value);
      } catch {}
      applyTheme(radio.value);
    });
  }
  for (const frame of document.querySelectorAll("main iframe")) {
    frame.addEventListener("load", () => {
      applyToFrame(frame, document.documentElement.dataset.theme);
    });
  }
  applyTheme(document.documentElement.dataset.theme);
});
