/**
 * Late bindings for calls between the screen modules.
 *
 * views.ts fills selectTrack and selectEntry. dialogs.ts fills
 * openMergeDialog. A click runs after those modules have loaded, so the
 * real function is in place. The empty defaults keep a render from
 * throwing when a test paints a row and does not open a dialog.
 */

export const bridge: {
  selectTrack: (id: number) => void | Promise<void>;
  selectEntry: (id: number) => void;
  openMergeDialog: () => Promise<void>;
} = {
  selectTrack(_id: number) {},
  selectEntry(_id: number) {},
  openMergeDialog() {
    return Promise.resolve();
  },
};
