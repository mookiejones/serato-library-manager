/**
 * Fuzzy name scoring for quick-open and the file search.
 *
 * A query matches when every word is a subsequence of the name, or of
 * the parent folder name. Consecutive letters, a whole word, and a
 * prefix score higher. The same rules are in files.py so the page and
 * the server rank names the same way. Matching is case-insensitive.
 */

const BOUNDARY = /[ ._/\-\\]/;

/**
 * Score one word against one string.
 *
 * @param needle Word to find, in order. An empty word does not match.
 * @param haystack Name or folder to search.
 * @returns A higher score for a tighter match, or null when needle is not a subsequence.
 */
export function fuzzyScore(needle: string, haystack: string): number | null {
  const query = needle.toLocaleLowerCase();
  const text = haystack.toLocaleLowerCase();
  if (!query) return null;
  let score = 0;
  let previous = -2;
  let from = 0;
  for (const letter of query) {
    const found = text.indexOf(letter, from);
    if (found < 0) return null;
    score += 8;
    if (found === previous + 1) score += 16;
    if (found === 0 || BOUNDARY.test(text.charAt(found - 1))) score += 12;
    previous = found;
    from = found + 1;
  }
  if (text.includes(query)) score += 40;
  if (text.startsWith(query)) score += 30;
  score -= Math.floor(Math.max(0, text.length - query.length) / 4);
  return score;
}

/**
 * Score a multi-word query against a name and an optional parent folder.
 *
 * Each word must match the name or, when it does not, the parent folder.
 * A word that matches the name scores higher than a word that matches
 * only the folder.
 *
 * @param query Text the person typed. Blank text does not match.
 * @param name File or track name.
 * @param parentName Folder that contains the file. Tracks omit this.
 * @returns The total score, or null when a word matches neither string.
 */
export function scoreQuery(query: string, name: string, parentName = ""): number | null {
  const terms = query.trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return null;
  let total = 0;
  for (const term of terms) {
    const nameScore = fuzzyScore(term, name);
    if (nameScore != null) {
      total += nameScore + 20;
      continue;
    }
    if (!parentName) return null;
    const parentScore = fuzzyScore(term, parentName);
    if (parentScore == null) return null;
    total += parentScore;
  }
  return total;
}
