/**
 * Copy for the player bar and the row play control.
 *
 * Each value is read from the active catalog when the bar is painted,
 * so a language change does not keep the English sentence.
 */

import { t } from "./i18n";

export const playerStrings = {
  get region(): string { return t("player.region"); },
  get play(): string { return t("player.play"); },
  get pause(): string { return t("player.pause"); },
  get seek(): string { return t("player.seek"); },
  get volume(): string { return t("player.volume"); },
  get elapsed(): string { return t("player.elapsed"); },
  get duration(): string { return t("player.duration"); },
  get nothingPlaying(): string { return t("player.nothingPlaying"); },
  get untitled(): string { return t("track.untitled"); },
  get previous(): string { return t("player.previous"); },
  get next(): string { return t("player.next"); },
  get cue(): string { return t("player.cue"); },
  get cannotPlay(): string { return t("player.cannotPlay"); },
  get notInLibrary(): string { return t("player.notInLibrary"); },
  get zoomIn(): string { return t("player.zoomIn"); },
  get zoomOut(): string { return t("player.zoomOut"); },
  get overview(): string { return t("player.overview"); },
  get waveformReading(): string { return t("player.waveformReading"); },
  get waveformUnavailable(): string { return t("player.waveformUnavailable"); },
};
