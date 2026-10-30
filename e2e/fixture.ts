/**
 * Paint one synthetic waveform for the screenshot test.
 *
 * The renderer is the same one the player mounts. Nothing is fetched.
 */

import { mountWaveformFixture } from "../src/waveform-view";

const host = document.getElementById("waveform-root");
if (host) mountWaveformFixture(host);
