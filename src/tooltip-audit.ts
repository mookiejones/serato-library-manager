/**
 * Checks that every control has a tooltip.
 *
 * Only tests read this file. `untippedControls` checks markup, and
 * `controlsMissingTip` checks the source of a module, because many
 * controls exist only after a view has painted.
 */

import { hasKey } from "./i18n";

/** What counts as a control. The hidden picker opens from the Import button. */
const CONTROLS = [
  "button",
  "input:not([type='file'][hidden])",
  "select",
  "textarea",
  "a[href]",
  "summary",
  "[role='separator'][tabindex]",
  "[role='slider']",
  "[role='option']",
].join(", ");

/**
 * List the controls under a root that have no tooltip.
 *
 * @param root Document or element to read.
 * @returns The controls with no data-tip.
 */
export function untippedControls(root: ParentNode): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(CONTROLS)].filter((node) => !node.dataset.tip);
}

/**
 * List the data-tip keys under a root that have no text.
 *
 * @param root Document or element to read.
 * @returns The keys with no text in the catalog.
 */
export function unknownTips(root: ParentNode): string[] {
  return [...root.querySelectorAll<HTMLElement>("[data-tip]")]
    .map((node) => node.dataset.tip as string)
    .filter((key) => !hasKey(`tip.${key}`));
}

/**
 * Name the controls a module creates without calling tip().
 *
 * A name can be declared again in a later function, so each declaration
 * is read up to the next declaration of that name. A plain assignment and
 * a role set on a div count too, because the player builds its bar that way.
 *
 * @param source Text of a TypeScript module.
 * @returns The variable names of the controls with no tip() call.
 */
export function controlsMissingTip(source: string): string[] {
  const created = /^\s*(?:const |let )?([\w.]+)\s*=[^;]*?document\.createElement\("(?:button|input|select|textarea)"\)[^;]*;/gm;
  const roles = /^\s*([\w.]+)\.setAttribute\("role", "(?:slider|option)"\);/gm;
  const missing: string[] = [];
  for (const match of [...source.matchAll(created), ...source.matchAll(roles)]) {
    const name = match[1] as string;
    const escaped = name.replaceAll(".", "\\.");
    const declared = source.lastIndexOf(`const ${name}`, match.index);
    const rest = source.slice(declared === -1 ? match.index : declared);
    const end = match.index + match[0].length - (source.length - rest.length);
    const next = rest.slice(end).search(new RegExp(`\\bconst ${escaped}\\b`));
    const scope = next === -1 ? rest : rest.slice(0, end + next);
    if (!new RegExp(`\\btip\\(\\s*${escaped}\\s*,`).test(scope)) missing.push(name);
  }
  return missing;
}
