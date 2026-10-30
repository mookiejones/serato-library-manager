/**
 * Copy for the player bar and the row play control.
 *
 * Kept in one object so it can move into the i18n catalog (#132) without
 * a search through the player. The player does not build these sentences.
 */

export const playerStrings = {
  region: "Player",
  play: "Play",
  pause: "Pause",
  seek: "Seek",
  volume: "Volume",
  elapsed: "Elapsed",
  duration: "Duration",
  nothingPlaying: "Nothing playing",
  untitled: "Untitled",
  cannotPlay: "This file cannot be played in this window.",
} as const;
