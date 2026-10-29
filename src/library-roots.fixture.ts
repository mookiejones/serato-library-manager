/**
 * A stub GET /api/library-roots payload for the Files page tests.
 *
 * The two Music folders use different labels. OLDDRIVE is missing.
 */

import type { LibraryRootsPayload } from "./api-types";

export const libraryRootsFixture: LibraryRootsPayload = {
  computed_at: "2026-10-29T13:00:00Z",
  roots: [
    {
      id: "home-music",
      path: "/Users/dj/Music",
      label: "Home · /Music",
      detail: "/Users/dj/Music",
      kind: "music_library",
      serato: true,
      removable: false,
      missing: false,
    },
    {
      id: "gig-music",
      path: "/Volumes/GIGDRIVE/Music",
      label: "GIGDRIVE · /Music",
      detail: "/Volumes/GIGDRIVE/Music",
      kind: "music_library",
      serato: true,
      removable: true,
      missing: false,
    },
    {
      id: "old-music",
      path: "/Volumes/OLDDRIVE/Music",
      label: "OLDDRIVE · /Music",
      detail: "/Volumes/OLDDRIVE/Music",
      kind: "music_library",
      serato: true,
      removable: true,
      missing: true,
    },
  ],
};
