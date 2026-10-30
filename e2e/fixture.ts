/**
 * Paint one synthetic waveform for the screenshot test.
 *
 * The renderer is the same one the player mounts. Nothing is fetched.
 */

import { mountWaveformFixture, type WaveformController } from "../src/waveform-view";

declare global {
  interface Window {
    waveformFixture: WaveformController;
  }
}

const host = document.getElementById("waveform-root");
if (host) window.waveformFixture = mountWaveformFixture(host);
