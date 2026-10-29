/**
 * Put the real page markup into the jsdom document.
 *
 * The tests call the same element ids the screen uses. The script tag is
 * left out so jsdom does not fetch /app.js.
 */

import html from "../static/index.html?raw";

export function installPage(): void {
  const start = html.indexOf("<body");
  const end = html.lastIndexOf("</body>");
  const body = html.slice(start, end).replace(/<script[\s\S]*?<\/script>/g, "");
  document.body.outerHTML = `${body}</body>`;
  const dialog = HTMLDialogElement.prototype;
  if (typeof dialog.showModal !== "function") {
    dialog.showModal = function showModal(this: HTMLDialogElement) {
      this.open = true;
    };
  }
  if (typeof dialog.close !== "function") {
    dialog.close = function close(this: HTMLDialogElement) {
      this.open = false;
    };
  }
}
